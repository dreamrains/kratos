"""P08-02: an evidenced boundary conclusion must finalize normally.

M02 repro through the real streaming loop: D7 descriptive evidence, one
run_python result, D30 beyond the observed range, and a final answer that
publishes only D7 plus the missing-evidence boundary. The fallback-resolution
guard must block further exploration but never trap the turn; an unbound D30
value stays rejected (S02).
"""

import csv
import json
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


def _run_boundary_turn(final_text, monkeypatch, substantive="run_python"):
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
    from data_agent.agent.intent import TurnIntent
    request="请计算并解释 D7 留存；判断当前数据是否可以预测 D30。若不能，请明确说明缺失证据与下一步。"
    intent=TurnIntent(intent_type="directed_analysis",clarity="clear",data_state="data_loaded",analysis_stage="execute",recommended_action="run_analysis",execution_readiness="ready",reason="frozen fixture",ambiguities=[],requested_outputs=[
        {"kind":"result","exact_span":"计算并解释 D7 留存",'business_scope':{'datasets': ['ret7'], 'quantity': 'value'}},
        {"kind":"result","exact_span":"预测 D30",'business_scope':{'datasets': ['ret7'], 'metrics': ['retention_rate']}},
        {"kind":"conditional_action","exact_span":"下一步",'business_scope':{'datasets': ['ret7'], 'quantity': 'value'}}])
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",lambda *a,**k:intent)
    cursor = {"index": 0}

    class ScriptedClient:
        def stream_chat_structured(self, messages, tools=None, system=None):
            index = cursor["index"]
            cursor["index"] += 1
            if index==1:
                state=loop.context.analysis_state
                factual=[r for r in state.answer_requirements if r["semantic_kind"]=="result"]
                deliveries=[{"requirement_id":r["id"],"kind":("forecast" if r["original_text"]=="预测 D30" else "measurement" if substantive=="run_python" else "series"),"label":r["original_text"],"scope":dict(r["business_scope"])} for r in factual]
                plan={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":request,"method_plan":[{"step_id":"bounded","goal":"Current D7 and forecast boundary","dataset_inputs":["ret7"],"combination_mode":"independent","expected_output":"Original observations and explicit unknown forecast","evidence_requirements":["actual receipt"],"required_deliveries":deliveries}],"visualization_strategy":[]}
                response=Response(tool_calls=[ToolCall("typed_plan","record_analysis_plan",{"plan_json":plan})])
            elif index<4:
                response=responses[index if index==0 else index-1]
            else:
                from data_agent.agent.publication.runtime import snapshot_for_turn
                host=snapshot_for_turn(loop);data=host.as_dict()
                result_req=next(r for r in data["requirements"] if r["text"]=="计算并解释 D7 留存")
                limit_req=next(r for r in data["requirements"] if r["text"]=="下一步")
                parts=[{"kind":"claim","ref":c} for c in result_req["claim_ids"]]
                if final_text==UNBOUND_FINAL: parts.append({"kind":"claim","ref":"fabricated_d30_5_percent"})
                response=Response(text=json.dumps({"schema":"answer_bindings.v2","snapshot_digest":host.digest,"sections":[
                    {"requirement_ids":[result_req["id"]],"parts":parts},
                    {"requirement_ids":[limit_req["id"]],"parts":[{"kind":"text","purpose":"conditional_action","text":"当前只观察到第7天；需补充第8至30天的真实观测与独立验证窗口。","claim_refs":result_req["claim_ids"]}]}]},ensure_ascii=False))
            yield StreamComplete(response=response)
        def chat(self,messages,**kwargs):
            payload=json.loads(messages[0]["content"])
            return Response(text=json.dumps({"schema":"publication_audit.v2","snapshot_digest":payload["snapshot_digest"],"draft_digest":payload["draft_digest"],"decisions":[{"part_id":p["part_id"],"disposition":"accept","reason":"Frozen boundary-only limitation; no invented forecast.","evidence_refs":p["requirement_ids"]+p["claim_refs"]} for p in payload["parts"]]}))

    loop = AgentLoop(client=ScriptedClient(), session_id="p08_m02_repro")
    events = list(loop.stream_turn(request))
    return loop, events


def test_m02_boundary_conclusion_finalizes_after_fallback_guard(isolated_env,monkeypatch):
    loop, events = _run_boundary_turn(BOUNDARY_FINAL,monkeypatch)

    # 观察点 3：探索性工具被 fallback-resolution 守卫阻止，但这是可恢复的
    # 工具拒绝，不得污染最终 run_state 为 failed。
    assert not any(
        e.get("type") == "error" and "Fallback Python result" in str(e.get("message", ""))
        for e in events
    )
    blocked_results = [
        e for e in events
        if e.get("type") == "tool_result"
        and "Fallback Python result" in str((e.get("web") or {}).get("error", ""))
    ]
    assert blocked_results
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
    assert final_deltas and "0.2296" in final_deltas[-1]["text"]
    assert "第8至30天" in final_deltas[-1]["text"]
    assert "10%" not in final_deltas[-1]["text"]
    turn_state = loop.context.turn_state
    assert turn_state is not None
    assert turn_state.pending_fallback_resolution is False


def test_m02_unbound_d30_value_still_rejected(isolated_env,monkeypatch):
    # 宿主可判范围来自 curve_fitting 的观测元数据（run_python 无范围元数据）
    loop, events = _run_boundary_turn(UNBOUND_FINAL,monkeypatch,substantive="curve_fitting")

    # S02 / R2：模型越界值不得发布，当前回执的独立观测仍可由宿主交付。
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    saved=load_session(loop.session_id)
    answer=read_answer(loop.session_id,saved["messages"][-1]["answer_ref"])
    published="".join(e["text"] for e in events if e.get("type")=="text_delta")
    assert published==answer["body"] and "大约是 5%" not in published
    assert "0.2296" in published and "预测 D30" in published
    assert any(issue["code"]=="unknown_claim_ref" for issue in answer["issues"])
    forecast_req=next(r["id"] for r in answer["source_snapshot"]["requirements"] if r["text"]=="预测 D30")
    assert next(o["status"] for o in answer["requirement_outcomes"] if o["requirement_id"]==forecast_req)=="not_computed"  # No forecast was executed; a curve is not a prediction.
    assert not [e for e in events if e.get("type")=="error"]
