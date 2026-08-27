"""沙盒代码执行：受限环境中运行自定义 Python 分析代码。"""

from __future__ import annotations

import io
import json
import re
import sys
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from contextlib import redirect_stdout
from contextvars import copy_context

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


def _build_safe_globals() -> dict:
    """构建受限的全局命名空间。"""
    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "filter": filter, "float": float, "int": int,
        "isinstance": isinstance, "len": len, "list": list, "map": map,
        "max": max, "min": min, "print": print, "range": range, "round": round,
        "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip, "True": True, "False": False, "None": None,
    }

    return {
        "__builtins__": safe_builtins,
        "pd": pd,
        "np": np,
        "get_dataset": _get_dataset,
    }


def _run_code(code: str, timeout: int) -> tuple[str, str]:
    """在受限环境中执行代码，返回 (stdout, result_repr)。"""
    stdout_buf = io.StringIO()
    result_repr = ""

    with redirect_stdout(stdout_buf):
        try:
            globs = _build_safe_globals()

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
        "不可用: open, os, subprocess, __import__, exec, eval。"
        "代码执行超时 30 秒。返回 stdout 和最后一个表达式的值。"
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
        return json.dumps({"error": f"安全检查: {ast_err}"}, ensure_ascii=False)

    # 风险评估
    risk = _assess_risk(code)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        context = copy_context()
        future = pool.submit(context.run, _run_code, code, timeout)
        stdout, result = future.result(timeout=timeout)
    except FuturesTimeout:
        future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        return json.dumps({
            "error": f"代码执行超时（{timeout}s）",
            "error_type": "sandbox_timeout",
            "timeout_seconds": timeout,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"执行失败: {e}"}, ensure_ascii=False)
    else:
        pool.shutdown(wait=True)

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
