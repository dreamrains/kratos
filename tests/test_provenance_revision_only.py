"""Original provenance oracles on the approved single v2 publication path.

SHA/current identity proves which bytes were measured, not real-world origin.
Historical function names are retained. The old automatic revision exemption
and lexicon annotation are retired; a bounded audit handles open provenance.
These fixed decisions test localization/budget, not natural semantic quality.
"""
import json
from tests.test_trusted_publication_semantics import engine, execute
from tests.test_trusted_publication_runtime import request, draft
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode

ORIGIN_CLAUSE="这份文件的取值特征表明它是典型模板/占位符特征的数据。"


def _source(engine):
    loop,_=engine
    request(loop,"描述当前数据并说明来源边界",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}},kind="result",purposes=["interpretation"])
    rid,_=execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    claim=next(c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"]==["shape","rows"])
    assert claim["value"]==12 and claim["basis_refs"][0]["receipt_id"]==rid
    return snapshot,claim


def _proposal(snapshot,claim,text):
    payload=json.loads(draft(snapshot))
    payload["sections"][0]["parts"].append({"kind":"text","purpose":"interpretation","text":text,"claim_refs":[claim["id"]]})
    return payload


def _auditor(calls,disposition):
    def audit(candidate):
        calls.append(candidate)
        return {"schema":"publication_audit.v2","snapshot_digest":candidate["snapshot_digest"],"draft_digest":candidate["draft_digest"],
            "decisions":[{"part_id":p["part_id"],"disposition":disposition,"reason":"original bytes do not establish real-world provenance",
                          "evidence_refs":p["requirement_ids"]+p["claim_refs"]} for p in candidate["parts"]]}
    return audit


def _assert_preserved(answer,snapshot):
    assert answer["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]
    assert {t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}=={cid for r in snapshot.as_dict()["requirements"] for cid in r["claim_ids"]}


def test_origin_finding_is_revision_only_classification(engine):
    snapshot,claim=_source(engine)
    calls=[]
    service=PublicationService(snapshot,auditor=_auditor(calls,"reject"))
    payload=_proposal(snapshot,claim,ORIGIN_CLAUSE)
    first=service.publish(encode(payload)).as_dict()
    assert ORIGIN_CLAUSE not in first["body"] and len(calls)==1
    assert first["requirement_outcomes"][0]["status"]=="partial"
    _assert_preserved(first,snapshot)
    assert service.publish(encode(payload)).as_dict()==first and len(calls)==1
    payload["sections"][0]["parts"][-1]["text"]="修订后仍断定是占位符数据。"
    second=service.publish(encode(payload)).as_dict()
    assert "修订后仍断定" not in second["body"] and len(calls)==1
    assert second["audit_status"]=="unavailable"
    _assert_preserved(second,snapshot)


def test_closed_class_findings_still_block_every_pass(engine):
    snapshot,claim=_source(engine)
    calls=[]
    service=PublicationService(snapshot,auditor=_auditor(calls,"accept"))
    for wrong in (99,999):
        payload=json.loads(draft(snapshot))
        payload["sections"][0]["parts"].append({"kind":"claim","ref":claim["id"],"value":wrong})
        answer=service.publish(encode(payload)).as_dict()
        assert any(i["code"]=="invalid_fields" for i in answer["issues"])
        _assert_preserved(answer,snapshot)
        assert next(c for c in answer["source_snapshot"]["claims"] if c["id"]==claim["id"])["value"]==12
    assert not calls


def test_appendix_renders_host_provenance_annotation(engine):
    snapshot,claim=_source(engine)
    text="当前回执对应的文件字节可核；其真实业务来源未经证实。"
    calls=[]
    answer=PublicationService(snapshot,auditor=_auditor(calls,"accept")).publish(encode(_proposal(snapshot,claim,text))).as_dict()
    assert text in answer["body"] and len(calls)==1
    assert all(c["unit"]!="provenance_status" for c in snapshot.as_dict()["claims"])
    _assert_preserved(answer,snapshot)


def test_appendix_without_flag_has_no_provenance_annotation(engine):
    snapshot,_=_source(engine)
    answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    assert ORIGIN_CLAUSE not in answer["body"] and "真实业务来源" not in answer["body"]
    assert answer["audit_status"]=="not_applicable"
    _assert_preserved(answer,snapshot)
