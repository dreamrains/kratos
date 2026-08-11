"""Independent, deterministic oracles for real-file user-journey gates.

The runner reads the versioned scenario manifest and source workbooks without
calling a model or product analysis tool.  Its output contains only aggregate
assertions and content digests, so Gate E/F can compare user-visible answers to
an oracle that was not derived from those answers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Sequence

import pandas as pd
from scipy.stats import wilcoxon


SCENARIO_MANIFEST_VERSION = "analysis_user_journey_scenarios.v1"
SCENARIO_ORACLE_VERSION = "analysis_scenario_oracle.v1"
DEFAULT_MANIFEST = Path(__file__).with_name("real_user_journey_scenarios.json")
_SCENARIO_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,79}$")


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def load_scenario_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("contract_version") != SCENARIO_MANIFEST_VERSION:
        raise ValueError("invalid_scenario_manifest_version")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("invalid_scenario_manifest_scenarios")
    observed: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("invalid_scenario_manifest_entry")
        scenario_id = scenario.get("scenario_id")
        if (
            not isinstance(scenario_id, str)
            or not _SCENARIO_ID_RE.fullmatch(scenario_id)
            or scenario_id in observed
        ):
            raise ValueError("invalid_scenario_manifest_id")
        observed.add(scenario_id)
        files = scenario.get("fixture_files")
        if not isinstance(files, list) or not files or any(
            not isinstance(name, str)
            or not name
            or Path(name).name != name
            for name in files
        ):
            raise ValueError("invalid_scenario_fixture_files")
        if not isinstance(scenario.get("prompt"), str) or not scenario["prompt"].strip():
            raise ValueError("invalid_scenario_prompt")
        if scenario.get("expected_confirmation") is not False:
            raise ValueError("invalid_scenario_confirmation_expectation")
        if not isinstance(scenario.get("oracle"), dict) or len(scenario["oracle"]) < 2:
            raise ValueError("invalid_scenario_oracle")
    risk_selection = manifest.get("risk_selection")
    if not isinstance(risk_selection, dict) or set(risk_selection) != {
        "provider_runtime",
        "task_evidence_recovery",
        "release_candidate",
    }:
        raise ValueError("invalid_scenario_risk_selection")
    if any(
        not isinstance(selected, list)
        or not selected
        or len(selected) != len(set(selected))
        or any(scenario_id not in observed for scenario_id in selected)
        for selected in risk_selection.values()
    ):
        raise ValueError("invalid_scenario_risk_selection")
    return manifest


def get_scenario(
    scenario_id: str,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest = load_scenario_manifest(manifest_path)
    for scenario in manifest["scenarios"]:
        if scenario["scenario_id"] == scenario_id:
            return scenario
    raise KeyError(f"unknown_scenario:{scenario_id}")


def scenario_prompt_digest(
    scenario_id: str,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> str:
    scenario = get_scenario(scenario_id, manifest_path=manifest_path)
    return _sha256_bytes(scenario["prompt"].encode("utf-8"))


def scenario_oracle_names(
    scenario_id: str,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> tuple[str, ...]:
    scenario = get_scenario(scenario_id, manifest_path=manifest_path)
    return tuple(scenario["oracle"])


def scenario_risk_selection(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, tuple[str, ...]]:
    manifest = load_scenario_manifest(manifest_path)
    return {
        risk_class: tuple(scenario_ids)
        for risk_class, scenario_ids in manifest["risk_selection"].items()
    }


def _numeric(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    percent = text.str.endswith("%", na=False)
    parsed = pd.to_numeric(text.str.rstrip("%"), errors="coerce")
    parsed.loc[percent] = parsed.loc[percent] / 100
    return parsed


def _assertion(name: str, expected: Any, observed: Any, *, tolerance: float = 0.0) -> dict[str, Any]:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        numeric_observed = float(observed)
        passed = math.isfinite(numeric_observed) and math.isclose(
            numeric_observed,
            float(expected),
            rel_tol=0.0,
            abs_tol=tolerance,
        )
    else:
        passed = observed == expected
    return {
        "name": name,
        "expected": expected,
        "observed": observed,
        "tolerance": tolerance,
        "passed": bool(passed),
    }


def _retention_oracle(frames: dict[str, pd.DataFrame], expected: dict[str, Any]) -> list[dict[str, Any]]:
    frame = next(iter(frames.values())).copy()
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce")
    frame = frame.sort_values("日期")
    d30 = _numeric(frame["30天后"])
    trailing_zeros = 0
    for value in reversed(d30.tolist()):
        if value != 0:
            break
        trailing_zeros += 1
    observed = {
        "row_count": len(frame),
        "date_min": str(frame["日期"].min().date()),
        "date_max": str(frame["日期"].max().date()),
        "trailing_30d_zero_rows": trailing_zeros,
    }
    return [_assertion(name, value, observed[name]) for name, value in expected.items()]


def _cross_promo_oracle(frames: dict[str, pd.DataFrame], expected: dict[str, Any]) -> list[dict[str, Any]]:
    frame = next(iter(frames.values())).copy()
    revenue = _numeric(frame["卖量收入"])
    exposure = _numeric(frame["曝光次数"])
    clicks = _numeric(frame["有效点击次数"])
    confirms = _numeric(frame["二次确认次数"])
    company = frame["公司"].astype("string").str.strip()

    def weighted_rates(label: str) -> tuple[float, float]:
        selected = company.eq(label)
        exposure_total = float(exposure[selected].sum())
        clicks_total = float(clicks[selected].sum())
        confirms_total = float(confirms[selected].sum())
        return clicks_total / exposure_total, confirms_total / clicks_total

    internal_ctr, internal_confirm_rate = weighted_rates("内部游戏")
    external_ctr, external_confirm_rate = weighted_rates("外部游戏")
    observed = {
        "row_count": len(frame),
        "total_exposure": int(exposure.sum()),
        "total_clicks": int(clicks.sum()),
        "total_confirms": int(confirms.sum()),
        "internal_ctr": internal_ctr,
        "external_ctr": external_ctr,
        "internal_confirm_rate": internal_confirm_rate,
        "external_confirm_rate": external_confirm_rate,
        "invalid_revenue_rows": int(revenue.isna().sum()),
        "zero_exposure_rows": int((exposure == 0).sum()),
        "confirm_gt_click_rows": int((confirms > clicks).sum()),
        "click_gt_exposure_rows": int((clicks > exposure).sum()),
    }
    ratio_fields = {
        "internal_ctr",
        "external_ctr",
        "internal_confirm_rate",
        "external_confirm_rate",
    }
    return [
        _assertion(
            name,
            value,
            observed[name],
            tolerance=1e-12 if name in ratio_fields else 0.0,
        )
        for name, value in expected.items()
    ]


def _card_oracle(frames: dict[str, pd.DataFrame], expected: dict[str, Any]) -> list[dict[str, Any]]:
    payments = frames["省钱卡0201到0510购卡用户付费数据.xlsx"]
    before_after = frames["省钱卡购卡前后订单.xlsx"]
    normalized_orders = payments["order_id"].map(
        lambda value: str(value).strip().lstrip("'") if pd.notna(value) else ""
    )
    dedup = before_after.drop_duplicates().copy()
    group_col = "用户类型（1是购卡前30天内，2是购卡后30天内）"
    aggregate = dedup.groupby(["user_id", group_col], as_index=False)["实收金额"].sum()
    paired = aggregate.pivot(index="user_id", columns=group_col, values="实收金额").dropna()
    test = wilcoxon(paired.iloc[:, 0], paired.iloc[:, 1], alternative="two-sided")
    observed = {
        "payment_rows": len(payments),
        "payment_unique_orders": int(normalized_orders.nunique()),
        "before_after_rows": len(before_after),
        "before_after_dedup_rows": len(dedup),
        "before_after_users": int(dedup["user_id"].nunique()),
        "complete_pairs": len(paired),
        "wilcoxon_two_sided_p": float(test.pvalue),
    }
    return [
        _assertion(
            name,
            value,
            observed[name],
            tolerance=5e-7 if name == "wilcoxon_two_sided_p" else 0.0,
        )
        for name, value in expected.items()
    ]


_ORACLE_RUNNERS: dict[
    str,
    Callable[[dict[str, pd.DataFrame], dict[str, Any]], list[dict[str, Any]]],
] = {
    "retention_descriptive_v1": _retention_oracle,
    "cross_promo_funnel_v1": _cross_promo_oracle,
    "card_multifile_paired_v1": _card_oracle,
}


def run_scenario_oracle(
    *,
    scenario_id: str,
    data_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    scenario = get_scenario(scenario_id, manifest_path=manifest_path)
    data_dir = Path(data_dir)
    paths = [data_dir / name for name in scenario["fixture_files"]]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing_scenario_fixtures:" + ",".join(missing))
    file_identities = [
        {"name": path.name, "sha256": _file_sha256(path)}
        for path in paths
    ]
    fixture_digest = _canonical_digest(file_identities)
    prompt_digest = scenario_prompt_digest(
        scenario_id,
        manifest_path=manifest_path,
    )
    frames = {path.name: pd.read_excel(path) for path in paths}
    assertions = _ORACLE_RUNNERS[scenario_id](frames, scenario["oracle"])
    oracle_identity = {
        "contract_version": SCENARIO_ORACLE_VERSION,
        "scenario_id": scenario_id,
        "fixture_digest": fixture_digest,
        "prompt_digest": prompt_digest,
        "assertions": assertions,
    }
    return {
        **oracle_identity,
        "oracle_digest": _canonical_digest(oracle_identity),
        "status": "PASS" if all(item["passed"] for item in assertions) else "FAIL",
        "expected_confirmation": scenario["expected_confirmation"],
        "fixture_files": file_identities,
    }


def write_scenario_oracle(path: Path, result: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute an independent real-file scenario oracle.")
    parser.add_argument("--scenario", required=True, choices=tuple(_ORACLE_RUNNERS))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_scenario_oracle(
        scenario_id=args.scenario,
        data_dir=args.data_dir,
        manifest_path=args.manifest,
    )
    if args.output:
        write_scenario_oracle(args.output, result)
        print(args.output.resolve())
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
