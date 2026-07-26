from __future__ import annotations

import numpy as np
import pandas as pd


def build_factor_relationship_frame(rows: int = 32) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    frame = pd.DataFrame(
        {
            "日期": pd.date_range("2026-01-01", periods=rows, freq="D"),
            "目标值": 80 + 2.4 * index + np.sin(index) * 3,
            "活跃度": 10 + index * 0.8,
            "价格": 30 + (index % 5),
            "渠道": np.where(index % 2 == 0, "自然", "投放"),
            "缺失特征": np.where(index % 7 == 0, np.nan, index / 10),
        }
    )
    for number in range(15):
        frame[f"辅助特征_{number:02d}"] = ((index + number) % (number + 3)).astype(
            float
        )
    return frame


def build_aggregate_payment_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": pd.date_range("2026-02-01", periods=14, freq="D"),
            "订单数": [20 + i for i in range(14)],
            "收入": [600 + i * 25 for i in range(14)],
        }
    )


def factor_relationship_prompt() -> str:
    return "请分析哪些影响因素与目标值存在显著关系，并说明方法、稳定性和局限。"
