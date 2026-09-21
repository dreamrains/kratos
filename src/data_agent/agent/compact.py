"""上下文压缩管理器。

参考 Claude Code 的 compact 策略，针对数据分析场景调优：
1. 大工具输出持久化到磁盘，用预览标记替代
2. 旧工具结果微压缩为占位符（先持久化完整内容）
3. 超阈值时 LLM 摘要早期对话（先保存 transcript）
4. compact 作为 LLM 可调用工具，支持主动压缩
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from data_agent.config import get_config
from data_agent.utils.logging import get_logger

logger = get_logger("compact")

# 针对数据分析场景调优的常量
PERSIST_THRESHOLD = 15_000   # 超过此字符数的工具输出持久化到磁盘
PREVIEW_CHARS = 2_000        # 持久化后保留的预览字符数
KEEP_RECENT = 8              # 微压缩时保留最近 N 个工具结果

_COMPACTED_MARKER = "[Compacted:"


@dataclass
class CompactState:
    has_compacted: bool = False
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)


def _session_tool_outputs_dir(session_id: str) -> Path:
    d = get_config().sessions_resolved / session_id / "tool_outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_transcripts_dir(session_id: str) -> Path:
    d = get_config().sessions_resolved / session_id / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _content_addressed_path(out_dir: Path, tool_call_id: str, content: str) -> Path:
    safe_id = tool_call_id.replace("/", "_").replace("\\", "_")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return out_dir / f"{safe_id}__{digest}.txt"


def persist_large_output(session_id: str, tool_call_id: str, content: str) -> str:
    """大工具输出持久化到磁盘，返回预览标记。"""
    if len(content) <= PERSIST_THRESHOLD:
        return content

    out_dir = _session_tool_outputs_dir(session_id)
    # Content-addressed storage: the same tool id with different content gets
    # its own file instead of silently reusing the previous body.
    stored_path = _content_addressed_path(out_dir, tool_call_id, content)
    if not stored_path.exists():
        stored_path.write_text(content, encoding="utf-8")

    preview = content[:PREVIEW_CHARS]
    rel_path = stored_path.name
    return (
        "<persisted-output>\n"
        f"Full output saved to: tool_outputs/{rel_path}\n"
        f"Preview ({PREVIEW_CHARS} chars):\n"
        f"{preview}\n"
        "</persisted-output>"
    )


def _collect_tool_result_blocks(messages: list[dict]) -> list[tuple[int, int, dict]]:
    """收集所有 role=tool 的消息块及其索引。"""
    blocks = []
    for msg_index, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        blocks.append((msg_index, msg))
    return blocks


def _extract_compact_preview(content: str, max_chars: int = 400) -> str:
    """从工具输出中提取有意义的摘要预览。

    策略：
    1. 识别结构化标签（如 [data_profile]、[insights]），提取每个标签的首行
    2. 提取包含结论关键词的行（如 "结论"、"发现"、"显著"、"增加"、"下降"）
    3. 如果没有明确结论，取首尾若干行
    """
    lines = content.strip().split("\n")

    # 策略1：提取结构化标签内的首行
    tagged_summaries = []
    in_tag = False
    tag_name = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("[/") and "]" in stripped:
            tag_name = stripped[1:stripped.index("]")]
            in_tag = True
            continue
        if stripped.startswith("[/") and "]" in stripped:
            in_tag = False
            continue
        if in_tag and stripped and len(tagged_summaries) < 8:
            tagged_summaries.append(f"{tag_name}: {stripped}")

    # 策略2：提取结论性行
    conclusion_keywords = [
        "结论", "发现", "显著", "增加", "下降", "增长", "减少",
        "conclusion", "finding", "significant", "insight",
        "趋势", "变化", "对比", "平均", "中位数", "占比",
    ]
    conclusion_lines = [
        l.strip() for l in lines
        if any(kw in l.lower() for kw in conclusion_keywords) and l.strip()
    ]

    # 组合预览
    parts = []
    if tagged_summaries:
        parts.extend(tagged_summaries[:5])
    elif conclusion_lines:
        parts.extend(conclusion_lines[:5])

    # 如果提取不到，用首尾行
    if not parts:
        if len(lines) <= 4:
            parts = lines
        else:
            parts = lines[:2] + ["..."] + lines[-2:]

    preview = "\n".join(parts)
    if len(preview) > max_chars:
        preview = preview[:max_chars] + "..."
    return preview


def _persist_micro_output(session_id: str, tool_call_id: str, content: str) -> Path | None:
    """Persist any compacted tool output before lossy replacement.

    Content-addressed: the same tool id with different content stores a new
    file rather than silently reusing the previous body. A failed or
    unverifiable write returns None and the caller must keep the original
    message content — no reliable copy, no compaction.
    """
    out_dir = _session_tool_outputs_dir(session_id)
    stored_path = _content_addressed_path(out_dir, tool_call_id, content)
    try:
        if not stored_path.exists():
            stored_path.write_text(content, encoding="utf-8")
        if stored_path.read_text(encoding="utf-8") != content:
            stored_path.unlink(missing_ok=True)
            return None
        return stored_path
    except OSError:
        return None


def micro_compact(session_id: str, messages: list[dict]) -> None:
    """微压缩：旧工具结果先可靠持久化，再替换为带引用的结论摘要。保留最近 KEEP_RECENT 个。"""
    tool_blocks = _collect_tool_result_blocks(messages)
    if len(tool_blocks) <= KEEP_RECENT:
        return

    for _, msg in tool_blocks[:-KEEP_RECENT]:
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) <= 120:
            continue
        if content.startswith(_COMPACTED_MARKER):
            # 已压缩消息的完整原文已落盘；二次压缩不得把旧摘要当原文，
            # 也不得覆盖已存储的完整结果。
            continue

        tool_call_id = msg.get("tool_call_id", f"legacy_{id(msg)}")
        stored = _persist_micro_output(session_id, tool_call_id, content)
        if stored is None:
            # 持久化失败：不进行有损替换
            continue
        preview = _extract_compact_preview(content)
        msg["content"] = (
            f"[Compacted: {stored.name}]\n{preview}"
        )


def write_transcript(session_id: str, messages: list[dict]) -> Path:
    """保存完整对话记录到 transcript 文件。"""
    out_dir = _session_transcripts_dir(session_id)
    path = out_dir / f"transcript_{int(time.time())}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")
    return path


_LEDGER_ARG_KEYS = ("name", "path", "dataset", "metric", "period_a", "period_b", "file")


def _argument_anchor(raw_arguments) -> str:
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return ""
    else:
        parsed = raw_arguments
    if not isinstance(parsed, dict):
        return ""
    for key in _LEDGER_ARG_KEYS:
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:60]
    return ""


def _execution_ledger(messages: list[dict]) -> list[str]:
    """Closed-class execution facts: tool name in call order with an argument anchor.

    Deterministically extracted so no generated summary can turn executed
    history into "nothing was executed" (P1-6 item 2, real M03 52a61396f8e6).
    """
    entries: list[str] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            function = (call or {}).get("function") or {}
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            anchor = _argument_anchor(function.get("arguments"))
            entries.append(f"{name}({anchor})" if anchor else name)
    return entries


def _execution_ledger_block(ledger: list[str]) -> str:
    if not ledger:
        return ""
    lines = [f"- {entry}" for entry in ledger[:30]]
    if len(ledger) > 30:
        lines.append(f"- …另有 {len(ledger) - 30} 次调用，完整序列见 transcript")
    return (
        "\n\n[Deterministically preserved execution ledger — context, not evidence]\n"
        + "\n".join(lines)
    )


def _summary_acknowledges_execution(summary: str, ledger: list[str]) -> bool:
    """Closed recall signals: a digit, or a ledger tool-name mention."""
    if not ledger:
        return True
    if re.search(r"\d", summary):
        return True
    tool_names = {entry.split("(", 1)[0] for entry in ledger}
    return any(name in summary for name in tool_names)


def _preserved_identity_and_obligations(messages: list[dict]) -> str:
    """Carry source identity and explicit user obligations across LLM compaction.

    The deterministic appendix is context only, never evidence for a data
    claim. It prevents a generated summary from becoming the sole carrier for
    binding identifiers or hard user constraints.
    """
    markers = (
        "dataset", "version_id", "fingerprint", "source digest", "source_digest",
        "数据集", "版本", "指纹", "来源摘要", "必须", "不得", "不要", "仅", "must ",
        "must not", "do not", "never ",
    )
    kept: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if not isinstance(content, str):
            continue
        for line in content.splitlines():
            normalized = line.strip()
            if normalized and any(marker in normalized.lower() for marker in markers):
                if normalized not in kept:
                    kept.append(normalized[:500])
            if len(kept) >= 12:
                break
        if len(kept) >= 12:
            break
    # Preserve server-owned publication and recoverable-detail references as
    # identifiers only. They remain context pointers, never evidence by
    # themselves, and survive an LLM-written history summary.
    for message in messages:
        packet_id = message.get("publication_packet_id")
        snapshot = message.get("publication_snapshot_digest")
        artifact = message.get("publication_artifact_path")
        if packet_id:
            kept.append(f"publication_packet_id={packet_id} snapshot_digest={snapshot or 'unknown'} artifact={artifact or 'unknown'}")
        if message.get("role") == "tool" and isinstance(message.get("content"), str):
            for ref in re.findall(r"tool_outputs/[A-Za-z0-9_.-]+", message["content"]):
                kept.append(f"detail_ref={ref}")
        if len(kept) >= 20:
            break
    kept = list(dict.fromkeys(kept))[:20]
    if not kept:
        return ""
    return (
        "\n\n[Deterministically preserved identity and obligations — context, not evidence]\n"
        + "\n".join(f"- {line}" for line in kept)
    )


def estimate_tokens(messages: list[dict]) -> int:
    """估算 messages 的 token 数。"""
    return len(json.dumps(messages, default=str, ensure_ascii=False)) // 4


def _find_safe_boundary(messages: list[dict], keep_recent: int) -> int:
    """找到安全的压缩分割点，确保 tool_use/tool_result 对不被拆分。

    从 messages[:-keep_recent] 开始向前扫描，如果分割点落在
    tool result（无对应 tool_use）或 assistant(tool_calls)（无对应 tool result）
    处，则前移分割点直到安全。
    """
    split_idx = len(messages) - keep_recent
    if split_idx <= 0:
        return 0

    max_attempts = keep_recent  # 最多前移 keep_recent 个位置
    for _ in range(max_attempts):
        if split_idx <= 0:
            return 0

        msg = messages[split_idx]

        # Case 1: 分割点处是 tool result → 需要找到对应的 tool_use
        if msg.get("role") == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            if tool_call_id:
                # 向前找对应的 assistant(tool_calls) 消息
                for i in range(split_idx - 1, max(split_idx - 20, -1), -1):
                    m = messages[i]
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            if tc.get("id") == tool_call_id:
                                # 前移到该 assistant 消息之前
                                split_idx = i
                                break
                        else:
                            continue
                        break
                else:
                    # 没找到对应的 tool_use，跳过这个 tool result
                    split_idx -= 1
                    continue
            else:
                split_idx -= 1
                continue

        # Case 2: 分割点处是 assistant 且包含 tool_calls → 需要包含后续 tool results
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_ids = {tc.get("id") for tc in msg["tool_calls"] if tc.get("id")}
            if tool_call_ids:
                # 向后找对应的 tool result
                found_ids = set()
                for i in range(split_idx + 1, min(split_idx + 20, len(messages))):
                    m = messages[i]
                    if m.get("role") == "tool" and m.get("tool_call_id") in tool_call_ids:
                        found_ids.add(m["tool_call_id"])
                    if found_ids == tool_call_ids:
                        break
                # 如果后续 tool result 不在 recent 范围内，前移分割点
                if found_ids != tool_call_ids:
                    split_idx -= 1
                    continue
            # 前移到该 assistant 消息之前
            split_idx -= 1
            continue

        # Case 3: 分割点处是 user 或 assistant（无 tool_calls）→ 安全
        else:
            break

    return split_idx


def compact_history(
    session_id: str,
    client,
    messages: list[dict],
    state: CompactState,
    focus: Optional[str] = None,
    token_threshold: int = 100_000,
) -> list[dict]:
    """压缩早期对话历史为 LLM 生成的摘要。先保存 transcript。"""

    # 保存完整 transcript 以便恢复
    transcript_path = write_transcript(session_id, messages)
    logger.info(f"Transcript saved: {transcript_path}")

    keep_recent = 10
    if len(messages) <= keep_recent:
        return messages

    split_idx = _find_safe_boundary(messages, keep_recent)
    early = messages[:split_idx]
    recent = messages[split_idx:]

    # 截断过长内容用于摘要
    conv_text = json.dumps(early, default=str, ensure_ascii=False)[:80000]

    summary_prompt = (
        "请将以下数据分析对话历史压缩为结构化摘要，必须保留以下关键信息：\n"
        "0. 用户对输出格式、质量、详细程度的明确要求（必须完整保留原文）\n"
        "1. 已加载的数据集名称、行数列数、关键字段、数据质量状态\n"
        "2. 已完成的分析步骤和每步的核心结论（含具体数值和统计显著性）\n"
        "3. 用户关注的核心指标和维度\n"
        "4. 用户表达的分析偏好或业务约束\n"
        "5. 当前分析进展（进行到哪一步、还有什么未完成）\n"
        "6. 数据质量问题或限制条件\n"
        "7. 已生成的图表和报告及其存放路径\n"
        "8. 已训练的模型及其性能指标\n\n"
        "不要丢失任何具体的数值结论和方法说明。\n\n"
        f"{conv_text}"
    )

    resp = client.chat(
        messages=[{"role": "user", "content": summary_prompt}],
        system="你是数据分析对话摘要专家。压缩对话时保留所有数值结论、分析方法和数据引用，去除闲聊和重复内容。用结构化列表输出。",
    )

    # P1-6 子项 2（真实 M03 52a61396f8e6 失实摘要）：摘要是否写到位是开放
    # 语义——召回式检查命中后给一次带确定性台账的修订机会；两次失实则以
    # 确定性骨架替换，"已执行"不可能被写成"未执行"。
    ledger = _execution_ledger(early)
    summary_text = resp.text or ""
    if not _summary_acknowledges_execution(summary_text, ledger):
        correction_prompt = (
            "你上一稿摘要与确定性执行台账矛盾：对话历史中确实存在下列已执行调用。\n"
            "请重写摘要，必须涵盖台账中的执行事实及其数值结论，"
            "不得声称历史未包含数据加载结果或执行过程。\n\n"
            "确定性执行台账：\n"
            + "\n".join(f"- {entry}" for entry in ledger)
            + "\n\n原始对话（可能截断）：\n"
            + conv_text
        )
        try:
            retry = client.chat(
                messages=[{"role": "user", "content": correction_prompt}],
                system="你是数据分析对话摘要专家。压缩对话时保留所有数值结论、分析方法和数据引用，去除闲聊和重复内容。用结构化列表输出。",
            )
            if _summary_acknowledges_execution(retry.text or "", ledger):
                summary_text = retry.text
        except Exception as exc:
            logger.warning("Compaction summary revision failed", extra={
                "extra_data": {"session_id": session_id, "error": str(exc)},
            })
        if not _summary_acknowledges_execution(summary_text, ledger):
            summary_text = (
                "## 数据分析对话历史结构化摘要（确定性兜底）\n"
                "> 摘要模型未能保留执行事实；以下为宿主确定性记录的执行台账。\n"
                + "\n".join(f"- 已执行 {entry}" for entry in ledger[:30])
            )

    summary = (
        summary_text
        + _execution_ledger_block(ledger)
        + _preserved_identity_and_obligations(early)
    )

    if focus:
        summary += f"\n\nFocus to preserve: {focus}"

    state.has_compacted = True
    state.last_summary = summary

    logger.info("History compacted", extra={"extra_data": {
        "early_messages": len(early),
        "recent_messages": len(recent),
        "summary_length": len(summary),
    }})

    return [
        {"role": "user", "content": (
            f"[Context compressed at turn boundary]\n{summary}\n\n"
            "[Instruction: This is a compressed summary of earlier conversation. "
            "Do NOT re-acknowledge or re-summarize this context. "
            "Continue the conversation naturally from the recent messages below.]"
        )},
        {"role": "assistant", "content": "好的，继续。"},
    ] + recent


def validate_tool_message_sequence(messages: list[dict]) -> list[str]:
    """P08-04: Provider 投递前的工具消息成对校验（纯函数）。

    不变量：每条 role=tool 必须有 tool_call_id，且对应此前未闭合的
    assistant.tool_calls 条目；每个调用至多一个结果；assistant 的
    tool_calls 必须全部有结果。返回违规描述列表（空＝合法）。
    """
    violations: list[str] = []
    # Tool-call IDs are scoped to one open assistant tool-call block.  A
    # scripted transport (and a recovered legacy transcript) may reuse an ID
    # in a later, already-complete round.  That is not an orphan or a duplicate
    # result; only an ID that is still open may not be repeated.
    open_calls: set[str] = set()
    for index, message in enumerate(messages):
        role = message.get("role")
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            if open_calls:
                unresolved = ", ".join(sorted(open_calls))
                violations.append(
                    f"message[{index}]: assistant tool_calls begin before prior results ({unresolved})"
                )
            block_ids: set[str] = set()
            for call in message["tool_calls"]:
                call_id = str((call or {}).get("id") or "")
                if not call_id:
                    violations.append(f"message[{index}]: assistant tool_call without id")
                    continue
                if call_id in block_ids or call_id in open_calls:
                    violations.append(f"message[{index}]: duplicate tool_call id {call_id}")
                block_ids.add(call_id)
                open_calls.add(call_id)
        elif role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "")
            if not tool_call_id:
                violations.append(f"message[{index}]: tool message without tool_call_id")
                continue
            if tool_call_id not in open_calls:
                violations.append(
                    f"message[{index}]: orphan tool result {tool_call_id} without a preceding tool_call"
                )
                continue
            open_calls.discard(tool_call_id)
    for call_id in sorted(open_calls):
        violations.append(f"assistant tool_call {call_id} has no tool result")
    return violations


def drop_orphan_tool_messages(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """P08-04: 从 Provider 投递副本中剔除不可配对的 tool 消息。

    原始历史不修改（审计保留）；被剔除的 id 以警告形式返回供日志。
    仅处理孤立结果；缺失结果由 loop 既有的 _repair_broken_tool_sequence
    在轮开始时补齐，此处不伪造。
    """
    # Pair in sequence rather than collecting every ID globally.  Otherwise an
    # orphan result could be retained merely because a later, unrelated round
    # happens to reuse the same call ID.
    open_calls: set[str] = set()
    dropped: list[str] = []
    provider_copy: list[dict] = []
    for message in messages:
        if message.get("role") == "assistant" and isinstance(message.get("tool_calls"), list):
            provider_copy.append(message)
            for call in message["tool_calls"]:
                call_id = str((call or {}).get("id") or "")
                if call_id:
                    open_calls.add(call_id)
            continue
        if message.get("role") == "tool":
            tool_call_id = str(message.get("tool_call_id") or "")
            if not tool_call_id or tool_call_id not in open_calls:
                dropped.append(tool_call_id or "<missing-id>")
                continue
            open_calls.discard(tool_call_id)
        provider_copy.append(message)
    return provider_copy, dropped
