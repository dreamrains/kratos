from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from data_agent.v2.release import (
    ReleaseReceipt,
    compute_release_source_digest,
    load_release_matrix,
)
from data_agent.v2.workbench_browser_journey import (
    compose_provider_neutral_workbench_release_receipts,
)


def _receipt_payload(receipt: ReleaseReceipt) -> dict:
    payload = asdict(receipt)
    payload["layer"] = receipt.layer.value
    payload["status"] = receipt.status.value
    payload["semantic_dimensions"] = {
        name: status.value for name, status in receipt.semantic_dimensions
    }
    for key in (
        "evidence_refs",
        "observed_semantic_events",
        "observed_block_types",
        "observed_interactions",
        "forbidden_behavior_hits",
    ):
        payload[key] = list(payload[key])
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compose current-source planning and interaction observations into "
            "unified browser and refresh release receipts."
        )
    )
    parser.add_argument("--planning-receipt", type=Path, required=True)
    parser.add_argument("--interaction-receipt", type=Path, required=True)
    parser.add_argument(
        "--matrix", type=Path, default=Path("tests/release/v2_release_matrix.json")
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    source = compute_release_source_digest(args.root)
    matrix = load_release_matrix(args.matrix)
    scenario = next(
        item for item in matrix.scenarios if item.scenario_id == "unified_analysis_entry"
    )
    planning = json.loads(args.planning_receipt.read_text(encoding="utf-8"))
    interaction = json.loads(args.interaction_receipt.read_text(encoding="utf-8"))
    result = compose_provider_neutral_workbench_release_receipts(
        planning,
        interaction,
        scenario=scenario,
        expected_source_digest=source.source_digest,
    )
    print(
        json.dumps(
            {
                "status": "pass" if result.passed else "fail",
                "source_digest": source.source_digest,
                "reason_codes": list(result.reason_codes),
                "release_receipts": [
                    _receipt_payload(receipt) for receipt in result.receipts
                ],
                "provider_calls": 0,
                "release_readiness_claimed": False,
                "root_switch_authorized": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
