from __future__ import annotations

from data_agent.agent.evidence_compatibility import compare_measurements
from data_agent.agent.verification import verify_analysis_claims


def _measurement(**overrides):
    measurement = {
        "metric": "conversion_rate",
        "definition": "Orders divided by product detail page visitors.",
        "value": 0.18,
        "unit": "ratio",
        "grain": "product_day",
        "time_scope": "2026-06-01 to 2026-06-07",
        "population_scope": "all product detail page visitors",
        "method": "aggregate ratio",
        "denominator": "visitors",
        "limitations": ["descriptive only"],
    }
    measurement.update(overrides)
    return measurement


def _evidence(**overrides):
    record = {
        "id": "ev_current",
        "plan_id": "plan_current",
        "step_id": "step_conversion",
        "claim_key": "conversion_rate",
        "claim": "Current conversion rate is 18%.",
        "dataset": "orders",
        "dataset_contract_id": "contract_orders",
        "method": "grouped aggregation",
        "tool_calls": [{"name": "run_python"}],
        "result_summary": "conversion_rate=0.18",
        "sample_size": 1000,
        "time_scope": "2026-06-01 to 2026-06-07",
        "calculation_method": "orders divided by visitors",
        "method_detail": "aggregated product-day visitors and orders",
        "limitations": ["descriptive only"],
        "confidence": "high",
        "evidence_requirement": "conversion_rate",
        "measurements": [_measurement()],
    }
    record.update(overrides)
    return record


def test_compare_measurements_accepts_identical_canonical_fields():
    result = compare_measurements(_measurement(value=0.18), _measurement(value=0.21))

    assert result.compatible is True
    assert result.reason_code == "compatible"
    assert result.fields == []


def test_compare_measurements_rejects_population_scope_mismatch():
    result = compare_measurements(
        _measurement(population_scope="all product detail page visitors"),
        _measurement(population_scope="new product detail page visitors"),
    )

    assert result.compatible is False
    assert result.reason_code == "population_scope_mismatch"
    assert result.fields == ["population_scope"]
    assert "统计对象不同" in result.user_message


def test_compare_measurements_rejects_missing_compatibility_fields():
    result = compare_measurements({}, {})

    assert result.compatible is False
    assert result.reason_code == "missing_measurement_field"
    assert result.fields


def test_verify_analysis_claims_rejects_explicit_evidence_id_outside_current_plan():
    report = verify_analysis_claims(
        claims=[{"id": "claim_1", "claim": "Current conversion rate is 18%.", "evidence_id": "ev_other"}],
        evidence_records=[
            _evidence(id="ev_other", plan_id="plan_other", claim="Current conversion rate is 18%.")
        ],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "fail"
    assert check["status"] == "failed"
    assert any("current plan" in issue for issue in check["issues"])


def test_verify_analysis_claims_rejects_explicit_nonexistent_evidence_id():
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_1",
            "claim": "Current conversion rate is 18%.",
            "evidence_id": "ev_missing",
        }],
        evidence_records=[_evidence(id="ev_current", claim="Current conversion rate is 18%.")],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "fail"
    assert check["status"] == "failed"
    assert check["strength"] == "unsupported"
    assert any("ev_missing" in issue for issue in check["issues"])


def test_verify_analysis_claims_rejects_incompatible_compare_evidence_ids():
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_compare",
            "claim": "Current and new-user conversion rates are comparable.",
            "compare_evidence_ids": ["ev_current", "ev_new_users"],
        }],
        evidence_records=[
            _evidence(id="ev_current"),
            _evidence(
                id="ev_new_users",
                claim="New-user conversion rate is 21%.",
                measurements=[_measurement(value=0.21, population_scope="new product detail page visitors")],
            ),
        ],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "fail"
    assert check["status"] == "failed"
    assert check["strength"] == "unsupported"
    assert any("Measurement compatibility failed" in issue for issue in check["issues"])


def test_verify_analysis_claims_accepts_compatible_compare_evidence_ids():
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_compare",
            "claim": "Current and comparison conversion rates are comparable.",
            "compare_evidence_ids": ["ev_current", "ev_comparison"],
        }],
        evidence_records=[
            _evidence(id="ev_current"),
            _evidence(id="ev_comparison", claim="Comparison conversion rate is 21%."),
        ],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "pass"
    assert check["status"] == "passed"
    assert check["evidence_id"] == "ev_current"
    assert check["issues"] == []


def test_verify_analysis_claims_rejects_compare_evidence_ids_with_malformed_measurements():
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_compare",
            "claim": "Malformed measurements are not comparable.",
            "compare_evidence_ids": ["ev_current", "ev_other"],
        }],
        evidence_records=[
            _evidence(id="ev_current", measurements=[{}]),
            _evidence(id="ev_other", claim="Other conversion rate is 21%.", measurements=[{}]),
        ],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "fail"
    assert check["status"] == "failed"
    assert check["strength"] == "unsupported"
    assert any("Measurement compatibility failed" in issue for issue in check["issues"])
