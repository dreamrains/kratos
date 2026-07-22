from data_agent.agent.verification import verify_analysis_claims


def _evidence(**overrides):
    value = {
        "id": "ev_effect",
        "claim": "The campaign caused revenue to increase.",
        "dataset": "orders",
        "method": "difference_in_differences",
        "sample_size": 2000,
        "time_scope": "2026-Q1 to 2026-Q2",
        "calculation_method": "difference in differences",
        "method_detail": "treated versus control before and after",
        "limitations": ["causal interpretation depends on identification assumptions"],
        "confidence": "medium",
        "confidence_interval": {"level": 0.95, "lower": 0.01, "upper": 0.08},
        "identification_status": {
            "status": "identified",
            "design_type": "difference_in_differences",
            "allowed_claim_class": "causal",
        },
        "comparison_group": "untreated stores",
        "parallel_trends": {"status": "passed", "reason": "pre-period slopes were compatible"},
        "treatment_timing": "2026-04-01",
    }
    value.update(overrides)
    return value


def _check(claim, evidence):
    return verify_analysis_claims(
        claims=[{"text": claim, "evidence_id": evidence["id"]}],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
    )["claim_checks"][0]


def test_pre_post_without_control_cannot_publish_causal_language():
    evidence = _evidence(
        method="before_after_comparison",
        identification_status={
            "status": "not_identified",
            "design_type": "pre_post",
            "allowed_claim_class": "association",
        },
        alternative_explanations=["seasonality", "concurrent promotions"],
    )

    check = _check("The campaign caused revenue to increase.", evidence)

    assert check["status"] == "failed"
    assert check["strength"] == "unsupported"
    assert any("not identify" in issue.lower() for issue in check["issues"])


def test_randomized_claim_without_assignment_unit_is_blocked():
    evidence = _evidence(
        method="randomized experiment",
        identification_status={
            "status": "identified",
            "design_type": "randomized_experiment",
            "allowed_claim_class": "causal",
        },
        treatment_arms=["control", "treatment"],
        exposure_definition="assigned campaign",
        outcome_definition="30-day revenue",
        per_arm_sample_size={"control": 500, "treatment": 500},
        randomization_integrity={"status": "passed"},
        balance_diagnostics={"status": "passed"},
        attrition={"status": "assessed", "rate": 0.02},
    )

    check = _check("Random assignment caused revenue to increase.", evidence)

    assert check["status"] == "failed"
    assert any("assignment_unit" in issue for issue in check["issues"])


def test_did_claim_requires_parallel_trends_diagnostic():
    evidence = _evidence(parallel_trends={"status": "not_estimable", "reason": "one pre period"})

    check = _check("The campaign caused revenue to increase.", evidence)

    assert check["status"] == "failed"
    assert any("parallel_trends" in issue for issue in check["issues"])


def test_identified_did_claim_passes_when_diagnostics_are_present():
    check = _check("The campaign caused revenue to increase.", _evidence())

    assert check["status"] == "passed"
    assert check["issues"] == []


def test_observational_comparison_can_publish_bounded_association():
    evidence = _evidence(
        claim="Campaign exposure was associated with higher revenue.",
        method="adjusted observational comparison",
        identification_status={
            "status": "not_identified",
            "design_type": "observational_comparison",
            "allowed_claim_class": "association",
        },
        alternative_explanations=["self-selection", "baseline demand"],
    )

    check = _check("Campaign exposure was associated with higher revenue.", evidence)

    assert check["status"] == "passed"
    assert check["strength"] == "likely"
