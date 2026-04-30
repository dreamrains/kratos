"""工具模块共享函数。"""

from __future__ import annotations

import json
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
    detail_dir = cfg.project_resolved / "sessions" / session_id / "tool_outputs"
    detail_dir.mkdir(parents=True, exist_ok=True)
    path = detail_dir / f"{tool_call_id}_detail.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return path
