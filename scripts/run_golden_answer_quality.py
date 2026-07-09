"""Run golden final-answer quality measurement.

generate: drive the agent on each golden scenario, evaluate, write artifacts.
--update-baseline: also persist each scenario answer into --baseline-dir.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MANIFEST = ROOT / "tests" / "real_data" / "golden_answer_manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "golden-quality"
DEFAULT_BASELINE_DIR = ROOT / "artifacts" / "golden-quality" / "baseline"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--update-baseline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    from data_agent.agent.golden_answer_runner import (
        load_golden_manifest,
        run_golden_manifest,
        write_baseline,
    )

    result_path = run_golden_manifest(
        manifest_path=args.manifest,
        data_dir=args.data_dir,
        output_root=args.output_root,
        mode="generate",
        baseline_dir=args.baseline_dir if args.update_baseline else None,
    )
    if args.update_baseline:
        manifest = load_golden_manifest(args.manifest)
        run = json.loads(result_path.read_text(encoding="utf-8"))
        ids_present = {s["id"] for s in manifest["scenarios"]}
        for scenario in run["scenarios"]:
            if scenario.get("status") == "evaluated" and scenario["id"] in ids_present:
                write_baseline(args.baseline_dir, scenario["id"], scenario["answer_text"])
    print(result_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
