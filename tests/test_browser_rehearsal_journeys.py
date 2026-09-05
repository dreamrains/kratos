"""Offline integration preflight for the *same* transport used by browsers.

Actual upload API, AgentLoop, tools, persistence and confirmation service run;
only model transport is scripted. This is not browser or Provider evidence.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "docs/audit/2026-08-30-architecture-browser-b01-candidate.json").read_text(encoding="utf-8"))["cases"]


def events(response):
    assert response.status_code == 200, response.get_data(as_text=True)
    result = []
    for frame in response.get_data(as_text=True).split("\n\n"):
        lines = frame.splitlines()
        kind = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if kind and data:
            result.append((kind, json.loads(data)))
    return result


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
def test_all_scripted_journeys_use_real_tools_and_persist_results(case, tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.llm.client import LLMClient
    from data_agent.llm.request_policy import ONE_SHOT
    from data_agent.tools import discover_tools
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from scripts.acceptance.browser_rehearsal_server import ScriptedTransport

    cfg = get_config()
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    discover_tools()
    transport = ScriptedTransport(case["case_id"], tmp_path)
    manager = AgentManager(client_factory=lambda model_id=None: LLMClient(transport=transport, request_policy=ONE_SHOT))
    app = create_app()
    app.config.update(TESTING=True, agent_manager=manager)
    client = app.test_client()
    uploads = []
    for source in case["data"]:
        path = ROOT / source["path"]
        response = client.post("/api/upload", data={"file": (io.BytesIO(path.read_bytes()), path.name)}, content_type="multipart/form-data")
        assert response.status_code == 200
        payload = response.get_json()
        uploads.append({"upload_id": payload["upload_id"], "filename": payload["filename"]})
    sid = None
    all_events = []
    for index, prompt in enumerate(case["prompts"]):
        message = prompt + ("\n" + "\n".join("分析文件: " + u["filename"] for u in uploads) if index == 0 else "")
        response = client.post("/api/chat", json={"message": message, "session_id": sid, "uploads": uploads if index == 0 else []}, buffered=True)
        sid = response.headers.get("X-Data-Agent-Session-Id") or sid
        emitted = events(response)
        all_events.extend(emitted)
        suspended = [data for kind, data in emitted if kind == "suspended"]
        if suspended:
            assert len(suspended) == 1
            question = suspended[0]
            assert any(o.get("value") == "confirm_method" for o in question["options"]), question
            response = client.post("/api/chat/resume", json={"session_id": sid, "confirmation_id": question["confirmation_id"], "expected_version": question["version"], "idempotency_key": f"offline-{index}", "user_response": "confirm_method"}, buffered=True)
            emitted = events(response)
            all_events.extend(emitted)
        (tmp_path / "events.json").write_text(json.dumps(all_events, ensure_ascii=False, indent=2), encoding="utf-8")
        assert emitted[-1][0] == "turn_end" and emitted[-1][1]["status"] == "completed", emitted[-4:]
        trust = client.get(f"/api/sessions/{sid}/trust").get_json()
        assert trust["workbench"]["verified_conclusions"], trust
    assert all(r["status"] == "completed" for r in transport.records), transport.records
    tool_names = [d["name"] for k, d in all_events if k == "tool_call"]
    assert set(case["oracle"]["required_tools"]).issubset(tool_names)
    loop = manager.get(sid)
    assert loop.context.analysis_state.evidence_records
    for evidence in loop.context.analysis_state.evidence_records:
        assert not any("未报告统计显著性" in limit for limit in evidence.get("auto_generated_limitations", []))
    def tool_result(name):
        data = next(d for k, d in reversed(all_events) if k == "tool_call" and d["name"] == name)
        return json.loads((cfg.sessions_resolved / sid / "tool_outputs" / (data["tool_call_id"] + "_detail.json")).read_text(encoding="utf-8"))

    if case["case_id"] == "M01":
        fitted = tool_result("curve_fitting")
        best = fitted["fits"][0]
        assert best["parameters"]["a"] == pytest.approx(0.18800129)
        assert best["parameters"]["b"] == pytest.approx(-0.71667274)
        assert best["r_squared"] == pytest.approx(0.98240474)
        assert sum(p["n_excluded_zeros"] for p in fitted["points"]) == 6
    elif case["case_id"] == "M02":
        assert len(tool_result("synthesize_time_series")["source_identities"]) == 3
    elif case["case_id"] == "M03":
        import ast
        assert ast.literal_eval(tool_result("run_python")["output"]) == {"rows":1985,"parseable":1926,"missing":59,"original_dash":59}
        assert tool_result("top_n")["n"] == 15
        grouped = loop.context.workspace.get("observable_income")
        assert grouped["卖量收入_size"].sum() == 1985
        assert grouped["卖量收入_count"].sum() == 1926
        assert (grouped["卖量收入_size"] - grouped["卖量收入_count"]).sum() == 59
        charts = list((cfg.sessions_resolved / sid / "charts").glob("*.json"))
        metadata = json.loads(charts[0].read_text(encoding="utf8"))
        assert metadata["label_columns"] == ["流量主游戏", "广告主游戏", "公司"]
        assert metadata["purpose"] == "evidence" and metadata["evidence_ids"]
        assert metadata["data_identity"]["dataset"] == "observable_top15"
    elif case["case_id"] == "M04":
        result = tool_result("compare_periods")
        assert [result[p]["rows"] for p in ["period_a", "period_b"]] == [47, 24]
        assert [result[p]["day_count"] for p in ["period_a", "period_b"]] == [15, 15]
        assert result["metrics"]["售价"]["period_a"] == 1818
        assert result["metrics"]["售价"]["period_b"] == 684
    elif case["case_id"] == "M05":
        result = tool_result("ab_test")
        assert result["paired_sample_size"] == 61
        assert result["difference"]["absolute"] == pytest.approx(-1220.1311, abs=0.001)
        assert result["test"]["p_value"] == pytest.approx(0.0186, abs=1e-6)
        assert result["wilcoxon_signed_rank"]["p_value"] == pytest.approx(0.027699, abs=1e-6)
        evidence = loop.context.analysis_state.evidence_records[-1]
        assert evidence["significance"]["test"]["p_value"] == result["test"]["p_value"]
        assert evidence["statistical_detail_status"] == "complete"
    elif case["case_id"] == "M06":
        result = tool_result("cohort_analysis")
        assert {r["cohort"]: r["size"] for r in result["cohorts"]} == {"2026-02":45,"2026-03":8,"2026-04":8,"2026-05":1}
        assert loop.context.analysis_state.evidence_records[0]["sample_size"] == 71
    detail_errors = []
    for path in (cfg.sessions_resolved / sid / "tool_outputs").glob("rehearsal_*_detail.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("error"):
            detail_errors.append(data)
    if case["case_id"] == "M01":
        assert len(detail_errors) == 1 and detail_errors[0].get("error_type") == "invalid_evidence_arguments", detail_errors
    elif case["case_id"] == "M02":
        assert len(detail_errors) == 1 and detail_errors[0].get("error_code") == "scale_label_mismatch", detail_errors
    else:
        assert not detail_errors, detail_errors
    snapshot = client.get(f"/api/sessions/{sid}").get_json()
    assert snapshot["run_state"]["status"] == "completed"
    assert any(m.get("content", "").startswith("先核对当前会话的数据和计算收据。") for m in snapshot["messages"] if isinstance(m.get("content"), str))
    assert any(m["role"] == "assistant" and m.get("content") for m in snapshot["messages"])
    manager.remove(sid)
    restored = manager.get_or_create(sid)
    assert restored.context.analysis_state.evidence_records


@pytest.mark.parametrize("text,expected", [
    ("只做描述性分析，不做因果解释", False),
    ("不要把共变解释为因果", False),
    ("不解释变化原因、不做因果或窗口外推", False),
    ("do not infer causality; compare observed revenue", False),
    ("effective revenue comparison", False),
    ("不要预测，但是请做因果分析", True),
    ("不要预测；请分析实验效果", True),
    ("不是不做因果分析", True),
    ("不能排除因果关系", True),
    ("predict next month revenue", True),
])
def test_negated_risk_is_not_an_affirmative_request(text, expected):
    from data_agent.agent.question_need_detector import _is_high_risk_request
    assert _is_high_risk_request(text) is expected


def test_named_group_comparison_does_not_require_two_time_windows():
    from data_agent.agent.question_need_detector import _infer_route
    period = {"direction": "period_compare"}
    dimension = {"direction": "dimension_decomposition"}
    text = "按流量主游戏、广告主游戏和公司的组合汇总可观测收入，给出收益对比图"
    assert _infer_route(text, [period, dimension]) == dimension
    assert _infer_route(text, [period]) is None
    assert _infer_route("compare revenue", [period]) == period


def test_current_plan_evidence_projection_uses_the_same_verification_scope():
    from types import SimpleNamespace
    from data_agent.agent.trust_workflow_runtime import _evidence_fingerprint
    from data_agent.agent.workbench_view import build_workbench_view
    old = {"id":"old", "plan_id":"old-plan", "claim":"old", "confidence":"medium"}
    current = {"id":"new", "plan_id":"new-plan", "claim":"current", "confidence":"medium"}
    state = SimpleNamespace(evidence_records=[old,current], analysis_plan={"id":"new-plan"}, verification_reports=[])
    state.verification_reports.append({"passed_evidence_ids":["old","new"],"evidence_fingerprint":_evidence_fingerprint(state,[current])})
    assert [c["id"] for c in build_workbench_view(state)["verified_conclusions"]] == ["new"]
    current["claim"] = "mutated after verification"
    assert build_workbench_view(state)["verified_conclusions"] == []


def test_group_sum_distinguishes_missing_from_zero_and_retains_missing_keys(tmp_path, monkeypatch):
    import pandas as pd
    from data_agent.config import get_config
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.session.workspace import workspace
    from data_agent.tools.data_transform import transform_data
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    loop = AgentLoop(client=object(), session_id="missing-groups")
    with use_agent_context(loop.context):
        workspace.add("income", pd.DataFrame({"group":["missing","missing","zero",None], "amount":[None,None,0.0,5.0]}))
        payload = json.loads(transform_data("income", "group_aggregate", group_by=["group"], aggregations=[{"column":"amount","functions":["sum","count"]}], save_as="summary"))
        assert "error" not in payload
        actual = workspace.get("summary")
        assert len(actual) == 3
        assert actual.loc[actual["group"] == "missing", "amount_sum"].isna().all()
        assert actual.loc[actual["group"] == "zero", "amount_sum"].item() == 0
        assert actual.loc[actual["group"].isna(), "amount_sum"].item() == 5


def test_first_response_failure_is_durable_in_history_and_export(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.llm.client import LLMClient
    from data_agent.llm.request_policy import ONE_SHOT
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from scripts.acceptance.browser_rehearsal_server import ScriptedTransport
    cfg = get_config()
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    transport = ScriptedTransport("M01", tmp_path)
    app = create_app()
    app.config["agent_manager"] = AgentManager(client_factory=lambda model_id=None: LLMClient(transport=transport, request_policy=ONE_SHOT))
    client = app.test_client()
    response = client.post("/api/chat", json={"message":"REHEARSAL_FAILURE"}, buffered=True)
    emitted = events(response)
    assert emitted[-1][1]["status"] == "failed"
    notice = emitted[-1][1]["execution_notice"]
    sid = response.headers["X-Data-Agent-Session-Id"]
    snapshot = client.get(f"/api/sessions/{sid}").get_json()
    assert snapshot["messages"][-1]["content"] == notice
    assert snapshot["run_state"]["notice"] == notice
    assert transport.records[-1]["status"] == "failed"
    assert all(r["status"] != "started" for r in transport.records)
    exported = client.get(f"/api/sessions/{sid}/export?format=html")
    assert exported.status_code == 200
    files = list((cfg.sessions_resolved / sid / "reports").glob("*.html"))
    assert len(files) == 1 and "执行失败" in files[0].read_text(encoding="utf-8")
