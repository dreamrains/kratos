import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view
from data_agent.agent.trust_workflow_runtime import _evidence_fingerprint
from data_agent.web.app import create_app


def _verified_state():
    state = AnalysisSessionState(session_id="slice6", data_state="data_loaded")
    state.evidence_records = [{
        "id": "ev_1", "claim": "收入下降", "result_summary": "较前期下降 10%",
        "confidence": "high", "dataset": "orders",
    }]
    state.verification_reports = [{"passed_evidence_ids": ["ev_1"]}]
    state.verification_reports[0]["evidence_fingerprint"] = _evidence_fingerprint(state, state.evidence_records)
    return state


def test_workbench_exposes_only_current_verified_conclusions():
    view = build_trust_view(_verified_state())

    # P6/U01—U03 契约更新：原精确集合断言 {"verified_conclusions"} 扩展为
    # 最简集合＋渐进展示字段（真实总数、完整集合、待验证发现独立分类）。
    # 防历史升级（stale 指纹隐藏）与会话隔离断言保留不变。
    assert {
        "verified_conclusions", "verified_total", "pending_findings",
    } <= set(view["workbench"])
    assert view["workbench"]["verified_conclusions"][0]["claim"] == "收入下降"


def test_stale_verification_never_projects_a_conclusion():
    state = _verified_state()
    state.evidence_records[0]["result_summary"] = "较前期下降 20%"

    assert build_trust_view(state)["workbench"]["verified_conclusions"] == []


def test_current_panel_has_no_removed_workbench_surfaces_and_keeps_output_export():
    client = create_app().test_client()
    html = client.get("/").get_data(as_text=True)
    js = client.get("/static/js/app.js").get_data(as_text=True)

    assert 'data-testid="workbench-verified-conclusions"' in html
    for removed in ("action-board", "workbench-scope", "workbench-full-answer", "workbench-breakdown", "multifile-data-understanding", "multifile-relationships"):
        assert removed not in html
    assert "exportConversation('html')" in html
    assert "exportConversation('markdown')" in html
    assert "sessionArtifacts" in html
    assert "verifiedConclusions()" in js
    for removed in (
        "actionBoard", "fullAnswer", "workbenchScope", "workbenchConfirmation",
        "multifileWorkbench", "multifileDataUnderstanding", "multifileRelationships",
    ):
        assert removed not in js


def test_workbench_scope_label_uses_exact_session_id_without_summary_or_project_substitution():
    client = create_app().test_client()
    html = client.get("/").get_data(as_text=True)

    assert "会话：" in html
    assert "('会话：' + currentSessionId)" in html
    assert "('会话：' + (sessionTitle || currentSessionId))" not in html
    assert "activeProjectName ? ('项目：'" not in html


# ── P6 (D04): progressive workbench projection (U01–U04) ──


def _multi_verified_state(count: int = 8):
    state = AnalysisSessionState(session_id=f"slice6_u{count}", data_state="data_loaded")
    state.evidence_records = [
        {
            "id": f"ev_{i}",
            "claim": f"已验证结论 {i}",
            "result_summary": f"summary {i}",
            "confidence": "high" if i % 2 == 0 else "medium",
            "dataset": "orders",
        }
        for i in range(1, count + 1)
    ]
    report = {
        "passed_evidence_ids": [f"ev_{i}" for i in range(1, count + 1)],
    }
    report["evidence_fingerprint"] = _evidence_fingerprint(state, state.evidence_records)
    state.verification_reports = [report]
    return state


def _hypothesis_state():
    state = _multi_verified_state(count=2)
    state.hypothesis_sets = [{
        "id": "hyps_orders_trend",
        "dataset": "orders",
        "route": "trend",
        "count": 3,
        "hypotheses": [
            {
                "id": "hyps_orders_trend_h1",
                "claim": "收入呈上升趋势",
                "status": "supported",
                "claim_type": "descriptive",
                "related_evidence_ids": ["ev_1"],
                "supporting_evidence_ids": ["ev_1"],
                "conflicting_evidence_ids": [],
                "evidence_requirements": [{"kind": "metric", "field": "revenue", "required": True}],
            },
            {
                "id": "hyps_orders_trend_h2",
                "claim": "收入变化由订单量驱动",
                "status": "inconclusive",
                "claim_type": "causal",
                "related_evidence_ids": [],
                "supporting_evidence_ids": [],
                "conflicting_evidence_ids": [],
                "evidence_requirements": [{"kind": "metric", "field": "orders", "required": True}],
            },
            {
                "id": "hyps_orders_trend_h3",
                "claim": "波动属于正常基线变异",
                "status": "proposed",
                "claim_type": "statistical",
                "related_evidence_ids": [],
                "supporting_evidence_ids": [],
                "conflicting_evidence_ids": [],
                "evidence_requirements": [{"kind": "metric", "field": "revenue", "required": True}],
            },
        ],
    }]
    return state


def test_u01_eight_verified_conclusions_show_total_with_expansion_data():
    view = build_trust_view(_multi_verified_state(8))
    workbench = view["workbench"]

    assert workbench["verified_total"] == 8
    assert len(workbench["verified_conclusions"]) == 8
    # 默认呈现与展开由前端完成；投影必须携带完整集合与真实总数


def test_u02_pending_findings_are_separate_from_verified():
    view = build_trust_view(_hypothesis_state())
    workbench = view["workbench"]

    verified_ids = {item["id"] for item in workbench["verified_conclusions"]}
    pending = workbench["pending_findings"]
    assert pending
    pending_ids = {item["id"] for item in pending}
    assert not (verified_ids & pending_ids)
    assert all(item["status"] in {"proposed", "inconclusive", "contested"} for item in pending)


def test_u03_pending_findings_carry_status_text_basis_gap_and_next_step():
    view = build_trust_view(_hypothesis_state())
    pending = view["workbench"]["pending_findings"]

    by_id = {item["id"]: item for item in pending}
    causal = by_id["hyps_orders_trend_h2"]
    assert causal["status_label"]
    assert "未决" in causal["status_label"]
    assert causal["next_step"]
    assert "orders" in (causal.get("gap") or "") or "区分" in causal["next_step"]
    # 不展示原始内部 JSON
    assert "artifact_path" not in causal
    assert "plan_id" not in causal


def test_u03_supported_hypothesis_not_projected_as_pending():
    view = build_trust_view(_hypothesis_state())
    pending_ids = {item["id"] for item in view["workbench"]["pending_findings"]}

    assert "hyps_orders_trend_h1" not in pending_ids


def test_u04_stale_fingerprint_hides_verified_and_upgrades_nowhere():
    state = _hypothesis_state()
    state.evidence_records[0]["result_summary"] = "changed content invalidates fingerprint"

    workbench = build_trust_view(state)["workbench"]
    assert workbench["verified_conclusions"] == []
    assert workbench["verified_total"] == 0
    # 指纹失效后：曾经 supported 的假设不得在任何区域以当前有效状态出现；
    # 仍为未决的假设继续以未决性质展示，不升级。
    pending_ids = {item["id"] for item in workbench["pending_findings"]}
    assert "hyps_orders_trend_h1" not in pending_ids
    assert all(item["status"] in {"proposed", "inconclusive", "contested"} for item in workbench["pending_findings"])
