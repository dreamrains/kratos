"""Real-data oracles for the static facts sent to Gate C candidates."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data_agent.agent.relationship_validation import validate_relationship
from data_agent.session.workspace import workspace
from data_agent.tools.curve_fitting import curve_fitting
from data_agent.tools.eda import cohort_analysis


ROOT = Path("reference/test_doc")
CANDIDATES = Path("tests/acceptance/route_a_gate_c_candidates.json")


def _facts() -> dict[str, dict[str, str]]:
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    return {
        scenario["id"]: {item["id"]: item["value"] for item in scenario["fact_packet"]}
        for scenario in payload["scenarios"]
    }


def test_r01_candidate_facts_match_real_curve_oracle():
    frame = pd.read_excel(ROOT / "游戏B留存.xlsx")
    workspace.remove("gate_c_r01")
    workspace.add("gate_c_r01", frame)
    result = curve_fitting("gate_c_r01", series_columns=",".join(c for c in frame.columns if c.endswith("天后"))).data
    facts = _facts()["R01_retention_curve"]

    assert len(frame) == 62
    assert str(pd.to_datetime(frame["日期"]).min().date()) == "2020-07-01"
    assert str(pd.to_datetime(frame["日期"]).max().date()) == "2020-08-31"
    assert result["best_family"] == "power"
    assert abs(result["fits"][0]["parameters"]["a"] - 0.18800129) < 1e-6
    assert abs(result["fits"][0]["parameters"]["b"] + 0.71667274) < 1e-6
    assert abs(result["fits"][0]["r_squared"] - 0.98240474) < 1e-6
    assert result["points"][-1]["n_excluded_zeros"] == 6
    assert "0.18800129" in facts["r01_fit"] and "0.98240474" in facts["r01_fit"]


def test_r05_candidate_facts_match_rejected_many_to_many_oracle():
    orders = pd.read_excel(ROOT / "省钱卡订单.xlsx")
    payments = pd.read_excel(ROOT / "省钱卡0201到0510购卡用户付费数据.xlsx")
    relationship = validate_relationship(orders, payments, left_key="user_id", right_key="user_id").to_record()
    facts = _facts()["R05_relationship_scope"]

    assert len(orders) == 71 and len(payments) == 13757
    assert relationship["status"] == "rejected"
    assert relationship["cardinality"] == "many_to_many"
    assert abs(relationship["left_row_coverage"] - 0.98591549) < 1e-8
    assert relationship["right_row_coverage"] == 1.0
    assert abs(relationship["row_multiplier"] - 1.11325144) < 1e-8
    assert "many_to_many_join_explosion" in relationship["risks"]
    assert "many_to_many_join_explosion" in facts["r05_limit"]


def test_r06_candidate_facts_match_cohort_window_oracle():
    frame = pd.read_excel(ROOT / "省钱卡0201到0510购卡用户付费数据.xlsx")
    workspace.remove("gate_c_r06")
    workspace.add("gate_c_r06", frame)
    cohorts = json.loads(cohort_analysis("gate_c_r06", user_col="user_id", time_col="支付时间"))["cohorts"]
    facts = _facts()["R06_long_term_value_cohort"]

    assert len(frame) == 13757 and frame["user_id"].nunique() == 62
    times = pd.to_datetime(frame["支付时间"])
    assert str(times.min().date()) == "2026-02-01"
    assert str(times.max().date()) == "2026-05-10"
    assert [(item["cohort"], item["size"]) for item in cohorts] == [
        ("2026-02", 45), ("2026-03", 8), ("2026-04", 8), ("2026-05", 1),
    ]
    assert cohorts[0]["retention"]["month_1"] == 97.78
    assert "右截断" in facts["r06_limit"]
