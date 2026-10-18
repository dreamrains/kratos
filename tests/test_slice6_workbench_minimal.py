import json
from tests.test_trusted_publication_semantics import engine

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view
from data_agent.web.app import create_app


def _verified_state(engine,count=1):
    """Declare one/eight actual observations before execution;keep the whole host snapshot."""
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    quantities=['rows','missing_count','missing_pct','unique_values','sum','mean','std','min'][:count]
    specs=[{'kind':'measurement','scope':dict(datasets=['orders'],quantity=q,**({'metrics':['amount']} if q!='rows' else {}))} for q in quantities]
    request(loop,"当前观测事实",specs)
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    assert len(snapshot.as_dict()["requirements"][0]["claim_ids"])==count
    body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    return loop.context.analysis_state


def test_workbench_exposes_only_current_verified_conclusions(engine):
    state=_verified_state(engine)
    workbench=build_trust_view(state)["workbench"]
    assert {"verified_conclusions","verified_total","pending_findings"} <= set(workbench)
    assert workbench["verified_total"]==1 and workbench["verified_conclusions"][0]["claim"]=="记录数"
    assert workbench["verified_conclusions"][0]["confidence"]=="host_verified"


def test_stale_verification_never_projects_a_conclusion(engine):
    import pandas as pd
    state=_verified_state(engine)
    engine[0].context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    workbench=build_trust_view(state)["workbench"]
    assert workbench["verified_conclusions"]==[] and workbench["verified_total"]==0
    assert workbench["pending_findings"][0]["status"]=="stale"


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


def _multi_verified_state(engine,count=8):
    return _verified_state(engine,count)


def _hypothesis_state(engine):
    from data_agent.agent.hypotheses import persist_hypothesis_set
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    request(loop,"当前描述假设",{'kind': 'hypothesis', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'hypothesis_ids': ['h1']}})
    request(loop,"需要区分订单量因果影响",{'kind': 'hypothesis', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'hypothesis_ids': ['h2']}})
    request(loop,"保留当前 amount 趋势原测量",{'kind': 'table', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'parameters': {'time_series_date_col':'day','time_series_value_col':'amount','time_series_output':'trend'}}})
    rid,_=execute(loop,"analyze_time_series",{"name":"orders","date_col":"day","value_col":"amount"})
    state=loop.context.analysis_state;receipt=state.tool_receipts[-1]
    plan_id=state.analysis_plan["id"]
    hypotheses=[{"id":hid,"claim":title,"claim_type":kind,"status":"inconclusive","verification_level":"verifiable","decision_rule":{"predicate":"changed","metrics":["amount"]}} for hid,title,kind in [("h1","amount changes","descriptive"),("h2","orders cause amount changes","causal")]]
    state.hypothesis_sets=[persist_hypothesis_set(loop.session_id,{"id":"hs1","plan_id":plan_id,"dataset":"orders","hypotheses":hypotheses})]
    state.evidence_records=[{"id":"ev1","plan_id":plan_id,"dataset":"orders","tool_receipt_ids":[rid],"result_bindings":[{"receipt_id":rid,"result_sha256":receipt["structured_result_sha256"],"data_identities":receipt["data_identities"]}]}]
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    return state


def test_u01_eight_verified_conclusions_show_total_with_expansion_data(engine):
    workbench=build_trust_view(_multi_verified_state(engine,8))["workbench"]
    assert workbench["verified_total"]==8 and len(workbench["verified_conclusions"])==8
    assert len({c["id"] for c in workbench["verified_conclusions"]})==8
    # 默认呈现与展开由前端完成；投影必须携带完整集合与真实总数


def test_u02_pending_findings_are_separate_from_verified(engine):
    workbench=build_trust_view(_hypothesis_state(engine))["workbench"]
    assert workbench["verified_conclusions"] and workbench["pending_findings"]
    assert not ({c["id"] for c in workbench["verified_conclusions"]}&{c["id"] for c in workbench["pending_findings"]})
    assert all(p["status"]=="evidence_insufficient" for p in workbench["pending_findings"])


def test_u03_pending_findings_carry_status_text_basis_gap_and_next_step(engine):
    pending=build_trust_view(_hypothesis_state(engine))["workbench"]["pending_findings"]
    causal=next(p for p in pending if p["claim"]=="需要区分订单量因果影响")
    assert causal["status_label"]=="证据不足" and "候选解释：orders cause amount changes" in causal["gap"] and "未决" in causal["gap"]
    assert causal["basis"] and causal["next_step"]
    assert "artifact_path" not in causal and "plan_id" not in causal


def test_u03_supported_hypothesis_not_projected_as_pending(engine):
    workbench=build_trust_view(_hypothesis_state(engine))["workbench"]
    assert any(c["claim"]=="候选解释：amount changes 的当前关系" for c in workbench["verified_conclusions"])
    assert all(p["claim"]!="当前描述假设" for p in workbench["pending_findings"])


def test_u04_stale_fingerprint_hides_verified_and_upgrades_nowhere(engine):
    import pandas as pd
    state=_hypothesis_state(engine)
    engine[0].context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    workbench=build_trust_view(state)["workbench"]
    assert workbench["verified_conclusions"]==[] and workbench["verified_total"]==0
    assert {p["status"] for p in workbench["pending_findings"]} <= {"stale","evidence_insufficient"}
    assert any(p["status"]=="stale" and p["claim"]=="候选解释：amount changes 的当前关系" for p in workbench["pending_findings"])


def test_u02_stale_hypothesis_shows_as_expired_history_not_verified(engine):
    from pathlib import Path
    state=_hypothesis_state(engine)
    Path(state.hypothesis_sets[0]["artifact_path"]).write_text("{}",encoding="utf-8")
    workbench=build_trust_view(state)["workbench"]
    assert workbench["verified_conclusions"] # Independent source measurements remain.
    stale=next(p for p in workbench["pending_findings"] if p["claim"]=="候选解释：amount changes 的当前关系")
    assert stale["status"]=="stale" and "失效" in stale["status_label"]


def test_named_version_replacement_hides_old_verified_and_marks_hypothesis_stale(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    state=_hypothesis_state(engine);loop,_=engine
    old_ids={c["id"] for c in build_trust_view(state)["workbench"]["verified_conclusions"]}
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    request(loop,"当前新版 amount 合计",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    workbench=build_trust_view(state)["workbench"]
    assert workbench["verified_conclusions"] and not old_ids&{c["id"] for c in workbench["verified_conclusions"]}
    assert any("99" in c["summary"] for c in workbench["verified_conclusions"])
    assert any(p["status"]=="stale" for p in workbench["pending_findings"])


import pytest

@pytest.mark.parametrize("entry", ["projection", "session_api"])
def test_s3_pending_basis_is_readable_evidence_instead_of_an_opaque_answer_id(engine, entry):
    import os
    from pathlib import Path
    state = _hypothesis_state(engine)
    if entry == "projection":
        view = build_trust_view(state)
    else:
        with create_app().test_client() as http:
            response = http.get("/api/sessions/" + state.session_id + "/trust")
            assert response.status_code == 200
            view = response.get_json()
    pending = next(p for p in view["workbench"]["pending_findings"] if p["claim"] == "需要区分订单量因果影响")
    opaque = {r["answer_id"] for r in state.accepted_answers}
    out = Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE", str(engine[1].sessions_resolved / "evidence")))
    out.mkdir(parents=True, exist_ok=True)
    (out / ("pending_basis_" + entry + ".json")).write_text(json.dumps({"view":view,"accepted_answer_ids":sorted(opaque),"provider_calls":0},ensure_ascii=False,indent=2),encoding="utf-8")
    assert pending["status_label"] == "证据不足"
    assert pending["basis"] not in opaque, "The displayed basis must explain evidence or its absence; an unlinked internal answer ID supplies neither."


@pytest.mark.parametrize("fault", ["none", "reject", "unassessed", "other_requirement", "changed_version", "receipt_tamper", "unrelated_version", "old_untyped", "answer_tamper"])
def test_s4_guidance_exact_source_owner_and_review_survives_save_without_prose_inference(engine, fault):
    from copy import deepcopy
    from types import SimpleNamespace
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.agent.publication.contracts import encode, AcceptedAnswer
    from data_agent.agent.workbench_view import build_workbench_view
    from tests.test_trusted_publication_runtime import request
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_pipeline import accept_all
    from pathlib import Path
    loop, cfg = engine
    if fault == "unrelated_version":
        import pandas as pd
        loop.context.workspace.add("other", pd.DataFrame({"amount":[3]}))
        request(loop, "独立其他来源合计", {"kind":"measurement", "scope":{"datasets":["other"], "metrics":["amount"], "quantity":"sum"}})
        execute(loop, "describe_dataset", {"name":"other"})
    request(loop, "当前完整用户ARPU", {"kind":"measurement", "scope":{"datasets":["orders"], "metrics":["arpu"], "quantity":"value"}})
    request(loop, "另一个独立窗口判断", kind="gap")
    request(loop, "当前支付额", {"kind":"measurement", "scope":{"datasets":["orders"], "metrics":["amount"], "quantity":"sum"}})
    execute(loop, "describe_dataset", {"name":"orders"})
    snap = snapshot_for_turn(loop);host = snap.as_dict()
    target = next(q for q in host["requirements"] if q["text"] == "当前完整用户ARPU")
    other = next(q for q in host["requirements"] if q["text"] == "另一个独立窗口判断")
    assert target["gap"] and target["gap"]["status"] == "not_computed"
    total = next(q for q in host["requirements"] if q["text"] == "当前支付额")
    limitation = "同范围全体有效用户分母未提供，付费记录数不能替代该分母。"
    action = "补充同范围全体有效用户分母，确认口径后再重算ARPU。"
    sections = []
    for q in host["requirements"]:
        parts = [{"kind":"claim", "ref":cid} for cid in q["claim_ids"]]
        if q["id"] == (other["id"] if fault == "other_requirement" else target["id"]):
            parts += [{"kind":"text", "purpose":purpose, "text":text,
                       "claim_refs":total["claim_ids"] if q["id"] == target["id"] else []}
                for purpose,text in [("limitation",limitation),("conditional_action",action)]]
        sections.append({"requirement_ids":[q["id"]], "parts":parts})
    requests = []
    def review(messages, **kwargs):
        request_body = json.loads(messages[0]["content"]);requests.append(request_body)
        result = accept_all(request_body)
        if fault in {"reject", "unassessed"}:
            for row in result["decisions"]:row["disposition"] = fault
        return SimpleNamespace(text=encode(result))
    loop.client = SimpleNamespace(chat=review)
    raw = encode({"schema":"answer_bindings.v2", "snapshot_digest":snap.digest, "sections":sections})
    body,error = publish(loop,raw);assert error is None and len(requests) == 1
    if fault == "old_untyped":
        historical = deepcopy(loop._accepted_answer);historical.pop("answer_id")
        for trace in historical["render_trace"]:
            for key in ("purpose", "claim_refs", "semantic_reviewed"):trace.pop(key,None)
        loop._accepted_answer = AcceptedAnswer.create(historical).as_dict()
    assert commit(loop, {"role":"assistant"}, body) is None
    state = loop.context.analysis_state;ref = state.accepted_answers[-1]
    saved_bytes = (cfg.sessions_resolved/loop.session_id/ref["path"]).read_bytes()
    if fault == "changed_version":
        import pandas as pd
        loop.context.workspace.add("orders", pd.DataFrame({"amount":[999]}))
    if fault == "unrelated_version":
        import pandas as pd
        loop.context.workspace.add("other", pd.DataFrame({"amount":[9]}))
    if fault == "receipt_tamper":
        detail = state.tool_receipts[-1]["detail_ref"]
        (cfg.sessions_resolved/loop.session_id/detail["path"]).write_text("{}",encoding="utf-8")
    if fault == "answer_tamper":
        (cfg.sessions_resolved/loop.session_id/ref["path"]).write_bytes(saved_bytes+b" ")
    workbench = build_workbench_view(state)
    if fault == "answer_tamper":
        assert not any(action in p["next_step"] for p in workbench["pending_findings"])
        assert any(p["status"] == "unassessed" for p in workbench["pending_findings"])
        return
    pending = next(p for p in workbench["pending_findings"] if p["id"] == target["id"])
    assert pending["status"] == "not_computed"
    if fault in {"none", "unrelated_version"}:
        assert pending["gap_explanation"] == limitation and pending["next_step"] == action
        assert pending["next_step_status"] == "reviewed"
        assert len(pending["guidance_refs"]) == 2
        assert all(g["answer_id"] == ref["answer_id"] and g["requirement_id"] == target["id"] for g in pending["guidance_refs"])
        original = read_answer(loop.session_id,ref)
        assert all(original["body"][g["start"]:g["end"]] == g["text"] for g in pending["guidance_refs"])
        with create_app().test_client() as http:
            projected = http.get('/api/sessions/'+loop.session_id+'/trust').get_json()["workbench"]
        assert next(p for p in projected["pending_findings"] if p["id"] == target["id"])["next_step"] == action
    else:
        assert action not in pending["next_step"] and pending["next_step_status"] == "unassessed"
        assert not pending["gap_explanation"]
    assert (cfg.sessions_resolved/loop.session_id/ref["path"]).read_bytes() == saved_bytes
