from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from data_agent.config import get_config
from data_agent.v2.release import compute_release_source_digest, load_release_matrix
from data_agent.v2.representative_provider_preflight import (
    build_representative_provider_preflight,
    validate_representative_provider_preflight,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze and validate the exact matrix-selected Provider call group "
            "without issuing authorization or calling the Provider."
        )
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--matrix", type=Path, default=Path("tests/release/v2_release_matrix.json")
    )
    parser.add_argument("--preflight", type=Path)
    parser.add_argument(
        "--confirmed-analysis-unit-column",
        required=True,
        help="Bind the user-confirmed analysis unit for the unified call.",
    )
    args = parser.parse_args()

    source = compute_release_source_digest(args.root)
    matrix = load_release_matrix(args.matrix)
    cfg = get_config()
    current = build_representative_provider_preflight(
        repository_root=args.root,
        matrix=matrix,
        source_digest=source.source_digest,
        config=cfg,
        confirmed_analysis_unit_column=args.confirmed_analysis_unit_column,
    )
    preflight = (
        json.loads(args.preflight.read_text(encoding="utf-8"))
        if args.preflight is not None
        else current
    )
    result = validate_representative_provider_preflight(
        preflight,
        repository_root=args.root,
        matrix=matrix,
        expected_source_digest=source.source_digest,
        expected_model_id=cfg.model_id,
        expected_provider_host=urlparse(cfg.api_base or "").hostname or "",
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
