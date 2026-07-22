from data_agent.agent.analysis_requirements import (
    compile_analysis_requirements,
    evaluate_requirement_satisfaction,
)
from data_agent.tools.analysis_flow import (
    _auto_generate_limitations,
    _calibrate_confidence,
)
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
import json
import pandas as pd


def _comparison_plan(**step_overrides):
    step = {
        "step_id": "step_compare",
        "goal": "compare the selected groups",
        "node_type": "analysis",
        "required_capability": "analysis.group_compare",
        "evidence_requirements": [],
    }
    step.update(step_overrides)
    return {
        "id": "plan_compare",
        "goal": "compare groups",
        "method_plan": [step],
    }


def _compile(plan, *, route=None, contracts=None, intent="compare groups"):
    return compile_analysis_requirements(
        plan=plan,
        route=route,
        playbook=None,
        dataset_contracts=contracts or [],
        user_intent=intent,
    )


def test_descriptive_group_comparison_requires_denominators_but_not_significance():
    requirements = _compile(_comparison_plan(claim_type="descriptive"))
    names = {item["name"] for item in requirements}

    assert {
        "effective_sample_size",
        "denominator",
        "missingness",
        "estimand",
        "effect_estimate",
        "calculation_method",
        "assumptions",
        "sample_adequacy",
    } <= names
    assert "confidence_interval" not in names
    assert "significance" not in names


def test_generalized_group_difference_requires_method_specific_support_and_interval():
    requirements = _compile(
        _comparison_plan(
            claim_type="inferential",
            sampling_structure="clustered",
        )
    )
    by_name = {item["name"]: item for item in requirements}

    assert "confidence_interval" in by_name
    assert by_name["sample_adequacy"]["required_evidence_fields"] == [
        "sample_adequacy.status",
        "sample_adequacy.design",
    ]
    assert by_name["sample_adequacy"]["parameters"] == {
        "sampling_structure": "clustered",
    }


def test_large_sample_significance_alone_cannot_satisfy_effect_or_interval():
    requirements = _compile(
        _comparison_plan(claim_type="inferential", evidence_requirements=["significance"])
    )
    by_name = {
        item["name"]: item
        for item in evaluate_requirement_satisfaction(
            requirements,
            [{
                "id": "evidence_p_only",
                "step_id": "step_compare",
                "sample_size": 1_000_000,
                "significance": "p < 0.001",
                "assumption_checks": {
                    "method_appropriate_for_design": "passed",
                },
            }],
        )
    }

    assert by_name["effect_estimate"]["status"] == "unmet"
    assert by_name["confidence_interval"]["status"] == "unmet"
    assert by_name["significance"]["status"] == "satisfied"


def test_large_sample_tiny_effect_still_requires_an_interval():
    requirements = _compile(
        _comparison_plan(
            claim_type="inferential",
            evidence_requirements=["significance"],
        )
    )
    by_name = {
        item["name"]: item
        for item in evaluate_requirement_satisfaction(
            requirements,
            [{
                "id": "evidence_tiny_effect",
                "step_id": "step_compare",
                "sample_size": 1_000_000,
                "effect_estimate": 0.0001,
                "significance": "p < 0.001",
                "assumption_checks": {
                    "method_appropriate_for_design": "passed",
                },
            }],
        )
    }

    assert by_name["effect_estimate"]["status"] == "satisfied"
    assert by_name["confidence_interval"]["status"] == "unmet"


def test_multiple_segment_comparisons_require_multiplicity_or_exploratory_label():
    requirements = _compile(
        _comparison_plan(
            required_capability="analysis.segment_compare",
            comparison_count=6,
            claim_type="inferential",
        )
    )
    multiplicity = next(item for item in requirements if item["name"] == "multiplicity_handling")

    assert multiplicity["required_evidence_fields"] == ["multiplicity_handling"]
    assert multiplicity["unmet_action"] == "block_claim"
    assert multiplicity["parameters"] == {
        "comparison_count": 6,
        "exploratory_label_allowed": True,
    }


def test_dimension_decomposition_with_multiple_segments_requires_exploratory_label():
    requirements = _compile(
        _comparison_plan(
            required_capability="analysis.dimension_decomposition",
            comparison_count=4,
            claim_type="descriptive",
        )
    )

    multiplicity = next(item for item in requirements if item["name"] == "multiplicity_handling")

    assert multiplicity["trigger"] == "multiple segment comparison"
    assert multiplicity["parameters"]["exploratory_label_allowed"] is True


def test_dataset_group_counts_trigger_decomposition_multiplicity_without_model_metadata():
    requirements = _compile(
        _comparison_plan(
            required_capability="analysis.dimension_decomposition",
            claim_type="descriptive",
        ),
        contracts=[{
            "dataset": "orders",
            "analysis_profiles": {
                "comparison": {
                    "group_sizes": {
                        "segment": {
                            "group_count": 4,
                            "minimum": 2,
                            "maximum": 20,
                            "median": 8.0,
                        },
                    },
                },
            },
        }],
    )

    multiplicity = next(item for item in requirements if item["name"] == "multiplicity_handling")

    assert multiplicity["trigger"] == "observed multi-segment decomposition"
    assert multiplicity["parameters"]["comparison_count"] == 4


def test_two_group_comparison_does_not_invent_a_multiplicity_family():
    contracts = [{
        "dataset": "orders",
        "analysis_profiles": {
            "comparison": {
                "group_sizes": {
                    "variant": {
                        "group_count": 2,
                        "minimum": 50,
                        "maximum": 50,
                        "median": 50.0,
                    },
                    "region": {
                        "group_count": 5,
                        "minimum": 10,
                        "maximum": 30,
                        "median": 20.0,
                    },
                },
            },
        },
    }]

    from_profile = _compile(
        _comparison_plan(
            required_capability="analysis.group_compare",
            group_col="variant",
        ),
        contracts=contracts,
    )
    from_segments = _compile(
        _comparison_plan(
            required_capability="analysis.segment_compare",
            segments=["control", "treatment"],
        )
    )

    assert "multiplicity_handling" not in {item["name"] for item in from_profile}
    assert "multiplicity_handling" not in {item["name"] for item in from_segments}


def test_three_group_profile_compiles_two_baseline_comparisons():
    requirements = _compile(
        _comparison_plan(required_capability="analysis.group_compare"),
        contracts=[{
            "dataset": "orders",
            "analysis_profiles": {
                "comparison": {
                    "group_sizes": {
                        "variant": {
                            "group_count": 3,
                            "minimum": 20,
                            "maximum": 30,
                            "median": 25.0,
                        },
                    },
                },
            },
        }],
    )

    multiplicity = next(item for item in requirements if item["name"] == "multiplicity_handling")

    assert multiplicity["parameters"]["comparison_count"] == 2


def test_effect_evaluation_playbook_compiles_the_base_comparison_contract():
    from data_agent.agent.method_playbooks import get_playbook

    playbook = get_playbook("effect_evaluation")
    effect_step = next(
        dict(step)
        for step in playbook.method_plan_template
        if step.get("required_capability") == "analysis.experiment"
    )
    effect_step["step_id"] = "step_effect"
    requirements = _compile({
        "id": "plan_effect",
        "goal": "evaluate a two-group effect",
        "method_plan": [effect_step],
    })
    names = {item["name"] for item in requirements}

    assert {
        "effective_sample_size",
        "denominator",
        "missingness",
        "estimand",
        "effect_estimate",
        "confidence_interval",
        "calculation_method",
        "assumptions",
        "sample_adequacy",
        "significance",
    } <= names


def test_small_descriptive_sample_does_not_manufacture_significance_or_n30_limit():
    payload = {
        "method": "descriptive_group_compare",
        "claim_type": "descriptive",
        "sample_size": 8,
        "limitations": [],
        "confidence": "high",
    }

    limitations = _auto_generate_limitations(payload)
    warnings = _calibrate_confidence(payload)

    assert not any("30" in item for item in limitations + warnings)
    assert not any("显著" in item for item in limitations + warnings)


def test_small_clean_dataset_is_not_globally_penalized_before_method_selection():
    from data_agent.tools.auto_insight import _assess_health

    frame = pd.DataFrame({"metric": range(8), "segment": list("abcdefgh")})

    health = _assess_health(frame)

    assert health["score"] == 100
    assert not any("30" in item or "统计结果置信度低" in item for item in health["items"])


def test_high_confidence_inferential_claim_uses_structured_adequacy_not_raw_n():
    unsupported = {
        "method": "clustered_group_compare",
        "claim_type": "inferential",
        "confidence": "high",
        "sample_size": 10_000,
        "sample_adequacy": {
            "status": "inadequate",
            "design": "clustered",
            "reason": "only two independent clusters per arm",
        },
        "effect_estimate": 0.01,
        "confidence_interval": [-0.02, 0.04],
        "limitations": ["few independent clusters"],
    }
    supported_small = {
        "method": "paired_group_compare",
        "claim_type": "inferential",
        "confidence": "high",
        "sample_size": 12,
        "sample_adequacy": {"status": "adequate", "design": "paired"},
        "effect_estimate": 4.2,
        "confidence_interval": [3.1, 5.3],
        "limitations": ["paired population only"],
    }

    assert any("independent clusters" in item for item in _calibrate_confidence(unsupported))
    assert not any("12" in item or "30" in item for item in _calibrate_confidence(supported_small))


def test_high_confidence_respects_not_estimable_seasonality_and_adjusted_windows():
    warnings = _calibrate_confidence({
        "confidence": "high",
        "claim_type": "descriptive",
        "seasonality_estimability": {"status": "not_estimable"},
        "window_comparability": {"status": "comparable_with_adjustment"},
        "limitations": ["short and gapped series"],
    })

    assert any("季节性不可估计" in item for item in warnings)
    assert any("需要调整" in item for item in warnings)


def test_inadequate_sample_status_satisfies_assessment_but_not_high_confidence():
    requirements = _compile(_comparison_plan(claim_type="inferential"))
    sample_requirement = next(
        item for item in requirements if item["name"] == "sample_adequacy"
    )

    evaluated = evaluate_requirement_satisfaction(
        [sample_requirement],
        [{
            "id": "evidence_inadequate",
            "requirement_ids": [sample_requirement["id"]],
            "sample_adequacy": {
                "status": "inadequate",
                "design": "independent_groups",
            },
        }],
    )

    assert evaluated[0]["status"] == "satisfied"
    assert evaluated[0]["evidence_ids"] == ["evidence_inadequate"]


def test_period_compare_tool_emits_method_specific_comparison_evidence(tmp_path):
    from data_agent.agent.evidence_contracts import persist_computation_output
    from data_agent.tools.eda import compare_periods
    from data_agent.tools.registry import registry

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=20, freq="D"),
        "revenue": range(1, 21),
    })
    context = AgentContext(session_id="period_compare_tool", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(compare_periods(
            "orders",
            date_col="date",
            metrics="revenue",
            period_a="2026-01-01~2026-01-10",
            period_b="2026-01-11~2026-01-20",
        ))

    assert result["effective_sample_size"] == {
        "total": 20,
        "groups": {"period_a": 10, "period_b": 10},
        "observed_rows": 20,
        "design": "repeated_measure_time",
    }
    assert result["estimand"] == {
        "metric": "revenue",
        "aggregation": "sum",
        "contrast": "period_b_minus_period_a",
    }
    assert result["effect_estimate"]["value"] == 100.0
    assert result["sample_adequacy"]["status"] == "adequate_with_limits"
    assert result["sample_adequacy"]["claim_scope"] == "descriptive"
    assert result["window_comparability"]["status"] == "comparable"

    capability = registry.capability_for("compare_periods")
    assert {
        "effective_sample_size",
        "denominator",
        "missingness",
        "estimand",
        "effect_estimate",
        "assumptions",
        "sample_adequacy",
        "period_definition",
        "period_comparability",
        "time_frequency",
        "missing_intervals",
        "window_comparability",
    } <= set(capability["evidence_fields"])
    ref = persist_computation_output(
        sessions_root=tmp_path,
        session_id="period_compare_tool",
        turn_id="turn_1",
        plan_id="plan_compare",
        step_id="step_compare",
        tool_call_id="call_compare",
        tool_name="compare_periods",
        arguments={"name": "orders"},
        output={"data": result},
        dataset_versions=["dataset_orders"],
        success=True,
        capability_id=capability["capability_id"],
        evidence_fields=capability["evidence_fields"],
    )
    assert {
        "effective_sample_size",
        "denominator",
        "missingness",
        "estimand",
        "effect_estimate",
        "assumptions",
        "sample_adequacy",
        "period_definition",
        "period_comparability",
        "time_frequency",
        "missing_intervals",
        "window_comparability",
    } <= set(ref["structured_checked_fields"])


def test_dimension_decomposition_emits_bound_exploratory_multiplicity_evidence(tmp_path):
    from data_agent.agent.evidence_contracts import persist_computation_output
    from data_agent.tools.eda import contribute_decomposition
    from data_agent.tools.registry import ToolResult, registry

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8, freq="D"),
        "segment": ["A", "B", "C", "D"] * 2,
        "revenue": [10, 20, 30, 40, 12, 18, 36, 44],
    })
    context = AgentContext(session_id="decomposition_tool", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = contribute_decomposition(
            "orders",
            metric="revenue",
            dimension="segment",
            date_col="date",
            period_a="2026-01-01~2026-01-04",
            period_b="2026-01-05~2026-01-08",
        )

    assert isinstance(result, ToolResult)
    assert result.data["multiplicity_handling"] == {
        "strategy": "exploratory_label",
        "status": "exploratory",
        "comparison_count": 4,
        "reason": (
            "Dimension-level contributions are descriptive exploratory comparisons; "
            "no family-wise inferential claim is made."
        ),
    }

    capability = registry.capability_for("contribute_decomposition")
    assert "multiplicity_handling" in capability["evidence_fields"]
    ref = persist_computation_output(
        sessions_root=tmp_path,
        session_id="decomposition_tool",
        turn_id="turn_1",
        plan_id="plan_decompose",
        step_id="step_decompose",
        tool_call_id="call_decompose",
        tool_name="contribute_decomposition",
        arguments={"name": "orders"},
        output={"data": result.data},
        dataset_versions=["dataset_orders"],
        success=True,
        capability_id=capability["capability_id"],
        evidence_fields=capability["evidence_fields"],
    )
    assert "multiplicity_handling" in ref["structured_checked_fields"]


def test_period_compare_uses_monthly_frequency_without_manufacturing_daily_gaps():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "month": pd.date_range("2025-01-01", periods=6, freq="MS"),
        "revenue": [10, 11, 12, 13, 14, 15],
    })
    context = AgentContext(session_id="monthly_periods", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("monthly", frame)
        result = json.loads(compare_periods(
            "monthly",
            date_col="month",
            metrics="revenue",
            period_a="2025-01-01~2025-03-31",
            period_b="2025-04-01~2025-06-30",
        ))

    assert result["time_frequency"] == "monthly"
    assert result["missing_intervals"] == {"count": 0, "frequency": "monthly"}
    assert not any(
        "missing" in warning
        for warning in result["window_comparability"]["warnings"]
    )


def test_period_compare_honors_explicit_mean_estimand():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=6, freq="D"),
        "revenue": [1, 3, 5, 11, 13, 15],
    })
    context = AgentContext(session_id="mean_estimand", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(compare_periods(
            "orders",
            date_col="date",
            metrics="revenue",
            period_a="2026-01-01~2026-01-03",
            period_b="2026-01-04~2026-01-06",
            agg_func="mean",
        ))

    assert result["estimand"]["aggregation"] == "mean"
    assert result["effect_estimate"] == {
        "value": 10.0,
        "metric": "revenue",
        "unit": "unspecified",
        "aggregation": "mean",
    }
    assert "daily_avg_a" not in result["metrics"]["revenue"]


def test_period_compare_duplicate_timestamps_require_explicit_aggregation():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "date": list(pd.date_range("2026-01-01", periods=4, freq="D")) * 2,
        "revenue": [1, 2, 3, 4, 10, 20, 30, 40],
    })
    context = AgentContext(session_id="period_duplicate_time", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("transactions", frame)
        blocked = json.loads(compare_periods(
            "transactions",
            date_col="date",
            metrics="revenue",
            period_a="2026-01-01~2026-01-02",
            period_b="2026-01-03~2026-01-04",
        ))
        explicit = json.loads(compare_periods(
            "transactions",
            date_col="date",
            metrics="revenue",
            period_a="2026-01-01~2026-01-02",
            period_b="2026-01-03~2026-01-04",
            agg_func="sum",
        ))

    assert blocked["error_type"] == "estimand_definition_required"
    assert explicit["estimand"]["aggregation"] == "sum"


def test_period_compare_mean_first_aggregates_each_time_point():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "date": pd.to_datetime([
            "2026-01-01", "2026-01-01", "2026-01-02",
            "2026-01-03", "2026-01-04", "2026-01-04",
        ]),
        "revenue": [0, 100, 0, 30, 20, 40],
    })
    context = AgentContext(session_id="unequal_duplicates", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(compare_periods(
            "orders",
            date_col="date",
            metrics="revenue",
            period_a="2026-01-01~2026-01-02",
            period_b="2026-01-03~2026-01-04",
            agg_func="mean",
        ))

    assert result["metrics"]["revenue"] == {
        "period_a": 25.0,
        "period_b": 30.0,
        "diff": 5.0,
        "change_pct": 20.0,
    }
    assert result["effect_estimate"]["value"] == 5.0


def test_segmented_period_compare_effect_uses_the_declared_mean_estimand():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8, freq="D"),
        "segment": ["A", "B"] * 4,
        "revenue": [1, 3, 5, 7, 11, 13, 15, 17],
    })
    context = AgentContext(session_id="segmented_mean", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(compare_periods(
            "orders",
            date_col="date",
            metrics="revenue",
            dimensions="segment",
            period_a="2026-01-01~2026-01-04",
            period_b="2026-01-05~2026-01-08",
            agg_func="mean",
        ))

    assert result["effect_estimate"]["aggregation"] == "mean"
    assert result["effect_estimate"]["value"] == 10.0


def test_segmented_period_compare_includes_segments_new_in_period_b():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=6, freq="D"),
        "segment": ["A", "A", "B", "A", "B", "C"],
        "revenue": [1, 2, 3, 4, 5, 6],
    })
    context = AgentContext(session_id="new_segment", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(compare_periods(
            "orders",
            date_col="date",
            metrics="revenue",
            dimensions="segment",
            period_a="2026-01-01~2026-01-03",
            period_b="2026-01-04~2026-01-06",
        ))

    assert [item["dimension"] for item in result["comparisons"]] == ["A", "B", "C"]
    assert result["multiplicity_handling"]["comparison_count"] == 3


def test_period_compare_does_not_count_weekends_as_business_daily_gaps():
    from data_agent.tools.eda import compare_periods

    frame = pd.DataFrame({
        "date": pd.bdate_range("2026-01-05", periods=10),
        "revenue": range(10),
    })
    context = AgentContext(session_id="business_periods", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("business", frame)
        result = json.loads(compare_periods(
            "business",
            date_col="date",
            metrics="revenue",
            period_a="2026-01-05~2026-01-09",
            period_b="2026-01-12~2026-01-16",
        ))

    assert result["time_frequency"] == "business_daily"
    assert result["missing_intervals"] == {
        "count": 0,
        "frequency": "business_daily",
    }


def test_ab_test_emits_bound_comparison_contract_for_a_tiny_effect(tmp_path):
    from data_agent.agent.evidence_contracts import persist_computation_output
    from data_agent.tools.registry import registry
    from data_agent.tools.statistics import ab_test

    frame = pd.DataFrame({
        "group": ["control"] * 100 + ["treatment"] * 100,
        "metric": list(range(100)) + [value + 0.000001 for value in range(100)],
    })
    context = AgentContext(session_id="ab_comparison", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("experiment", frame)
        result = json.loads(ab_test(
            "experiment",
            group_col="group",
            metric_col="metric",
            method="ttest",
        ))

    assert result["effect_estimate"] == {
        "value": 0.000001,
        "metric": "mean_difference",
    }
    assert result["confidence_interval"]["lower"] < 0.000001
    assert result["confidence_interval"]["upper"] > 0.000001
    assert result["sample_adequacy"]["design"] == "independent_groups"
    capability = registry.capability_for("ab_test")
    assert {
        "effective_sample_size",
        "denominator",
        "missingness",
        "estimand",
        "effect_estimate",
        "confidence_interval",
        "test",
        "assumptions",
        "sample_adequacy",
    } <= set(capability["evidence_fields"])

    ref = persist_computation_output(
        sessions_root=tmp_path,
        session_id="ab_comparison",
        turn_id="turn_1",
        plan_id="plan_compare",
        step_id="step_compare",
        tool_call_id="call_ab",
        tool_name="ab_test",
        arguments={"name": "experiment"},
        output={"data": result},
        dataset_versions=["dataset_experiment"],
        success=True,
        capability_id=capability["capability_id"],
        evidence_fields=capability["evidence_fields"],
    )
    assert {
        "effective_sample_size",
        "denominator",
        "missingness",
        "estimand",
        "effect_estimate",
        "confidence_interval",
        "test",
        "assumptions",
        "sample_adequacy",
    } <= set(ref["structured_checked_fields"])


def test_ab_test_rejects_silent_first_two_selection_from_three_groups():
    from data_agent.tools.statistics import ab_test

    frame = pd.DataFrame({
        "group": ["A", "A", "B", "B", "C", "C"],
        "metric": [1, 2, 3, 4, 5, 6],
    })
    context = AgentContext(session_id="three_groups", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("experiment", frame)
        result = ab_test("experiment", group_col="group", metric_col="metric")

    assert "恰好 2 个分组" in result


def test_mann_whitney_reports_a_rank_effect_with_matching_interval():
    from data_agent.tools.statistics import ab_test

    frame = pd.DataFrame({
        "group": ["control"] * 6 + ["treatment"] * 6,
        "metric": [0, 0, 0, 1, 1, 8, 2, 3, 3, 4, 5, 6],
    })
    context = AgentContext(session_id="rank_effect", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("experiment", frame)
        result = json.loads(ab_test(
            "experiment",
            group_col="group",
            metric_col="metric",
            method="mannwhitneyu",
        ))

    assert result["estimand"] == {
        "metric": "metric",
        "aggregation": "pairwise_probability",
        "contrast": "group_2_stochastic_superiority_minus_reverse",
    }
    assert result["effect_estimate"]["metric"] == "rank_biserial_correlation"
    assert result["confidence_interval"]["method"] == "bootstrap_rank_biserial_correlation"
    assert result["confidence_interval"]["lower"] <= result["effect_estimate"]["value"]
    assert result["confidence_interval"]["upper"] >= result["effect_estimate"]["value"]


def test_ttest_with_two_constant_groups_is_explicitly_not_estimable():
    from data_agent.tools.statistics import ab_test

    frame = pd.DataFrame({
        "group": ["control"] * 3 + ["treatment"] * 3,
        "metric": [1.0] * 6,
    })
    context = AgentContext(session_id="constant_groups", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("experiment", frame)
        raw = ab_test(
            "experiment",
            group_col="group",
            metric_col="metric",
            method="ttest",
        )
        result = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError(f"non-standard JSON constant: {value}")
        ))

    assert result["effect_estimate"] == {"value": 0.0, "metric": "mean_difference"}
    assert result["test"] == {
        "status": "not_estimable",
        "reason": "Both groups have zero within-group variance; a t-test is undefined.",
    }
    assert result["levene_test"]["status"] == "not_estimable"
    assert result["sample_adequacy"]["status"] == "not_estimable"
    method_check = next(
        item for item in result["assumptions"]
        if item["name"] == "method_appropriate_for_design"
    )
    assert method_check["status"] == "failed"
