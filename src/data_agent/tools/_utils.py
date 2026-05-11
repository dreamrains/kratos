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
    path = detail_dir / f"{tool_call_id}_detail.json"
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
                if module in _DANGEROUS_IMPORTS:
                    return f"不允许导入: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split('.')[0] in _DANGEROUS_IMPORTS:
                return f"不允许导入: {node.module}"

        # 检查函数调用
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in _DANGEROUS_CALLS:
                    return f"不允许调用: {node.func.id}()"
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in _DANGEROUS_CALLS or node.func.attr in _DANGEROUS_ATTRS:
                    return f"不允许调用: .{node.func.attr}()"

        # 检查 dunder 属性访问
        if isinstance(node, ast.Attribute) and node.attr.startswith('__') and node.attr.endswith('__'):
            return f"不允许访问: .{node.attr}"

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
            if df[c].dtype == object:
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
