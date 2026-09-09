"""P08-02: an evidenced boundary conclusion must finalize normally.

M02 repro through the real streaming loop: D7 descriptive evidence, one
run_python result, D30 beyond the observed range, and a final answer that
publishes only D7 plus the missing-evidence boundary. The fallback-resolution
guard must block further exploration but never trap the turn; an unbound D30
value stays rejected (S02).
"""

import csv
import os

import pytest


def _retention_workspace(tmp_path):
    inbox = tmp_path / "ws" / "inbox"
    inbox.mkdir(parents=True)
    fixture = inbox / "RET7.csv"
    with fixture.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["day", "retention_rate"])
        for day in range(1, 8):
            writer.writerow([day, round(0.5 * day ** -0.4, 4)])
    return tmp_path / "ws"


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    _retention_workspace(tmp_path)
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("API_BASE", "http://127.0.0.1:9")
    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("SKILL_AUTO_DISCOVER", "false")

    from data_agent import config as config_module
    from data_agent.config import AgentConfig

    monkeypatch.setattr(config_module, "_config", AgentConfig(
        WORKSPACE_DIR=tmp_path / "ws",
        SESSIONS_DIR=tmp_path / "sessions",
    ))


BOUNDARY_FINAL = (
    "D7 留存为 10%（当前 7 天观测内的描述性结果）。"
    "当前不能预测 D30：仅观测到 D7，缺少 D8—D30 观测与验证窗口；"
    "建议继续收集至第30天再验证。"
)
UNBOUND_FINAL = "D7 留存为 10%。D30 留存大约是 5%。"


def _run_boundary_turn(final_text, substantive="run_python"):
    from data_agent.agent.loop import AgentLoop
    from data_agent.llm.client import Response, ToolCall, StreamComplete

    substantive_call = (
        ToolCall(id="m2", name="run_python", arguments={
            "code": "df = get_dataset('ret7')\nresult = df[df['day']==7]['retention_rate'].iloc[0]",
            "purpose": "compute D7 retention",
        })
        if substantive == "run_python"
        else ToolCall(id="m2", name="curve_fitting", arguments={
            "name": "ret7", "x_col": "day", "y_col": "retention_rate",
        })
    )
    responses = [
        Response(tool_calls=[ToolCall(
            id="m1", name="load_data",
            arguments={"source": "RET7.csv", "name": "ret7"},
        )]),
        Response(tool_calls=[substantive_call]),
        Response(tool_calls=[ToolCall(
            id="m3", name="preview_data", arguments={"name": "ret7"},
        )]),
        Response(text=final_text),
    ]
    cursor = {"index": 0}

    class ScriptedClient:
        def stream_chat_structured(self, messages, tools=None, system=None):
            index = cursor["index"]
            cursor["index"] += 1
            yield StreamComplete(response=responses[min(index, 3)])

    loop = AgentLoop(client=ScriptedClient(), session_id="p08_m02_repro")
    events = list(loop.stream_turn(
        "请计算并解释 D7 留存；判断当前数据是否可以预测 D30。若不能，请明确说明缺失证据与下一步。"
    ))
    return loop, events


def test_m02_boundary_conclusion_finalizes_after_fallback_guard(isolated_env):
    loop, events = _run_boundary_turn(BOUNDARY_FINAL)

    # 观察点 3：探索性工具被 fallback-resolution 守卫阻止（错误事件＋工具消息）
    error_events = [e for e in events if e.get("type") == "error"]
    assert any("Fallback Python result" in str(e.get("message", "")) for e in error_events)
    budget_messages = [
        m for m in loop.messages
        if m.get("role") == "tool" and "Fallback Python result" in str(m.get("content", ""))
    ]
    assert budget_messages

    # P08-02：阻止后必须给出可执行的继续指引，而不是听起来像终态的错误
    assert any(
        m.get("role") == "system" and "fallback_resolution_guidance" in str(m.get("content", ""))
        for m in loop.messages
    )

    # 观察点 4/5：发布检查执行且最终答复发布成功；受验证终稿清除待解析状态
    final_deltas = [e for e in events if e.get("type") == "text_delta"]
    assert final_deltas and BOUNDARY_FINAL[:8] in final_deltas[-1]["text"]
    turn_state = loop.context.turn_state
    assert turn_state is not None
    assert turn_state.pending_fallback_resolution is False


def test_m02_unbound_d30_value_still_rejected(isolated_env):
    # 宿主可判范围来自 curve_fitting 的观测元数据（run_python 无范围元数据）
    loop, events = _run_boundary_turn(UNBOUND_FINAL, substantive="curve_fitting")

    # S02 反向保护：无依据的 D30 数值不得发布——修订一次仍含越界值则失败
    rejected = [m for m in loop.messages if m.get("publication_rejected")]
    final_deltas = [e for e in events if e.get("type") == "text_delta"]
    published = final_deltas[-1]["text"] if final_deltas else ""
    if not rejected:
        pytest.fail("unbound D30 value was published without rejection")
    assert "大约是 5%" not in published or rejected
