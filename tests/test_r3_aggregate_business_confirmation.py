"""Original business-name mapping must bind a real current grouped receipt."""
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
from data_agent.agent.confirmation.service import ConfirmationService
from data_agent.session.history import load_canonical_history
from data_agent.agent.publication.runtime import snapshot_for_turn,publish
from data_agent.agent.publication.native import resolve_native_claims


def scenario(engine,response):
    loop,cfg=engine
    loop.context.workspace.add("sales",pd.DataFrame({"channel":["all","all"],"amount":[10,10]}))
    request(loop,"请汇总当前销售额，先让我确认它与 amount 列的关系",{'kind': 'table', 'scope': {'datasets': ['sales'], 'metrics': ['销售额']}})
    history=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=history,
        source_message_ref=history.messages[-1]["request_id"],exact_span="销售额",dataset="sales",column="amount")
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry());service.request(candidate)
    version=service.checkpoint(loop.session_id).version
    if response=="skipped":service.skip(loop.session_id,candidate.confirmation_id,version,"skip_mapping")
    else:service.respond(loop.session_id,candidate.confirmation_id,response,version,"mapping_answer")
    rid,result=execute(loop,"transform_data",{"name":"sales","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":"amount","functions":["sum","count"]}]})
    return loop,rid,result,candidate


@pytest.mark.parametrize("response,confirmed",[("raw",True),("skipped",False),("unconfirmed",False),("fraction",False),("percentage_points",False)])
def test_current_user_choice_controls_aggregate_business_name(engine,response,confirmed):
    loop,rid,result,candidate=scenario(engine,response)
    facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    native=next(c for c in facts if c["basis_refs"][0]["result_path"]==["measurement_records"])
    assert native["value"]==result["measurement_records"]==[{"channel":"all","amount_sum":20,"amount_count":2}]
    mapped=[c for c in facts if c.get("target",{}).get("statistic")=="business_sum"]
    assert bool(mapped) is confirmed
    if confirmed:
        claim=mapped[0]
        assert claim["label"]=="销售额" and claim["unit"] is None
        assert claim["value"]==[{"channel":"all","amount":20}]
        assert claim["derivation"]["confirmation_id"]==candidate.confirmation_id
        assert claim["basis_refs"][0]["result_path"]==["measurement_records",0,"amount_sum"]
        snapshot=snapshot_for_turn(loop)
        body,error=publish(loop,draft(snapshot));assert error is None
        assert "销售额" in body and "单位未知" in body
        assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    else:
        assert native["unit"] is None
        assert [(c["basis_refs"][0]["result_path"],c["unit"]) for c in facts if c["unit"] is not None] == [(["rows"],"条")]
        assert next(c for c in facts if c["basis_refs"][0]["result_path"]==["rows"])["value"]==1
        snapshot=snapshot_for_turn(loop)
        body,error=publish(loop,draft(snapshot));assert error is None
        assert loop._accepted_answer["requirement_outcomes"][0]["status"]!="answered"


def test_source_version_change_invalidates_prior_business_mapping(engine):
    loop,rid,_,_=scenario(engine,"raw")
    loop.context.workspace.add("sales",pd.DataFrame({"channel":["all"],"amount":[99]}))
    with pytest.raises(ValueError):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    fresh,_=execute(loop,"transform_data",{"name":"sales","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":"amount","functions":["sum","count"]}]})
    facts=resolve_native_claims(session_id=loop.session_id,receipt_id=fresh)
    assert not any(c.get("target",{}).get("statistic")=="business_sum" for c in facts)
    assert next(c for c in facts if c["basis_refs"][0]["result_path"]==["measurement_records"])["value"]==[{"channel":"all","amount_sum":99,"amount_count":1}]


@pytest.mark.parametrize("fault",["missing_choice","foreign_choice","missing_operand","forged_currency"])
def test_business_name_snapshot_rejects_forged_confirmation_or_unit(engine,fault):
    from data_agent.agent.publication.contracts import HostSnapshot
    loop,_,_,_=scenario(engine,"raw")
    original=snapshot_for_turn(loop).as_dict()
    claim=next(c for c in original["claims"] if c.get("derivation",{}).get("operator")=="confirmed_business_sum")
    if fault=="missing_choice": original["confirmation_refs"]=[]
    if fault=="foreign_choice": claim["derivation"]["confirmation_id"]="foreign-confirmation"
    if fault=="missing_operand": claim["derivation"]["operand_paths"]=[]
    if fault=="forged_currency": claim["unit"]="CNY"
    with pytest.raises(ValueError): HostSnapshot.freeze(**original)
