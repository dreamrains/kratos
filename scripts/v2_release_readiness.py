from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_agent.v2.release import (
    compute_release_source_digest,
    evaluate_release_readiness,
    load_receipts,
    load_release_matrix,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Data Agent V2 release readiness inspection."
    )
    parser.add_argument("command", choices=("digest", "evaluate"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("tests/release/v2_release_matrix.json"),
    )
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--include-files", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    snapshot = compute_release_source_digest(args.root)
    if args.command == "digest":
        payload = snapshot.to_dict(include_files=args.include_files)
    else:
        matrix = load_release_matrix(args.manifest)
        decision = evaluate_release_readiness(
            matrix,
            load_receipts(args.receipts),
            current_source_digest=snapshot.source_digest,
        )
        payload = {
            "source": snapshot.to_dict(include_files=args.include_files),
            "decision": decision.to_dict(),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
