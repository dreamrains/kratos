"""New publication behavior: model text cannot own host facts or coverage."""
import json
from copy import deepcopy

import pytest


IDENTITY = {"orders": {"version_id": "v1", "fingerprint": "orders-sha"}}


def requirement(rid="r1", *, claims=(), purposes=(), gap=None, withdrawn=False):
    return {"id": rid, "text": rid, "source_turn": "user-1", "claim_ids": list(claims),
            "open_purposes": list(purposes), "artifact_ids": [], "gap": gap,
            "withdrawn": withdrawn}


def claim(cid="total", value=120):
    return {"id": cid, "label": cid, "value": value, "unit": None,
            "scope": {"dataset": "orders", "population": "uploaded records", "time_scope": "2026-09-01/2026-09-12", "grain": "order"},
            "limitations": ["仅描述当前文件"],
            "basis_refs": [{"receipt_id": "tr1", "session_id": "s1", "tool_name": "describe_dataset",
                            "result_sha256": "sha256:" + "a" * 64, "data_identities": deepcopy(IDENTITY),
                            "result_path": [cid]}]}


def snapshot(*, requirements=(), claims=(), mode="analysis", uses_result_context=False,
             data_identities=None, turn="t1", artifacts=()):
    from data_agent.agent.publication.contracts import HostSnapshot
    return HostSnapshot.freeze(session_id="s1", turn_id=turn, history_revision=4,
        requirement_revision=1, mode=mode, requirements=list(requirements), claims=list(claims),
        artifacts=list(artifacts), data_identities=deepcopy(IDENTITY if data_identities is None else data_identities),
        plan_id="" if mode == "consultation" else "plan1", uses_result_context=uses_result_context)


def draft(snap, parts, refs=("r1",)):
    return json.dumps({"schema": "answer_bindings.v2", "snapshot_digest": snap.digest,
                       "sections": [{"requirement_ids": list(refs), "parts": parts}]}, ensure_ascii=False)


def accept_all(request):
    return {"schema": "publication_audit.v2", "snapshot_digest": request["snapshot_digest"],
            "draft_digest": request["draft_digest"], "decisions": [
                {"part_id": p["part_id"], "disposition": "accept", "reason": "语义和当前请求一致",
                 "evidence_refs": p["requirement_ids"] + p["claim_refs"]}
                for p in request["parts"]]}


def publish(snap, raw, auditor=None):
    from data_agent.agent.publication.service import PublicationService
    return PublicationService(snap, auditor=auditor).publish(raw).as_dict()


def text_part(text="条件满足时再执行行动。", purpose="interpretation", refs=()):
    return {"kind": "text", "purpose": purpose, "text": text, "claim_refs": list(refs)}


def outcomes(answer):
    return {r["requirement_id"]: r for r in answer["requirement_outcomes"]}


@pytest.mark.parametrize("data", [{}, IDENTITY])
def test_pure_consultation_delivers_examples_without_receipts_or_extra_audit(data):
    snap = snapshot(mode="consultation", data_identities=data,
                    requirements=[requirement(purposes=["knowledge"])])
    def forbidden(_):
        pytest.fail("Pure consultation must not require another model call")
    answer = publish(snap, draft(snap, [text_part("示例：100 人中 10 人转化，比例为 10%。", "knowledge")]), forbidden)
    assert "10%" in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "answered"
    assert answer["audit_status"] == "not_applicable"


def test_bad_reference_is_local_and_independent_host_facts_survive():
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"])])
    answer = publish(snap, draft(snap, [{"kind": "claim", "ref": "foreign"}, {"kind": "claim", "ref": "total"}]))
    assert "120" in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "answered"
    assert any(i["code"] == "unknown_claim_ref" for i in answer["issues"])


@pytest.mark.parametrize("mutation", [
    lambda obj: obj.update(snapshot_digest="sha256:" + "b" * 64),
    lambda obj: obj.update(schema="answer_bindings.v1"),
    lambda obj: obj.update(coverage={"r1": "answered"}),
    lambda obj: obj["sections"][0]["parts"][0].update(value=999),
])
def test_model_cannot_replace_values_schema_or_coverage(mutation):
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"], purposes=["interpretation"])])
    obj = json.loads(draft(snap, [{"kind": "claim", "ref": "total"}]))
    mutation(obj)
    answer = publish(snap, json.dumps(obj), accept_all)
    assert "120" in answer["body"] and "999" not in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "partial"
    assert answer["issues"]


@pytest.mark.parametrize("raw", ["not JSON", '{"schema":"answer_bindings.v2","schema":"forged"}', "[]"])
def test_unparseable_draft_preserves_host_facts_with_specific_gap(raw):
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"], purposes=["interpretation"])])
    answer = publish(snap, raw, accept_all)
    assert "120" in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "partial"
    assert outcomes(answer)["r1"]["reason"]


def test_conditional_action_and_explanation_share_one_evidence_bound_review():
    calls = []
    def auditor(request):
        calls.append(deepcopy(request))
        return accept_all(request)
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"], purposes=["conditional_action", "interpretation"])])
    answer = publish(snap, draft(snap, [
        {"kind": "claim", "ref": "total"},
        text_part("只有未来收入与利润两个条件同时满足才追加预算。", "conditional_action", ["total"]),
        text_part("这是描述性观察，尚不能归因为干预。", refs=["total"]),
    ]), auditor)
    assert len(calls) == 1 and len(calls[0]["parts"]) == 2
    assert calls[0]["claims"][0]["value"] == 120
    assert "同时满足" in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "answered"


def test_rejected_open_segment_does_not_remove_neighbor_or_fact():
    def auditor(request):
        result = accept_all(request)
        result["decisions"][0].update(disposition="reject", reason="没有因果证据")
        return result
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"], purposes=["conditional_action", "interpretation"])])
    answer = publish(snap, draft(snap, [
        text_part("这个结果证明活动造成收入增长。", "conditional_action", ["total"]),
        text_part("仅描述当前文件，后续需要对照组。", refs=["total"]),
    ]), auditor)
    assert "120" in answer["body"] and "需要对照组" in answer["body"]
    assert "证明活动造成" not in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "partial"


@pytest.mark.parametrize("fault", ["timeout", "wrong_snapshot", "unknown_part", "unknown_evidence", "replace_fact", "missing_decision"])
def test_review_faults_preserve_closed_facts_without_granting_open_coverage(fault):
    def auditor(request):
        if fault == "timeout": raise TimeoutError("bounded review timeout")
        result = accept_all(request)
        if fault == "wrong_snapshot": result["snapshot_digest"] = "sha256:" + "b" * 64
        if fault == "unknown_part": result["decisions"][0]["part_id"] = "outside"
        if fault == "unknown_evidence": result["decisions"][0]["evidence_refs"] = ["outside"]
        if fault == "replace_fact": result["claims"] = [{"value": 999}]
        if fault == "missing_decision": result["decisions"] = []
        return result
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"], purposes=["interpretation"])])
    answer = publish(snap, draft(snap, [text_part("仅供描述性比较。", refs=["total"])]), auditor)
    assert "120" in answer["body"]
    assert "仅供描述性比较。" not in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "partial"


def test_model_knowledge_label_cannot_bypass_review_when_result_context_exists():
    snap = snapshot(mode="consultation", uses_result_context=True, claims=[claim()],
                    requirements=[requirement(purposes=["knowledge"])])
    answer = publish(snap, draft(snap, [text_part("当前数据证明了因果。", "knowledge")]))
    assert "当前数据证明" not in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "failed"


def test_review_is_once_per_turn_and_repeat_publication_is_idempotent():
    from data_agent.agent.publication.service import PublicationService
    calls = []
    snap = snapshot(claims=[claim()], requirements=[requirement(claims=["total"], purposes=["interpretation"])])
    service = PublicationService(snap, auditor=lambda req: calls.append(req) or accept_all(req))
    raw = draft(snap, [text_part("有条件的描述性说明。", refs=["total"])])
    first = service.publish(raw).as_dict()
    repeat = service.publish(raw).as_dict()
    changed = service.publish(draft(snap, [text_part("另一个尚未审核的说明。")])).as_dict()
    assert len(calls) == 1
    assert first == repeat
    assert first["answer_id"] != changed["answer_id"]
    assert "另一个尚未审核" not in changed["body"]
    assert "120" in changed["body"]


def test_one_fact_cannot_answer_two_independent_metric_requirements():
    snap = snapshot(claims=[claim()], requirements=[
        requirement("revenue", claims=["total"]),
        requirement("cost", gap={"status": "not_computed", "reason": "成本数据未提供"}),
    ])
    answer = publish(snap, draft(snap, [{"kind": "claim", "ref": "total"}], refs=["revenue", "cost"]))
    assert outcomes(answer)["revenue"]["status"] == "answered"
    assert outcomes(answer)["cost"]["status"] == "not_computed"
    assert "成本数据未提供" in answer["body"]


def test_nine_requirements_keep_eight_answers_and_one_precise_gap():
    facts = [claim("metric" + str(i), i) for i in range(8)]
    reqs = [requirement("r" + str(i), claims=[c["id"]]) for i,c in enumerate(facts)]
    reqs.append(requirement("r8", gap={"status": "evidence_insufficient", "reason": "无对照，不能检验增量"}))
    snap = snapshot(claims=facts, requirements=reqs)
    answer = publish(snap, draft(snap, [], refs=["r0"]))
    assert sum(r["status"] == "answered" for r in answer["requirement_outcomes"]) == 8
    assert outcomes(answer)["r8"]["status"] == "evidence_insufficient"
    assert len([r for r in answer["render_trace"] if r["kind"] == "claim"]) == 8


def test_confirmed_partial_result_separates_cost_not_computed_from_effect_insufficient():
    snap = snapshot(claims=[claim("total"), claim("days",12)], requirements=[
        requirement("current", claims=["total","days"]),
        requirement("net", gap={"status":"not_computed","reason":"确认成本口径后仍未提供成本结果"}),
        requirement("effect", gap={"status":"evidence_insufficient","reason":"缺少对照，无法评估增量"}),
        requirement("withdrawn", purposes=["conditional_action"], withdrawn=True),
    ])
    answer = publish(snap, draft(snap, [], refs=["current"]))
    assert outcomes(answer)["current"]["status"] == "answered"
    assert outcomes(answer)["net"]["status"] == "not_computed"
    assert outcomes(answer)["effect"]["status"] == "evidence_insufficient"
    assert outcomes(answer)["withdrawn"]["status"] == "withdrawn"
    assert "withdrawn" not in answer["body"]


def test_snapshot_is_immutable_and_trace_positions_locate_actual_body():
    source = claim()
    snap = snapshot(claims=[source], requirements=[requirement(claims=["total"])])
    digest = snap.digest
    source["value"] = 999
    exported = snap.as_dict()
    exported["claims"][0]["value"] = 888
    answer = publish(snap, draft(snap, [{"kind":"claim","ref":"total"}]))
    assert snap.digest == digest and snap.as_dict()["claims"][0]["value"] == 120
    for row in answer["render_trace"]:
        if row["start"] is not None:
            assert answer["body"][row["start"]:row["end"]] == row["rendered_text"]


@pytest.mark.parametrize("invalid", ["duplicate_id", "stale_identity", "other_session", "nonfinite"])
def test_host_manifest_cannot_admit_ambiguous_or_stale_claims(invalid):
    value = claim()
    claims = [value]
    if invalid == "duplicate_id": claims.append(deepcopy(value))
    if invalid == "stale_identity": value["basis_refs"][0]["data_identities"]["orders"]["version_id"] = "v0"
    if invalid == "other_session": value["basis_refs"][0]["session_id"] = "other"
    if invalid == "nonfinite": value["value"] = float("nan")
    with pytest.raises(ValueError): snapshot(claims=claims)


@pytest.mark.parametrize("fault", ["kind_object","purpose_list","nested_refs","surrogate_text"])
def test_malformed_node_types_degrade_without_crashing_the_whole_answer(fault):
    snap = snapshot(claims=[claim()],requirements=[requirement(claims=["total"],purposes=["interpretation"])])
    obj = json.loads(draft(snap,[text_part(refs=["total"])]))
    part = obj["sections"][0]["parts"][0]
    if fault == "kind_object": part["kind"] = {}
    if fault == "purpose_list": part["purpose"] = []
    if fault == "nested_refs": part["claim_refs"] = [["total"]]
    if fault == "surrogate_text": part["text"] = chr(0xD800)
    answer = publish(snap,json.dumps(obj))
    assert "120" in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "partial"
    assert answer["issues"]


def test_six_accepted_presentation_variants_retain_same_facts_but_change_body():
    texts = ["业务建议：观察收入，再设验证窗口。", "分析师说明：本期仅有描述性统计。",
             "管理者摘要：当前观察可支持小规模验证。", "大白话：文件里这些记录合起来是当前结果。",
             "技术说明：结果由当前文件的统计回执绑定。", "简短说明：先保留观察，再验证原因。"]
    answers = []
    for index,wording in enumerate(texts):
        snap = snapshot(claims=[claim()],turn="style"+str(index),
                        requirements=[requirement(claims=["total"],purposes=["interpretation"])])
        answers.append(publish(snap,draft(snap,[text_part(wording,refs=["total"])]),accept_all))
    assert len({a["body"] for a in answers}) == 6
    assert all(a["source_snapshot"]["claims"][0]["value"] == 120 for a in answers)
    assert all(outcomes(a)["r1"]["status"] == "answered" for a in answers)


def artifact(path="charts/chart1.json"):
    return {"id":"a1","session_id":"s1","path":path,"type":"chart",
            "description":"当前来源图","sha256":"sha256:"+"a"*64}


def test_repeated_accepted_host_artifact_ref_renders_once():
    req = requirement()
    req["artifact_ids"] = ["a1"]
    snap = snapshot(artifacts=[artifact()],requirements=[req])
    answer = publish(snap,draft(snap,[{"kind":"artifact","ref":"a1"}]*2))
    assert len(answer["artifact_refs"]) == 1
    assert sum(row["kind"]=="artifact" and row["start"] is not None for row in answer["render_trace"]) == 1
    assert outcomes(answer)["r1"]["status"] == "answered"


@pytest.mark.parametrize("path", ["sessions/other/charts/foreign.json","charts/../other/file.json","javascript:alert(1)"])
def test_host_artifact_metadata_cannot_point_outside_owning_session(path):
    with pytest.raises(ValueError): snapshot(artifacts=[artifact(path)])


@pytest.mark.parametrize("kind", ["claim", "artifact"])
def test_draft_cannot_reassign_withdrawn_deliverables_to_an_active_requirement(kind):
    current = requirement("current", purposes=["knowledge"])
    old = requirement("old", claims=["total"] if kind == "claim" else [], withdrawn=True)
    if kind == "artifact": old["artifact_ids"] = ["a1"]
    snap = snapshot(requirements=[current,old], claims=[claim()] if kind == "claim" else [],
                    artifacts=[artifact()] if kind == "artifact" else [], mode="consultation")
    raw = draft(snap,[{"kind":kind,"ref":"total" if kind == "claim" else "a1"}], refs=["current"])
    answer = publish(snap,raw)
    assert all(row["kind"] != kind or row["start"] is None for row in answer["render_trace"])
    assert outcomes(answer)["old"]["status"] == "withdrawn"
    assert any(row["code"] == "unbound_deliverable_ref" for row in answer["issues"])


def test_trace_claim_ownership_is_derived_from_host_requirement_binding():
    snap = snapshot(claims=[claim()], requirements=[requirement("amount",claims=["total"]),
                    requirement("meaning",purposes=["knowledge"])])
    answer = publish(snap,draft(snap,[{"kind":"claim","ref":"total"}],refs=["amount","meaning"]))
    rows = [row for row in answer["render_trace"] if row["kind"] == "claim" and row["start"] is not None]
    assert len(rows) == 1 and rows[0]["requirement_ids"] == ["amount"]
    assert outcomes(answer)["amount"]["status"] == "answered"
    assert outcomes(answer)["meaning"]["status"] == "failed"



def test_open_part_cannot_borrow_claims_from_a_result_outside_its_section():
    snap = snapshot(claims=[claim()],requirements=[requirement("amount",claims=["total"]),
                    requirement("method",purposes=["interpretation"])])
    calls = []
    def auditor(request):
        calls.append(request)
        return accept_all(request)
    answer = publish(snap,draft(snap,[text_part(refs=["total"])],refs=["method"]),auditor)
    assert calls == []
    assert outcomes(answer)["amount"]["status"] == "answered"
    assert outcomes(answer)["method"]["status"] == "failed"
    assert any(issue["code"] == "unbound_text_claim" for issue in answer["issues"])


@pytest.mark.parametrize("decision",["accept","reject","unassessed"])
def test_separate_action_requirement_references_its_section_result(decision):
    calls=[]
    def auditor(request):
        calls.append(request)
        response=accept_all(request)
        response["decisions"][0].update(disposition=decision,reason="未来双条件语义核对")
        return response
    action=dict(requirement("action",purposes=["conditional_action"]),context_claim_ids=["total"])
    snap=snapshot(claims=[claim()],requirements=[requirement("result",claims=["total"]),action])
    answer=publish(snap,draft(snap,[{"kind":"claim","ref":"total"},text_part("未来收入和利润同时达标才追加预算。","conditional_action",["total"])],refs=["result","action"]),auditor)
    assert len(calls)==1 and calls[0]["parts"][0]["requirement_ids"]==["action"]
    assert outcomes(answer)["result"]["status"]=="answered" and "120" in answer["body"]
    assert (outcomes(answer)["action"]["status"]=="answered")== (decision=="accept")
    assert ("同时达标" in answer["body"])==(decision=="accept")


def test_action_cannot_borrow_fact_outside_its_section():
    snap=snapshot(claims=[claim()],requirements=[requirement("result",claims=["total"]),requirement("action",purposes=["conditional_action"])])
    def forbidden(_): pytest.fail("Unbound text cannot reach semantic review")
    answer=publish(snap,draft(snap,[text_part("未来同时达标才追加预算。","conditional_action",["total"])],refs=["action"]),forbidden)
    assert any(i["code"]=="unbound_text_claim" for i in answer["issues"])
    assert outcomes(answer)["action"]["status"]!="answered" and "120" in answer["body"]


@pytest.mark.parametrize("fault",["foreign_evidence","duplicate","unknown_extra","malformed_row"])
def test_audit_row_fault_is_local_and_keeps_other_valid_decision(fault):
    def auditor(request):
        result=accept_all(request)
        if fault=="foreign_evidence":result["decisions"][0]["evidence_refs"]=["foreign"]
        if fault=="duplicate":result["decisions"][1]=deepcopy(result["decisions"][0])
        if fault=="unknown_extra":result["decisions"][0]["part_id"]="outside"
        if fault=="malformed_row":result["decisions"][0]={"part_id":request["parts"][0]["part_id"]}
        return result
    snap=snapshot(claims=[claim()],requirements=[requirement(claims=["total"],purposes=["interpretation"])])
    answer=publish(snap,draft(snap,[text_part("第一解释",refs=["total"]),text_part("第二解释",refs=["total"])]),auditor)
    assert "120" in answer["body"]
    if fault=="duplicate":
        assert "第一解释" not in answer["body"] and "第二解释" not in answer["body"]
    else:
        assert "第一解释" not in answer["body"] and "第二解释" in answer["body"]
        assert answer["audit_status"]=="incomplete"


def test_audit_whole_answer_context_has_current_facts_and_limits_but_no_invalid_node():
    captured=[]
    def auditor(request):captured.append(request);return accept_all(request)
    snap=snapshot(claims=[claim()],requirements=[requirement(claims=["total"],purposes=["interpretation"])])
    answer=publish(snap,draft(snap,[{"kind":"claim","ref":"foreign"},text_part("本段不重复每个技术术语。",refs=["total"])]),auditor)
    context=captured[0]["answer_context"]
    assert captured[0]["claims"][0]["value"]==120
    assert captured[0]["claims"][0]["limitations"]==["仅描述当前文件"]
    assert all("error" not in n for n in context["nodes"])
    assert "120" in answer["body"]


def test_audit_projection_omits_unrequested_proof_graph_and_keeps_full_snapshot():
    from data_agent.agent.publication.contracts import encode
    from data_agent.agent.publication.audit import MAX_AUDIT_BYTES
    facts=[claim("fact"+str(i),i) for i in range(122)]
    for fact in facts:
        fact["basis_refs"][0]["result_path"]=["internal_"+"x"*1000]
    snap=snapshot(claims=facts,requirements=[requirement(claims=["fact0"],purposes=["interpretation"])])
    assert len(encode(snap.as_dict()).encode("utf-8"))>MAX_AUDIT_BYTES
    captured=[]
    def auditor(request):
        captured.append(request)
        assert len(encode(request).encode("utf-8"))<=MAX_AUDIT_BYTES
        return accept_all(request)
    raw=draft(snap,[text_part("当前值的范围和限制由原事实确定。",refs=["fact0"])])
    answer=publish(snap,raw,auditor)
    assert answer["audit_status"]=="reviewed" and len(captured)==1
    assert [c["id"] for c in captured[0]["claims"]]==["fact0"]
    assert "basis_refs" not in captured[0]["claims"][0]
    assert len(answer["source_snapshot"]["claims"])==122


@pytest.mark.parametrize("bad",[{"kind":"text","purpose":"invented","text":"bad"},{"kind":"claim","ref":"total","value":999},["invalid"]])
def test_local_protocol_fault_preserves_independent_explanation(bad):
    snap=snapshot(claims=[claim()],requirements=[requirement(claims=["total"],purposes=["interpretation"])])
    reviewed=[]
    def auditor(request):
        reviewed.append(request)
        return accept_all(request)
    answer=publish(snap,draft(snap,[bad,text_part("当前记录的描述性观察。",refs=["total"])]),auditor)
    assert "当前记录的描述性观察。" in answer["body"] and "120" in answer["body"]
    assert len(reviewed)==1 and [p["part_id"] for p in reviewed[0]["parts"]]==["s0p1"]
    assert any(i["part_id"]=="s0p0" for i in answer["issues"])
    assert not any(t["disposition"]=="accepted" and t["part_id"]=="s0p0" for t in answer["render_trace"])


@pytest.mark.parametrize("mode", ["accept", "capacity", "oversized_response"])
def test_audit_large_required_input_uses_client_capacity_and_keeps_parse_bound(mode):
    from data_agent.agent.publication.audit import MAX_AUDIT_BYTES, review_parts
    from data_agent.agent.publication.contracts import encode
    from data_agent.llm.request_policy import RequestCapacityError
    request={"snapshot_digest":"sha256:source", "draft_digest":"sha256:draft",
        "claims":[{"value":"required value "*10000}],
        "parts":[{"part_id":"p1","requirement_ids":["r1"],"claim_refs":["c1"]}]}
    original=deepcopy(request);calls=[]
    assert len(encode(request).encode("utf-8"))>MAX_AUDIT_BYTES
    def auditor(payload):
        calls.append(payload)
        if mode=="capacity":
            raise RequestCapacityError("request_context_capacity","too large for actual endpoint")
        response=accept_all(payload)
        if mode=="oversized_response":response["decisions"][0]["reason"]="x"*(MAX_AUDIT_BYTES+1)
        return response
    decisions,status=review_parts(request,auditor)
    assert len(calls)==1 and calls[0]==original and request==original
    assert status==("reviewed" if mode=="accept" else "unavailable")
    assert decisions["p1"]["disposition"]==("accept" if mode=="accept" else "unassessed")


@pytest.mark.parametrize("gap_status", ["not_computed", "evidence_insufficient", "needs_confirmation", "failed"])
def test_s4_reviewed_gap_guidance_keeps_host_status_and_one_existing_audit(gap_status):
    calls = []
    def reviewer(request):
        calls.append(deepcopy(request))
        return accept_all(request)
    snap = snapshot(claims=[claim()], requirements=[
        requirement("r1", gap={"status": gap_status, "reason": "原交付仍缺独立分母。"}),
        requirement("r2", claims=["total"]),
    ])
    raw = json.dumps({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[
        {"requirement_ids":["r1"],"parts":[text_part("当前同范围分母尚未核定。", "limitation"),
            text_part("补充同范围分母并确认口径后再重算。", "conditional_action")]},
        {"requirement_ids":["r2"],"parts":[{"kind":"claim","ref":"total"}]}]}, ensure_ascii=False)
    from data_agent.agent.publication.service import PublicationService
    service = PublicationService(snap, auditor=reviewer)
    answer = service.publish(raw).as_dict()
    assert service.publish(raw).as_dict() == answer and len(calls) == 1
    assert len(calls[0]["parts"]) == 2
    assert outcomes(answer)["r1"]["status"] == gap_status
    assert outcomes(answer)["r1"]["reason"] == "原交付仍缺独立分母。"
    assert outcomes(answer)["r2"]["status"] == "answered" and "120" in answer["body"]
    traces = [t for t in answer["render_trace"] if t["kind"] == "text"]
    assert {t["purpose"] for t in traces} == {"limitation", "conditional_action"}
    assert all(t["semantic_reviewed"] is True and t["requirement_ids"] == ["r1"] for t in traces)
    assert all(answer["body"][t["start"]:t["end"]] == t["rendered_text"] for t in traces)


@pytest.mark.parametrize("decision", ["reject", "unassessed"])
def test_s4_unaccepted_gap_guidance_is_not_published_as_a_reviewed_action(decision):
    def reviewer(request):
        result = accept_all(request)
        for row in result["decisions"]:row["disposition"] = decision
        return result
    snap = snapshot(requirements=[requirement(gap={"status":"not_computed", "reason":"当前计算未交付。"})])
    answer = publish(snap, draft(snap, [text_part("条件满足后再执行。", "conditional_action")]), reviewer)
    assert "条件满足后再执行。" not in answer["body"]
    assert outcomes(answer)["r1"]["status"] == "not_computed"
    trace = next(t for t in answer["render_trace"] if t["kind"] == "text")
    assert trace["semantic_reviewed"] is False
