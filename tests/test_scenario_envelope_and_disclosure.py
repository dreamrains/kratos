"""Original scenario oracles migrated to actual receipts and v2 references.

The old r2 summary failed clause-local family pairing. Family/value order is
now host rendered from the original parameter receipt; free range summaries
are open interpretations. Fixed audit replies here verify orchestration only.
Historical test names remain for traceability, not lexical compatibility.
"""
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record
import json
import math
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine, execute
from tests.test_trusted_publication_runtime import request, draft
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode


@pytest.fixture
def scope(engine):
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":range(1,8),"rate":[.55,.42,.31,.24,.18,.13,.10]}))
    request(loop,"计算 D30 参数情景并解释范围",[{'kind':k,'scope':{'datasets':['orders'],'parameters':{'scenario_points':[30]}}} for k in ['series','fit','scenario']],kind="result",purposes=["interpretation"])
    rid,result=execute(loop,"curve_fitting",{"name":"orders","x_col":"day","y_col":"rate","scenario_points":[30]})
    snapshot=snapshot_for_turn(loop)
    claim=next(c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"]==["scenarios"])
    assert claim["basis_refs"][0]["receipt_id"]==rid and claim["value"]==result["scenarios"]
    return snapshot,result,claim


def _publish(scope, *, text=None, disposition="accept", reverse=False, extra=None):
    snapshot,_,claim=scope
    payload=json.loads(draft(snapshot))
    if extra is not None: payload["sections"][0]["parts"].append(extra)
    if text is not None:
        node={"kind":"text","purpose":"interpretation","text":text,"claim_refs":[claim["id"]]}
        payload["sections"][0]["parts"].insert(0 if reverse else len(payload["sections"][0]["parts"]),node)
    calls=[]
    def audit(candidate):
        calls.append(candidate)
        return {"schema":"publication_audit.v2","snapshot_digest":candidate["snapshot_digest"],"draft_digest":candidate["draft_digest"],
            "decisions":[{"part_id":p["part_id"],"disposition":disposition,"reason":"frozen scenario oracle",
                          "evidence_refs":p["requirement_ids"]+p["claim_refs"]} for p in candidate["parts"]]}
    answer=PublicationService(snapshot,auditor=audit).publish(encode(payload)).as_dict()
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert accepted=={cid for r in snapshot.as_dict()["requirements"] if not r["withdrawn"] for cid in r["claim_ids"]}
    assert answer["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]
    return answer,calls


class TestRangeEnvelope:
    def test_real_r2_summary_clause_publishes(self,scope):
        _,result,claim=scope
        rows=claim["value"]
        assert len(rows)==3 and {r["family"] for r in rows}=={"exponential","power","logarithmic"}
        for row in rows:
            fit=next(f for f in result["fits"] if f["family"]==row["family"])
            a,b=fit["parameters"]["a"],fit["parameters"]["b"]
            expected=a*math.exp(b*30) if row["family"]=="exponential" else a*30**b if row["family"]=="power" else a+b*math.log(30)
            assert row["value"]==pytest.approx(expected,abs=1e-12)
            assert row["parameters"]==fit["parameters"] and row["validation"]=="none"
        low,high=min(r["value"] for r in rows),max(r["value"] for r in rows)
        assert low<0<high and claim["unit"] is None
        text=f"三个模型在请求点的未验证参数情景范围为 {low!r} 到 {high!r}，不是未来真实值。"
        answer,calls=_publish(scope,text=text)
        assert text in answer["body"] and len(calls)==1
        assert next(c for c in calls[0]["claims"] if c["id"]==scope[2]["id"])=={k:scope[2][k] for k in ("id","label","value","unit","scope","limitations")}
        assert calls[0]["parts"][0]["claim_refs"]==[scope[2]["id"]]

    def test_range_outside_family_envelope_still_rejects(self,scope):
        # An invented free-prose endpoint is an open semantic violation.
        answer,calls=_publish(scope,text="三个模型 D30 的参数情景范围上界为 50%。",disposition="reject")
        assert len(calls)==1 and "上界为 50%" not in answer["body"]
        assert any(t["kind"]=="text" and t["disposition"]=="reject" for t in answer["render_trace"])

    def test_single_anonymous_value_outside_all_families_rejects(self,scope):
        answer,calls=_publish(scope,extra={"kind":"claim","ref":"invented-anonymous-D30-50-percent"})
        assert not calls and any(i["code"]=="unknown_claim_ref" for i in answer["issues"])
        assert "invented-anonymous-D30" not in answer["body"]


class TestBidirectionalPairing:
    @pytest.mark.parametrize("reverse",[False,True])
    def test_value_before_family_pairs_correctly(self,scope,reverse):
        text="以下表中各模型的数值只表示原参数在请求点的情景，不代表未来真实值。"
        answer,calls=_publish(scope,text=text,reverse=reverse)
        assert len(calls)==1 and text in answer["body"]
        trace=next(t for t in answer["render_trace"] if t["ref"]==scope[2]["id"])
        assert answer["body"][trace["start"]:trace["end"]]==trace["rendered_text"]
        assert all(has_record(trace["rendered_text"], {'模型族':row['family'], '情景值（原值）':row['value'], '验证状态':row['validation']}) for row in scope[2]['value'])

    def test_value_before_family_wrong_number_rejects(self,scope):
        # A model cannot supply its own value even with a legitimate host ID.
        answer,_=_publish(scope,extra={"kind":"claim","ref":scope[2]["id"],"value":.05})
        assert any(i["code"]=="invalid_fields" for i in answer["issues"])
        assert answer["source_snapshot"]["claims"]==scope[0].as_dict()["claims"]


class TestDisclosureRegexesRetired:
    def test_scenario_passes_without_prose_disclosures(self,scope):
        answer,calls=_publish(scope)
        assert not calls and answer["audit_status"]=="not_applicable"
        assert has_record(answer["body"], {'状态':'unvalidated'})
        assert "未来真实值未知" in answer["body"] and "不裁剪负值" in answer["body"]

    def test_true_violation_still_rejected_without_disclosures(self,scope):
        answer,calls=_publish(scope,text="D30 真实值为 9.9%。",disposition="reject")
        assert len(calls)==1 and "真实值为 9.9%" not in answer["body"]
        assert answer["requirement_outcomes"][0]["status"]=="partial"


class TestHostRenderedDisclosure:
    def test_appendix_renders_disclosure_for_scenario_sources(self,scope):
        answer,_=_publish(scope)
        assert "没有留出、回测或外部验证" in answer["body"]
        assert all(r["observed_x_range"]==[1,7] and r["x"]==30 for r in scope[2]["value"])
        assert next(r for r in scope[2]["value"] if r["family"]=="logarithmic")["value"]<0

    def test_appendix_without_scenario_sources_has_no_disclosure(self,engine):
        loop,_=engine
        request(loop,"描述当前数据",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
        execute(loop,"describe_dataset",{"name":"orders"})
        snapshot=snapshot_for_turn(loop)
        answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
        assert all(c["basis_refs"][0]["tool_name"]=="describe_dataset" for c in snapshot.as_dict()["claims"])
        assert "参数情景" not in answer["body"] and not has_record(answer["body"], {'状态':'unvalidated'})
