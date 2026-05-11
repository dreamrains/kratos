from __future__ import annotations

from pathlib import Path
from typing import Optional

from data_agent.config import get_config
from data_agent.tools._utils import sanitize_filename
from data_agent.tools.registry import registry


def _safe_path(p: str) -> Path:
    """确保路径在工作空间内，防止路径穿越。"""
    cfg = get_config()
    workspace = cfg.project_resolved
    resolved = (workspace / p).resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError(f"Path escapes workspace: {p}")
    return resolved


def _get_session_output_dir() -> Optional[Path]:
    """获取当前会话的 output 目录，无会话时返回 None。"""
    from data_agent.tools.visualization import current_session_id
    session_id = current_session_id()
    if not session_id:
        return None
    from data_agent.config import get_config
    d = get_config().sessions_resolved / session_id / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


@registry.register(
    name="read_file",
    description="读取文件内容。path 为工作空间内的相对路径。",
)
def read_file(path: str, limit: Optional[int] = None) -> str:
    fp = _safe_path(path)
    if not fp.exists():
        return f"Error: File not found: {path}"
    if fp.is_dir():
        return f"Error: {path} is a directory"
    try:
        lines = fp.read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@registry.register(
    name="write_file",
    description="写入内容到文件。path 为相对路径。文件会保存到当前会话的 output 目录中，并自动注册到会话清单。",
)
def write_file(path: str, content: str) -> str:
    from data_agent.tools.visualization import current_session_id

    safe_name = sanitize_filename(path)
    session_dir = _get_session_output_dir()
    if session_dir:
        session_id = current_session_id()
        fp = session_dir / safe_name
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

        # 注册到会话 artifact 清单
        from data_agent.session.history import register_artifact
        artifact_path = f"sessions/{session_id}/output/{safe_name}"
        register_artifact(session_id, artifact_path, "file", path)
        return f"Wrote {len(content)} bytes to {artifact_path}"
    else:
        fp = _safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"


@registry.register(
    name="edit_file",
    description="精确替换文件中的文本。old_text 必须在文件中唯一存在。",
)
def edit_file(path: str, old_text: str, new_text: str) -> str:
    fp = _safe_path(path)
    if not fp.exists():
        return f"Error: File not found: {path}"
    try:
        content = fp.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count == 0:
            return f"Error: Text not found in {path}"
        if count > 1:
            return f"Error: Text appears {count} times in {path}, must be unique"
        new_content = content.replace(old_text, new_text, 1)
        fp.write_text(new_content, encoding="utf-8")
        return f"Edited {path}: replaced 1 occurrence"
    except Exception as e:
        return f"Error: {e}"


@registry.register(
    name="list_files",
    description="列出工作空间中的文件。pattern 为 glob 模式，如 '**/*.csv'。",
)
def list_files(pattern: str = "**/*") -> str:
    cfg = get_config()
    workspace = cfg.project_resolved
    matches = sorted(workspace.glob(pattern))
    if not matches:
        return "No files found."
    lines = []
    for m in matches:
        rel = m.relative_to(workspace)
        kind = "dir" if m.is_dir() else f"{m.stat().st_size} bytes"
        lines.append(f"  {rel} ({kind})")
    return "\n".join(lines)
