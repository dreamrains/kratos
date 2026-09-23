"""Phase 5 offline protocol: semantic findings never grant publication authority."""

from copy import deepcopy

from data_agent.agent.publication_audit import validate_shadow_audit


def _packet():
    return {
        "snapshot_digest": "sha256:current-snapshot",
        "answer_sha256": "sha256:accepted-answer",
        "sources": [{"receipt_id": "tr_m02", "tool_name": "curve_fitting"},
                    {"receipt_id": "tr_unrelated", "tool_name": "basic_stats"}],
        "publication_scope": [{
            "receipt_id": "tr_m02", "tool": "curve_fitting",
            "observed_x_range": [1.0, 7.0], "unit_status": "not_confirmed",
            "claim_ceiling": "descriptive", "scenario_extrapolation": {
                "status": "descriptive_fit_only", "validation": "none",
                "models": [{
                    "family": "exponential",
                    "parameters": {"a": 0.73892193, "b": -0.28583215},
                    "r_squared": 0.99946726,
                }],
            },
        }],
        "answer_bindings": {
            "schema_version": "answer_bindings.v1",
            "packet_digest": "sha256:current-snapshot",
            "blocks": [{
                "claim_id": "claim_m02_d30",
                "exact_text": "[[claim:claim_m02_d30]]",
                "claim_type": "scenario_extrapolation",
                "status": "unvalidated",
                "unit_status": "not_confirmed",
                "validation_status": "none",
                "receipt_ref": "tr_m02",
                "time_point": 30,
                "families": ["exponential"],
                "requirement_refs": [],
                "fact_refs": [],
                "derived_refs": [],
            }],
        },
    }


def _audit(*, claim_id="claim_m02_d30", evidence_refs=None,
           action="downgrade", dimension="claim_strength", **changes):
    raw = {
        "schema_version": "publication_audit.v1",
        "packet_digest": "sha256:current-snapshot",
        "answer_sha256": "sha256:accepted-answer",
        "overall": "pass_with_findings",
        "findings": [{
            "finding_id": "finding_001",
            "claim_id": claim_id,
            "dimension": dimension,
            "severity": "high",
            "recommended_action": action,
            "evidence_refs": ["tr_m02"] if evidence_refs is None else evidence_refs,
            "reason": "仅有描述拟合，未做留出验证。",
        }],
        "missing_requirements": [],
        "contradictions": [],
    }
    raw.update(changes)
    return raw


def test_bound_r4_m02_finding_is_shadow_only_and_does_not_mutate_packet():
    packet = _packet()
    before = deepcopy(packet)
    result = validate_shadow_audit(_audit(), packet)
    assert result["status"] == "valid"
    assert result["findings"][0]["suggested_action"] == "downgrade"
    assert result["publication_effect"] == "none"
    assert packet == before


def test_even_bound_remove_recommendation_cannot_delete_correct_r4_m02_claim():
    packet = _packet()
    before = deepcopy(packet)
    result = validate_shadow_audit(_audit(action="remove"), packet)
    assert result["findings"][0]["suggested_action"] == "remove"
    assert result["publication_effect"] == "none"
    assert packet == before


def test_unbound_or_foreign_finding_can_only_be_advisory():
    for raw in (
        _audit(evidence_refs=[]),
        _audit(evidence_refs=["tr_unrelated"]),
        _audit(evidence_refs=["tr_m02", "tr_unrelated"]),
        _audit(claim_id="claim_not_in_packet"),
    ):
        result = validate_shadow_audit(raw, _packet())
        assert result["status"] == "valid"
        assert result["findings"][0]["suggested_action"] == "advisory_only"


def test_model_overall_pass_cannot_override_deterministic_failure():
    packet = _packet()
    packet["deterministic_issues"] = [{"code": "invalid_scenario_binding"}]
    result = validate_shadow_audit(_audit(overall="pass", findings=[]), packet)
    assert result["status"] == "valid"
    assert result["reported_overall"] == "pass"
    assert result["publication_effect"] == "none"
    assert packet["deterministic_issues"] == [{"code": "invalid_scenario_binding"}]


def test_stale_answer_or_packet_rejects_audit_not_answer():
    for raw in (_audit(packet_digest="sha256:old"), _audit(answer_sha256="sha256:old")):
        result = validate_shadow_audit(raw, _packet())
        assert result["status"] == "invalid"
        assert result["publication_effect"] == "none"


def test_invalid_dimension_action_and_unscoped_extra_facts_are_not_accepted():
    for raw in (
        _audit(dimension="approve_everything"),
        _audit(action="replace_answer"),
        _audit(missing_requirements=["new business fact"]),
        _audit(schema_version="publication_audit.v2"),
    ):
        result = validate_shadow_audit(raw, _packet())
        assert result["status"] == "invalid"
        assert result["publication_effect"] == "none"


def test_generic_binding_without_typed_claim_id_cannot_grant_action():
    packet = _packet()
    packet["answer_bindings"]["blocks"] = [{
        "exact_text": "已观察 D7 结果",
        "fact_refs": ["fact_1"],
        "derived_refs": [],
    }]
    result = validate_shadow_audit(_audit(), packet)
    assert result["status"] == "valid"
    assert result["findings"][0]["suggested_action"] == "advisory_only"
