"""沙盒代码执行：受限环境中运行自定义 Python 分析代码。"""

from __future__ import annotations

import io
import json
import re
import sys
import calendar as calendar_module
import datetime as datetime_module
import math
import statistics
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from contextlib import redirect_stdout
import multiprocessing

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry


def _get_dataset(name: str) -> pd.DataFrame | None:
    """沙盒内获取数据集的安全接口。"""
    from data_agent.agent.execution_scope import ensure_dataset_allowed_in_current_context

    guard = ensure_dataset_allowed_in_current_context(name)
    if not guard.allowed:
        raise PermissionError(f"{guard.error_type}: {guard.message}")
    return workspace.get(name)


def _build_safe_globals(dataset_snapshot=None) -> dict:
    """构建受限的全局命名空间。"""
    safe_modules = {
        "pandas": pd,
        "numpy": np,
        "datetime": datetime_module,
        "calendar": calendar_module,
        "math": math,
        "statistics": statistics,
        "decimal": sys.modules[Decimal.__module__],
        "fractions": sys.modules[Fraction.__module__],
    }

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        module_name = str(name or "").split(".", 1)[0]
        if level or name != module_name or module_name not in safe_modules:
            available = ", ".join(sorted(safe_modules))
            raise ImportError(
                f"Sandbox import denied for '{name}'; allowed modules: {available}; "
                "use a native analysis tool for other modules"
            )
        module = safe_modules[module_name]
        for item in fromlist or ():
            if item != "*" and not hasattr(module, item):
                raise ImportError(f"cannot import name '{item}' from '{module_name}'")
        return module

    safe_builtins = {
        "__import__": safe_import,
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "filter": filter, "float": float, "int": int,
        "isinstance": isinstance, "len": len, "list": list, "map": map,
        "max": max, "min": min, "print": print, "range": range, "round": round,
        "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip, "True": True, "False": False, "None": None,
    }

    def snapshot_dataset(name):
        if name not in dataset_snapshot:
            raise PermissionError("dataset_outside_current_task_scope")
        if isinstance(dataset_snapshot[name], PermissionError):
            raise dataset_snapshot[name]
        return dataset_snapshot[name].copy(deep=True)

    return {
        "__builtins__": safe_builtins,
        "pd": pd,
        "np": np,
        "datetime": datetime_module.datetime,
        "date": datetime_module.date,
        "time": datetime_module.time,
        "timedelta": datetime_module.timedelta,
        "timezone": datetime_module.timezone,
        "calendar": calendar_module,
        "math": math,
        "statistics": statistics,
        "Decimal": Decimal,
        "Fraction": Fraction,
        "get_dataset": _get_dataset if dataset_snapshot is None else snapshot_dataset,
    }


def _run_code(code: str, timeout: int, dataset_snapshot=None) -> tuple[str, str]:
    """在受限环境中执行代码，返回 (stdout, result_repr)。"""
    stdout_buf = io.StringIO()
    result_repr = ""

    with redirect_stdout(stdout_buf):
        try:
            globs = _build_safe_globals(dataset_snapshot)

            # 尝试编译为表达式（返回最后一个值）
            try:
                compiled = compile(code, "<sandbox>", "eval")
                result = eval(compiled, globs)
                if result is not None:
                    result_repr = str(result)[:10000]
            except SyntaxError:
                # 不是纯表达式，作为语句执行
                compiled = compile(code, "<sandbox>", "exec")
                exec(compiled, globs)
                # exec 模式下，尝试读取 result 变量
                if "result" in globs and globs["result"] is not None:
                    result_repr = str(globs["result"])[:10000]

        except Exception as e:
            return stdout_buf.getvalue(), f"Error: {type(e).__name__}: {e}"

    return stdout_buf.getvalue(), result_repr


def _sandbox_worker(connection, code, timeout, datasets):
    try:
        connection.send(_run_code(code, timeout, datasets))
    finally:
        connection.close()


def _execute_isolated(code, timeout, datasets):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_sandbox_worker, args=(sender, code, timeout, datasets), daemon=True)
    try:
        process.start()
        sender.close()
        if not receiver.poll(timeout):
            raise TimeoutError(f"sandbox exceeded {timeout}s")
        return receiver.recv()
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        sender.close()
        receiver.close()


# 风险分级：基于代码内容检测
_HIGH_RISK_PATTERNS = [
    re.compile(r'\.to_csv\(|\.to_excel\(|\.to_json\(', re.IGNORECASE),
    re.compile(r'\.to_sql\(|\.to_parquet\(', re.IGNORECASE),
    re.compile(r'remove|delete|drop|unlink|rmdir|shutil', re.IGNORECASE),
    re.compile(r'\.reset_index\(.*drop.*True', re.IGNORECASE),
    re.compile(r'del\s+\w+', re.IGNORECASE),
]


def _assess_risk(code: str) -> str:
    """评估代码风险等级。返回 'low' | 'high'。"""
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(code):
            return "high"
    return "low"


@registry.register(
    name="run_python",
    description=(
        "在受限沙盒中执行自定义 Python 分析代码。"
        "可用: pd (pandas), np (numpy), get_dataset(name) 获取工作区数据集。"
        "也可直接使用 datetime/date/time/timedelta/timezone、calendar、math、statistics、Decimal、Fraction。"
        "允许显式导入 pandas、numpy、datetime、calendar、math、statistics、decimal、fractions；其他 import 以及 open、os、subprocess、exec、eval 不可用。"
        "代码执行超时 30 秒。返回 stdout 和最后一个表达式的值。"
        "多语句请将结果赋给 result 字典（转换 np 标量为 int/float）；只有 print 的混合正文不会自动成为统计证据。"
        "配对用户前后比较优先用 ab_test(unit_col='user_id',unit_aggregation='sum'或'mean')，原生提供配对t及Wilcoxon；不要在沙盒手算p值。"
        "适用于现有工具无法覆盖的自定义分析需求。"
    ),
    recovery_hint="请检查代码语法是否正确，确保只使用 pd/np/get_dataset 等安全接口。",
)
def run_python(code: str, timeout: int = 30, purpose: str = "") -> str:
    if not code.strip():
        return json.dumps({"error": "代码不能为空"}, ensure_ascii=False)

    try:
        timeout = max(1, min(int(timeout), 30))
    except (TypeError, ValueError):
        return json.dumps({"error": "timeout 必须是 1 到 30 的整数秒"}, ensure_ascii=False)

    # AST 级别安全检查（替代字符串匹配，防绕过）
    from data_agent.tools._utils import validate_python_code
    ast_err = validate_python_code(code)
    if ast_err:
        return json.dumps({
            "error": f"安全检查: {ast_err}",
            "error_type": "sandbox_violation",
            "alternatives": ["describe_dataset", "preview_data", "list_data", "transform_data"],
        }, ensure_ascii=False)
    # 风险评估
    risk = _assess_risk(code)

    try:
        # Copy only data already allowed by this task's workspace facade and
        # permission guard. The child never inherits an unrestricted workspace.
        datasets = {}
        for name in workspace.list_datasets():
            try:
                datasets[name] = _get_dataset(name)
            except PermissionError as exc:
                # Preserve the scoped denial code, without sending its frame
                # to the child or blocking an unrelated permitted read.
                datasets[name] = PermissionError(str(exc))
        stdout, result = _execute_isolated(code, timeout, datasets)
    except TimeoutError:
        return json.dumps({
            "error": f"代码执行超时（{timeout}s）",
            "error_type": "sandbox_timeout",
            "timeout_seconds": timeout,
            "local_execution_stopped": True,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"执行失败: {e}"}, ensure_ascii=False)

    if result.startswith("Error:"):
        return json.dumps({
            "error": result,
            "error_type": "sandbox_execution_error",
            "result": result,
            "local_execution_stopped": True,
            "recovery_hint": "修正代码后可重试；pd/np 与常用时间、数学模块已预置，也支持白名单 import。",
            "available_modules": [
                "pandas", "numpy", "datetime", "calendar", "math",
                "statistics", "decimal", "fractions",
            ],
        }, ensure_ascii=False)

    response = {
        "output": stdout[:20000] if stdout else "",
        "risk_level": risk,
        "execution_label": "exploratory_sandbox",
        "replay": {
            "contract_version": "sandbox_replay.v1",
            "code_sha256": sha256(code.encode("utf-8")).hexdigest(),
            "code": code,
            "timeout_seconds": timeout,
        },
        "fallback_policy": {
            "role": "supplemental",
            "purpose": purpose,
            "purpose_missing": not bool((purpose or "").strip()),
        },
    }
    if result:
        response["result"] = result

    return json.dumps(response, ensure_ascii=False, indent=2)
