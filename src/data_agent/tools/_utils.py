"""工具模块共享函数。"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace


def get_df(name: str):
    """获取数据集，返回 (df, error_msg)。error_msg 为 None 表示成功。"""
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return None, f"数据集 '{name}' 不存在。可用: {available}"
    return df, None


def safe_jsonify(obj):
    """将 numpy/pandas 类型转换为 JSON 安全的 Python 类型。"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if pd.isna(obj):
        return None
    return obj


def persist_detail(session_id: str, tool_call_id: str, data: dict) -> Path:
    """将工具详细输出持久化到磁盘，返回文件路径。

    数据不进入对话历史，LLM 需要时可通过 read_file 获取。
    """
    from data_agent.config import get_config
    cfg = get_config()
    detail_dir = cfg.sessions_resolved / session_id / "tool_outputs"
    detail_dir.mkdir(parents=True, exist_ok=True)
    path = detail_dir / f"{sanitize_filename(tool_call_id)}_detail.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


# === 安全校验函数 ===

# pandas 表达式中禁止的 AST 节点类型
_BLOCKED_EXPR_NODES = {
    ast.Call, ast.Attribute,
    ast.Import, ast.ImportFrom,
    ast.Assign, ast.AugAssign, ast.Delete,
    ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
    ast.Yield, ast.YieldFrom, ast.Await,
    ast.Global, ast.Nonlocal,
    ast.For, ast.AsyncFor, ast.While,
    ast.With, ast.AsyncWith,
    ast.Try, ast.TryStar,
}


def validate_pandas_expr(expr: str) -> str | None:
    """校验 pandas 表达式安全性（derive_field / filter 使用）。

    只允许算术、比较、布尔运算和列名引用。
    返回 None 表示安全，否则返回错误描述。
    """
    if not expr.strip():
        return "表达式不能为空"
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        return f"表达式语法错误: {e}"

    for node in ast.walk(tree):
        if type(node) in _BLOCKED_EXPR_NODES:
            return f"不允许的操作: {type(node).__name__}"
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            return f"不允许的变量名: {node.id}"

    return None


# run_python 沙盒中允许导入的纯计算模块。白名单之外一律拒绝，避免
# “不是危险模块”被误解为“可以导入任意模块”。
_SANDBOX_SAFE_IMPORTS = frozenset({
    'pandas', 'numpy', 'datetime', 'calendar', 'math', 'statistics',
    'decimal', 'fractions',
})


# run_python 沙盒中禁止导入的模块
_DANGEROUS_IMPORTS = frozenset({
    'os', 'sys', 'subprocess', 'shutil', 'socket', 'http',
    'urllib', 'requests', 'pickle', 'shelve', 'marshal',
    'ctypes', 'multiprocessing', 'signal', 'resource',
})

# 禁止直接调用的函数名
_DANGEROUS_CALLS = frozenset({
    '__import__', 'exec', 'eval', 'compile', 'open',
    'input', 'breakpoint', 'globals', 'locals', 'vars',
    'getattr', 'setattr', 'delattr', 'type',
})

# 禁止访问的属性名
_DANGEROUS_ATTRS = frozenset({
    '__import__', '__builtins__', '__class__', '__bases__',
    '__subclasses__', '__globals__', '__code__', '__closure__',
    '__mro__', '__dict__',
})

# `run_python` exposes pandas and NumPy for in-memory analysis. Their I/O
# helpers would otherwise bypass the sandbox's no-files/no-network contract.
_SANDBOX_IO_ATTRS = frozenset({
    "read_clipboard", "read_csv", "read_excel", "read_feather", "read_fwf",
    "read_gbq", "read_hdf", "read_html", "read_json", "read_orc",
    "read_parquet", "read_pickle", "read_sas", "read_spss", "read_sql",
    "read_sql_query", "read_sql_table", "read_stata", "read_table", "read_xml",
    "ExcelFile", "HDFStore", "to_clipboard", "to_csv", "to_excel",
    "to_feather", "to_gbq", "to_hdf", "to_json", "to_orc", "to_parquet",
    "to_pickle", "to_sql", "load", "save", "savez", "savez_compressed",
})


def validate_python_code(code: str) -> str | None:
    """AST 级别校验 Python 代码安全性（run_python 使用）。

    返回 None 表示安全，否则返回错误描述。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # 语法错误交给执行阶段处理

    for node in ast.walk(tree):
        # 检查 import
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split('.')[0]
                if module in _DANGEROUS_IMPORTS or module not in _SANDBOX_SAFE_IMPORTS:
                    return f"不允许导入: {alias.name}；可用模块: {', '.join(sorted(_SANDBOX_SAFE_IMPORTS))}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split('.')[0] if node.module else ''
            if node.level or module in _DANGEROUS_IMPORTS or module not in _SANDBOX_SAFE_IMPORTS:
                return f"不允许导入: {node.module or 'relative import'}；可用模块: {', '.join(sorted(_SANDBOX_SAFE_IMPORTS))}"

        # 检查函数调用
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in _DANGEROUS_CALLS:
                    return f"不允许调用: {node.func.id}()"
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in _DANGEROUS_CALLS or node.func.attr in _DANGEROUS_ATTRS:
                    return f"不允许调用: .{node.func.attr}()"
                if node.func.attr in _SANDBOX_IO_ATTRS:
                    return f"不允许文件或网络 I/O: .{node.func.attr}()"

        # 检查 dunder 属性访问
        if isinstance(node, ast.Attribute) and node.attr.startswith('__') and node.attr.endswith('__'):
            return f"不允许访问: .{node.attr}"

        # Vectorised pandas/NumPy operations are the supported path. Reject
        # unbounded loops before they can outlive a best-effort timeout.
        if isinstance(node, ast.While):
            return "不允许 while 循环；请使用受限的向量化计算或有限 range()"

    return None


def validate_path_in_allowed(path: str, allowed_dirs: list[Path]) -> Path:
    """校验路径在允许目录范围内。返回解析后的绝对路径。"""
    p = Path(path)
    # 先解析绝对路径
    if p.is_absolute():
        resolved = p.resolve()
    else:
        # 相对路径：检查每个 allowed_dir
        for base in allowed_dirs:
            candidate = (base / path).resolve()
            if candidate.exists() and candidate.is_relative_to(base.resolve()):
                return candidate
        # 不存在也检查是否在范围内
        for base in allowed_dirs:
            candidate = (base / path).resolve()
            if candidate.is_relative_to(base.resolve()):
                return candidate
        raise ValueError(f"路径超出允许范围: {path}")

    # 绝对路径需在允许目录内
    resolved = p.resolve()
    for base in allowed_dirs:
        if resolved.is_relative_to(base.resolve()):
            return resolved
    raise ValueError(f"路径超出允许范围: {path}")


_SANITIZE_PATH_RE = re.compile(r'[<>:"|?*]')


def sanitize_filename(name: str) -> str:
    """清理文件名中的危险字符和路径分隔符。"""
    name = name.replace('\\', '_').replace('/', '_').replace('..', '_')
    name = _SANITIZE_PATH_RE.sub('_', name)
    name = name.strip('. ')
    return name or "unnamed"


_SQL_BLOCKED_RE = re.compile(
    r';\s*(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|EXEC)\b'
    r'|^\s*(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|EXEC)\b',
    re.IGNORECASE,
)


def validate_sql_query(query: str) -> str | None:
    """校验 SQL 查询安全性（仅允许 SELECT/WITH）。返回错误或 None。"""
    stripped = query.strip().upper()
    if not stripped.startswith(('SELECT', 'WITH', '(')):
        return "仅允许 SELECT 查询（或 WITH ... SELECT）"
    if _SQL_BLOCKED_RE.search(query):
        return "查询中包含不允许的 SQL 操作（仅允许 SELECT）"
    return None


def resolve_date_col(df: pd.DataFrame, date_col: str = "") -> tuple[str, str | None]:
    """自动推断或验证日期列。

    Returns:
        (date_col, error) — date_col 为推断/验证后的列名，error 为 None 表示成功。
    """
    if date_col and date_col in df.columns:
        return date_col, None

    dt_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    if not dt_cols:
        for c in df.columns:
            if pd.api.types.is_string_dtype(df[c].dtype):
                try:
                    pd.to_datetime(df[c].dropna().head(20))
                    dt_cols.append(c)
                    break
                except (ValueError, TypeError):
                    continue
    if not dt_cols:
        return "", "无法自动推断日期列，请指定 date_col 参数"
    return dt_cols[0], None


def parse_period_range(
    period_str: str,
    ref_date: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """解析时间段字符串为 (start, end)。

    支持快捷词: last_week / this_week / last_month / this_month
    支持显式格式: YYYY-MM-DD~YYYY-MM-DD

    Args:
        period_str: 时间段字符串
        ref_date: 参考日期（通常为数据最大日期），快捷词基于此计算
    """
    ref = ref_date.normalize()
    this_month_start = ref.replace(day=1)
    last_month_end = this_month_start - pd.Timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    this_week_start = ref - pd.Timedelta(days=ref.weekday())
    last_week_start = this_week_start - pd.Timedelta(weeks=1)
    last_week_end = this_week_start - pd.Timedelta(days=1)

    shortcuts = {
        "last_week": (last_week_start, last_week_end),
        "this_week": (this_week_start, ref),
        "last_month": (last_month_start, last_month_end),
        "this_month": (this_month_start, ref),
    }
    if period_str in shortcuts:
        return shortcuts[period_str]
    if "~" in period_str:
        parts = period_str.split("~")
        return pd.Timestamp(parts[0].strip()), pd.Timestamp(parts[1].strip())
    return None


def inclusive_date_period_mask(
    values: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Return the mask for an inclusive pair of calendar-date boundaries.

    ``parse_period_range`` exposes business periods as dates, not instants.
    Comparing a timestamp column to its normalized end date with ``<=``
    silently discards all events later that day.  A half-open next-day bound
    keeps the public date contract inclusive while retaining timestamp-level
    precision and is shared by every period-comparison tool.
    """
    start_day = pd.Timestamp(start).normalize()
    next_day = pd.Timestamp(end).normalize() + pd.Timedelta(days=1)
    return (values >= start_day) & (values < next_day)


def analyze_period_structure(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """分析一个时间段的结构信息：天数、工作日/周末构成、日期列表。

    Args:
        start: 开始日期
        end: 结束日期（包含）

    Returns:
        时段结构字典，包含 day_count / weekday_count / weekend_count / dates 等
    """
    start = start.normalize()
    end = end.normalize()
    day_count = (end - start).days + 1

    date_range = pd.date_range(start, end, freq="D")
    weekday_count = sum(1 for d in date_range if d.weekday() < 5)
    weekend_count = day_count - weekday_count

    dow_summary: dict[str, int] = {}
    for d in date_range:
        name = d.day_name()
        dow_summary[name] = dow_summary.get(name, 0) + 1

    result: dict = {
        "start": str(start.date()),
        "end": str(end.date()),
        "day_count": day_count,
        "weekday_count": weekday_count,
        "weekend_count": weekend_count,
        "weekday_ratio": round(weekday_count / day_count, 3) if day_count > 0 else 0,
        "weekend_ratio": round(weekend_count / day_count, 3) if day_count > 0 else 0,
        "dow_summary": dow_summary,
    }

    # 超过31天不输出逐日列表，避免过长
    if day_count <= 31:
        result["dates"] = [
            {
                "date": str(d.date()),
                "dow": d.day_name(),
                "is_weekend": d.weekday() >= 5,
            }
            for d in date_range
        ]
    else:
        result["dates_note"] = f"Period spans {day_count} days; individual dates omitted"

    return result


def compare_period_structures(
    struct_a: dict,
    struct_b: dict,
) -> dict:
    """比较两个时段的结构可比性，生成评估和警告。

    Args:
        struct_a: analyze_period_structure 的输出
        struct_b: analyze_period_structure 的输出

    Returns:
        可比性评估字典，包含 lengths_equal / warnings / daily_avg_recommended 等
    """
    lengths_equal = struct_a["day_count"] == struct_b["day_count"]
    weekday_ratio_diff = round(
        abs(struct_a["weekday_ratio"] - struct_b["weekday_ratio"]), 3
    )

    warnings: list[str] = []
    if not lengths_equal:
        warnings.append(
            f"period_a has {struct_a['day_count']} days, period_b has {struct_b['day_count']} days"
        )
    if weekday_ratio_diff > 0.1:
        warnings.append(
            f"weekday/weekend ratio differs by {weekday_ratio_diff:.3f} "
            f"(A: {struct_a['weekday_ratio']:.1%} weekday, "
            f"B: {struct_b['weekday_ratio']:.1%} weekday)"
        )

    return {
        "lengths_equal": lengths_equal,
        "day_count_a": struct_a["day_count"],
        "day_count_b": struct_b["day_count"],
        "weekday_ratio_diff": weekday_ratio_diff,
        "warnings": warnings,
        "daily_avg_recommended": not lengths_equal,
    }
