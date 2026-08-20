from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from data_agent.config import get_config
from data_agent.v2.real_provider_journey import (
    UNIFIED_FIXTURE_PATH,
    build_real_provider_preflight,
    validate_real_provider_preflight,
)
from data_agent.v2.release import compute_release_source_digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Count and validate the first unified real-provider planning request "
            "without issuing authorization or calling the Provider."
        )
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--preflight",
        type=Path,
        help="Validate an existing preflight instead of building a new one.",
    )
    args = parser.parse_args()

    source = compute_release_source_digest(args.root)
    cfg = get_config()
    current_preflight = build_real_provider_preflight(
        fixture_path=args.root / UNIFIED_FIXTURE_PATH,
        source_digest=source.source_digest,
        config=cfg,
    )
    preflight = (
        json.loads(args.preflight.read_text(encoding="utf-8"))
        if args.preflight is not None
        else current_preflight
    )
    result = validate_real_provider_preflight(
        preflight,
        expected_source_digest=source.source_digest,
        expected_model_id=cfg.model_id,
        expected_dataset_fingerprint=(
            "sha256:"
            + hashlib.sha256(
                (args.root / UNIFIED_FIXTURE_PATH).read_bytes()
            ).hexdigest()
        ),
        expected_planner_contract_gate=current_preflight["planner_contract_gate"],
    )
    print(
        json.dumps(
            {
                "status": "pass" if result.passed else "fail",
                "reason_codes": list(result.reason_codes),
                "preflight": preflight,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
