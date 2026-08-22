import numpy as np
import pandas as pd

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
    assert check["strength"] == "likely"
    assert check["issues"] == []


def test_high_confidence_complete_evidence_is_confirmed():
    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[_complete_evidence(confidence="high")],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["claim_checks"][0]["status"] == "passed"
    assert report["claim_checks"][0]["strength"] == "confirmed"


def test_missing_required_evidence_fields_downgrades_claim():
    evidence = _complete_evidence(sample_size=None, time_scope="")

    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "pass_with_downgrades"
    assert check["status"] == "downgraded"
    assert check["strength"] == "likely"
    assert any("sample_size" in issue and "time_scope" in issue for issue in check["issues"])


def test_punctuation_case_and_light_paraphrase_can_match_evidence():
    report = verify_analysis_claims(
        claims=["revenue increased 12 percent in may!"],
        evidence_records=[_complete_evidence(claim="May revenue increased by 12 percent.")],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["overall_status"] == "pass"
    assert report["claim_checks"][0]["evidence_id"] == "ev_1"
    assert report["claim_checks"][0]["status"] == "passed"


def test_claim_dict_id_matches_evidence_claim_id_or_id():
    claim_by_claim_id = {"id": "claim_77", "claim": "Different wording"}
    claim_by_evidence_id = {"id": "ev_2", "claim": "Another wording"}

    report = verify_analysis_claims(
        claims=[claim_by_claim_id, claim_by_evidence_id],
        evidence_records=[
            _complete_evidence(id="ev_1", claim_id="claim_77", claim="Original text"),
            _complete_evidence(id="ev_2", claim="Original text 2"),
        ],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["overall_status"] == "pass"
    assert [check["evidence_id"] for check in report["claim_checks"]] == ["ev_1", "ev_2"]


def test_malformed_non_list_inputs_do_not_crash_or_split_strings():
    report = verify_analysis_claims(
        claims="Revenue increased 12% in May",
        evidence_records=_complete_evidence(),
        route_proposals={"id": "route_1"},
        cleaning_logs={"dataset": "sales", "decisions": "not a list"},
    )

    assert len(report["claim_checks"]) == 1
    assert report["claim_checks"][0]["status"] == "passed"
    assert report["route_proposal_ids"] == ["route_1"]


def test_pandas_and_numpy_missing_values_do_not_trigger_truth_value_ambiguity():
    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[_complete_evidence(
            sample_size=np.array([]),
            time_scope=pd.Series(dtype="object"),
            limitations=np.array(["descriptive"]),
        )],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["overall_status"] == "pass_with_downgrades"
    assert report["claim_checks"][0]["status"] == "downgraded"
    assert any("sample_size" in issue and "time_scope" in issue for issue in report["claim_checks"][0]["issues"])


def test_malformed_cleaning_decisions_and_dataset_mismatch_do_not_downgrade():
    report = verify_analysis_claims(
        claims=["Revenue increased 12% in May"],
        evidence_records=[_complete_evidence(dataset="sales")],
        route_proposals=[],
        cleaning_logs=[
            {"dataset": "sales", "decisions": ["bad decision", None]},
            {"dataset": "support", "decisions": [{"decision_type": "blocked", "column": "ticket_id"}]},
        ],
    )

    assert report["overall_status"] == "pass"
    assert report["claim_checks"][0]["issues"] == []


def test_report_id_is_stable_for_same_payload_ignoring_created_at():
    kwargs = {
        "claims": ["Revenue increased 12% in May"],
        "evidence_records": [_complete_evidence()],
        "route_proposals": [{"id": "route_1"}],
        "cleaning_logs": [],
    }

    first = verify_analysis_claims(**kwargs)
    second = verify_analysis_claims(**kwargs)

    assert first["id"] == second["id"]
    assert first["created_at"] != ""
    assert second["created_at"] != ""


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
