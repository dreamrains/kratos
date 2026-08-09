"""Run deterministic acceptance checks against the local reference workbooks.

This gate validates data semantics and selected project analysis behavior. It makes
no model calls and never modifies the source workbooks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_FILES = {
    "game_a_banner": "游戏Abanner汇总数据.xlsx",
    "game_a_iap": "游戏A内购数据.xlsx",
    "game_a_video": "游戏A激励视频汇总数据报表.xlsx",
    "game_b_retention": "游戏B留存.xlsx",
    "cross_promotion": "游戏互推.xlsx",
    "card_user_payments": "省钱卡0201到0510购卡用户付费数据.xlsx",
    "coupon_orders": "省钱卡代金券明细订单.xlsx",
    "card_orders": "省钱卡订单.xlsx",
    "card_before_after": "省钱卡购卡前后订单.xlsx",
}


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _numeric(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    is_percent = text.str.endswith("%", na=False)
    parsed = pd.to_numeric(text.str.rstrip("%"), errors="coerce")
    parsed.loc[is_percent] = parsed.loc[is_percent] / 100
    return parsed


def _max_relative_error(actual: pd.Series, expected: pd.Series) -> float:
    valid = actual.notna() & expected.notna() & np.isfinite(actual) & np.isfinite(expected)
    if not bool(valid.any()):
        return float("inf")
    denominator = expected.abs().clip(lower=1e-12)
    return float(((actual - expected).abs() / denominator)[valid].max())


def _normalized_ids(series: pd.Series) -> pd.Series:
    return series.map(
        lambda value: str(value).strip().lstrip("'") if pd.notna(value) else ""
    )


def run_acceptance(data_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: Any) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    missing = [name for name in REQUIRED_FILES.values() if not (data_dir / name).is_file()]
    check("all_reference_files_present", not missing, {"missing": missing})
    if missing:
        return {
            "contract": "reference_data_acceptance.v1",
            "status": "failed",
            "data_dir": str(data_dir.resolve()),
            "file_count": len(REQUIRED_FILES) - len(missing),
            "checks": checks,
            "warnings": warnings,
        }

    paths = {key: data_dir / name for key, name in REQUIRED_FILES.items()}
    before_hashes = {key: _digest(path) for key, path in paths.items()}
    frames = {key: pd.read_excel(path) for key, path in paths.items()}
    check(
        "all_workbooks_readable_and_nonempty",
        all(not frame.empty and len(frame.columns) > 0 for frame in frames.values()),
        {key: list(frame.shape) for key, frame in frames.items()},
    )

    banner = frames["game_a_banner"].copy()
    iap = frames["game_a_iap"].copy()
    video = frames["game_a_video"].copy()
    for frame in (banner, iap, video):
        frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce")
    shared_dates = set(banner["日期"]) & set(iap["日期"]) & set(video["日期"])
    check(
        "game_a_daily_grain_alignment",
        len(shared_dates) == len(banner) == len(iap) == len(video),
        {"shared_dates": len(shared_dates), "rows": [len(banner), len(iap), len(video)]},
    )
    banner_by_date = banner.set_index("日期")
    iap_by_date = iap.set_index("日期")
    video_by_date = video.set_index("日期")
    active_matches = bool(
        banner_by_date["活跃用户数"].equals(video_by_date["活跃用户数"])
        and banner_by_date["活跃用户数"].equals(iap_by_date["活跃用户"])
    )
    new_matches = bool(
        banner_by_date["新增用户数"].equals(video_by_date["新增用户数"])
        and banner_by_date["新增用户数"].equals(iap_by_date["新增用户"])
    )
    check(
        "game_a_shared_population_metrics_match",
        active_matches and new_matches,
        {"active_matches": active_matches, "new_matches": new_matches},
    )

    formula_errors = {
        "banner_arpu": _max_relative_error(
            _numeric(banner["BN_arpu"]),
            _numeric(banner["BN_广告收入"]) / _numeric(banner["活跃用户数"]),
        ),
        "banner_ecpm": _max_relative_error(
            _numeric(banner["BN_eCPM"]),
            _numeric(banner["BN_广告收入"]) / _numeric(banner["BN_曝光量"]) * 1000,
        ),
        "video_arpu": _max_relative_error(
            _numeric(video["视频arpu"]),
            _numeric(video["视频广告收入"]) / _numeric(video["活跃用户数"]),
        ),
        "iap_arpu": _max_relative_error(
            _numeric(iap["内购arpu"]),
            _numeric(iap["内购收入"]) / _numeric(iap["活跃用户"]),
        ),
    }
    check(
        "published_game_a_formulas_match_with_rounding",
        all(value <= 0.01 for value in formula_errors.values()),
        formula_errors,
    )

    retention = frames["game_b_retention"].copy()
    retention["日期"] = pd.to_datetime(retention["日期"], errors="coerce")
    retention = retention.sort_values("日期")
    d30 = _numeric(retention["30天后"])
    trailing_zero_count = 0
    for value in reversed(d30.tolist()):
        if value != 0:
            break
        trailing_zero_count += 1
    warnings.append({
        "id": "retention_right_censoring_candidate",
        "observed_trailing_zero_rows": trailing_zero_count,
        "interpretation": (
            "The extract date is unknown. Treat the final zero-valued long-horizon cohorts as "
            "possible censoring, not confirmed performance, until the observation window is known."
        ),
    })
    check(
        "retention_horizon_columns_numeric",
        all(_numeric(retention[column]).notna().all() for column in ("1天后", "7天后", "30天后")),
        {"rows": len(retention), "trailing_30d_zero_rows": trailing_zero_count},
    )

    cross = frames["cross_promotion"].copy()
    cross_revenue = _numeric(cross["卖量收入"])
    cross_exposure = _numeric(cross["曝光次数"])
    cross_clicks = _numeric(cross["有效点击次数"])
    cross_confirms = _numeric(cross["二次确认次数"])
    invalid_revenue = int(cross_revenue.isna().sum())
    impossible_funnel = int((cross_confirms > cross_clicks).sum())
    warnings.append({
        "id": "cross_promotion_quality_issues",
        "invalid_revenue_rows": invalid_revenue,
        "zero_exposure_rows": int((cross_exposure == 0).sum()),
        "confirmation_gt_click_rows": impossible_funnel,
    })
    check(
        "cross_promotion_numeric_conversion_is_explicit",
        invalid_revenue > 0 and cross_revenue.notna().any(),
        {"invalid_revenue_rows": invalid_revenue, "valid_revenue_rows": int(cross_revenue.notna().sum())},
    )

    payments = frames["card_user_payments"].copy()
    before_after = frames["card_before_after"].copy()
    coupons = frames["coupon_orders"].copy()
    cards = frames["card_orders"].copy()
    payments["_order"] = _normalized_ids(payments["order_id"])
    before_after["_user"] = _normalized_ids(before_after["user_id"])
    payment_duplicate_excess = int(len(payments) - payments["_order"].nunique())
    before_after_duplicate_rows = int(before_after.duplicated().sum())
    warnings.append({
        "id": "savings_card_duplicate_rows",
        "payment_duplicate_order_excess": payment_duplicate_excess,
        "before_after_exact_duplicate_rows": before_after_duplicate_rows,
    })
    check(
        "savings_card_duplicates_are_observable",
        payment_duplicate_excess > 0 and before_after_duplicate_rows > 0,
        {
            "payment_duplicate_order_excess": payment_duplicate_excess,
            "before_after_exact_duplicate_rows": before_after_duplicate_rows,
        },
    )

    used = coupons["状态"].astype("string").eq("已使用")
    expected_paid = (
        _numeric(coupons["sdk订单金额(分)"]) - _numeric(coupons["代金券面值(分)"])
    ) / 100
    price_error = (_numeric(coupons["实付"]) - expected_paid).abs()
    check(
        "coupon_used_order_price_identity",
        bool((price_error[used] <= 0.01).all()),
        {"used_rows": int(used.sum()), "max_error": float(price_error[used].max())},
    )

    card_users = set(_normalized_ids(cards["user_id"])) - {""}
    payment_users = set(_normalized_ids(payments["user_id"])) - {""}
    coupon_main_users = set(_normalized_ids(coupons["主用户ID"])) - {""}
    check(
        "savings_card_user_id_namespace_alignment",
        len(card_users & payment_users) / len(card_users) > 0.95
        and len(card_users & coupon_main_users) / len(card_users) > 0.95,
        {
            "card_users_in_payments": len(card_users & payment_users) / len(card_users),
            "card_users_in_coupon_main_user": len(card_users & coupon_main_users) / len(card_users),
        },
    )

    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace
    from data_agent.tools.statistics import ab_test

    group_col = "用户类型（1是购卡前30天内，2是购卡后30天内）"
    dedup = before_after.drop_duplicates().copy()
    complete_pair_count = int(
        (dedup.groupby("user_id")[group_col].nunique() == 2).sum()
    )
    analysis_workspace = Workspace()
    analysis_context = AgentContext(
        session_id="reference_data_acceptance",
        workspace=analysis_workspace,
    )
    with use_agent_context(analysis_context):
        analysis_workspace.add("card_before_after", dedup)
        blocked = json.loads(ab_test(
            "card_before_after",
            group_col=group_col,
            metric_col="实收金额",
        ))
        paired = json.loads(ab_test(
            "card_before_after",
            group_col=group_col,
            metric_col="实收金额",
            observation_design="paired",
            unit_col="user_id",
            unit_aggregation="sum",
        ))
    check(
        "row_independence_violation_is_blocked",
        blocked.get("error_type") == "analysis_unit_design_required" and "test" not in blocked,
        {"error_type": blocked.get("error_type")},
    )
    check(
        "paired_user_level_before_after_analysis_succeeds",
        paired.get("observation_design") == "paired"
        and paired.get("effective_sample_size", {}).get("pairs") == complete_pair_count
        and complete_pair_count >= 2
        and isinstance(paired.get("test"), dict),
        {
            "method": paired.get("method"),
            "matched_pairs": paired.get("effective_sample_size", {}).get("pairs"),
            "independently_counted_complete_pairs": complete_pair_count,
            "effect_estimate": paired.get("effect_estimate"),
            "test": paired.get("test"),
        },
    )

    after_hashes = {key: _digest(path) for key, path in paths.items()}
    check("source_workbooks_unchanged", before_hashes == after_hashes, {})
    return {
        "contract": "reference_data_acceptance.v1",
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "data_dir": str(data_dir.resolve()),
        "file_count": len(frames),
        "checks": checks,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_acceptance(args.data_dir)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(args.output.resolve())
    else:
        print(payload, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
