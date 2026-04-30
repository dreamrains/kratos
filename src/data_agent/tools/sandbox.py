"""沙盒代码执行：受限环境中运行自定义 Python 分析代码。"""

from __future__ import annotations

import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry


def _get_dataset(name: str) -> pd.DataFrame | None:
    """沙盒内获取数据集的安全接口。"""
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


@registry.register(
    name="run_python",
    description=(
        "在受限沙盒中执行自定义 Python 分析代码。"
        "可用: pd (pandas), np (numpy), get_dataset(name) 获取工作区数据集。"
        "不可用: open, os, subprocess, __import__, exec, eval。"
        "代码执行超时 30 秒。返回 stdout 和最后一个表达式的值。"
        "适用于现有工具无法覆盖的自定义分析需求。"
    ),
)
def run_python(code: str, timeout: int = 30) -> str:
    if not code.strip():
        return json.dumps({"error": "代码不能为空"}, ensure_ascii=False)

    # 安全检查：阻止危险操作
    dangerous = ["__import__", "import os", "import sys", "import subprocess",
                 "open(", ".system(", ".popen(", ".exec(", "__builtins__"]
    for d in dangerous:
        if d in code:
            return json.dumps({"error": f"不允许的操作: {d}"}, ensure_ascii=False)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_code, code, timeout)
            stdout, result = future.result(timeout=timeout)
    except FuturesTimeout:
        return json.dumps({"error": f"代码执行超时（{timeout}s）"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"执行失败: {e}"}, ensure_ascii=False)

    response = {"output": stdout[:20000] if stdout else ""}
    if result:
        response["result"] = result

    return json.dumps(response, ensure_ascii=False, indent=2)
