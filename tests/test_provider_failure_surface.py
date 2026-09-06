"""Provider 失败必须把真实异常摘要透传到事件与用户可见错误里。

回归背景：会话中 LLM 请求失败时，用户只看到「provider_request_failed」
字样与服务控制台里 litellm 的尾部提示，真实异常类型与消息被丢弃，
导致无法定位（例如进程内配置指向失效模型或密钥时完全无从判断）。
"""

from data_agent.agent.loop import AgentLoop


class _ExplodingClient:
    def __init__(self, message: str = "connection reset by peer"):
        self.message = message

    def stream_chat_structured(self, **kwargs):
        # 与真实 LLMClient 一致的生成器语义：异常在迭代时抛出
        raise RuntimeError(self.message)
        yield  # noqa: unreachable — 保持生成器函数形态


def _loop_with_failure(session_id: str, message: str = "connection reset by peer"):
    loop = AgentLoop(client=None, session_id=session_id)
    loop.client = _ExplodingClient(message)
    return loop


def test_round_failure_event_carries_exception_summary():
    loop = _loop_with_failure("failure_surface_event", "connection reset by peer\nsecond line")

    failure = list(loop._stream_llm_round(1))[-1]

    assert failure["type"] == "_round_failure"
    assert failure["code"] == "provider_request_failed"
    assert "RuntimeError" in failure["detail"]
    assert "connection reset by peer" in failure["detail"]
    assert "\n" not in failure["detail"]  # 单行，避免撑破 UI 与日志


def test_turn_error_message_includes_provider_detail():
    loop = AgentLoop(client=None, session_id="failure_surface_message")
    loop._stream_llm_round = lambda _round_num: iter([{
        "type": "_round_failure",
        "code": "provider_request_failed",
        "detail": "AuthenticationError: invalid api key (401)",
    }])

    events = list(loop.stream_turn("分析数据"))

    error = [e for e in events if e["type"] == "error"][0]
    assert "provider_request_failed" in error["message"]
    assert "AuthenticationError: invalid api key (401)" in error["message"]


def test_detail_is_truncated_for_noisy_provider_errors():
    # litellm 异常体内嵌完整 provider 响应，不能原样进入 UI
    loop = _loop_with_failure("failure_surface_truncate", "x" * 5000)

    failure = list(loop._stream_llm_round(1))[-1]

    assert len(failure["detail"]) <= 320


def test_detail_redacts_provider_credentials(monkeypatch):
    from data_agent.agent import loop as loop_module

    class _Config:
        api_key = "configured-secret-key"

    monkeypatch.setattr(loop_module, "get_config", lambda: _Config())
    detail = loop_module._provider_failure_detail(RuntimeError(
        "Authorization: Bearer configured-secret-key; api_key=sk-testsecret123456",
    ))

    assert "configured-secret-key" not in detail
    assert "sk-testsecret123456" not in detail
    assert "[REDACTED]" in detail
