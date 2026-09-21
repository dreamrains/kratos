"""P1-6 子项 2：压缩摘要保真。

RED 素材为 Codex 批次 M03 会话 52a61396f8e6 真实回放：compact_context 后
摘要声称"当前对话历史中仅包含用户提出的分析请求，未包含数据加载结果、
分析执行过程、数值结论"，而该会话已加载 6 个数据集并执行多步对比——
截断喂给摘要模型的 JSON 与宽松摘要共同造成了这条失实元主张。

治理分层：摘要是否写到位是开放语义——召回式检查→一次修订→确定性兜底；
执行台账（工具名/顺序/参数锚点）是封闭类事实，由宿主确定性附加，
保证"已执行"不可能被摘要写成"未执行"。
"""

from types import SimpleNamespace

from data_agent.agent.compact import CompactState, compact_history


LYING_SUMMARY = (
    "## 数据分析对话历史结构化摘要\n"
    "> 说明：当前对话历史中仅包含用户提出的分析请求，未包含数据加载结果、"
    "分析执行过程、数值结论。\n"
)

HONEST_SUMMARY = (
    "## 数据分析对话历史结构化摘要\n"
    "- 已加载 M03-source-1（2 行）与 M03-source-2（2 行）；\n"
    "- compare_periods 对比完成：合计 210 与 231，差异 +10%。\n"
)


class _ScriptedClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages=None, system=""):
        self.calls.append({"messages": messages, "system": system})
        return SimpleNamespace(text=self.replies.pop(0) if self.replies else "")


def _execution_messages() -> list[dict]:
    """含真实执行轨迹的消息序列（load×2 + compare_periods + 数值结果）。"""
    def tool_call(call_id, name, arguments):
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": arguments}}],
        }

    return [
        {"role": "user", "content": "请分别比较当前六个来源"},
        tool_call("tc_1", "load_data", '{"name": "M03-source-1.csv"}'),
        {"role": "tool", "tool_call_id": "tc_1", "content": '{"rows": 2, "columns": 3}'},
        tool_call("tc_2", "load_data", '{"name": "M03-source-2.csv"}'),
        {"role": "tool", "tool_call_id": "tc_2", "content": '{"rows": 2, "columns": 3}'},
        tool_call("tc_3", "compare_periods", '{"period_a": "2026-09-01~2026-09-02", "period_b": "2026-09-08~2026-09-09"}'),
        {"role": "tool", "tool_call_id": "tc_3", "content": '{"metrics": {"合计": {"period_a": 210, "period_b": 231}}}'},
        {"role": "assistant", "content": "六来源合计 210 与 231。"},
        {"role": "user", "content": "继续"},
    ] + [{"role": "user", "content": f"filler {i}"} for i in range(11)]


def _run_compact(tmp_path, monkeypatch, client):
    from data_agent.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    state = CompactState()
    result = compact_history("compaction_fidelity", client, _execution_messages(), state)
    return result, state


def _compressed_user_text(result: list[dict]) -> str:
    return next(m["content"] for m in result if m.get("role") == "user" and "Context compressed" in str(m.get("content")))


def test_execution_ledger_survives_persistently_lying_summary(tmp_path, monkeypatch):
    """两次都撒谎：确定性台账兜底，失实元主张不得进入压缩上下文。"""
    client = _ScriptedClient([LYING_SUMMARY, LYING_SUMMARY])

    result, _state = _run_compact(tmp_path, monkeypatch, client)

    text = _compressed_user_text(result)
    assert "[Deterministically preserved execution ledger" in text
    assert "load_data" in text and "compare_periods" in text
    # 失实句不得原样进入压缩上下文（兜底骨架替换了撒谎摘要）
    assert "仅包含用户提出的分析请求" not in text


def test_one_revision_recovers_execution_summary(tmp_path, monkeypatch):
    """第一次撒谎、修订后如实：采用修订稿并附台账（召回→一次修订）。"""
    client = _ScriptedClient([LYING_SUMMARY, HONEST_SUMMARY])

    result, _state = _run_compact(tmp_path, monkeypatch, client)

    text = _compressed_user_text(result)
    assert "合计 210 与 231" in text
    assert "[Deterministically preserved execution ledger" in text
    assert len(client.calls) == 2


def test_honest_summary_is_used_without_revision(tmp_path, monkeypatch):
    """首稿如实：不触发修订，摘要原样采用并附台账。"""
    client = _ScriptedClient([HONEST_SUMMARY])

    result, _state = _run_compact(tmp_path, monkeypatch, client)

    text = _compressed_user_text(result)
    assert "合计 210 与 231" in text
    assert "[Deterministically preserved execution ledger" in text
    assert len(client.calls) == 1
