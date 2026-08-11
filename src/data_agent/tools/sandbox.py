"""沙盒代码执行：受限环境中运行自定义 Python 分析代码。"""

from __future__ import annotations

import io
import json
import math as _math_module
import re
import statistics as _statistics_module
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from contextlib import redirect_stdout
from contextvars import ContextVar, copy_context
import json as _json_module

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import (
    SandboxContractError,
    normalize_preloaded_imports,
    validate_python_code,
)
from data_agent.tools.registry import registry


_DATASET_READS: ContextVar[set[str] | None] = ContextVar(
    "data_agent_sandbox_dataset_reads",
    default=None,
)

# Recovery suggestions surfaced on every sandbox failure payload. Kept short
# and tool-focused so the LLM can route to a structured alternative.
_SAFE_ALTERNATIVES: list[str] = [
    "describe_dataset",
    "preview_data",
    "list_data",
    "transform_data",
]


def _preload_map() -> dict[str, object]:
    """Resolve the modules the sandbox is allowed to expose to user code.

    Keys are dotted module names so the import normalizer can match both
    top-level roots (``pandas``) and dotted paths (``scipy.stats``).
    """

    from scipy import stats as _scipy_stats

    return {
        "pandas": pd,
        "numpy": np,
        "math": _math_module,
        "statistics": _statistics_module,
        "json": _json_module,
        "scipy.stats": _scipy_stats,
    }


def _visible_dataset_names() -> list[str]:
    """Dataset names visible to the sandbox right now.

    Active execution scopes constrain visibility to their allowed datasets;
    otherwise every dataset in the session workspace is selectable.
    """

    try:
        from data_agent.agent.execution_scope import current_context_execution_scope

        scope = current_context_execution_scope()
    except Exception:
        scope = None
    if scope is not None and scope.active:
        try:
            return sorted({str(name) for name in scope.allowed_datasets if name})
        except Exception:
            pass
    try:
        return sorted({str(name) for name in workspace.list_datasets().keys() if name})
    except Exception:
        return []


def _get_dataset(name: str) -> pd.DataFrame:
    """沙盒内获取数据集的安全接口。

    The execution-scope guard runs first (raising ``PermissionError`` for
    datasets outside the active task scope). After the scope check passes,
    a missing dataset raises a structured :class:`SandboxContractError`
    instead of returning ``None`` and cascading through user code.
    """

    from data_agent.agent.execution_scope import ensure_dataset_allowed_in_current_context

    guard = ensure_dataset_allowed_in_current_context(name)
    if not guard.allowed:
        raise PermissionError(f"{guard.error_type}: {guard.message}")

    reads = _DATASET_READS.get()
    if reads is not None:
        reads.add(str(name))

    frame = workspace.get(name)
    if frame is None:
        raise SandboxContractError(
            error_type="dataset_not_found",
            message=f"数据集 {str(name)!r} 不存在。",
            details={
                "allowed_datasets": _visible_dataset_names(),
                "failed_operation": "get_dataset",
            },
        )
    return frame


def _preloaded_runtime_importer(preloaded: dict[str, object]):
    """Resolve only already-loaded internals of preloaded libraries.

    Some NumPy/Pandas operations call ``__import__`` from the caller's
    builtins for lazy formatting helpers. User-authored imports are removed or
    rejected before execution and direct ``__import__`` calls are rejected by
    the AST validator. This importer therefore exists only for library code
    and never loads a new module or crosses a preloaded module root.
    """

    allowed_roots = {name.split(".", 1)[0] for name in preloaded}

    def _runtime_import(
        name: str,
        globals: dict | None = None,
        locals: dict | None = None,
        fromlist: tuple | list = (),
        level: int = 0,
    ):
        del globals, locals
        module_name = str(name or "")
        root = module_name.split(".", 1)[0]
        if level != 0 or root not in allowed_roots or module_name not in sys.modules:
            raise ImportError(f"sandbox runtime import not preloaded: {module_name}")
        module = sys.modules[module_name]
        if fromlist:
            return module
        return sys.modules.get(root, module)

    return _runtime_import


def _build_safe_globals(preloaded: dict[str, object] | None = None) -> dict:
    """构建受限的全局命名空间。"""

    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "filter": filter, "float": float, "int": int,
        "isinstance": isinstance, "len": len, "list": list, "map": map,
        "max": max, "min": min, "print": print, "range": range, "round": round,
        "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip, "True": True, "False": False, "None": None,
        "Exception": Exception, "ImportError": ImportError,
        "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
        "AttributeError": AttributeError, "RuntimeError": RuntimeError,
        "ZeroDivisionError": ZeroDivisionError,
    }

    if preloaded is None:
        preloaded = _preload_map()

    # The name remains unavailable to user source: validate_python_code blocks
    # direct calls and dunder access. It is present for NumPy/Pandas internals
    # that consult the caller's builtins while formatting or dispatching.
    safe_builtins["__import__"] = _preloaded_runtime_importer(preloaded)

    return {
        "__builtins__": safe_builtins,
        "pd": preloaded["pandas"],
        "np": preloaded["numpy"],
        "math": preloaded["math"],
        "statistics": preloaded["statistics"],
        "json": preloaded["json"],
        "stats": preloaded["scipy.stats"],
        "get_dataset": _get_dataset,
    }


def _run_code(
    code: str,
    timeout: int,
    preloaded: dict[str, object],
    bindings: dict[str, object],
) -> tuple[str, str]:
    """在受限环境中执行代码，返回 (stdout, result_repr)。

    :class:`SandboxContractError` is allowed to propagate so ``run_python``
    can render the structured payload directly; other exceptions are folded
    into a result-repr string to preserve the existing sandbox boundary.
    """

    stdout_buf = io.StringIO()
    result_repr = ""

    with redirect_stdout(stdout_buf):
        try:
            globs = _build_safe_globals(preloaded)
            if bindings:
                globs.update(bindings)

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

        except SandboxContractError:
            raise
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


def _sandbox_failure_payload(
    *,
    error_type: str,
    message: str,
    dataset_reads: list[str],
    failed_operation: str,
    allowed_datasets: list[str] | None = None,
) -> dict:
    """Build the canonical structured failure payload for ``run_python``."""

    payload = SandboxContractError(
        error_type=error_type,
        message=message,
        details={"failed_operation": failed_operation},
    ).to_payload(
        dataset_reads=dataset_reads,
        failed_operation=failed_operation,
        allowed_datasets=allowed_datasets if allowed_datasets is not None else _visible_dataset_names(),
        safe_alternatives=_SAFE_ALTERNATIVES,
    )
    return payload


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

    preloaded = _preload_map()

    # 1) 归一化 allowlist 导入：剥离已预加载的导入并绑定别名。
    #    未批准的导入在此处抛出 SandboxContractError，不会进入安全校验。
    try:
        normalized_code, bindings = normalize_preloaded_imports(code, preloaded)
    except SandboxContractError as exc:
        payload = exc.to_payload(
            dataset_reads=[],
            failed_operation="normalize_imports",
            allowed_datasets=_visible_dataset_names(),
            safe_alternatives=_SAFE_ALTERNATIVES,
        )
        return json.dumps(payload, ensure_ascii=False)

    # 2) AST 级安全校验：归一化后的代码已不含 allowlist 导入，
    #    仍拦截 __import__/exec/eval/open 与 dunder 属性访问。
    ast_err = validate_python_code(normalized_code)
    if ast_err:
        payload = _sandbox_failure_payload(
            error_type="sandbox_violation",
            message=f"安全检查: {ast_err}",
            dataset_reads=[],
            failed_operation="security_check",
        )
        return json.dumps(payload, ensure_ascii=False)

    # 3) 风险评估
    risk = _assess_risk(code)

    dataset_reads: set[str] = set()
    reads_token = _DATASET_READS.set(dataset_reads)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            context = copy_context()
            future = pool.submit(
                context.run, _run_code, normalized_code, timeout, preloaded, bindings
            )
            stdout, result = future.result(timeout=timeout)
    except SandboxContractError as exc:
        payload = exc.to_payload(
            dataset_reads=sorted(dataset_reads),
            failed_operation=exc.details.get("failed_operation") or "execute",
            allowed_datasets=_visible_dataset_names(),
            safe_alternatives=_SAFE_ALTERNATIVES,
        )
        return json.dumps(payload, ensure_ascii=False)
    except FuturesTimeout:
        payload = _sandbox_failure_payload(
            error_type="sandbox_timeout",
            message=f"代码执行超时（{timeout}s）",
            dataset_reads=sorted(dataset_reads),
            failed_operation="execute",
        )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        payload = _sandbox_failure_payload(
            error_type="sandbox_execution_error",
            message=f"执行失败: {type(e).__name__}: {e}",
            dataset_reads=sorted(dataset_reads),
            failed_operation="execute",
        )
        return json.dumps(payload, ensure_ascii=False)

    finally:
        _DATASET_READS.reset(reads_token)

    if result.strip().lower().startswith("error:"):
        payload = _sandbox_failure_payload(
            error_type="sandbox_execution_error",
            message=result,
            dataset_reads=sorted(dataset_reads),
            failed_operation="execute",
        )
        return json.dumps(payload, ensure_ascii=False)

    response = {
        "success": True,
        "output": stdout[:20000] if stdout else "",
        "risk_level": risk,
        "fallback_policy": {
            "role": "supplemental",
            "purpose": purpose,
            "purpose_missing": not bool((purpose or "").strip()),
        },
        "dataset_reads": sorted(dataset_reads),
    }
    if result:
        response["result"] = result

    return json.dumps(response, ensure_ascii=False, indent=2)
