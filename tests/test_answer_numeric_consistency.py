import json


from data_agent.agent.evidence_contracts import validate_derived_measurements

from tests.test_trusted_publication_semantics import engine


def _measurement(mid, value, unit="count", identity="v1"):

    return {

        "id": mid,

        "metric": mid,

        "definition": mid,

        "value": value,

        "unit": unit,

        "grain": "user",

        "population_scope": "new users",

        "time_scope": "2026-09",

        "method": "computed",

        "denominator": "all new users",

        "limitations": [],

        "data_identity": identity,

    }


def _derived(operation, refs, result, unit, *, scenario=False):

    return {

        "id": "dm_result",

        "operation": operation,

        "operand_refs": refs,

        "result": result,

        "unit": unit,

        "scale": "1",

        "rounding": "nearest displayed precision",

        "scope_ref": "new_users_2026_09",

        "scenario": scenario,

    }


def test_ac22_bound_product_rejects_tenfold_display_and_accepts_integer_rounding(engine):
    _actual_product(engine,"0.051",1142,"1.14万人")


def test_ac23_small_rate_product_rejects_3200_and_accepts_317(engine):
    _actual_product(engine,"0.01417",317,"3200人")


def test_ac24_percentage_points_and_relative_percent_are_different_operations():

    measurements = [_measurement("ordinary", "0.16803", "ratio"), _measurement("weighted", "0.17080", "ratio")]

    pp = _derived("percentage_point_change", ["ordinary", "weighted"], "0.277", "percentage_point")

    relative = _derived("percent_change", ["ordinary", "weighted"], "1.648515146104862", "percent")

    assert validate_derived_measurements([pp], measurements).ok

    assert validate_derived_measurements([relative], measurements).ok

    wrong = dict(relative, result="0.277")

    assert validate_derived_measurements([wrong], measurements).error_type == "derived_result_mismatch"


def test_ac25_undefined_and_nonfinite_derivations_fail_closed():

    zero = [_measurement("a", 0, "ratio"), _measurement("b", 1, "ratio")]

    assert validate_derived_measurements([_derived("ratio", ["b", "a"], 0, "ratio")], zero).error_type == "undefined_derived_measurement"

    assert validate_derived_measurements([_derived("ratio", ["a", "b"], "NaN", "ratio")], zero).error_type == "invalid_derived_result"

    negative = [_measurement("a", -2, "count"), _measurement("b", 1, "count")]

    assert validate_derived_measurements([_derived("percent_change", ["a", "b"], -150, "percent")], negative).error_type == "undefined_derived_measurement"

    mixed = [_measurement("a", 1, "CNY"), _measurement("b", 2, "USD")]

    assert validate_derived_measurements([_derived("sum", ["a", "b"], 3, "currency")], mixed).error_type == "derived_unit_mismatch"


def test_ac26_dates_versions_and_quoted_corrections_are_not_new_arithmetic_claims():
    from data_agent.agent.publication.contracts import HostSnapshot,encode
    from data_agent.agent.publication.service import PublicationService
    requirement={"id":"rq_knowledge","text":"解释舍入示例","source_turn":"actual_request",
        "claim_ids":[],"artifact_ids":[],"open_purposes":["knowledge"],"gap":None,"withdrawn":False}
    snapshot=HostSnapshot.freeze(session_id="knowledge",turn_id="example",history_revision=1,requirement_revision=1,
        mode="consultation",requirements=[requirement],claims=[],artifacts=[],data_identities={})
    text="2026-09-07使用版本v2。原文‘22400人×5.1%约1.14万人’是错误说法；正确约1142人。"
    answer=PublicationService(snapshot).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,
        "sections":[{"requirement_ids":["rq_knowledge"],"parts":[{"kind":"text","purpose":"knowledge","text":text,"claim_refs":[]}]}]})).as_dict()
    assert answer["body"].startswith(text) and answer["source_snapshot"]["claims"]==[]
    assert answer["audit_status"]=="not_applicable" and answer["issues"]==[]


def test_ac27_cross_version_operands_and_unlabelled_scenario_fail(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    import pandas as pd
    mixed=[_measurement("a",10,identity="v1"),_measurement("b",12,identity="v2")]
    assert validate_derived_measurements([_derived("difference",["a","b"],-2,"count")],mixed).error_type=="derived_source_mismatch"
    loop,_=engine
    loop.context.workspace.add("retention",pd.DataFrame({"day":range(1,8),"value":[.55,.42,.31,.24,.18,.13,.1]}))
    request(loop,"显示未验证参数情景",{'kind': 'series', 'scope': {'datasets': ['retention'], 'parameters': {'scenario_points': [30]}}})
    execute(loop,"curve_fitting",{"name":"retention","x_col":"day","y_col":"value","scenario_points":[30]})
    snapshot=snapshot_for_turn(loop);answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    scenario=next(c for c in answer["source_snapshot"]["claims"] if c["target"].get("statistic")=="scenario")
    assert "未验证参数情景" in answer["body"] and "未来真实值未知" in answer["body"]
    assert all(row["validation"]=="none" and row["status"]=="unvalidated" for row in scenario["value"])
    assert any(row["value"]<0 for row in scenario["value"])


def test_ac29_multiple_issue_classes_are_returned_together(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.contracts import encode
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import request
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    request(loop,"计算记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);rid=snapshot.as_dict()["requirements"][0]["id"]
    answer=PublicationService(snapshot).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,
        "sections":[{"requirement_ids":["foreign_requirement"],"parts":[]},
                    {"requirement_ids":[rid],"parts":[{"kind":"claim","ref":"foreign_claim"}]}]})).as_dict()
    assert {i["code"] for i in answer["issues"]}=={"unknown_requirement_ref","unknown_claim_ref"}
    assert any(c["label"]=="记录数" and c["value"]==12 for c in answer["source_snapshot"]["claims"])
    assert answer["requirement_outcomes"][0]["status"]=="answered"


def _actual_product(engine,rate,expected_rounded,wrong_display):
    from decimal import Decimal
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.contracts import encode
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    loop.context.workspace.add("population",pd.DataFrame({"population":[22400],"rate":[float(rate)]}))
    request(loop,"计算当前留存人数示例",{'kind': 'table', 'scope': {'datasets': ['population']}})
    execute(loop,"run_python",{"code":"df=get_dataset('population')\nvalue=float(df['population'].iloc[0])*float(df['rate'].iloc[0])\nresult={'rounded_count':round(value),'raw_product':value}\nresult"})
    snapshot=snapshot_for_turn(loop);host=snapshot.as_dict();cid=host["claims"][0]["id"];rid=host["requirements"][0]["id"]
    value=host["claims"][0]["value"]
    assert value["rounded_count"]==expected_rounded==round(Decimal(22400)*Decimal(rate))
    assert abs(Decimal(str(value["raw_product"]))-Decimal(22400)*Decimal(rate))<Decimal("0.000000001")
    bad=encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":[{"requirement_ids":[rid],
        "parts":[{"kind":"claim","ref":cid,"value":wrong_display}]}]})
    rejected=PublicationService(snapshot).publish(bad).as_dict()
    assert rejected["issues"] and rejected["source_snapshot"]["claims"][0]["value"]==value
    assert wrong_display not in rejected["body"]
    accepted=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    assert accepted["issues"]==[] and accepted["requirement_outcomes"][0]["status"]=="answered"
    assert accepted["source_snapshot"]["claims"][0]["value"]==value
