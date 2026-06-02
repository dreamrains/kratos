from data_agent.agent.verification import verify_analysis_claims


def _complete_evidence(**overrides):
    evidence = {
        "id": "ev_1",
        "claim": "Revenue increased 12% in May",
        "dataset": "sales",
        "method": "period_compare",
        "sample_size": 1200,
        "time_scope": "2026-05-01 to 2026-05-31",
        "calculation_method": "monthly revenue delta",
        "method_detail": "compared May revenue against April revenue",
        "limitations": ["descriptive comparison only"],
    }
    evidence.update(overrides)
    return evidence


def test_claim_without_evidence_fails_as_unsupported():
    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[],
        route_proposals=[],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert report["id"].startswith("verify_")
    assert report["overall_status"] == "fail"
    assert check["status"] == "failed"
    assert check["strength"] == "unsupported"
    assert any("No evidence record" in issue for issue in check["issues"])


def test_causal_wording_without_causal_method_is_downgraded_in_english_and_chinese():
    report = verify_analysis_claims(
        claims=["Discount caused higher revenue", "渠道变化导致 GMV 下滑"],
        evidence_records=[
            _complete_evidence(id="ev_1", claim="Discount caused higher revenue", method="period_compare"),
            _complete_evidence(id="ev_2", claim="渠道变化导致 GMV 下滑", method="correlation"),
        ],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["overall_status"] == "pass_with_downgrades"
    for check in report["claim_checks"]:
        assert check["status"] == "downgraded"
        assert check["strength"] == "likely"
        assert any("causal" in issue.lower() for issue in check["issues"])


def test_complete_evidence_fields_pass_and_collect_route_ids():
    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[_complete_evidence()],
        route_proposals=[{"id": "route_1"}, {"id": "route_2"}],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert report["created_at"]
    assert report["overall_status"] == "pass"
    assert report["route_proposal_ids"] == ["route_1", "route_2"]
    assert check["status"] == "passed"
    assert check["strength"] == "supported"
    assert check["issues"] == []


def test_risky_cleaning_decision_downgrades_related_claim():
    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[_complete_evidence()],
        route_proposals=[],
        cleaning_logs=[{
            "id": "clean_1",
            "dataset": "sales",
            "decisions": [
                {
                    "column": "revenue",
                    "decision_type": "needs_confirmation",
                    "impact": "May change aggregate values",
                },
                {
                    "column": "raw_payload",
                    "decision_type": "blocked",
                    "impact": "Blocks dependent analysis",
                },
            ],
        }],
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "pass_with_downgrades"
    assert check["status"] == "downgraded"
    assert check["strength"] == "likely"
    assert any("cleaning decision" in issue.lower() for issue in check["issues"])
