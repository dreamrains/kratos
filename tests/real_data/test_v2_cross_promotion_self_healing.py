"""Real-data replay: the cross-promotion sheet's object-typed revenue column
(卖量收入) must be healed into a metric candidate and run end to end (B1.4)."""

from pathlib import Path

import pandas as pd
import pytest

from data_agent.v2.group_comparison import (
    GroupComparisonSpec,
    analyze_group_comparison,
)
from data_agent.v2.planner import ColumnRole, DatasetPlanningContext


TEST_DOC_DIR = Path("reference/test_doc")


@pytest.mark.skipif(
    not (TEST_DOC_DIR / "游戏互推.xlsx").exists(),
    reason="游戏互推.xlsx not found",
)
def test_cross_promotion_revenue_column_is_healed_and_comparable():
    path = TEST_DOC_DIR / "游戏互推.xlsx"
    frame = pd.read_excel(path)

    context = DatasetPlanningContext.from_frame(
        filename=path.name,
        source_fingerprint="sha256:" + "0" * 64,
        frame=frame,
    )
    roles = {column.name: column.role for column in context.columns}
    assert roles["卖量收入"] is ColumnRole.NUMERIC
    assert roles["公司"] is ColumnRole.CATEGORICAL

    result = analyze_group_comparison(
        frame,
        GroupComparisonSpec("卖量收入", "公司", "流量主游戏"),
    )

    # The same publisher appears under both company types, so the engine
    # aggregates per publisher per company and runs the matched design.
    assert result.design == "paired"
    assert result.unit_aggregation == "sum"
    assert result.status in {"supported", "null_result"}
    assert result.group_order == ("内部游戏", "外部游戏")
    assert result.paired_sample_size > 1
    assert result.assumed_independent_units is False
    assert any("聚合" in item for item in result.limitations)
