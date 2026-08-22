"""Curve fitting engine tests (B1.3)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_agent.v2.curve_fitting import CurveFitSpec, analyze_curve_fit
from data_agent.v2.models import ClaimClass


TEST_DOC_DIR = Path("reference/test_doc")
_DAYS = [1, 2, 3, 5, 7, 10, 14, 21, 30]


def _power_frame(cohorts: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    data = {}
    for day in _DAYS:
        true_value = 2.0 * day ** -0.7
        data[f"{day}天后"] = [true_value * (1 + rng.normal(scale=0.002)) for _ in range(cohorts)]
    data["日期"] = pd.date_range("2021-01-01", periods=cohorts)
    return pd.DataFrame(data)


def test_wide_series_recovers_power_law():
    result = analyze_curve_fit(_power_frame(), CurveFitSpec(series_columns=tuple(f"{d}天后" for d in _DAYS)))

    assert result.status == "supported"
    assert result.best_family == "power"
    best = result.fits[0]
    assert best.params["a"] == pytest.approx(2.0, abs=0.02)
    assert best.params["b"] == pytest.approx(-0.7, abs=0.01)
    assert best.r_squared > 0.99
    assert result.maximum_claim_class is ClaimClass.DESCRIPTIVE
    assert len(result.fits) == 3  # power/exponential/logarithmic all fit positive data
    assert [fit.r_squared for fit in result.fits] == sorted(
        [fit.r_squared for fit in result.fits], reverse=True
    )


def test_truncation_zeros_are_excluded_and_disclosed():
    frame = _power_frame()
    frame.loc[0:3, "30天后"] = 0.0  # four truncated cohorts
    columns = tuple(f"{d}天后" for d in _DAYS)

    excluded = analyze_curve_fit(frame, CurveFitSpec(series_columns=columns))
    kept = analyze_curve_fit(
        frame, CurveFitSpec(series_columns=columns, zero_values="keep")
    )

    last_point = excluded.points[-1]
    assert last_point.x == 30
    assert last_point.n_excluded_zeros == 4
    assert last_point.n_observed == 4
    assert any("截断" in item for item in excluded.limitations)
    # keeping the truncation zeros visibly corrupts the late-curve mean
    assert excluded.fits[0].params["b"] != kept.fits[0].params["b"]


def test_long_columns_mode_uses_xy_binding():
    frame = pd.DataFrame(
        {
            "day": [1, 2, 3, 5, 7, 10, 14, 21, 30, 45],
            "retention": [0.19, 0.117, 0.092, 0.068, 0.055, 0.044, 0.034, 0.026, 0.019, 0.014],
        }
    )

    result = analyze_curve_fit(
        frame, CurveFitSpec(x_column="day", y_column="retention")
    )

    assert result.mode == "long_columns"
    assert result.best_family == "power"
    assert result.fits[0].params["a"] == pytest.approx(0.19, abs=0.01)


def test_too_few_points_is_limited():
    frame = pd.DataFrame({"1天后": [1.0], "2天后": [0.6], "3天后": [0.4]})

    result = analyze_curve_fit(frame, CurveFitSpec(series_columns=("1天后", "2天后", "3天后")))

    assert result.status == "limited"
    assert result.reason_code == "insufficient_points"


def test_non_positive_y_excludes_log_families_but_keeps_logarithmic():
    frame = pd.DataFrame(
        {
            f"{d}天后": [10.0 - d * 0.25 + (0.1 if d % 2 else -0.1)]
            for d in _DAYS
        }
    )
    frame.loc[0, "21天后"] = -0.5  # one non-positive observation poisons the column mean

    result = analyze_curve_fit(frame, CurveFitSpec(series_columns=tuple(f"{d}天后" for d in _DAYS)))

    assert "power" in result.excluded_families
    assert "exponential" in result.excluded_families
    assert any(fit.family == "logarithmic" for fit in result.fits)


@pytest.mark.skipif(
    not (TEST_DOC_DIR / "游戏B留存.xlsx").exists(),
    reason="游戏B留存.xlsx not found",
)
def test_real_retention_data_matches_independent_ground_truth():
    """5/18 session ground truth: a=0.1879, b=-0.7164, R²=0.9825 (zeros excluded)."""

    frame = pd.read_excel(TEST_DOC_DIR / "游戏B留存.xlsx")
    columns = tuple(c for c in frame.columns if c.endswith("天后"))

    result = analyze_curve_fit(frame, CurveFitSpec(series_columns=columns))

    assert result.status == "supported"
    assert result.best_family == "power"
    best = result.fits[0]
    assert best.params["a"] == pytest.approx(0.1880, abs=0.002)
    assert best.params["b"] == pytest.approx(-0.7167, abs=0.003)
    assert best.r_squared == pytest.approx(0.9824, abs=0.002)
    assert result.points[-1].n_excluded_zeros == 6
