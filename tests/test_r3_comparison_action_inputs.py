"""Original M01 action inputs through actual tools and one bounded review.

Closed arithmetic is an original execution value. Future AND rules remain open
user requirements; no legacy prose parser or model-supplied metric-role waiver.
"""
from copy import deepcopy
import json
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number

import pandas as pd
import pytest

from data_agent.agent.publication.contracts import encode
from data_agent.agent.publication.native import resolve_native_claims
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.service import PublicationService
from tests.test_trusted_publication_semantics import engine, execute, change
from tests.test_trusted_publication_runtime import request

RULE = "只有下一同口径七日窗口净贡献不低于基准期且成本每单不高于本期，才考虑小规模试验；否则暂停预算并复核。"


def scenario(engine, *, fault=None, fragments=False):
    loop, cfg = engine
    frame = pd.DataFrame({
        "date": pd.date_range("2026-09-07", periods=14),
        "amount": [100]*7+[110]*7, "campaign_cost": [20]*7+[25]*7,
        "net_contribution": [80]*7+[85]*7, "orders": [10]*7+[11]*7,
    })
    if fault == "wrong_net": frame.loc[0,"net_contribution"] = 81
    if fault == "zero_denominator": frame.loc[7:,"orders"] = 0
    end = "2026-09-19" if fault == "uneven" else "2026-09-20"
    loop.context.workspace.add("action_sales", frame)
    request(loop,"比较两期原列 amount,campaign_cost,net_contribution,orders",
            [{'kind': 'measurement', 'scope': {'datasets': ['action_sales'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['action_sales'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['action_sales'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['action_sales'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['action_sales'], 'quantity': 'calendar_days'}}])
    rid, comparison = execute(loop,"compare_periods",{
        "name":"action_sales","date_col":"date",
        "metrics":"amount,campaign_cost,net_contribution,orders",
        "period_a":"2026-09-07~2026-09-13","period_b":"2026-09-14~"+end,
    })
    content = "请给出有条件行动建议。我的行动规则是：" + RULE
    request(loop, content, kind="conditional_action")
    from tests.support.plan_inputs import declare_goal_deliveries
    declare_goal_deliveries(loop,[(loop.context.turn_requirement_ids[0],"table",{"datasets":["action_sales"]})])
    if fragments:
        from data_agent.session.history import load_canonical_history
        from data_agent.agent.publication.requirements import update_requirements
        spans = ["只有下一同口径七日窗口净贡献不低于基准期", "成本每单不高于本期", "否则暂停预算并复核"]
        update_requirements(loop.context.analysis_state, load_canonical_history(loop.session_id),
            loop.messages[-1]["request_id"],
            [change(content,span,"conditional_action",business_scope={'datasets': ['action_sales']}) for span in spans],
            expected_revision=loop.context.analysis_state.requirement_revision)
    # These explicit column operands are frozen inputs, not inferred prose roles.
    code = """df=get_dataset('action_sales')
result={'periods':{}, 'future_window_observed':False}
for key,start,end in [('a','2026-09-07','2026-09-13'),('b','2026-09-14',END)]:
    part=df[(df['date']>=start)&(df['date']<=end)]
    totals={col:int(part[col].sum()) for col in ['amount','campaign_cost','net_contribution','orders']}
    count=totals['orders']
    result['periods'][key]={'totals':totals,'rows':len(part),
        'inclusive_days':int((pd.Timestamp(end)-pd.Timestamp(start)).days)+1,
        'net_row_arithmetic':bool((part['amount']-part['campaign_cost']==part['net_contribution']).all()),
        'cost_per_count':{'numerator':totals['campaign_cost'],'denominator':count,
                          'value':totals['campaign_cost']/count if count>0 else None}}
""".replace("END",repr(end))
    calculation_id, calculation = execute(loop,"run_python",{"code":code,"purpose":"original action operands; future not observed"})
    return loop,cfg,rid,comparison,calculation_id,calculation["result_data"]


def raw(snapshot, text, *, only=None):
    sections=[]
    for req in snapshot.as_dict()["requirements"]:
        parts=[{"kind":"claim","ref":cid} for cid in req["claim_ids"]]
        if "conditional_action" in req["open_purposes"] and (only is None or req["id"] in only):
            parts.append({"kind":"text","purpose":"conditional_action","text":text,"claim_refs":req["claim_ids"]})
        sections.append({"requirement_ids":[req["id"]],"parts":parts})
    return encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":sections})


def reviewer(disposition, calls):
    def audit(payload):
        calls.append(deepcopy(payload))
        return {"schema":"publication_audit.v2","snapshot_digest":payload["snapshot_digest"],
                "draft_digest":payload["draft_digest"],"decisions":[
                    {"part_id":p["part_id"],"disposition":disposition,
                     "reason":"固定条件规则审核；只验证编排，不证明自然语义质量。",
                     "evidence_refs":p["requirement_ids"]+p["claim_refs"]} for p in payload["parts"]]}
    return audit


def test_current_comparison_rechecks_row_arithmetic_and_cost_denominator(engine):
    loop,_,rid,comparison,calc_id,values=scenario(engine)
    expected={"amount":(700,770,70,10),"campaign_cost":(140,175,35,25),
              "net_contribution":(560,595,35,6.25),"orders":(70,77,7,10)}
    for metric,(a,b,d,pct) in expected.items():
        assert comparison["metrics"][metric]["exact_aggregates"]=={"period_a":a,"period_b":b,"diff":d}
        assert comparison["metrics"][metric]["change_pct"]==pct
    assert values["periods"]["a"]["totals"]=={"amount":700,"campaign_cost":140,"net_contribution":560,"orders":70}
    assert values["periods"]["b"]["totals"]=={"amount":770,"campaign_cost":175,"net_contribution":595,"orders":77}
    assert values["periods"]["a"]["cost_per_count"]=={"numerator":140,"denominator":70,"value":2}
    assert values["periods"]["b"]["cost_per_count"]=={"numerator":175,"denominator":77,"value":pytest.approx(175/77)}
    assert all(p["net_row_arithmetic"] and p["inclusive_days"]==7 for p in values["periods"].values())
    assert values["future_window_observed"] is False
    snapshot=snapshot_for_turn(loop);host=snapshot.as_dict()
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    assert len([c for c in claims if c["target"]["business_product"]["kind"]=="measurement"])==22
    assert len([c for c in claims if c["target"]["business_product"]["kind"]=="table"])==2
    original=next(c for c in host["claims"] if c["basis_refs"][0]["receipt_id"]==calc_id and c["basis_refs"][0]["result_path"]==["result_data"])
    assert original["value"]==values and original["unit"] is None
    assert original["basis_refs"][0]["data_identities"]["action_sales"]==loop.context.workspace.get_data_identity("action_sales")
    calls=[];service=PublicationService(snapshot,auditor=reviewer("accept",calls))
    answer=service.publish(raw(snapshot,RULE)).as_dict()
    assert len(calls)==1 and all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    referenced={cid for part in calls[0]["parts"] for cid in part["claim_refs"]}
    assert referenced=={original["id"]}
    assert referenced <= {c["id"] for c in calls[0]["claims"]}
    assert {c["id"] for c in calls[0]["claims"]} <= {c["id"] for c in host["claims"]}
    assert answer["source_snapshot"]["claims"]==host["claims"] and len(host["claims"])==25
    assert RULE in answer["body"] and has_number(answer["body"], "denominator", 77)
    assert has_pair(answer["body"], "future_window_observed", "false")
    forged=json.loads(raw(snapshot,RULE));forged["sections"][1]["parts"][0]["value"]={"count":1}
    refused=service.publish(encode(forged)).as_dict()
    assert any(i["code"]=="invalid_fields" for i in refused["issues"])
    assert original in refused["source_snapshot"]["claims"] and has_number(refused["body"], "denominator", 77)
    assert has_number(refused["body"], "net_contribution：差值", 35)


def test_stale_or_inconsistent_inputs_fail_closed_and_model_prose_has_no_authority(engine):
    loop,_,rid,_,calc_id,_=scenario(engine)
    snapshot=snapshot_for_turn(loop)
    proposal=json.loads(raw(snapshot,"成本每单高于本期也立即加预算。"))
    proposal["sections"][1]["parts"][-1]["rule_source_text"]="模型改写的规则"
    answer=PublicationService(snapshot).publish(encode(proposal)).as_dict()
    assert any(i["code"]=="invalid_fields" for i in answer["issues"])
    assert has_number(answer["body"], "net_contribution：差值", 35)
    frame=loop.context.workspace.get("action_sales").copy()
    frame.loc[0,"amount"] += 1
    loop.context.workspace.add("action_sales",frame)
    for old in (rid,calc_id):
        with pytest.raises(ValueError):resolve_native_claims(session_id=loop.session_id,receipt_id=old)
    assert snapshot_for_turn(loop).as_dict()["claims"]==[]
    for fault in ("wrong_net","uneven","zero_denominator"):
        loop,_,_,comparison,_,values=scenario(engine,fault=fault)
        if fault=="wrong_net":
            assert values["periods"]["a"]["net_row_arithmetic"] is False
            assert comparison["metrics"]["net_contribution"]["exact_aggregates"]["period_a"]==561
        if fault=="uneven":assert values["periods"]["b"]["inclusive_days"]==6
        if fault=="zero_denominator":
            assert values["periods"]["b"]["cost_per_count"]=={"numerator":175,"denominator":0,"value":None}
        snapshot=snapshot_for_turn(loop);calls=[]
        answer=PublicationService(snapshot,auditor=reviewer("reject",calls)).publish(raw(snapshot,"立即加预算。" )).as_dict()
        assert len(calls)==1 and "立即加预算。" not in answer["body"], {"fault":fault,"audit_status":answer["audit_status"],"issues":answer["issues"],"claim_bytes":len(encode(snapshot.as_dict()["claims"]).encode("utf-8")),"requirements":len(snapshot.as_dict()["requirements"])}
        assert has_number(answer["body"], "campaign_cost：后期", 175) if fault!="uneven" else has_number(answer["body"], "campaign_cost：后期", 150)
        assert all(o["status"]!="answered" for o in answer["requirement_outcomes"] if "未交付所需开放内容" in o["reason"])


def test_partial_user_span_never_turns_verified_numbers_into_action_coverage(engine):
    loop,_,_,_,_,_=scenario(engine)
    snapshot=snapshot_for_turn(loop);calls=[]
    partial="净贡献不低于基准期就小试。"
    answer=PublicationService(snapshot,auditor=reviewer("reject",calls)).publish(raw(snapshot,partial)).as_dict()
    assert len(calls)==1 and calls[0]["requirements"][1]["text"].endswith(RULE)
    assert partial not in answer["body"] and has_number(answer["body"], "net_contribution：后期", 595)
    assert answer["requirement_outcomes"][0]["status"]=="answered"
    assert answer["requirement_outcomes"][1]["status"]=="partial"
    from data_agent.session.history import load_canonical_history,push_messages
    push_messages(loop.session_id,[{"role":"user","content":"修改后的用户条件","request_id":"changed_rule"}])
    assert load_canonical_history(loop.session_id).revision!=snapshot.as_dict()["history_revision"]
    # Reusing the old closed-input draft against the new snapshot cannot grant coverage.
    changed=snapshot_for_turn(loop)
    refused=PublicationService(changed).publish(raw(snapshot,RULE)).as_dict()
    assert any(i["code"]=="stale_draft" for i in refused["issues"])
    assert has_number(refused["body"], "net_contribution：后期", 595)
    assert all(o["status"]!="answered" for o in refused["requirement_outcomes"][1:])


def test_same_turn_action_fragments_bind_as_one_ordered_current_rule(engine):
    loop,_,_,_,_,_=scenario(engine,fragments=True)
    snapshot=snapshot_for_turn(loop);host=snapshot.as_dict();calls=[]
    current=[r for r in host["requirements"] if "conditional_action" in r["open_purposes"]]
    assert len(current)==4 and current[0]["text"].endswith(RULE)
    full=PublicationService(snapshot,auditor=reviewer("accept",calls)).publish(raw(snapshot,RULE)).as_dict()
    assert len(calls)==1 and all(o["status"]=="answered" for o in full["requirement_outcomes"])
    assert [r["text"] for r in calls[0]["requirements"]][2:]==[r["text"] for r in current[1:]]
    # Reference order is no longer a prose-authority gate. All current rule
    # sources must still be delivered; omitted clauses cannot borrow coverage.
    reverse=json.loads(raw(snapshot,RULE));reverse["sections"].reverse()
    reordered=PublicationService(snapshot,auditor=reviewer("accept",[])).publish(encode(reverse)).as_dict()
    assert all(o["status"]=="answered" for o in reordered["requirement_outcomes"])
    omitted=PublicationService(snapshot,auditor=reviewer("accept",[])).publish(raw(snapshot,RULE,only={current[0]["id"]})).as_dict()
    outcomes={o["requirement_id"]:o["status"] for o in omitted["requirement_outcomes"]}
    assert outcomes[current[0]["id"]]=="answered" and all(outcomes[r["id"]]=="failed" for r in current[1:])
    forged=json.loads(raw(snapshot,RULE));forged["sections"][-1]["requirement_ids"]=["old_rule"]
    refused=PublicationService(snapshot,auditor=reviewer("accept",[])).publish(encode(forged)).as_dict()
    assert any(i["code"]=="unknown_requirement_ref" for i in refused["issues"])
    assert refused["requirement_outcomes"][-1]["status"]=="failed"
