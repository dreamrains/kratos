import json

from data_agent.agent.evidence_contracts import validate_derived_measurements
from data_agent.agent.publication_synthesis import (
    apply_answer_binding_coverage,
    parse_answer_bindings,
    render_bound_claims,
    validate_final_narrative_issues,
)


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


def _bound_packet(measurements, derived):
    return {
        "snapshot_digest": "sha256:packet",
        "requirements": [{"id": "rq_count", "label": "留存人数"}],
        "sources": [],
        "publication_scope": [],
        "evidence": [{"evidence_id": "ev1", "measurements": measurements, "derived_measurements": [derived]}],
    }


def _with_binding(packet, visible):
    return visible + "\n```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1",
        "packet_digest": packet["snapshot_digest"],
        "blocks": [{
            "exact_text": visible,
            "requirement_refs": ["rq_count"],
            "fact_refs": [],
            "derived_refs": ["dm_result"],
        }],
    }, ensure_ascii=False) + "\n```"


def test_ac22_bound_product_rejects_tenfold_display_and_accepts_integer_rounding():
    measurements = [_measurement("population", 22400), _measurement("rate", "0.051", "ratio")]
    derived = _derived("product", ["population", "rate"], "1142.4", "count")
    assert validate_derived_measurements([derived], measurements).ok
    packet = _bound_packet(measurements, derived)
    bad_clean, bad_bindings, _ = parse_answer_bindings(_with_binding(packet, "留存人数约1.14万人。"), packet)
    packet["answer_bindings"] = bad_bindings
    assert any(issue["code"] == "derived_display_mismatch" for issue in validate_final_narrative_issues(bad_clean, packet))
    good_clean, good_bindings, _ = parse_answer_bindings(_with_binding(packet, "留存人数约1142人。"), packet)
    packet["answer_bindings"] = good_bindings
    apply_answer_binding_coverage(packet, good_bindings)
    assert not [issue for issue in validate_final_narrative_issues(good_clean, packet) if issue["code"] == "derived_display_mismatch"]


def test_ac23_small_rate_product_rejects_3200_and_accepts_317():
    measurements = [_measurement("population", 22400), _measurement("rate", "0.01417", "ratio")]
    derived = _derived("product", ["population", "rate"], "317.408", "count")
    packet = _bound_packet(measurements, derived)
    clean, bindings, _ = parse_answer_bindings(_with_binding(packet, "留存人数约3200人。"), packet)
    packet["answer_bindings"] = bindings
    assert any(issue["code"] == "derived_display_mismatch" for issue in validate_final_narrative_issues(clean, packet))
    clean, bindings, _ = parse_answer_bindings(_with_binding(packet, "留存人数约317人。"), packet)
    packet["answer_bindings"] = bindings
    assert not [issue for issue in validate_final_narrative_issues(clean, packet) if issue["code"] == "derived_display_mismatch"]


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
    packet = {"publication_scope": [], "requirements": []}
    text = "2026-09-07使用版本v2。原文‘22400人×5.1%约1.14万人’是错误说法；正确约1142人。"
    assert not [issue for issue in validate_final_narrative_issues(text, packet) if issue["code"] == "arithmetic_mismatch"]


def test_ac27_cross_version_operands_and_unlabelled_scenario_fail():
    mixed = [_measurement("a", 10, identity="v1"), _measurement("b", 12, identity="v2")]
    result = validate_derived_measurements([_derived("difference", ["a", "b"], -2, "count")], mixed)
    assert result.error_type == "derived_source_mismatch"

    same = [_measurement("a", 10), _measurement("b", 12)]
    scenario = _derived("difference", ["a", "b"], -2, "count", scenario=True)
    packet = _bound_packet(same, scenario)
    clean, bindings, _ = parse_answer_bindings(_with_binding(packet, "留存人数为-2人。"), packet)
    packet["answer_bindings"] = bindings
    assert any(issue["code"] == "scenario_label_missing" for issue in validate_final_narrative_issues(clean, packet))


def test_ac29_multiple_issue_classes_are_returned_together():
    packet = {
        "publication_scope": [],
        "requirements": [{"id": "rq_repeat", "label": "复购率"}],
    }
    issues = validate_final_narrative_issues("22400人×5.1%=1.14万人。", packet)
    assert {issue["code"] for issue in issues} >= {"arithmetic_mismatch", "missing_answer_requirement"}


def _tool_owned_derived_packet():
    packet = _bound_packet(
        [_measurement("population", 22400), _measurement("rate", "0.051", "ratio")],
        _derived("product", ["population", "rate"], "1142.4", "count"),
    )
    packet["sources"] = [{
        "receipt_id": "tr_result",
        "facts": [{
            "fact_id": "f_retained_count", "path": "留存人数.value",
            "value": "1142.4", "unit": "unknown",
        }],
    }]
    packet["evidence"][0]["tool_receipt_ids"] = ["tr_result"]
    return packet


def _typed_derived_text(packet):
    placeholder = "[[claim:claim_retained_count]]"
    return placeholder + "\n```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1",
        "packet_digest": packet["snapshot_digest"],
        "blocks": [{
            "claim_id": "claim_retained_count", "claim_type": "derived_metric",
            "status": "computed", "unit_status": "not_confirmed",
            "exact_text": placeholder,
            "requirement_refs": ["rq_count"],
            "fact_refs": ["f_retained_count"],
            "derived_refs": ["dm_result"],
        }],
    }, ensure_ascii=False) + "\n```"


def test_cr03_derived_metric_needs_tool_owned_metric_fact_and_host_rendering():
    packet = _tool_owned_derived_packet()
    clean, bindings, issues = parse_answer_bindings(_typed_derived_text(packet), packet)
    assert not issues
    packet["answer_bindings"] = bindings
    assert not validate_final_narrative_issues(clean, packet)
    assert packet["requirements"][0]["answer_coverage"] == "answered"
    assert "留存人数：1142.4" in render_bound_claims(clean, packet, bindings)


def test_cr03_model_label_alone_cannot_make_unrelated_fact_a_derived_answer():
    packet = _tool_owned_derived_packet()
    packet["sources"][0]["facts"][0]["path"] = "收入.value"
    assert any(
        issue["code"] == "invalid_derived_binding"
        for issue in parse_answer_bindings(_typed_derived_text(packet), packet)[2]
    )


def test_cr03_derived_result_must_match_tool_fact_and_receipt_link():
    packet = _tool_owned_derived_packet()
    packet["sources"][0]["facts"][0]["value"] = "999"
    assert any(
        issue["code"] == "invalid_derived_binding"
        for issue in parse_answer_bindings(_typed_derived_text(packet), packet)[2]
    )
    packet = _tool_owned_derived_packet()
    packet["evidence"][0]["tool_receipt_ids"] = []
    assert any(
        issue["code"] == "invalid_derived_binding"
        for issue in parse_answer_bindings(_typed_derived_text(packet), packet)[2]
    )


def test_cr03_derived_binding_rejects_cross_version_operands_and_unit_promotion():
    packet = _tool_owned_derived_packet()
    packet["evidence"][0]["measurements"][1]["data_identity"] = "v2"
    assert any(
        issue["code"] == "invalid_derived_binding"
        for issue in parse_answer_bindings(_typed_derived_text(packet), packet)[2]
    )
    packet = _tool_owned_derived_packet()
    promoted = _typed_derived_text(packet).replace('"unit_status": "not_confirmed"', '"unit_status": "confirmed"')
    assert any(
        issue["code"] == "invalid_derived_binding"
        for issue in parse_answer_bindings(promoted, packet)[2]
    )


def test_cr03_derived_operands_must_match_current_tool_dataset_version():
    packet = _tool_owned_derived_packet()
    packet["sources"][0]["data_identities"] = {"orders": {"version_id": "v2", "fingerprint": "hash_v2"}}
    assert any(
        issue["code"] == "invalid_derived_binding"
        for issue in parse_answer_bindings(_typed_derived_text(packet), packet)[2]
    )
    packet["sources"][0]["data_identities"]["orders"]["version_id"] = "v1"
    assert not parse_answer_bindings(_typed_derived_text(packet), packet)[2]


def test_cr03_unrelated_measurement_version_does_not_block_owned_derivation():
    packet = _tool_owned_derived_packet()
    packet["sources"][0]["data_identities"] = {"orders": {"version_id": "v1"}}
    packet["evidence"][0]["measurements"].append(_measurement("unrelated", 8, identity="v2"))
    assert not parse_answer_bindings(_typed_derived_text(packet), packet)[2]


def test_cr03_derived_zero_remains_a_computed_result():
    packet = _tool_owned_derived_packet()
    packet["sources"][0]["facts"][0]["value"] = 0
    packet["evidence"][0]["measurements"][1]["value"] = 0
    packet["evidence"][0]["derived_measurements"][0]["result"] = 0
    clean, bindings, issues = parse_answer_bindings(_typed_derived_text(packet), packet)
    assert not issues
    packet["answer_bindings"] = bindings
    assert not validate_final_narrative_issues(clean, packet)
    assert "留存人数：0" in render_bound_claims(clean, packet, bindings)
