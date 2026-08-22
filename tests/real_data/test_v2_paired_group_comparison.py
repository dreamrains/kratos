"""Real-data replay: savings-card pre/post orders must run as a paired design.

Ground truth (independently computed 2026-08-22, per-user 30-day paid totals):
61 paired users, 1 single-group user, mean diff -1220.13,
paired t p=0.0186, Wilcoxon signed-rank p=0.0277.
"""

from pathlib import Path

import pandas as pd
import pytest

from data_agent.v2.group_comparison import (
    GroupComparisonSpec,
    analyze_group_comparison,
)


TEST_DOC_DIR = Path("reference/test_doc")
GROUP_COLUMN = "用户类型（1是购卡前30天内，2是购卡后30天内）"


@pytest.mark.skipif(
    not (TEST_DOC_DIR / "省钱卡购卡前后订单.xlsx").exists(),
    reason="省钱卡购卡前后订单.xlsx not found",
)
def test_pre_post_orders_run_as_paired_design():
    frame = pd.read_excel(TEST_DOC_DIR / "省钱卡购卡前后订单.xlsx")

    result = analyze_group_comparison(
        frame,
        GroupComparisonSpec("实收金额", GROUP_COLUMN, "user_id"),
    )

    assert result.design == "paired"
    assert result.status == "supported"
    assert result.reason_code == "reliable_paired_mean_difference"
    assert result.paired_sample_size == 61
    assert result.excluded_unpaired_units == 1
    assert result.difference == pytest.approx(-1220.13, abs=0.5)
    assert result.confidence_high < 0
    assert result.p_value == pytest.approx(0.0186, abs=0.001)
    assert result.wilcoxon_signed_rank_p_value == pytest.approx(0.0277, abs=0.001)
    assert result.assumed_independent_units is False
    assert result.unit_aggregation == "sum"
    # The honest causal boundary stays attached.
    assert any("因果" in item for item in result.limitations)
