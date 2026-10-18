from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode
from data_agent.agent.publication.requirements import update_requirements
from data_agent.session.history import save_session,load_canonical_history
import json







def test_ac16_two_explicit_requirements_cannot_be_satisfied_by_one_metric(engine):
    loop,_=engine
    request(loop,"回答收入",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    request(loop,"回答复购率",{'kind': 'table', 'scope': {'datasets': ['orders'], 'metrics': ['repurchase_rate']}})
    execute(loop,"describe_dataset",{"name":"orders"})
    answer=_publish(loop)
    assert [r["status"] for r in answer["requirement_outcomes"]]==["answered","not_computed"]
    assert any(c["value"]==180 for c in answer["source_snapshot"]["claims"])


def test_ac17_nine_items_allow_eight_answers_and_one_specific_gap(engine):
    import pandas as pd
    loop,_=engine
    for number in range(1,9):
        name="metric_"+str(number)
        loop.context.workspace.add(name,pd.DataFrame({"amount":[number]}))
        request(loop,"指标"+str(number),{'kind': 'measurement', 'scope': {'datasets': [name], 'metrics': ['amount'], 'quantity': 'sum'}})
        execute(loop,"describe_dataset",{"name":name})
    request(loop,"指标9复购率缺少分母，请说明证据缺口",kind="gap")
    answer=_publish(loop)
    assert len(answer["requirement_outcomes"])==9
    assert [r["status"] for r in answer["requirement_outcomes"]]==["answered"]*8+["evidence_insufficient"]
    values=[c["value"] for c in answer["source_snapshot"]["claims"] if c["target"].get("statistic")=="sum"]
    assert sorted(values)==list(range(1,9))
    assert "指标9复购率缺少分母" in answer["body"]


def test_ac18_not_computed_and_evidence_insufficient_stay_distinct(engine):
    loop,_=engine
    request(loop,"渠道拆分尚未计算",{'kind': 'table', 'scope': {'datasets': ['orders']}})
    request(loop,"复购率缺少订单分母，请说明缺口",kind="gap")
    answer=_publish(loop)
    assert [r["status"] for r in answer["requirement_outcomes"]]==["not_computed","evidence_insufficient"]
    assert not answer["source_snapshot"]["claims"]


def test_ac19_host_rejects_model_binding_to_unknown_fact(engine):
    loop,_=engine
    request(loop,"计算收入",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    request(loop,"计算复购率",{'kind': 'table', 'scope': {'datasets': ['orders'], 'metrics': ['repurchase_rate']}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);rid=snapshot.as_dict()["requirements"][1]["id"]
    answer=PublicationService(snapshot).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,
        "sections":[{"requirement_ids":[rid],"parts":[{"kind":"claim","ref":"fact_from_old_version"}]}]})).as_dict()
    assert {i["code"] for i in answer["issues"]}=={"unknown_claim_ref"}
    assert [r["status"] for r in answer["requirement_outcomes"]]==["answered","not_computed"]


def test_ac20_requirement_retraction_and_window_replacement_are_versioned(engine):
    loop,_=engine
    first=_change(loop,"收入和复购率",[{"op":"add","start":0,"end":2,"kind":"result"},{"op":"add","start":3,"end":6,"kind":"result"}])
    _change(loop,"撤回复购率",[{"op":"withdraw","start":0,"end":len("撤回复购率"),"kind":"result","target_id":first[1]}])
    old=_change(loop,"最近7天收入",[{"op":"add","start":0,"end":len("最近7天收入"),"kind":"result","business_scope":{"datasets":["orders"],"parameters":{"window_days":7}}}])[0]
    new=_change(loop,"最近30天收入",[{"op":"replace","start":0,"end":len("最近30天收入"),"kind":"result","target_id":old,"business_scope":{"datasets":["orders"],"parameters":{"window_days":30}}}])[0]
    state=loop.context.analysis_state
    assert state.requirement_revision==4
    assert {r["id"] for r in state.answer_requirements if r["lifecycle_status"]=="withdrawn"}=={first[1],old}
    current=next(r for r in state.answer_requirements if r["id"]==new)
    assert current["original_text"]=="最近30天收入" and current["business_scope"]["parameters"]=={"window_days":30}
    assert current["source_message_ref"]==loop.messages[-1]["request_id"]


def test_semantic_requirements_keep_source_identity_without_claiming_coverage(engine):
    import pytest
    loop,_=engine
    content="促销净收益；已算未算与证据缺口"
    valid=[{"op":"add","start":0,"end":5,"kind":"result"},{"op":"add","start":6,"end":len(content),"kind":"gap"}]
    with pytest.raises(ValueError):_change(loop,content,valid+[{"op":"add","start":0,"end":len(content)+1,"kind":"result"}])
    state=loop.context.analysis_state
    assert state.answer_requirements==[] and state.requirement_revision==0
    snapshot=load_canonical_history(loop.session_id);ref=loop.messages[-1]["request_id"]
    ids=update_requirements(state,snapshot,ref,valid,expected_revision=0)
    assert update_requirements(state,snapshot,ref,valid,expected_revision=1)==ids
    assert len(ids)==2 and state.requirement_revision==1
    assert {r["source_message_ref"] for r in state.answer_requirements}=={ref}
    assert not any("answer_coverage" in r for r in state.answer_requirements)


def test_presentation_rewording_cannot_create_a_replacement_requirement(engine):
    loop,_=engine
    request(loop,"计算当前金额",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop);body,error=publish(loop,draft(current));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    prior=loop.context.analysis_state.accepted_answers[-1]["answer_id"]
    ids=_change(loop,"改成业务负责人表达",[{"op":"add","start":0,"end":len("改成业务负责人表达"),"kind":"presentation","source_answer_id":prior}])
    state=loop.context.analysis_state
    assert len(state.answer_requirements)==2 and all(r["lifecycle_status"]=="active" for r in state.answer_requirements)
    changed=next(r for r in state.answer_requirements if r["id"]==ids[0])
    assert changed["source_answer_id"]==prior and changed["semantic_kind"]=="presentation"
    snapshot=snapshot_for_turn(loop)
    assert any(r["id"]==ids[0] and r["claim_ids"] for r in snapshot.as_dict()["requirements"])


def test_ac21_binding_is_removed_and_stale_or_malformed_protocol_is_not_trusted(engine):
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);raw=draft(snapshot)
    good=PublicationService(snapshot).publish(raw).as_dict()
    assert good["issues"]==[] and "answer_bindings.v2" not in good["body"]
    for bad in [raw.replace(snapshot.digest,"sha256:old"),"{bad}"]:
        answer=PublicationService(snapshot).publish(bad).as_dict()
        assert answer["issues"] and any(c["label"]=="记录数" and c["value"]==12 for c in answer["source_snapshot"]["claims"])


def _publish(loop):
    snapshot=snapshot_for_turn(loop)
    return PublicationService(snapshot).publish(draft(snapshot)).as_dict()


def _change(loop,content,changes):
    ref="coverage_request_"+str(len(loop.messages))
    loop.messages.append({"role":"user","content":content,"request_id":ref})
    save_session(loop.messages,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    loop._last_jsonl_idx=len(loop.messages)
    state=loop.context.analysis_state
    return update_requirements(state,load_canonical_history(loop.session_id),ref,changes,expected_revision=state.requirement_revision)
