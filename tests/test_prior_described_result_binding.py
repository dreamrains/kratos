"""Cross-turn reuse binds an exact accepted answer and current original receipts."""
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from tests.test_answer_content_coverage import _change
from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
from data_agent.agent.publication.service import PublicationService


def _accepted(loop):
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    return loop._accepted_answer


def _reuse(loop,answer_id):
    text="保留指定原答案的当前观测"
    rid=_change(loop,text,[{"op":"add","start":0,"end":len(text),"kind":"result",
        "business_scope":{"datasets":["orders"]},"source_answer_id":answer_id}])[0]
    loop.context.turn_requirement_ids=[rid]
    loop.context.turn_receipt_ids=[]
    current=snapshot_for_turn(loop)
    return current,next(r for r in current.as_dict()["requirements"] if r["id"]==rid)


def test_current_exact_source_binding_selects_only_prior_verified_receipt(engine):
    loop,_=engine
    original=_accepted(loop)
    prior_ids={t["ref"] for t in original["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    # A newly calculated result does not become part of that original answer.
    execute(loop,"run_python",{"code":"result = {'sum': float(get_dataset('orders')['amount'].sum())}"})
    current,requirement=_reuse(loop,original["answer_id"])
    assert set(requirement["claim_ids"])==prior_ids
    answer=PublicationService(current).publish(draft(current)).as_dict()
    assert next(r for r in answer["requirement_outcomes"] if r["requirement_id"]==requirement["id"])["status"]=="answered"
    assert {p["receipt_id"] for c in current.as_dict()["claims"] for p in c["basis_refs"]}=={p["receipt_id"] for c in original["source_snapshot"]["claims"] for p in c["basis_refs"]}


@pytest.mark.parametrize("fault",["stale","foreign_answer","tampered_answer","new_unrendered_result"])
def test_prior_result_rejects_stale_or_ambiguous_source_and_unrendered_claim(engine,fault):
    loop,cfg=engine
    original=_accepted(loop)
    answer_id=original["answer_id"]
    if fault=="stale":
        loop.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    elif fault=="foreign_answer": answer_id="ans_other_session"
    elif fault=="tampered_answer":
        reference=loop.messages[-1]["answer_ref"]
        (cfg.sessions_resolved/loop.session_id/reference["path"]).write_text("tampered",encoding="utf-8")
    else:
        execute(loop,"run_python",{"code":"result = {'mean': float(get_dataset('orders')['amount'].mean())}"})
    current,requirement=_reuse(loop,answer_id)
    if fault=="new_unrendered_result":
        assert set(requirement["claim_ids"])=={t["ref"] for t in original["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
        assert all(c["target"]["tool"]=="describe_dataset" for c in current.as_dict()["claims"])
    else:
        assert requirement["claim_ids"]==[] and requirement["gap"]["status"]=="evidence_insufficient"
        answer=PublicationService(current).publish(draft(current)).as_dict()
        assert next(r for r in answer["requirement_outcomes"] if r["requirement_id"]==requirement["id"])["status"]!="answered"
