"""P4 (D03): compaction must persist before any lossy replacement (E06–E08)."""

import hashlib

from data_agent.agent.compact import micro_compact


def _tool_message(tool_call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _recent_filler(index: int) -> dict:
    return _tool_message(f"filler_{index}", "ok")


def _tail_facts_text(length: int = 714) -> str:
    header = "[insights]\n渠道对比完成\n[/insights]\n"
    filler = "背景说明数据行，用于撑起长度。\n" * 20
    tail = "[key_facts]\n尾部关键字段: 渠道D 金额999 分母12 期间2026-08\n[/key_facts]"
    text = header + filler + tail
    return text + "x" * max(0, length - len(text))


def _run_micro_compact(tmp_path, monkeypatch, messages):
    from data_agent.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    micro_compact("compact_preservation", messages)
    return tmp_path / "sessions" / "compact_preservation" / "tool_outputs"


class TestCompactPreservation:

    def test_e06_medium_output_persisted_before_replacement(self, tmp_path, monkeypatch):
        original = _tail_facts_text()
        messages = [_tool_message("tc_target", original)] + [_recent_filler(i) for i in range(8)]

        out_dir = _run_micro_compact(tmp_path, monkeypatch, messages)

        stored = [path for path in out_dir.glob("tc_target*.txt")]
        assert stored, "120–15000 字符的工具输出必须先持久化再压缩"
        content = stored[0].read_text(encoding="utf-8")
        assert content == original
        assert hashlib.sha256(content.encode("utf-8")).hexdigest() == hashlib.sha256(original.encode("utf-8")).hexdigest()
        # 尾部事实可从持久化原文恢复
        assert "渠道D 金额999" in content
        # 消息体被替换为带引用的摘要
        assert messages[0]["content"] != original
        assert "渠道D 金额999" in messages[0]["content"] or stored[0].name in messages[0]["content"] or "Compacted" in messages[0]["content"]

    def test_e07_same_id_different_content_never_silently_reused(self, tmp_path, monkeypatch):
        first = _tail_facts_text()
        second = _tail_facts_text().replace("999", "1001")
        messages_a = [_tool_message("tc_collide", first)] + [_recent_filler(i) for i in range(8)]
        out_dir = _run_micro_compact(tmp_path, monkeypatch, messages_a)

        messages_b = [_tool_message("tc_collide", second)] + [_recent_filler(i) for i in range(8)]
        micro_compact("compact_preservation", messages_b)

        stored = sorted(out_dir.glob("tc_collide*.txt"))
        assert len(stored) == 2, "同 id 不同内容必须各自落盘，不得静默复用旧文件"
        bodies = {path.read_text(encoding="utf-8") for path in stored}
        assert first in bodies and second in bodies

    def test_e07_persistence_failure_skips_lossy_replacement(self, tmp_path, monkeypatch):
        original = _tail_facts_text()
        messages = [_tool_message("tc_fail", original)] + [_recent_filler(i) for i in range(8)]
        from data_agent.config import get_config

        cfg = get_config()
        monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
        out_dir = tmp_path / "sessions" / "compact_preservation" / "tool_outputs"
        out_dir.mkdir(parents=True)

        def fail_write(self, data, encoding=None):
            raise OSError("disk full")

        monkeypatch.setattr("pathlib.Path.write_text", fail_write)
        micro_compact("compact_preservation", messages)

        assert messages[0]["content"] == original, "持久化失败时不得进行有损替换"

    def test_e08_recompacting_compacted_message_keeps_original(self, tmp_path, monkeypatch):
        original = _tail_facts_text()
        messages = [_tool_message("tc_twice", original)] + [_recent_filler(i) for i in range(8)]
        out_dir = _run_micro_compact(tmp_path, monkeypatch, messages)
        compacted = messages[0]["content"]
        stored_before = sorted(out_dir.glob("tc_twice*.txt"))
        assert stored_before

        micro_compact("compact_preservation", messages)

        assert messages[0]["content"] == compacted, "已压缩消息不得被二次摘要覆盖"
        stored_after = sorted(out_dir.glob("tc_twice*.txt"))
        assert len(stored_after) == len(stored_before)
        assert stored_after[0].read_text(encoding="utf-8") == original
