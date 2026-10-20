"""Missing named data is a host gap from current inventory, never a prose claim."""
import json
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode


def test_missing_named_dataset_renders_one_concrete_host_action(engine):
    loop,_=engine
    request(loop,"分析 missing_orders 并只给一个具体下一步",{'kind': 'measurement', 'scope': {'datasets': ['missing_orders'], 'quantity': 'rows'}})
    snapshot=snapshot_for_turn(loop)
    from tests.test_trusted_publication_pipeline import accept_all
    from tests.support.rendered_text import visible_text
    proposal=json.loads(draft(snapshot))
    proposal["sections"][0]["parts"].append({"kind":"text","purpose":"conditional_action","text":"下一步：请上传 missing_orders 对应文件。","claim_refs":[]})
    reviews=[]
    def review(value):reviews.append(value);return accept_all(value)
    answer=PublicationService(snapshot,auditor=review).publish(encode(proposal)).as_dict()
    assert snapshot.as_dict()["claims"]==[]
    assert answer["requirement_outcomes"][0]["status"]=="evidence_insufficient"
    assert "missing_orders" in visible_text(answer["body"]) and "缺少" in answer["body"]
    assert answer["body"].count("下一步：请上传")==1 and "上传" in answer["body"]
    assert len([t for t in answer["render_trace"] if t["kind"]=="gap"])==1
    assert not any(t["kind"]=="claim" for t in answer["render_trace"])
    assert len(reviews)==1 and any(t.get("semantic_reviewed") for t in answer["render_trace"] if t["kind"]=="text")


def test_missing_dataset_claim_rejects_existing_target_and_tampered_inventory(engine):
    loop,_=engine
    request(loop,"分析 orders",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    before=snapshot_for_turn(loop)
    assert before.as_dict()["requirements"][0]["gap"]["status"]=="not_computed"
    assert "没有数据集" not in before.as_dict()["requirements"][0]["gap"]["reason"]
    execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop)
    payload=json.loads(draft(current));payload["available_datasets"]=["zeta"]
    answer=PublicationService(current).publish(encode(payload)).as_dict()
    assert answer["issues"] and next(c for c in current.as_dict()["claims"] if c["label"]=="记录数")["value"]==12
    assert answer["requirement_outcomes"][0]["status"]=="answered"


def test_missing_dataset_claim_requires_current_structured_target_binding(engine):
    loop,_=engine
    request(loop,"分析 missing_orders")
    unspecified=snapshot_for_turn(loop)
    assert unspecified.as_dict()["claims"]==[]
    assert "下一步：" not in unspecified.as_dict()["requirements"][0]["gap"]["reason"]
    assert unspecified.as_dict()["requirements"][0]["gap"]["status"]=="not_computed"
    # Only an explicit typed dataset target can identify a missing data action.
    request(loop,"分析指定 missing_orders",{'kind': 'measurement', 'scope': {'datasets': ['missing_orders'], 'quantity': 'rows'}})
    current=snapshot_for_turn(loop)
    targeted=next(r for r in current.as_dict()["requirements"] if r["text"]=="分析指定 missing_orders")
    assert "missing_orders" in targeted["gap"]["reason"] and "下一步：" in targeted["gap"]["reason"]
