"""P1-6 子项 4：压缩 ACK 不窃取回复身份（导出双产物恢复）。

RED 素材为双批次真实轨迹（Codex r1 M03 52a61396f8e6 / GLM r3 M03）：
compact_context 之后，合成 ACK 消息（"好的，继续。"，紧跟
"[Context compressed at turn boundary]" 用户消息）被并入回复组——
组 id 变成 ACK 的新 uuid（save_session 的 assign_reply_ids 还会把
recent 消息上的原 id 覆写成 ACK 的 id），组内容多出 ACK 前缀。
前端在压缩前收到的 turn_end 身份（reply_id=R、内容=无 ACK 的分组）
与压缩后的服务端分组双双失配，export-reply 以 unbound_reply 失败，
conversation Markdown 双产物缺失（发布回执独存）。

修复：公开投影剔除该合成 ACK——它是压缩机制的产物，不是助手陈述。
判定为封闭类：用户消息以压缩标记开头 + 相邻 assistant 内容恰为
"好的，继续。"。
"""

import json

from data_agent.config import get_config
from data_agent.session.history import save_session
from data_agent.session.public_messages import public_messages

_COMPACTED_USER = "[Context compressed at turn boundary]\n## 结构化摘要"
_FINAL_ANSWER = "## 最终结论\n12 条订单，合计 120。"
_ORIGINAL_REPLY_ID = "reply_original_group"


def _save_compacted_session(tmp_path, monkeypatch, sid):
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    # 模拟压缩后的持久化历史：recent 里的回答消息携带原组 id
    save_session([
        {"role": "user", "content": _COMPACTED_USER},
        {"role": "assistant", "content": "好的，继续。"},
        {"role": "assistant", "content": _FINAL_ANSWER, "reply_id": _ORIGINAL_REPLY_ID},
    ], sid)


def test_compaction_ack_does_not_steal_reply_identity(tmp_path, monkeypatch):
    _save_compacted_session(tmp_path, monkeypatch, "ack-export-1")
    from data_agent.tools.report import export_assistant_reply

    # 前端在压缩前收到的身份：reply_id=原组 id，内容=无 ACK 的分组
    result = export_assistant_reply(
        "ack-export-1", _FINAL_ANSWER, "markdown", reply_id=_ORIGINAL_REPLY_ID,
    )

    assert result.get("artifact_path"), result


def test_compaction_ack_is_not_projected_or_exported(tmp_path, monkeypatch):
    _save_compacted_session(tmp_path, monkeypatch, "ack-export-2")
    from data_agent.tools.report import export_assistant_reply

    projected = public_messages(
        json.loads(
            (tmp_path / "sessions" / "ack-export-2" / "conversation.json").read_text(encoding="utf-8")
        ),
        "ack-export-2",
    )
    assert all(msg.get("content") != "好的，继续。" for msg in projected)

    result = export_assistant_reply("ack-export-2", _FINAL_ANSWER, "markdown")
    assert result.get("artifact_path"), result
    text = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
    assert "好的，继续。" not in text
    assert "12 条订单，合计 120" in text


def test_genuine_ack_wording_away_from_marker_is_kept(tmp_path, monkeypatch):
    """不在压缩标记邻接位的"好的，继续。"是真实陈述，不得剔除。"""
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    save_session([
        {"role": "user", "content": "请继续"},
        {"role": "assistant", "content": "好的，继续。"},
        {"role": "assistant", "content": _FINAL_ANSWER},
    ], "ack-export-3")

    projected = public_messages(
        json.loads(
            (tmp_path / "sessions" / "ack-export-3" / "conversation.json").read_text(encoding="utf-8")
        ),
        "ack-export-3",
    )
    assert any(msg.get("content") == "好的，继续。" for msg in projected)
