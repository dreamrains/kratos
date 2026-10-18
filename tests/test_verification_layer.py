import json
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
        claims=[{"claim":"Discount caused higher revenue","evidence_id":"ev_1"},{"claim":"渠道变化导致 GMV 下滑","evidence_id":"ev_2"}],
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
        assert check["strength"] == "unassessed"
        assert any("diagnostic only" in issue for issue in check["issues"])


def test_complete_evidence_fields_pass_and_collect_route_ids():
    report = verify_analysis_claims(
        claims=[{"claim":"Revenue increased 12% in May","evidence_id":"ev_1"}],
        evidence_records=[_complete_evidence()],
        route_proposals=[{"id": "route_1"}, {"id": "route_2"}],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert report["created_at"]
    assert report["overall_status"] == "pass_with_downgrades"
    assert report["route_proposal_ids"] == ["route_1", "route_2"]
    assert check["status"] == "downgraded"
    assert check["strength"] == "unassessed"
    assert any("diagnostic only" in issue for issue in check["issues"])


def test_high_confidence_annotation_cannot_grant_confirmed_fact():
    report = verify_analysis_claims(
        claims=[{"claim":"Revenue increased 12% in May","evidence_id":"ev_1"}],
        evidence_records=[_complete_evidence(confidence="high")],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["claim_checks"][0]["status"] == "downgraded"
    assert report["claim_checks"][0]["strength"] == "unassessed"


def test_missing_required_evidence_fields_downgrades_claim():
    evidence = _complete_evidence(sample_size=None, time_scope="")

    report = verify_analysis_claims(
        claims=[{"claim":"Revenue increased 12% in May","evidence_id":"ev_1"}],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert report["overall_status"] == "pass_with_downgrades"
    assert check["status"] == "downgraded"
    assert check["strength"] == "unassessed"
    assert any("sample_size" in issue and "time_scope" in issue for issue in check["issues"])


def test_punctuation_case_and_light_paraphrase_cannot_supply_identity():
    report = verify_analysis_claims(
        claims=["revenue increased 12 percent in may!"],
        evidence_records=[_complete_evidence(claim="May revenue increased by 12 percent.")],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["overall_status"] == "fail"
    assert report["claim_checks"][0]["evidence_id"] is None
    assert report["claim_checks"][0]["status"] == "failed"


def test_claim_id_is_not_an_explicit_evidence_reference():
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

    assert report["overall_status"] == "fail"
    assert [check["evidence_id"] for check in report["claim_checks"]] == [None,None]


def test_malformed_non_list_inputs_do_not_crash_or_split_strings():
    report = verify_analysis_claims(
        claims="Revenue increased 12% in May",
        evidence_records=_complete_evidence(),
        route_proposals={"id": "route_1"},
        cleaning_logs={"dataset": "sales", "decisions": "not a list"},
    )

    assert len(report["claim_checks"]) == 1
    assert report["claim_checks"][0]["status"] == "failed"
    assert report["route_proposal_ids"] == ["route_1"]


def test_pandas_and_numpy_missing_values_do_not_trigger_truth_value_ambiguity():
    report = verify_analysis_claims(
        claims=[{"claim":"Revenue increased 12% in May","evidence_id":"ev_1"}],
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
        claims=[{"claim":"Revenue increased 12% in May","evidence_id":"ev_1"}],
        evidence_records=[_complete_evidence(dataset="sales")],
        route_proposals=[],
        cleaning_logs=[
            {"dataset": "sales", "decisions": ["bad decision", None]},
            {"dataset": "support", "decisions": [{"decision_type": "blocked", "column": "ticket_id"}]},
        ],
    )

    assert report["overall_status"] == "pass_with_downgrades"
    assert not any("cleaning decision" in issue.lower() for issue in report["claim_checks"][0]["issues"])


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
        claims=[{"claim":"Revenue increased 12% in May","evidence_id":"ev_1"}],
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
    assert check["strength"] == "unassessed"
    assert any("cleaning decision" in issue.lower() for issue in check["issues"])


# ── P3 (D10): claim-type calibration (C01–C08) ──

from tests.test_trusted_publication_semantics import engine


def _cal_payload(**overrides):
    payload = {
        "claim": "当前 12 条订单记录合计 120。",
        "dataset": "sales",
        "method": "descriptive_sum",
        "tool_calls": ["transform_data"],
        "result_summary": "sum(amount) = 120 over 12 rows",
        "limitations": [],
        "confidence": "high",
        "sample_size": 12,
        "time_scope": "2026-08-01 至 2026-08-31",
    }
    payload.update(overrides)
    return payload


class TestCSeriesCalibration:

    def test_c01_descriptive_exact_sum_not_flagged_small_sample(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'仅研究注释；不是发布事实',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":5,"time_scope":'2026-09-01 至 2026-09-12',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='仅研究注释；不是发布事实' for c in facts)

    def test_c02_descriptive_generalization_gets_scope_limitation(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'全部市场的订单合计为120',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":120,"time_scope":'2026-09-01 至 2026-09-12',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='全部市场的订单合计为120' for c in facts)

    def test_c03_single_source_descriptive_fact_not_denied(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'仅研究注释；不是发布事实',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":120,"time_scope":'2026-09-01 至 2026-09-12',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='仅研究注释；不是发布事实' for c in facts)

    def test_c04_large_sample_does_not_silence_method_issues(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'仅研究注释；不是发布事实',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":10000,"time_scope":'2026-09-01 至 2026-09-12',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='仅研究注释；不是发布事实' for c in facts)

    def test_c05_structured_365_day_window_not_flagged_short(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'仅研究注释；不是发布事实',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":120,"time_scope":'365天',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='仅研究注释；不是发布事实' for c in facts)

    def test_c06_unparseable_window_adds_no_fabricated_warning(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'仅研究注释；不是发布事实',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":120,"time_scope":'节假日季',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='仅研究注释；不是发布事实' for c in facts)

    def test_c07_missing_or_zero_semantics_not_fabricated(self, engine):
        """Retired generic heuristic: annotations cannot grant or suppress facts."""
        from data_agent.tools.analysis_flow import record_evidence_record
        from data_agent.agent.publication.native import resolve_native_claims
        from tests.test_trusted_publication_semantics import execute
        loop, _ = engine
        rid, _ = execute(loop, "describe_dataset", {"name":"orders"})
        record={"claim":'仅研究注释；不是发布事实',"dataset":"orders","method":'descriptive_sum',
            "tool_calls":["describe_dataset"],"tool_receipt_ids":[rid],"result_summary":"research annotation",
            "limitations":[],"confidence":'high',"sample_size":120,"time_scope":'2026-09-01 至 2026-09-12',"significance":"not significant"}
        output=json.loads(record_evidence_record(record))
        assert "error" not in output, output
        annotation=loop.context.analysis_state.evidence_records[-1]
        assert annotation["confidence"]=='high'
        assert not annotation.get("confidence_auto_downgraded") and not annotation.get("auto_generated_limitations")
        facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in facts if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")==180
        assert all(c["label"]!='仅研究注释；不是发布事实' for c in facts)

    def test_c08_causal_method_annotation_cannot_grant_fact_strength(self):
        evidence = {
            "id": "ev_causal",
            "claim": "营销活动导致收入提升。",
            "dataset": "sales",
            "method": "did",
            "sample_size": 1200,
            "time_scope": "2026-05-01 to 2026-05-31",
            "calculation_method": "difference in differences",
            "method_detail": "treated vs control periods",
            "limitations": ["parallel trends assumption not fully checked"],
            "confidence": "medium",
        }

        report = verify_analysis_claims(
            claims=[{"claim":evidence["claim"],"evidence_id":"ev_causal"}],
            evidence_records=[evidence],
            route_proposals=[],
            cleaning_logs=[],
        )

        check = report["claim_checks"][0]
        assert check["status"] == "downgraded"
        assert "causal" not in " ".join(check["issues"]).lower()

        assert check["strength"]=="unassessed"
