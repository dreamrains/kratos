"""Prepare auditable multi-file quality scenarios without modifying source data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests" / "real_data" / "scenario_manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "multifile-quality"


class ManifestError(ValueError):
    pass


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"malformed manifest: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ManifestError("malformed manifest: root must be an object")
    if not isinstance(manifest.get("schema_version"), str):
        raise ManifestError("malformed manifest: schema_version must be a string")
    forbidden_modes = manifest.get("forbidden_modes")
    if not isinstance(forbidden_modes, list) or not all(
        isinstance(mode, str) for mode in forbidden_modes
    ):
        raise ManifestError("malformed manifest: forbidden_modes must be a string list")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        raise ManifestError("malformed manifest: scenarios must be a list")
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            raise ManifestError(f"malformed manifest: scenario {index} requires an id")
        required_files = scenario.get("required_files")
        if not isinstance(required_files, list) or not all(
            isinstance(name, str) and name for name in required_files
        ):
            raise ManifestError(
                f"malformed manifest: scenario {scenario['id']} has invalid required_files"
            )
        if scenario.get("executed_join") is not False:
            raise ManifestError(
                f"malformed manifest: scenario {scenario['id']} must forbid executed joins"
            )
    return manifest


def run_scenarios(
    *,
    manifest_path: Path,
    data_dir: Path,
    output_root: Path,
) -> tuple[Path, bool]:
    manifest = _load_manifest(manifest_path)
    scenario_results: list[dict[str, Any]] = []
    any_missing = False

    for scenario in manifest["scenarios"]:
        missing_files = [
            name for name in scenario["required_files"] if not (data_dir / name).is_file()
        ]
        any_missing = any_missing or bool(missing_files)
        scenario_results.append(
            {
                "id": scenario["id"],
                "analysis_mode": scenario.get("analysis_mode"),
                "executed_join": False,
                "status": "missing_required_files" if missing_files else "ready_for_execution",
                "missing_files": missing_files,
            }
        )

    generated_at = datetime.now(timezone.utc)
    result = {
        "schema_version": "multifile_quality_results.v1",
        "generated_at": generated_at.isoformat(),
        "manifest": str(manifest_path.resolve()),
        "data_dir": str(data_dir.resolve()),
        "forbidden_modes": list(manifest["forbidden_modes"]),
        "global_publish_gate": None,
        "notes": [
            "This runner verifies scenario readiness; it does not score or publish analysis claims.",
            "Relationship diagnostics never authorize an executed join.",
        ],
        "scenarios": scenario_results,
    }
    result_dir = output_root / generated_at.strftime("%Y%m%dT%H%M%S.%fZ")
    result_dir.mkdir(parents=True, exist_ok=False)
    result_path = result_dir / "results.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result_path, any_missing


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result_path, any_missing = run_scenarios(
            manifest_path=args.manifest,
            data_dir=args.data_dir,
            output_root=args.output_root,
        )
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(result_path.resolve())
    return 2 if any_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
