from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_agent.v2.release import compute_release_source_digest
from data_agent.v2.workbench_browser_journey import (
    validate_provider_neutral_journey,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one actual-browser provider-neutral journey receipt."
    )
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    source = compute_release_source_digest(args.root)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    result = validate_provider_neutral_journey(
        receipt, expected_source_digest=source.source_digest
    )
    print(
        json.dumps(
            {
                "status": "pass" if result.passed else "fail",
                "source_digest": source.source_digest,
                "reason_codes": list(result.reason_codes),
                "observed_interactions": list(result.observed_interactions),
                "release_readiness_claimed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
