from __future__ import annotations

import ast
import hashlib
import io
import multiprocessing as mp
import queue
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from data_agent.tools._utils import validate_python_code
from data_agent.v2.models import ExploratoryArtifact


_BLOCKED_IO_ATTRIBUTES = frozenset(
    {
        "load",
        "loads",
        "loadtxt",
        "genfromtxt",
        "fromfile",
        "memmap",
        "save",
        "savez",
        "savez_compressed",
        "savetxt",
        "dump",
        "dumps",
        "io",
        "ExcelFile",
        "ExcelWriter",
        "HDFStore",
        "open_memmap",
        "savefig",
        "tofile",
        "read_clipboard",
        "read_csv",
        "read_excel",
        "read_feather",
        "read_fwf",
        "read_hdf",
        "read_html",
        "read_json",
        "read_orc",
        "read_parquet",
        "read_pickle",
        "read_sas",
        "read_spss",
        "read_sql",
        "read_stata",
        "to_clipboard",
        "to_csv",
        "to_excel",
        "to_feather",
        "to_hdf",
        "to_json",
        "to_html",
        "to_latex",
        "to_markdown",
        "to_orc",
        "to_parquet",
        "to_pickle",
        "to_sql",
        "to_stata",
        "to_string",
    }
)

_SAFE_TO_ATTRIBUTES = frozenset(
    {"to_datetime", "to_dict", "to_list", "to_numpy", "to_numeric", "to_timedelta"}
)


@dataclass(frozen=True, slots=True)
class ExploratoryExecutionResult:
    status: str
    purpose: str
    code_fingerprint: str
    output: str = ""
    result: str = ""
    error_code: str = ""
    risk_level: str = "low"
    output_truncated: bool = False
    result_truncated: bool = False
    verification_level: str = "exploratory_only"
    limitations: tuple[str, ...] = (
        "自由 Python 输出未经 ResultContract 校验，不作为 verified Finding。",
        "该结果只能用于探索和诊断，不能支持高置信推断、预测或因果结论。",
    )


def _validate(code: str) -> tuple[str, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return "syntax_error", str(exc)
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
        return "import_not_allowed", "探索性 Python 不允许 import。"
    generic_error = validate_python_code(code)
    if generic_error:
        return "unsafe_code", generic_error
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attribute = node.attr
            if (
                attribute in _BLOCKED_IO_ATTRIBUTES
                or attribute.startswith("read_")
                or (attribute.startswith("to_") and attribute not in _SAFE_TO_ATTRIBUTES)
            ):
                return "io_not_allowed", f"不允许访问可能读写外部状态的方法 .{attribute}。"
    return "", ""


def _worker(frame: pd.DataFrame, code: str, output_queue) -> None:
    safe_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "print": print,
        "range": range,
        "repr": repr,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }
    namespace = {
        "__builtins__": safe_builtins,
        "data": frame.copy(deep=True),
        "pd": pd,
        "np": np,
    }
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            compiled = compile(code, "<v2-exploratory>", "exec")
            exec(compiled, namespace)
        result = namespace.get("result")
        if isinstance(result, np.generic):
            result = result.item()
        output_queue.put(
            {"status": "succeeded", "output": buffer.getvalue(), "result": repr(result) if result is not None else ""}
        )
    except BaseException as exc:
        output_queue.put(
            {
                "status": "failed",
                "output": buffer.getvalue(),
                "result": "",
                "error_code": type(exc).__name__,
            }
        )


def _bounded(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    suffix = "…[truncated]"
    return value[: max(0, limit - len(suffix))] + suffix, True


def execute_exploratory_python(
    frame: pd.DataFrame,
    *,
    code: str,
    purpose: str,
    timeout_seconds: float = 3.0,
    max_output_chars: int = 4000,
    max_result_chars: int = 2000,
) -> ExploratoryExecutionResult:
    normalized_code = str(code or "").strip()
    normalized_purpose = str(purpose or "").strip()
    if not normalized_code or not normalized_purpose:
        raise ValueError("purpose and code are required")
    fingerprint = f"sha256:{hashlib.sha256(normalized_code.encode('utf-8')).hexdigest()}"
    error_code, message = _validate(normalized_code)
    if error_code:
        return ExploratoryExecutionResult(
            status="failed" if error_code == "syntax_error" else "rejected",
            purpose=normalized_purpose,
            code_fingerprint=fingerprint,
            result=message,
            error_code=error_code,
        )

    context = mp.get_context("spawn")
    output_queue = context.Queue(maxsize=1)
    process = context.Process(target=_worker, args=(frame.copy(deep=True), normalized_code, output_queue))
    process.start()
    process.join(timeout=max(0.05, float(timeout_seconds)))
    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
        output_queue.close()
        return ExploratoryExecutionResult(
            status="timed_out",
            purpose=normalized_purpose,
            code_fingerprint=fingerprint,
            error_code="execution_timeout",
        )
    try:
        payload = output_queue.get(timeout=1)
    except queue.Empty:
        payload = {"status": "failed", "error_code": "worker_no_result"}
    finally:
        output_queue.close()
    output, output_truncated = _bounded(str(payload.get("output") or ""), max_output_chars)
    result, result_truncated = _bounded(str(payload.get("result") or ""), max_result_chars)
    return ExploratoryExecutionResult(
        status=str(payload.get("status") or "failed"),
        purpose=normalized_purpose,
        code_fingerprint=fingerprint,
        output=output,
        result=result,
        error_code=str(payload.get("error_code") or ""),
        output_truncated=output_truncated,
        result_truncated=result_truncated,
    )


def build_exploratory_artifact(
    result: ExploratoryExecutionResult,
    *,
    artifact_id: str,
    dataset_version_id: str,
) -> ExploratoryArtifact:
    payload = {
        "artifact_id": artifact_id,
        "dataset_version_ids": (dataset_version_id,),
        "purpose": result.purpose,
        "code_fingerprint": result.code_fingerprint,
        "status": result.status,
        "output": result.output,
        "result": result.result,
        "error_code": result.error_code,
        "risk_level": result.risk_level,
        "limitations": result.limitations,
        "verification_level": result.verification_level,
    }
    import json

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_fingerprint = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    return ExploratoryArtifact(**payload, content_fingerprint=content_fingerprint)
