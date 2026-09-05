from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from data_agent.config import get_config
from data_agent.tools._utils import sanitize_filename
from data_agent.tools.registry import registry


def _safe_path(p: str) -> Path:
    """确保路径在工作空间内，防止路径穿越。"""
    cfg = get_config()
    from data_agent.session.artifact_paths import resolve_reference
    from data_agent.tools.visualization import current_session_id
    return resolve_reference(p, project=cfg.project_resolved,
                             sessions=cfg.sessions_resolved, session_id=current_session_id() or "")


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
    description="读取工作空间文件或当前会话工具产物。长文件返回 file_page.v1：使用同一 path 和 next_offset 继续读取，可传 expected_sha256 保证原件未变；max_chars 为每页字符数(最多2000)。直接使用 tool_outputs/... 或 sessions/<当前会话ID>/...；禁止跨会话和路径穿越。",
)
def read_file(path: str, limit: Optional[int] = None, offset: int = 0, max_chars: int = 2000,
              expected_sha256: str = "") -> str:
    fp = _safe_path(path)
    if not fp.exists():
        return f"Error: File not found: {path}"
    if fp.is_dir():
        return f"Error: {path} is a directory"
    try:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer character offset")
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 1 <= max_chars <= 2000:
            raise ValueError("max_chars must be an integer from 1 to 2000")
        content = fp.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if expected_sha256 and expected_sha256 != digest:
            raise ValueError("file_changed: restart reading from offset 0")
        if offset or len(content) > max_chars:
            end = min(offset + max_chars, len(content))
            return json.dumps({"schema_version": "file_page.v1", "path": path, "offset": offset,
                               "content": content[offset:end], "next_offset": end if end < len(content) else None,
                               "total_chars": len(content), "sha256": digest}, ensure_ascii=False)
        lines = content.splitlines()
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
        normalized = path.replace("\\", "/")
        if normalized.startswith(("output/", "sessions/")):
            fp = _safe_path(path)
            if not fp.is_relative_to(session_dir.resolve()):
                raise ValueError("write_file may only write current-session output artifacts")
        else:
            fp = session_dir / safe_name
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

        # 注册到会话 artifact 清单
        from data_agent.session.history import register_artifact
        artifact_path = f"sessions/{session_id}/output/{fp.relative_to(session_dir).as_posix()}"
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
    try:
        matches = sorted(workspace.glob(pattern), key=lambda item: str(item).casefold())
    except OSError as exc:
        return f"Error: Unable to enumerate workspace files: {exc}"
    lines = []
    skipped = 0
    for m in matches:
        try:
            if m.resolve().is_relative_to(cfg.sessions_resolved.resolve()):
                continue
            _safe_path(str(m.relative_to(workspace)))
            rel = m.relative_to(workspace)
            kind = "dir" if m.is_dir() else f"{m.stat().st_size} bytes"
            lines.append(f"  {rel} ({kind})")
        except (FileNotFoundError, PermissionError, OSError, ValueError):
            # SQLite sidecars and other runtime files can disappear between
            # glob enumeration and stat. One unrelated transient entry must
            # not hide valid uploaded data from the entire listing.
            skipped += 1
    from data_agent.tools.visualization import current_session_id
    from data_agent.session.artifact_paths import ARTIFACT_DIRS
    sid = current_session_id()
    if sid:
        root = cfg.sessions_resolved / sid
        for item in sorted(root.glob(pattern)):
            rel = item.relative_to(root)
            if rel.parts and rel.parts[0] in ARTIFACT_DIRS:
                try:
                    _safe_path(f"sessions/{sid}/{rel.as_posix()}")
                    if item.is_file():
                        lines.append(f"  sessions/{sid}/{rel.as_posix()} ({item.stat().st_size} bytes)")
                except (OSError, ValueError):
                    skipped += 1
    if skipped:
        lines.append(f"[Skipped {skipped} transient or inaccessible entry/entries]")
    if not lines:
        return "No files found."
    return "\n".join(lines)
