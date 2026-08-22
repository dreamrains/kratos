import numpy as np
import pandas as pd

from data_agent.v2.factor import FactorAnalysisSpec, analyze_factor_relationships
from data_agent.v2.models import ClaimClass


def _strong_signal_frame(rows: int = 48) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    marketing = ((index * 7) % 31) + 10
    service = ((index * 11) % 23) + 60
    noise = np.sin(index * 1.7) * 3
    target = 0.8 * marketing + 0.35 * service + noise
    return pd.DataFrame(
        {
            "unit_id": [f"u{i:03d}" for i in range(rows)],
            "target": target,
            "marketing": marketing,
            "service": service,
            "noise_feature": np.cos(index * 0.9),
        }
    )


def test_factor_analysis_returns_adjusted_associations_with_uncertainty():
    result = analyze_factor_relationships(
        _strong_signal_frame(),
        FactorAnalysisSpec(
            target="target",
            features=("marketing", "service", "noise_feature"),
            analysis_unit="unit_id",
        ),
    )

    assert result.status == "supported"
    assert result.covariance_method == "HC3"
    assert result.complete_case_rows == 48
    assert result.effective_units == 48
    assert result.maximum_claim_class is ClaimClass.INFERENTIAL
    reliable = {item.feature: item for item in result.reliable_factors}
    assert reliable["marketing"].coefficient > 0
    assert reliable["marketing"].confidence_low > 0
    assert reliable["marketing"].p_adjusted < 0.05
    assert reliable["service"].coefficient > 0
    assert reliable["service"].confidence_low > 0


def test_mathematical_identity_features_are_excluded_as_target_leakage():
    frame = pd.DataFrame(
        {
            "unit_id": [f"u{i}" for i in range(12)],
            "employees": np.arange(10, 22, dtype=float),
            "confirmations": np.arange(10, 22, dtype=float) * 3,
            "quality": [1, 3, 2, 4, 1, 4, 2, 3, 2, 4, 1, 3],
        }
    )
    frame["per_capita"] = frame["confirmations"] / frame["employees"]

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="per_capita",
            features=("confirmations", "employees", "quality"),
            analysis_unit="unit_id",
        ),
    )

    assert result.status == "null_result"
    assert "confirmations" in result.excluded_features
    assert "employees" in result.excluded_features
    assert "mathematical_identity" in result.excluded_features["confirmations"]


def test_high_collinearity_does_not_produce_reliable_factor_claims():
    x = np.arange(1, 33, dtype=float)
    frame = pd.DataFrame(
        {
            "unit_id": [f"u{i}" for i in range(len(x))],
            "target": x + np.sin(x),
            "x1": x,
            "x2": x * 2,
        }
    )

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="target",
            features=("x1", "x2"),
            analysis_unit="unit_id",
        ),
    )

    assert result.status == "limited"
    assert result.reliable_factors == ()
    assert set(result.unstable_features) == {"x1", "x2"}


def test_repeated_units_without_time_field_publish_limited_diagnostic():
    frame = pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "b", "c", "c"],
            "target": [1, 2, 2, 3, 3, 4],
            "factor": [2, 3, 3, 4, 4, 5],
        }
    )

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="target",
            features=("factor",),
            analysis_unit="unit_id",
        ),
    )

    assert result.status == "limited"
    assert result.reason_code == "repeated_units_require_time_field"
    assert result.effective_units == 3


def test_repeated_units_with_time_use_cluster_robust_uncertainty():
    units = np.repeat([f"u{i:02d}" for i in range(12)], 3)
    time = np.tile(pd.date_range("2026-01-01", periods=3), 12)
    factor = np.arange(len(units), dtype=float) % 11
    target = 2.5 * factor + np.sin(np.arange(len(units)))
    frame = pd.DataFrame(
        {"unit_id": units, "date": time, "target": target, "factor": factor}
    )

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="target",
            features=("factor",),
            analysis_unit="unit_id",
            time_field="date",
        ),
    )

    assert result.status == "supported"
    assert result.covariance_method == "cluster"
    assert result.effective_units == 12
    assert result.time_controlled is True


def test_repeated_units_with_too_few_clusters_publish_method_limit():
    frame = pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "b", "c", "c"],
            "period": pd.date_range("2026-01-01", periods=6, freq="D"),
            "target": [1.2, 3.1, 2.3, 4.2, 1.8, 3.7],
            "factor": [1.0, 3.0, 2.0, 4.0, 1.5, 3.5],
        }
    )

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec("target", ("factor",), "unit_id", "period"),
    )

    assert result.status == "limited"
    assert result.reason_code == "insufficient_cluster_degrees_of_freedom"
    assert result.maximum_claim_class is ClaimClass.ASSOCIATIONAL


def test_small_but_identifiable_model_is_not_rejected_by_fixed_n_30_rule():
    frame = _strong_signal_frame(rows=16)

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="target",
            features=("marketing",),
            analysis_unit="unit_id",
        ),
    )

    assert result.complete_case_rows == 16
    assert result.reason_code != "fixed_small_sample_rule"
    assert result.status in {"supported", "null_result"}


def _null_multivariate_frame(rows: int = 60) -> pd.DataFrame:
    """Target is pure noise; features are mutually collinear and unrelated."""
    rng = np.random.default_rng(7)
    base = rng.normal(size=rows)
    return pd.DataFrame(
        {
            "unit_id": [f"u{index}" for index in range(rows)],
            "target": rng.normal(size=rows),
            "factor_a": base,
            "factor_b": base * 1.05 + rng.normal(scale=0.05, size=rows),
            "factor_c": base * 0.95 + rng.normal(scale=0.05, size=rows),
        }
    )


def test_null_result_carries_unadjusted_bivariate_ranking():
    frame = _null_multivariate_frame()

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="target",
            features=("factor_a", "factor_b", "factor_c"),
            analysis_unit="unit_id",
        ),
    )

    assert result.status in {"null_result", "limited"}
    assert result.bivariate_associations, "degraded results must not be empty of information"
    ranked = result.bivariate_associations
    magnitudes = [abs(item.pearson_r) for item in ranked]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert all(item.n_pairs == result.complete_case_rows for item in ranked)
    assert all(0 <= item.pearson_p_adjusted <= 1 for item in ranked)


def test_supported_result_does_not_render_bivariate_fallback():
    frame = _strong_signal_frame(rows=48)

    result = analyze_factor_relationships(
        frame,
        FactorAnalysisSpec(
            target="target",
            features=("marketing",),
            analysis_unit="unit_id",
        ),
    )

    assert result.status == "supported"
    assert result.bivariate_associations == ()
