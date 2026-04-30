"""上下文压缩管理器。

参考 Claude Code 的 compact 策略，针对数据分析场景调优：
1. 大工具输出持久化到磁盘，用预览标记替代
2. 旧工具结果微压缩为占位符（先持久化完整内容）
3. 超阈值时 LLM 摘要早期对话（先保存 transcript）
4. compact 作为 LLM 可调用工具，支持主动压缩
"""

from __future__ import annotations

import json
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


def persist_large_output(session_id: str, tool_call_id: str, content: str) -> str:
    """大工具输出持久化到磁盘，返回预览标记。"""
    if len(content) <= PERSIST_THRESHOLD:
        return content

    out_dir = _session_tool_outputs_dir(session_id)
    safe_id = tool_call_id.replace("/", "_").replace("\\", "_")
    stored_path = out_dir / f"{safe_id}.txt"

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


def micro_compact(session_id: str, messages: list[dict]) -> None:
    """微压缩：旧工具结果先持久化，再替换为占位符。保留最近 KEEP_RECENT 个。"""
    tool_blocks = _collect_tool_result_blocks(messages)
    if len(tool_blocks) <= KEEP_RECENT:
        return

    for _, msg in tool_blocks[:-KEEP_RECENT]:
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) <= 120:
            continue

        # 先持久化完整内容
        tool_call_id = msg.get("tool_call_id", f"legacy_{id(msg)}")
        persisted = persist_large_output(session_id, tool_call_id, content)

        # 如果内容确实被持久化（超出阈值），替换为简短占位符
        if persisted != content:
            msg["content"] = (
                f"[Earlier tool result for {tool_call_id} compacted. "
                f"Full output saved to tool_outputs/{tool_call_id.replace('/', '_').replace(chr(92), '_')}.txt]\n"
                f"Preview: {content[:200]}..."
            )
        else:
            # 内容不大但超 120 字符，直接截断
            msg["content"] = content[:200] + "\n...[truncated]"


def write_transcript(session_id: str, messages: list[dict]) -> Path:
    """保存完整对话记录到 transcript 文件。"""
    out_dir = _session_transcripts_dir(session_id)
    path = out_dir / f"transcript_{int(time.time())}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")
    return path


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

    summary = resp.text or ""

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
