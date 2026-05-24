"""会话持久化管理：以 sessions/<session_id>/ 为核心组织。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from data_agent.config import get_config

logger = logging.getLogger(__name__)


def _sessions_dir() -> Path:
    return get_config().sessions_resolved


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _session_dir(session_id: str) -> Path:
    d = _sessions_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("analyses", "charts", "reports"):
        (d / sub).mkdir(exist_ok=True)
    return d


def _try_index_session_evidence(session_id: str) -> None:
    try:
        from data_agent.knowledge.evidence import EvidenceStore

        EvidenceStore().index_session(session_id)
    except Exception:
        logger.debug("Session evidence indexing skipped", exc_info=True)


def session_knowledge_dir(session_id: str) -> Path:
    """返回会话级知识目录路径，自动创建。"""
    d = _session_dir(session_id) / "knowledge"
    d.mkdir(exist_ok=True)
    return d


# ── JSONL 追加式持久化 ──────────────────────────────────────

_JSONL_ROTATE_BYTES = 256 * 1024  # 256 KiB


def _read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件为消息列表。跳过损坏行。"""
    messages = []
    if not path.exists():
        return messages
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def _rotate_jsonl(session_id: str) -> None:
    """JSONL 超过阈值时合并到 conversation.json 并清空 JSONL。"""
    sdir = _session_dir(session_id)
    jsonl_path = sdir / "conversation.jsonl"
    conv_path = sdir / "conversation.json"

    jsonl_messages = _read_jsonl(jsonl_path)
    if not jsonl_messages:
        jsonl_path.unlink(missing_ok=True)
        return

    # 合并：JSON 中的旧消息 + JSONL 中的新消息
    json_messages = []
    if conv_path.exists():
        try:
            json_messages = json.loads(conv_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    all_messages = json_messages + jsonl_messages
    conv = _serialize_messages(all_messages)
    conv_path.write_text(
        json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    jsonl_path.unlink(missing_ok=True)


def push_message(session_id: str, message: dict) -> None:
    """追加一条消息到 JSONL。快速的 per-turn 持久化。"""
    sdir = _session_dir(session_id)
    jsonl_path = sdir / "conversation.jsonl"
    line = json.dumps(message, default=str, ensure_ascii=False)
    try:
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        return  # 写入失败不影响内存状态

    # 超过阈值时轮转
    try:
        if jsonl_path.stat().st_size > _JSONL_ROTATE_BYTES:
            _rotate_jsonl(session_id)
    except OSError:
        pass


def push_messages(session_id: str, messages: list[dict]) -> None:
    """批量追加多条消息到 JSONL。"""
    sdir = _session_dir(session_id)
    jsonl_path = sdir / "conversation.jsonl"
    lines = []
    for msg in messages:
        lines.append(json.dumps(msg, default=str, ensure_ascii=False))
    try:
        with jsonl_path.open("a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
    except OSError:
        return

    try:
        if jsonl_path.stat().st_size > _JSONL_ROTATE_BYTES:
            _rotate_jsonl(session_id)
    except OSError:
        pass


# ── 会话保存与恢复 ────────────────────────────────────────

def save_session(
    messages: list[dict],
    session_id: str,
    tag: str = "",
    data_file: str = "",
    extra_meta: Optional[dict] = None,
    merge_protect: bool = True,
) -> str:
    """保存会话到 sessions/<session_id>/。写入 conversation.json 并清空 JSONL。

    包含合并保护：如果磁盘上的 conversation.json 比内存中的消息更多，
    说明会话历史可能在内存中丢失（如 AgentLoop 重建），此时合并而非覆盖。
    """
    sdir = _session_dir(session_id)

    # Merge protection: prevent data loss if in-memory messages are incomplete.
    # Rewind is an intentional truncation and must bypass this guard.
    if merge_protect:
        messages = _merge_protect_messages(sdir, messages)

    # 提取会话摘要：第一条非命令用户消息的前 100 字符
    summary = _extract_summary(messages)

    # meta.json
    meta = {
        "session_id": session_id,
        "saved_at": _now_str(),
        "tag": tag,
        "data_file": data_file,
        "message_count": len(messages),
        "summary": summary,
        "project_name": None,
    }
    if extra_meta:
        extra = dict(extra_meta)
        project_name = extra.pop("project_name", None)
        object_name = extra.pop("object_name", None)
        active_project = project_name if project_name is not None else object_name
        meta["project_name"] = active_project
        meta.update(extra)
    (sdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # conversation.json
    conv = _serialize_messages(messages)
    (sdir / "conversation.json").write_text(
        json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # JSONL 已合并到 JSON，删除
    jsonl_path = sdir / "conversation.jsonl"
    jsonl_path.unlink(missing_ok=True)

    _try_index_session_evidence(session_id)

    return session_id


def load_session(session_id: str) -> Optional[dict]:
    """加载指定会话。自动检测 JSON/JSONL 格式并合并。自动清洗连续同 role 消息。"""
    sdir = _session_dir(session_id)
    meta_path = sdir / "meta.json"
    conv_path = sdir / "conversation.json"
    jsonl_path = sdir / "conversation.jsonl"

    # 至少要有 meta.json 或 conversation.jsonl 才能加载
    if not meta_path.exists() and not jsonl_path.exists():
        return None

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 先读 JSON（旧格式/轮转后快照）
    messages = []
    if conv_path.exists():
        try:
            messages = json.loads(conv_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 再读 JSONL（追加的新消息）
    if jsonl_path.exists():
        jsonl_messages = _read_jsonl(jsonl_path)
        if jsonl_messages:
            messages = messages + jsonl_messages

    messages = _sanitize_messages(messages)
    return {
        "session_id": session_id,
        "saved_at": meta.get("saved_at", ""),
        "tag": meta.get("tag", ""),
        "data_file": meta.get("data_file", ""),
        "message_count": len(messages),
        "messages": messages,
        "summary": meta.get("summary", ""),
        "project_name": meta.get("project_name") or meta.get("object_name"),
    }


def list_sessions(object_name: str = "", project_name: str = "") -> list[dict]:
    """列出所有会话摘要。支持按项目名过滤，object_name 为兼容别名。"""
    results = []
    filter_project = project_name or object_name
    for d in _sessions_dir().iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            proj_name = meta.get("project_name") or meta.get("object_name")
            # 按项目过滤
            if filter_project:
                if proj_name != filter_project:
                    continue
            results.append({
                "session_id": meta["session_id"],
                "saved_at": meta.get("saved_at", ""),
                "tag": meta.get("tag", ""),
                "data_file": meta.get("data_file", ""),
                "message_count": meta.get("message_count", 0),
                "summary": meta.get("summary", ""),
                "project_name": proj_name,
            })
        except (json.JSONDecodeError, KeyError):
            continue
    results.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return results


def update_session_meta(session_id: str, updates: dict) -> bool:
    """原子更新会话元数据。用于动态绑定/解绑对象。"""
    sdir = _session_dir(session_id)
    meta_path = sdir / "meta.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        updates = dict(updates)
        if "project_name" in updates or "object_name" in updates:
            project_name = updates.get("project_name", updates.get("object_name"))
            updates["project_name"] = project_name
            updates.pop("object_name", None)
        meta.update(updates)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except (json.JSONDecodeError, OSError):
        return False


# ── 动态绑定/解绑 ────────────────────────────────────────

def bind_session_to_project(session_id: str, project_name: str) -> dict:
    """Bind a session to a project without promoting or moving knowledge."""
    from data_agent.project_manager import get_project_manager

    mgr = get_project_manager()
    if mgr.get(project_name) is None:
        return {
            "success": False,
            "message": f"Project '{project_name}' not found",
            "from_project": None,
        }

    sdir = _session_dir(session_id)
    meta_path = sdir / "meta.json"
    current_project = None
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        current_project = meta.get("project_name") or meta.get("object_name")

    if current_project == project_name:
        return {
            "success": True,
            "message": f"Session already bound to project '{project_name}'",
            "from_project": current_project,
            "project_name": project_name,
        }

    if current_project:
        mgr.unbind_session(current_project, session_id)

    mgr.bind_session(project_name, session_id)
    update_session_meta(session_id, {"project_name": project_name})
    return {
        "success": True,
        "message": f"Session bound to project '{project_name}'" + (f" from '{current_project}'" if current_project else ""),
        "from_project": current_project,
        "project_name": project_name,
    }


def unbind_session_from_project(session_id: str) -> dict:
    """Remove a session's project binding."""
    from data_agent.project_manager import get_project_manager

    sdir = _sessions_dir() / session_id
    meta_path = sdir / "meta.json"
    if not meta_path.exists():
        return {
            "success": True,
            "message": "Session does not exist or has no project binding",
            "from_project": None,
        }

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    current_project = meta.get("project_name") or meta.get("object_name")
    if not current_project:
        return {
            "success": True,
            "message": "Session is not bound to a project",
            "from_project": None,
        }

    mgr = get_project_manager()
    mgr.unbind_session(current_project, session_id)
    update_session_meta(session_id, {"project_name": None})

    return {
        "success": True,
        "message": f"Session unbound from project '{current_project}'",
        "from_project": current_project,
    }


def bind_session_to_object(session_id: str, object_name: str) -> dict:
    """Compatibility alias for pre-release callers."""
    result = bind_session_to_project(session_id, object_name)
    result["from_object"] = result.get("from_project")
    return result


def unbind_session_from_object(session_id: str) -> dict:
    """Compatibility alias for pre-release callers."""
    result = unbind_session_from_project(session_id)
    result["from_object"] = result.get("from_project")
    return result

def branch_session(parent_id: str, branch_name: str = "") -> dict:
    """从父会话分叉出一个新会话，继承消息和上下文。不修改父会话。"""
    parent_data = load_session(parent_id)
    if parent_data is None:
        return {"success": False, "message": f"Session {parent_id} not found"}

    new_id = uuid.uuid4().hex[:12]
    sdir = _session_dir(new_id)

    # 复制消息
    conv = _serialize_messages(parent_data["messages"])
    (sdir / "conversation.json").write_text(
        json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 创建 meta，记录分支溯源
    meta = {
        "session_id": new_id,
        "saved_at": _now_str(),
        "tag": branch_name or f"branch-{new_id[:6]}",
        "data_file": parent_data.get("data_file", ""),
        "message_count": len(parent_data["messages"]),
        "summary": parent_data.get("summary", ""),
        "project_name": parent_data.get("project_name"),
        "forked_from": parent_id,
        "branch_name": branch_name,
    }
    (sdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 复制对象绑定
    if parent_data.get("project_name"):
        try:
            from data_agent.project_manager import get_project_manager
            mgr = get_project_manager()
            mgr.bind_session(parent_data["project_name"], new_id)
        except Exception:
            pass

    return {
        "success": True,
        "session_id": new_id,
        "parent_id": parent_id,
        "message_count": len(parent_data["messages"]),
    }


def list_branches(session_id: str) -> list[dict]:
    """列出从指定会话分叉出的所有分支。"""
    results = []
    for d in _sessions_dir().iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("forked_from") == session_id:
                results.append({
                    "session_id": meta["session_id"],
                    "branch_name": meta.get("branch_name", ""),
                    "saved_at": meta.get("saved_at", ""),
                    "message_count": meta.get("message_count", 0),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return results


# ── Artifact 清单 ─────────────────────────────────────────

def register_artifact(session_id: str, path: str, artifact_type: str, description: str = "") -> str:
    """将输出物注册到会话的 artifact 清单。"""
    sdir = _session_dir(session_id)
    manifest_path = sdir / "artifacts.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = []

    entry = {
        "path": path,
        "type": artifact_type,
        "description": description,
        "registered_at": _now_str(),
    }
    manifest.append(entry)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def list_artifacts(session_id: str) -> list[dict]:
    """列出会话的所有注册输出物。"""
    manifest_path = _session_dir(session_id) / "artifacts.json"
    if not manifest_path.exists():
        return []
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def delete_artifact(session_id: str, artifact_index: int) -> bool:
    """删除会话中指定索引的输出物（从 manifest 移除并删除物理文件）。"""
    import shutil as _shutil

    sdir = _session_dir(session_id)
    manifest_path = sdir / "artifacts.json"
    if not manifest_path.exists():
        return False

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if artifact_index < 0 or artifact_index >= len(manifest):
        return False

    entry = manifest.pop(artifact_index)

    # 尝试删除物理文件
    artifact_path = entry.get("path", "")
    if artifact_path:
        # 解析相对路径：sessions/<sid>/reports/xxx.html
        parts = Path(artifact_path).parts
        if len(parts) >= 2 and parts[0] == "sessions":
            physical = _sessions_dir().joinpath(*parts[1:])
        else:
            physical = Path(artifact_path)
        if not physical.is_absolute():
            physical = sdir / physical
        if physical.exists():
            try:
                physical.unlink()
            except OSError:
                pass

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def delete_session(session_id: str) -> bool:
    import shutil
    sdir = _sessions_dir() / session_id
    if sdir.exists():
        shutil.rmtree(sdir)
        return True
    return False


# ── 会话子目录路径 ─────────────────────────────────────────

def session_charts_dir(session_id: str) -> Path:
    d = _session_dir(session_id) / "charts"
    d.mkdir(exist_ok=True)
    return d


def session_reports_dir(session_id: str) -> Path:
    d = _session_dir(session_id) / "reports"
    d.mkdir(exist_ok=True)
    return d


# ── 分析记录归档 ──────────────────────────────────────────

def archive_analysis(
    session_id: str,
    data_file: str,
    summary: str,
    insights: list[dict],
    tools_used: list[str],
) -> str:
    """将分析结果归档到会话的 analyses/ 目录。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_id = f"ana_{ts}_{uuid.uuid4().hex[:4]}"
    data = {
        "archive_id": archive_id,
        "timestamp": _now_str(),
        "session_id": session_id,
        "data_file": data_file,
        "summary": summary,
        "insights": insights,
        "tools_used": tools_used,
    }
    sdir = _session_dir(session_id)
    (sdir / "analyses").mkdir(exist_ok=True)
    path = sdir / "analyses" / f"{archive_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return archive_id


def list_analyses(session_id: str = "") -> list[dict]:
    """列出分析记录。"""
    results = []
    sessions = [_sessions_dir() / session_id] if session_id else list(_sessions_dir().iterdir())

    for sdir in sessions:
        if not sdir.is_dir():
            continue
        analyses_dir = sdir / "analyses"
        if not analyses_dir.exists():
            continue
        for f in sorted(analyses_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append({
                    "archive_id": data.get("archive_id", ""),
                    "timestamp": data.get("timestamp", ""),
                    "session_id": data.get("session_id", ""),
                    "data_file": data.get("data_file", ""),
                    "summary": (data.get("summary", "") or "")[:100],
                    "tools_used": data.get("tools_used", []),
                })
            except (json.JSONDecodeError, OSError):
                continue

    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results


# ── 合并保护 ─────────────────────────────────────────────

def _merge_protect_messages(sdir: Path, messages: list[dict]) -> list[dict]:
    """Prevent save_session from overwriting a more complete conversation.json.

    If the disk file has significantly more messages than in-memory (e.g. due to
    AgentLoop being recreated without loading history), merge the disk content
    with new messages instead of overwriting.
    """
    conv_path = sdir / "conversation.json"
    if not conv_path.exists() or not messages:
        return messages

    try:
        existing = json.loads(conv_path.read_text(encoding="utf-8"))
        if not isinstance(existing, list) or len(existing) <= len(messages):
            return messages

        # Disk has more messages — likely a restore miss.
        # Strategy: keep disk history as base, append any genuinely new tail messages.
        disk_len = len(existing)
        mem_len = len(messages)

        # If memory messages are a subset (same starting content), use disk + tail
        if mem_len > 0:
            # Find overlap: check if the first memory message matches the start of disk
            # Simple heuristic: if disk is much longer, trust disk and append tail
            if disk_len > mem_len * 1.5:
                # Take disk base + any memory messages beyond disk length
                # (shouldn't exist, but handle gracefully)
                merged = list(existing)
                # Append messages that are truly new (beyond disk range)
                if mem_len > disk_len:
                    merged.extend(messages[disk_len:])
                logger.warning(
                    "Merge protection activated: disk had %d messages, memory had %d. Keeping disk.",
                    disk_len, mem_len,
                    extra={"extra_data": {"disk": disk_len, "memory": mem_len}},
                )
                return merged

        return messages
    except (json.JSONDecodeError, OSError):
        return messages


# ── 摘要提取 ─────────────────────────────────────────────

def _extract_summary(messages: list[dict]) -> str:
    """提取第一条非命令用户消息的前 100 字符作为会话摘要。"""
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text or text.startswith("/"):
            continue
        return text[:100]
    return ""


# ── 序列化辅助 ────────────────────────────────────────────

def _serialize_messages(messages: list[dict]) -> list[dict]:
    result = []
    for msg in messages:
        m = dict(msg)
        if m.get("role") == "tool" and isinstance(m.get("content"), str) and len(m["content"]) > 10000:
            m["content"] = m["content"][:10000] + "\n...[truncated]"
        result.append(m)
    return result


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """清洗消息历史：合并连续同 role 消息，删除空 assistant 消息。

    大多数 LLM API 要求 user/assistant 消息交替出现。
    此函数确保加载的会话历史格式合法。
    """
    if not messages:
        return messages

    # 第一步：删除 content 为空或 "None" 的尾部 user 消息（LLM 未响应的残留）
    while messages and messages[-1].get("role") == "user":
        last_content = messages[-1].get("content", "")
        if not last_content or last_content == "None":
            messages.pop()
        else:
            break

    # 第二步：合并连续同 role 的 user/assistant 消息
    merged: list[dict] = [messages[0]]
    for msg in messages[1:]:
        prev = merged[-1]
        if msg["role"] == prev["role"] and msg["role"] in ("user", "assistant"):
            prev_content = prev.get("content", "") or ""
            cur_content = msg.get("content", "") or ""
            if cur_content:
                combined = f"{prev_content}\n{cur_content}" if prev_content else cur_content
                prev["content"] = combined
        else:
            merged.append(msg)

    return merged

