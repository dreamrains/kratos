"""Actual business choices scale only matching current original curve points."""
import json
from copy import deepcopy
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
from data_agent.agent.confirmation.service import ConfirmationService
from data_agent.session.history import load_canonical_history
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.native import resolve_native_claims
from data_agent.agent.publication.renderer import claim_text
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode

VALUES=[.55,.42,.31,.24,.18,.13,.10]


def setup_actual(engine,response="fraction",*,scenarios=False):
    loop,cfg=engine
    loop.context.workspace.add("ret_a",pd.DataFrame({"day":range(1,8),"retention":VALUES}))
    request(loop,"请解释留存序列并判断 D30 证据边界",[{'kind':k,'scope':{'datasets':['ret_a'],'metrics':['retention']}} for k in ['series','fit']+(['scenario'] if scenarios else [])])
    current=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=current,
        source_message_ref=current.messages[-1]["request_id"],exact_span="留存序列",dataset="ret_a",column="retention",x_column="day",x_start=1,x_end=7)
    assert candidate is not None
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry())
    service.request(candidate);version=service.checkpoint(loop.session_id).version
    if response=="skipped": service.skip(loop.session_id,candidate.confirmation_id,version,"scale_skip")
    else: service.respond(loop.session_id,candidate.confirmation_id,response,version,"scale_answer")
    args={"name":"ret_a","x_col":"day","y_col":"retention"}
    if scenarios: args["scenario_points"]=[30]
    rid,result=execute(loop,"curve_fitting",args)
    return loop,cfg,rid,result,candidate


@pytest.mark.parametrize("response,unit,expected",[("fraction","proportion","10%"),("percentage_points","percent","0.1%"),("skipped",None,"单位未知")])
def test_real_confirmation_choice_controls_scale(engine,response,unit,expected):
    loop,_,rid,result,_=setup_actual(engine,response)
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    point=next(c for c in claims if c["basis_refs"][0]["result_path"]==["points",6,"y"])
    assert point["value"]==result["points"][6]["y"]==.1 and point["unit"]==unit
    assert expected in claim_text(point)
    snapshot=snapshot_for_turn(loop)
    answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    assert expected in answer["body"] and answer["requirement_outcomes"][0]["status"]=="answered"
    assert all(c["value"]==VALUES[c["basis_refs"][0]["result_path"][1]] for c in claims if len(c["basis_refs"][0]["result_path"])==3)


@pytest.mark.parametrize("mutation",["version","column","point"])
def test_stale_or_mismatched_receipt_cannot_inherit_confirmation(engine,mutation):
    loop,_,rid,_,_=setup_actual(engine)
    if mutation=="version":
        loop.context.workspace.add("ret_a",pd.DataFrame({"day":range(1,8),"retention":VALUES[:-1]+[.2]}))
        with pytest.raises(ValueError): resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        return
    if mutation=="column":
        # A new actual result for another column cannot borrow the first choice.
        loop.context.workspace.add("ret_a",pd.DataFrame({"day":range(1,8),"retention":VALUES,"different":VALUES}))
        rid,_=execute(loop,"curve_fitting",{"name":"ret_a","x_col":"day","y_col":"different"})
        assert all(c["unit"] is None for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid))
    else:
        from data_agent.agent.publication.facts import _safe_path
        receipt=loop.context.analysis_state.tool_receipts[-1]
        original=_safe_path(receipt["detail_ref"]["path"])
        payload=json.loads(original.read_text("utf8"));payload["points"]=payload["points"][:-1]
        original.write_text(json.dumps(payload),encoding="utf8")
        with pytest.raises(ValueError): resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


def test_forged_binding_or_confirmation_context_cannot_gain_coverage(engine):
    loop,cfg,rid,_,candidate=setup_actual(engine)
    snapshot=snapshot_for_turn(loop)
    original=json.loads(draft(snapshot)); forged=deepcopy(original)
    forged["sections"][0]["parts"][0]["unit"]="proportion"
    answer=PublicationService(snapshot).publish(encode(forged)).as_dict()
    assert any(i["code"]=="invalid_fields" for i in answer["issues"])
    assert answer["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]
    from data_agent.agent.confirmation.store import ConfirmationStore
    store=ConfirmationStore(cfg.sessions_resolved,loop.session_id)
    loaded=store.load(); record=loaded.records[candidate.confirmation_id]
    from dataclasses import replace
    from data_agent.agent.confirmation.models import ConfirmationEvent
    changed=replace(record,version=record.version+1,data_version="dv_stale")
    store.append(ConfirmationEvent(event_id="changed_scope",confirmation_id=record.confirmation_id,session_id=loop.session_id,event_type="changed",version=changed.version,occurred_at=record.updated_at,record=changed))
    point=next(c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c["basis_refs"][0]["result_path"]==["points",6,"y"])
    assert point["unit"] is None and point["value"]==.1
