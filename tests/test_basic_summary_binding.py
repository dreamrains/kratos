"""Descriptive summaries retain actual source values and reject model substitution."""
from copy import deepcopy
import json
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.contracts import encode
from data_agent.agent.publication.service import PublicationService


def _small(loop):
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=2),"amount":[10,20]}))


def _values(snapshot):
    return {c["label"]:c["value"] for c in snapshot.as_dict()["claims"]}


def test_basic_summary_uses_current_frame_and_keeps_prose_separate(engine):
    loop,_=engine;_small(loop)
    request(loop,"计算当前观测",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    request(loop,"解释当前观测",kind="presentation")
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    values=_values(snapshot)
    assert values["记录数"]==2 and values["amount：sum"]==30 and values["观测日期含首尾日数"]==2
    assert next(c for c in snapshot.as_dict()["claims"] if c["label"]=="amount：sum")["unit"] is None
    prose="This is a descriptive result; the cause remains unknown."
    payload=json.loads(draft(snapshot))
    payload["sections"][0]["parts"].append({"kind":"text","purpose":"interpretation","text":prose,
        "claim_refs":[c["id"] for c in snapshot.as_dict()["claims"]]})
    calls=[]
    def audit(candidate):
        calls.append(candidate)
        return {"schema":"publication_audit.v2","snapshot_digest":candidate["snapshot_digest"],"draft_digest":candidate["draft_digest"],
            "decisions":[{"part_id":p["part_id"],"disposition":"accept","reason":"descriptive scope",
                "evidence_refs":p["requirement_ids"]+p["claim_refs"]} for p in candidate["parts"]]}
    answer=PublicationService(snapshot,auditor=audit).publish(encode(payload)).as_dict()
    assert len(calls)==1 and prose in answer["body"]
    for trace in answer["render_trace"]:
        if trace["kind"]=="text" and trace["disposition"]=="accepted":
            assert answer["body"][trace["start"]:trace["end"]]==prose


@pytest.mark.parametrize("fault",["wrong_model_sum","stale_version","tampered_result"])
def test_basic_summary_rejects_wrong_sum_stale_version_and_tampered_binding(engine,fault):
    loop,cfg=engine;_small(loop)
    request(loop,"计算当前观测",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    if fault=="wrong_model_sum":
        payload=json.loads(draft(snapshot));payload["sections"][0]["parts"][0]["value"]=31
        answer=PublicationService(snapshot).publish(encode(payload)).as_dict()
        assert answer["issues"] and _values(snapshot)["amount：sum"]==30
    else:
        if fault=="stale_version": loop.context.workspace.add("orders",pd.DataFrame({"amount":[999]}))
        else:
            receipt=loop.context.analysis_state.tool_receipts[-1]
            (cfg.sessions_resolved/loop.session_id/receipt["detail_ref"]["path"]).write_text("tampered",encoding="utf-8")
        current=snapshot_for_turn(loop)
        assert current.as_dict()["claims"]==[] and current.as_dict()["requirements"][0]["gap"]


def test_described_table_renders_only_packet_bound_observations(engine):
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    values=_values(snapshot)
    assert values["记录数"]==12 and values["amount：sum"]==180 and values["观测日期含首尾日数"]==12
    answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    assert {t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}=={cid for r in snapshot.as_dict()["requirements"] for cid in r["claim_ids"]}
    payload=json.loads(draft(snapshot));payload["sections"][0]["parts"][0]["value"]=181
    assert PublicationService(snapshot).publish(encode(payload)).as_dict()["issues"]


def test_described_table_rejects_ambiguous_observations(engine):
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    state=loop.context.analysis_state
    state.tool_receipts.append(deepcopy(state.tool_receipts[-1]))
    snapshot=snapshot_for_turn(loop)
    assert snapshot.as_dict()["claims"]==[] and snapshot.as_dict()["requirements"][0]["gap"]


def test_described_only_does_not_reuse_python_summary_when_other_host_claims_exist(engine):
    loop,_=engine;_small(loop)
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"run_python",{"code":"result = {'amount_sum': float(get_dataset('orders')['amount'].sum())}"})
    current=snapshot_for_turn(loop).as_dict()
    assert current["requirements"][0]["claim_ids"]==[] and current["requirements"][0]["gap"]["status"]=="not_computed"
    # A valid Python calculation is retained but cannot discharge another tool's obligation.
    assert any(c["value"]=={"amount_sum":30.0} for c in current["claims"])
    execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop).as_dict()
    bound=current["requirements"][0]["claim_ids"]
    assert bound and all(c["target"]["tool"]=="describe_dataset" for c in current["claims"] if c["id"] in bound)


def test_described_summary_precedes_supplemental_python_and_host_recomputes_rows(engine):
    loop,_=engine;_small(loop)
    request(loop,"计算当前观测",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"run_python",{"code":"result = {'amount_sum': float(get_dataset('orders')['amount'].sum())}"})
    before=snapshot_for_turn(loop)
    assert "记录数" not in _values(before) and "观测日期含首尾日数" not in _values(before)
    execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop)
    values=_values(current)
    assert values["记录数"]==2 and values["观测日期含首尾日数"]==2 and values["amount：sum"]==30
    answer=PublicationService(current).publish(draft(current)).as_dict()
    assert answer["requirement_outcomes"][0]["status"]=="answered"
    assert {c["target"]["tool"] for c in current.as_dict()["claims"]}=={"run_python","describe_dataset"}
