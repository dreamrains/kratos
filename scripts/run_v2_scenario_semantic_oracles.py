from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from data_agent.v2.release import (
    ReleaseReceipt,
    compute_release_source_digest,
    load_release_matrix,
)
from data_agent.v2.scenario_semantic_oracle import (
    collect_scenario_semantic_evidence,
    validate_scenario_semantic_evidence,
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
            "Run or validate all fixture-bound, provider-neutral V2 scenario "
            "semantic oracles."
        )
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--matrix", type=Path, default=Path("tests/release/v2_release_matrix.json")
    )
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()

    source = compute_release_source_digest(args.root)
    matrix = load_release_matrix(args.matrix)
    if args.evidence is not None:
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    else:
        with tempfile.TemporaryDirectory(prefix="data-agent-v2-semantic-") as temp:
            evidence = collect_scenario_semantic_evidence(
                temp,
                matrix=matrix,
                source_digest=source.source_digest,
                repository_root=args.root,
            )
    result = validate_scenario_semantic_evidence(
        evidence,
        matrix=matrix,
        expected_source_digest=source.source_digest,
    )
    print(
        json.dumps(
            {
                "status": "pass" if result.passed else "fail",
                "source_digest": source.source_digest,
                "reason_codes": list(result.reason_codes),
                "evidence": evidence,
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
