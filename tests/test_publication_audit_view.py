"""Original review behavior on the sole publication.v2 and accepted answer.

Legacy shadow/trial/view/revision APIs are replaced, not kept as compatibility.
Fixed decisions test orchestration and local retention, not natural quality.
"""
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record
from copy import deepcopy
import json
import pandas as pd
import pytest

from data_agent.agent.publication.contracts import encode,digest
from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
from data_agent.agent.publication.service import PublicationService
from data_agent.session.history import load_canonical_history,load_session
from tests.test_trusted_publication_runtime import request,draft
from tests.test_trusted_publication_semantics import engine,execute


class AuditClient:
    def __init__(self, dispositions=(), mutate=None):
        self.dispositions=dispositions;self.mutate=mutate;self.calls=[]
    def chat(self,messages,**kwargs):
        from data_agent.llm.client import Response
        data=json.loads(messages[0]["content"]);self.calls.append(deepcopy(data))
        assert kwargs.get("tools") is None
        value={"schema":"publication_audit.v2","snapshot_digest":data["snapshot_digest"],
               "draft_digest":data["draft_digest"],"decisions":[
                   {"part_id":p["part_id"],"disposition":self.dispositions[i] if i<len(self.dispositions) else "reject",
                    "reason":"独立固定定位决定；不签收自然审核质量。","evidence_refs":p["requirement_ids"]+p["claim_refs"]}
                    for i,p in enumerate(data["parts"])]}
        return Response(text=encode(self.mutate(value) if self.mutate else value))


def _setup(engine):
    loop,cfg=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=12),"amount":[10]*12}))
    request(loop,"解释当前记录和观察边界",[{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': q}} for q in ['rows','sum','calendar_days']],kind="result",purposes=["interpretation"])
    rid,_=execute(loop,"describe_dataset",{"name":"orders"})
    return loop,cfg,rid,snapshot_for_turn(loop)


def _raw(snapshot,*texts):
    value=json.loads(draft(snapshot));refs=snapshot.as_dict()["requirements"][0]["claim_ids"]
    value["sections"][0]["parts"] += [{"kind":"text","purpose":"interpretation","text":t,"claim_refs":refs} for t in texts]
    return encode(value)


def _archives(loop,cfg):
    return [json.loads(p.read_text(encoding="utf-8")) for p in (cfg.sessions_resolved/loop.session_id/"publication_rejected").glob("candidate_*.json")]


def test_audit_view_locates_latest_reused_answer_without_changing_publication(engine):
    loop,_,_,host=_setup(engine);loop.client=AuditClient(["accept"])
    raw=_raw(host,"当前描述只适用于原观察范围，不证明原因。")
    body,error=publish(loop,raw);assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    saved=load_session(loop.session_id);ref=saved["messages"][-1]["answer_ref"]
    before=load_canonical_history(loop.session_id)
    assert commit(loop,{"role":"assistant"},body) is None
    accepted=read_answer(loop.session_id,ref)
    assert accepted["body"]==body and load_canonical_history(loop.session_id)==before
    assert loop.context.analysis_state.accepted_answers==[ref] and len(loop.client.calls)==1
    assert accepted["source_snapshot"]["claims"]==host.as_dict()["claims"]
    for row in accepted["render_trace"]:
        if row["rendered_text"] is not None:assert body[row["start"]:row["end"]]==row["rendered_text"]


@pytest.mark.parametrize("fault",["body","trace"])
def test_audit_view_rejects_changed_answer_or_trace_identity(engine,fault):
    loop,cfg,_,host=_setup(engine);loop.client=AuditClient(["accept"])
    body,error=publish(loop,_raw(host,"原观察没有证明原因。"));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    ref=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    path=cfg.sessions_resolved/loop.session_id/ref["path"]
    accepted=json.loads(path.read_text(encoding="utf-8"))
    if fault=="body":accepted["body"]+="!"
    else:accepted["render_trace"][0]["rendered_text"]="另一答案"
    path.write_text(encode(accepted),encoding="utf-8")
    with pytest.raises(ValueError,match="摘要"):read_answer(loop.session_id,ref)


def test_trial_action_release_updates_only_current_action_coverage(engine):
    loop,_,_,host=_setup(engine)
    request(loop,"另算未提供的成本",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['cost'], 'quantity': 'sum'}})
    request(loop,"未来条件满足才小试，否则暂停并复核",kind="conditional_action")
    host=snapshot_for_turn(loop);proposal=json.loads(draft(host));action=host.as_dict()["requirements"][-1]
    proposal["sections"].append({"requirement_ids":[action["id"]],"parts":[{"kind":"text","purpose":"conditional_action","text":action["text"],"claim_refs":[]}]})
    loop.client=AuditClient(["accept"])
    body,error=publish(loop,encode(proposal));assert error is None
    outcomes={o["requirement_id"]:o["status"] for o in loop._accepted_answer["requirement_outcomes"]}
    assert outcomes[action["id"]]=="answered" and outcomes[host.as_dict()["requirements"][1]["id"]]=="not_computed"
    assert outcomes[host.as_dict()["requirements"][0]["id"]]=="partial"
    assert has_number(body, 'amount：sum', 120) and len(loop.client.calls)==1
    refused=PublicationService(host,auditor=None).publish(encode(proposal)).as_dict()
    assert next(o for o in refused["requirement_outcomes"] if o["requirement_id"]==action["id"])["status"]=="failed"
    assert has_number(refused["body"], 'amount：sum', 120)


def test_nested_describe_summary_and_withheld_draft_enter_existing_audit_view(engine):
    loop,cfg,rid,host=_setup(engine);bad="只有11天，净收益为120，应立即扩大投放。"
    loop.client=AuditClient(["reject"]);raw=_raw(host,bad)
    body,error=publish(loop,raw);assert error is None
    audit=loop.client.calls[0]
    assert audit["parts"][0]["text"]==bad and audit["requirements"][0]["text"]=="解释当前记录和观察边界"
    values={c["label"]:c["value"] for c in audit["claims"]}
    assert values["记录数"]==12 and values["观测日期含首尾日数"]==12 and values["amount：sum"]==120
    assert all(c["basis_refs"][0]["receipt_id"]==rid for c in host.as_dict()["claims"])
    assert audit["claims"]==[{k:c[k] for k in ("id","label","value","unit","scope","limitations")} for c in host.as_dict()["claims"] if c["id"] in host.as_dict()["requirements"][0]["claim_ids"]]
    assert bad not in body and has_number(body, '含首尾日数', 12)
    assert not loop.context.analysis_state.accepted_answers
    rows=_archives(loop,cfg);assert any(r["raw_draft"]==raw and r["draft_digest"]==digest(raw) for r in rows)


def test_prepublication_view_uses_same_trace_without_persisting_candidate(engine):
    loop,_,_,host=_setup(engine);before=load_canonical_history(loop.session_id)
    loop.client=AuditClient(["accept","reject"])
    raw=_raw(host,"当前正确描述已保留。","这个解释仍需核对。")
    body,error=publish(loop,raw);assert error is None
    assert load_canonical_history(loop.session_id)==before and not loop.context.analysis_state.accepted_answers
    audited=loop.client.calls[0]
    assert audited["snapshot_digest"]==host.digest and audited["draft_digest"]==digest(raw)
    assert [p["text"] for p in audited["parts"]]==["当前正确描述已保留。","这个解释仍需核对。"]
    assert "当前正确描述已保留。" in body and "这个解释仍需核对。" not in body
    for row in loop._accepted_answer["render_trace"]:
        if row["rendered_text"] is not None:assert body[row["start"]:row["end"]]==row["rendered_text"]


def test_prepublication_review_limits_one_bad_sentence_and_keeps_adjacent_text(engine):
    loop,_,_,host=_setup(engine);loop.client=AuditClient(["accept","reject"])
    raw=_raw(host,"当前正确结果已保留。","这个解释仍需核对。")
    body,error=publish(loop,raw);assert error is None
    assert "当前正确结果已保留。" in body and "这个解释仍需核对。" not in body
    assert has_number(body, 'amount：sum', 120) and len(loop.client.calls)==1
    texts=[r for r in loop._accepted_answer["render_trace"] if r["kind"]=="text"]
    assert [r["disposition"] for r in texts]==["accepted","reject"] and texts[1]["start"] is None
    assert sum(r["kind"]=="gap" for r in loop._accepted_answer["render_trace"])==1
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="partial"
    assert publish(loop,raw)==(body,None) and len(loop.client.calls)==1


def test_trial_runtime_requests_one_revision_then_locally_limits_final_sentence(engine):
    """The approved replacement limits one bad part in one audit, without revision loops."""
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.llm.client import Response
    loop,_=engine
    request(loop,"解释当前结果",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}},kind="result",purposes=["interpretation"])
    execute(loop,"describe_dataset",{"name":"orders"})
    host=snapshot_for_turn(loop);proposal=json.loads(draft(host));refs=host.as_dict()["requirements"][0]["claim_ids"]
    proposal["sections"][0]["parts"] += [{"kind":"text","purpose":"interpretation","text":"当前记录的描述不证明原因。","claim_refs":refs},{"kind":"text","purpose":"interpretation","text":"这是促销造成的全部增量。","claim_refs":refs}]
    class Client:
        calls=0
        def chat(self,messages,**kwargs):
            self.calls+=1;data=json.loads(messages[0]["content"])
            assert data["snapshot_digest"]==host.digest and len(data["parts"])==2
            return Response(text=json.dumps({"schema":"publication_audit.v2","snapshot_digest":data["snapshot_digest"],"draft_digest":data["draft_digest"],"decisions":[{"part_id":p["part_id"],"disposition":"accept" if i==0 else "reject","reason":"Frozen independent descriptive/unsupported causal oracle","evidence_refs":p["claim_refs"]} for i,p in enumerate(data["parts"])]}))
    loop.client=Client();raw=json.dumps(proposal,ensure_ascii=False)
    body,error=publish(loop,raw)
    assert error is None and "当前记录的描述不证明原因。" in body and "全部增量" not in body and "12" in body
    assert loop.client.calls==1 and publish(loop,raw)==(body,None) and loop.client.calls==1
    assert any(t["disposition"]=="reject" for t in loop._accepted_answer["render_trace"])
    assert not loop.context.analysis_state.accepted_answers


def test_trial_review_locates_plain_open_answer_without_typed_blocks(engine):
    """Plain legacy prose is retained for audit; it cannot bypass the sole v2 draft contract."""
    from tests.test_trusted_publication_runtime import request
    from tests.test_trusted_publication_semantics import execute
    from data_agent.agent.publication.runtime import publish
    loop,cfg=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    class NoAudit:
        def chat(self,*a,**k): raise AssertionError("Invalid prose must not become a second semantic path")
    loop.client=NoAudit()
    raw="无绑定的原因解释：促销造成全部增长。"
    assert publish(loop,raw)[1]
    body,error=publish(loop,raw)
    assert error is None and "12" in body and "促销造成" not in body
    records=[json.loads(p.read_text(encoding="utf-8")) for p in (cfg.sessions_resolved/loop.session_id/"publication_rejected").glob("candidate_*.json")]
    assert records and all(r["raw_draft"]==raw and r["reasons"] for r in records)


def test_unavailable_audit_coalesces_adjacent_open_fragments_into_one_gap(engine):
    loop,_,_,host=_setup(engine)
    answer=PublicationService(host).publish(_raw(host,"当前正确结果已保留。","这个解释仍需核对。")).as_dict()
    assert answer["audit_status"]=="unavailable" and has_number(answer["body"], 'amount：sum', 120)
    assert "当前正确结果已保留。" not in answer["body"] and "这个解释仍需核对。" not in answer["body"]
    assert sum(t["kind"]=="gap" for t in answer["render_trace"])==1
    assert [t["disposition"] for t in answer["render_trace"] if t["kind"]=="text"]==["unassessed","unassessed"]


def test_unbound_natural_action_draft_is_locatable_for_diagnosis_only(engine):
    loop,cfg,_,host=_setup(engine)
    request(loop,"比较两期并给出完整未来条件行动；否则暂停预算。",kind="conditional_action")
    snapshot=snapshot_for_turn(loop)
    raw="本期上涨，但下一窗口尚未观测；不得立即执行预算动作。"
    loop.client=AuditClient()
    assert publish(loop,raw)[1]
    body,error=publish(loop,raw);assert error is None
    assert len(loop.client.calls)==0 and raw not in body and has_number(body, 'amount：sum', 120)
    rows=_archives(loop,cfg)
    assert rows and all(r["raw_draft"]==raw and r["draft_digest"]==digest(raw) for r in rows)
    assert any(r["code"] for record in rows for r in record["reasons"] if "code" in r)
    assert not any(t["kind"]=="text" and t["disposition"]=="accepted" for t in loop._accepted_answer["render_trace"])


@pytest.mark.parametrize("fault",[None,"whitespace","invalid_json","oversize","wrong_digest","foreign_part","foreign_evidence","unknown_fields"])
def test_one_shot_shadow_dispatch_is_bounded_and_keeps_publication_unchanged(engine,fault):
    from tests.test_r3_comparison_action_inputs import reviewer
    loop,_,_,host=_setup(engine);calls=[]
    original=host.as_dict();raw=_raw(host,"原观察不能证明原因。")
    def audit(payload):
        value=reviewer("accept",calls)(payload)
        if fault=="whitespace":return encode(value)+" "*33000
        if fault=="invalid_json":return "not json"
        if fault=="oversize":return encode(value)+" "*64000
        if fault=="wrong_digest":value["draft_digest"]=digest("different")
        if fault=="foreign_part":value["decisions"][0]["part_id"]="other"
        if fault=="foreign_evidence":value["decisions"][0]["evidence_refs"]=["old-version"]
        if fault=="unknown_fields":value["decisions"][0]["value"]=999
        return value
    service=PublicationService(host,auditor=audit);answer=service.publish(raw).as_dict()
    assert len(calls)==1 and host.as_dict()==original and not loop.context.analysis_state.accepted_answers
    assert has_number(answer["body"], 'amount：sum', 120)
    assert answer["audit_status"]==("reviewed" if fault in {None,"whitespace"} else "unavailable")
    assert service.publish(raw).as_dict()==answer and len(calls)==1
    changed=service.publish(_raw(host,"另一段未核解释。")).as_dict()
    assert len(calls)==1 and "另一段未核解释。" not in changed["body"]


def test_withheld_action_draft_is_locatable_but_has_no_publication_authority(engine):
    from tests.test_r3_comparison_action_inputs import scenario,raw,RULE
    loop,cfg,_,_,calc_id,values=scenario(engine)
    host=snapshot_for_turn(loop);loop.client=AuditClient(["reject"])
    candidate=raw(host,"下一窗口两个条件均满足才可小试；否则暂停并复核。")
    body,error=publish(loop,candidate);assert error is None
    payload=loop.client.calls[0]
    assert len(payload["parts"])==1 and payload["requirements"][-1]["text"].endswith(RULE)
    source=next(c for c in host.as_dict()["claims"] if c["basis_refs"][0]["receipt_id"]==calc_id)
    original=next(c for c in payload["claims"] if c["id"]==source["id"])
    assert original=={k:source[k] for k in ("id","label","value","unit","scope","limitations")}
    assert original["value"]==values and original["value"]["periods"]["b"]["cost_per_count"]["denominator"]==77
    assert "下一窗口两个条件均满足才可小试" not in body and has_number(body, 'net_contribution：后期', 595)
    assert any(r["raw_draft"]==candidate and r["draft_digest"]==digest(candidate) for r in _archives(loop,cfg))
    assert loop._accepted_answer["requirement_outcomes"][-1]["status"]=="partial"
    assert not loop.context.analysis_state.accepted_answers
