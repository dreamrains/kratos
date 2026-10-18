import hashlib
import json

import pytest
from tests.test_trusted_publication_semantics import engine

from data_agent.agent.analysis_state import AnalysisSessionState, load_analysis_state
from data_agent.agent.compact import _preserved_identity_and_obligations
from data_agent.agent.loop import AgentLoop
from data_agent.session.public_messages import assistant_replies, public_messages




def test_ac02_digest_changes_for_value_limit_version_and_verification(engine):
    import pandas as pd
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    before=snapshot_for_turn(loop)
    # Diagnostic annotations are not another publication authority.
    loop.context.analysis_state.verification_reports=[{"overall_status":"pass","confidence":1}]
    assert snapshot_for_turn(loop).digest==before.digest
    loop.context.analysis_state.verification_reports=[{"overall_status":"fail","confidence":0}]
    assert snapshot_for_turn(loop).digest==before.digest
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[10,20,30]}))
    stale=snapshot_for_turn(loop)
    assert stale.digest!=before.digest and stale.as_dict()["claims"]==[]
    execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop)
    assert current.digest not in {before.digest,stale.digest}
    assert next(c["value"] for c in current.as_dict()["claims"] if c["label"]=="记录数")==3


def test_ac03_packet_keeps_current_data_identity_without_cross_session_lookup(engine):
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.facts import load_receipt_result
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    rid,_=execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop).as_dict()
    identity=loop.context.workspace.get_data_identity("orders")
    assert current["session_id"]==loop.session_id and current["data_identities"]["orders"]==identity
    with pytest.raises(ValueError): load_receipt_result(session_id="other",receipt_id=rid)
    assert all(p["session_id"]==loop.session_id and p["data_identities"]["orders"]==identity for c in current["claims"] for p in c["basis_refs"])


def test_ac04_reply_projection_keeps_exact_publication_binding(engine):
    from data_agent.agent.publication.runtime import publish,snapshot_for_turn,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    bodies=[]
    for _ in range(2):
        request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
        execute(loop,"describe_dataset",{"name":"orders"})
        body,error=publish(loop,draft(snapshot_for_turn(loop)));assert error is None
        assert commit(loop,{"role":"assistant"},body) is None
        bodies.append(body)
    replies=assistant_replies(loop.messages,loop.session_id)
    refs=loop.context.analysis_state.accepted_answers
    assert len(replies)==2 and len(refs)==2 and refs[0]["answer_id"]!=refs[1]["answer_id"]
    assert [r["content"] for r in replies]==bodies
    assert [r["answer_ref"] for r in replies]==refs
    assert all(r["answer_sha256"]=="sha256:"+hashlib.sha256(r["content"].encode()).hexdigest() for r in replies)


def test_ac04_same_snapshot_answer_is_idempotent_and_revision_gets_new_binding(engine):
    from data_agent.agent.publication.runtime import publish,snapshot_for_turn,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    raw=draft(snapshot_for_turn(loop));first,error=publish(loop,raw);assert error is None
    identity=loop._accepted_answer["answer_id"]
    assert publish(loop,raw)==(first,None) and loop._accepted_answer["answer_id"]==identity
    assert commit(loop,{"role":"assistant"},first) is None
    assert commit(loop,{"role":"assistant"},first) is None
    assert len(loop.context.analysis_state.accepted_answers)==1
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    revised,error=publish(loop,draft(snapshot_for_turn(loop)));assert error is None
    assert loop._accepted_answer["answer_id"]!=identity
    assert commit(loop,{"role":"assistant"},revised) is None
    assert len(loop.context.analysis_state.accepted_answers)==2


def test_ac05_artifact_write_failure_does_not_commit_packet(engine,monkeypatch):
    from data_agent.agent.publication.runtime import publish,snapshot_for_turn,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    from data_agent.session.history import load_canonical_history
    import data_agent.session.history as history
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    body,error=publish(loop,draft(snapshot_for_turn(loop)));assert error is None
    before=load_canonical_history(loop.session_id)
    def fail(*a,**k): raise OSError("disk full")
    monkeypatch.setattr(history,"_write_json_atomic",fail)
    assert commit(loop,{"role":"assistant"},body)
    assert load_canonical_history(loop.session_id)==before and not loop.context.analysis_state.accepted_answers


def test_ac05_session_save_failure_rolls_back_public_reply_and_packet(engine,monkeypatch):
    from data_agent.agent.publication.runtime import publish,snapshot_for_turn,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    from data_agent.session.history import load_canonical_history
    import data_agent.session.history as history
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    body,error=publish(loop,draft(snapshot_for_turn(loop)));assert error is None
    before=load_canonical_history(loop.session_id)
    monkeypatch.setattr(history,"save_session",lambda *a,**k:(_ for _ in ()).throw(OSError("save failed")))
    assert commit(loop,{"role":"assistant"},body)
    assert load_canonical_history(loop.session_id)==before and not loop.context.analysis_state.accepted_answers
    assert not [m for m in loop.messages if m.get("answer_ref")]


def test_ac06_rejected_candidate_never_enters_public_projection():
    messages = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "bad candidate", "publication_rejected": True},
        {"role": "assistant", "content": "accepted"},
    ]
    projected = public_messages(messages, "session")
    assert [item.get("content") for item in projected] == ["question", "accepted"]


def test_ac10_fact_groups_remain_whole_and_naturally_ordered(engine):
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine
    _group_data(loop,12)
    request(loop,"逐一列出全部分组",{'kind': 'table', 'scope': {'datasets': ['orders']}})
    execute(loop,"run_python",{"code":"result = {'groups': get_dataset('orders').to_dict('records')}"})
    current=snapshot_for_turn(loop)
    groups=next(c["value"]["groups"] for c in current.as_dict()["claims"] if c["target"]["tool"]=="run_python")
    assert groups==[{"name":f"segment_{i}","count":i*10,"revenue":i*100} for i in range(12)]
    assert current.as_dict()["requirements"][0]["gap"] is None


def test_ac12_scan_limit_is_disclosed_and_detail_ref_closes_omission(engine):
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.facts import load_receipt_result
    loop,_=engine
    _group_data(loop,150)
    request(loop,"保留全部一百五十分组",{'kind': 'table', 'scope': {'datasets': ['orders']}})
    rid,_=execute(loop,"run_python",{"code":"result = {'groups': get_dataset('orders').to_dict('records')}"})
    current=snapshot_for_turn(loop)
    value=next(c["value"] for c in current.as_dict()["claims"] if c["target"]["tool"]=="run_python")
    _,_,original,binding=load_receipt_result(session_id=loop.session_id,receipt_id=rid)
    assert len(value["groups"])==150 and value["groups"][-1]=={"name":"segment_149","count":1490,"revenue":14900}
    assert value==original["result_data"] and binding["receipt_id"]==rid
    # The retired 100-group scan does not silently omit the last 50 groups.


def test_ac13_detail_reader_checks_session_path_hash_and_missing_file(engine):
    from copy import deepcopy
    from tests.test_trusted_publication_semantics import execute
    from data_agent.agent.publication.facts import load_receipt_result
    loop,_=engine
    rid,_=execute(loop,"describe_dataset",{"name":"orders"})
    state=loop.context.analysis_state;receipt=state.tool_receipts[-1];original=deepcopy(receipt["detail_ref"])
    assert load_receipt_result(session_id=loop.session_id,receipt_id=rid)[2]["shape"]["rows"]==12
    faults=[dict(original,sha256="sha256:bad"),dict(original,path="tool_outputs/missing.json"),dict(original,path="../other/tool_outputs/detail.json")]
    for detail in faults:
        receipt["detail_ref"]=detail
        with pytest.raises((ValueError,OSError)): load_receipt_result(session_id=loop.session_id,receipt_id=rid)
    receipt["detail_ref"]=original
    assert load_receipt_result(session_id=loop.session_id,receipt_id=rid)[2]["shape"]["rows"]==12


def test_ac14_compaction_appendix_preserves_publication_and_detail_refs():
    reference={"answer_id":"ans_123","path":"analyses/answer_123.json","sha256":"sha256:original","snapshot_digest":"sha256:snapshot","content_sha256":"sha256:body"}
    messages=[{"role":"user","content":"必须回答收入与复购率","request_id":"msg_original"},{"role":"assistant","content":"answer","answer_id":"ans_123","answer_ref":reference},{"role":"tool","content":"[detail: tool_outputs/result_detail.json]"}]
    appendix=_preserved_identity_and_obligations(messages)
    assert "必须回答收入与复购率" in appendix
    assert "accepted_answer="+json.dumps(reference,ensure_ascii=False,sort_keys=True) in appendix
    assert "detail_ref=tool_outputs/result_detail.json" in appendix


def test_ac36_new_requirement_fields_round_trip_without_rewriting_legacy(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState("roundtrip")
        state.answer_requirements = [{"id": "rq1", "label": "收入", "lifecycle_status": "active"}]
        state.requirement_revision = 3
        state.save()
        restored = load_analysis_state("roundtrip")
        assert restored.answer_requirements == state.answer_requirements
        assert restored.requirement_revision == 3
        legacy = AnalysisSessionState.from_dict({"schema_version": "legacy"}, "old")
        assert legacy.answer_requirements == [] and legacy.requirement_revision == 0
    finally:
        cfg.sessions_dir = old


def test_ac38_small_medium_large_fixtures_stay_bounded_without_provider_calls(engine):
    from pathlib import Path
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt
    loop,_=engine
    manifest=json.loads((Path(__file__).parent/"fixtures/answer_content/manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        _group_data(loop,case["group_count"])
        code="result = {'groups': get_dataset('orders').to_dict('records')}"
        request(loop,"保留完整分组 "+case["id"],{'kind': 'table', 'scope': {'datasets': ['orders']}})
        execute(loop,"run_python",{"code":code})
        current=snapshot_for_turn(loop)
        groups=next(c["value"]["groups"] for c in current.as_dict()["claims"] if c["target"]["tool"]=="run_python")
        assert len(groups)==case["group_count"] and groups[-1]["count"]==(case["group_count"]-1)*10
        assert len(publication_prompt(loop))<=manifest["prompt_max_chars"]
    assert manifest["provider_calls"]==0


def _group_data(loop,count):
    import pandas as pd
    loop.context.workspace.add("orders",pd.DataFrame({"name":[f"segment_{i}" for i in range(count)],"count":[i*10 for i in range(count)],"revenue":[i*100 for i in range(count)]}))
