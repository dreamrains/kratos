"""Golden final-answer quality measurement harness.

Measurement-only layer. Not imported by agent runtime synthesis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLDEN_MANIFEST_SCHEMA = "golden_answer_scenarios.v1"
ALLOWED_SOFT_DIMENSIONS = {
    "rigor",
    "insight_depth",
    "guidance",
    "data_explanation",
    "direction_expansion",
    "synthesis",
}


class GoldenManifestError(ValueError):
    pass


def load_golden_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoldenManifestError(f"malformed golden manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise GoldenManifestError("golden manifest root must be an object")
    if manifest.get("schema_version") != GOLDEN_MANIFEST_SCHEMA:
        raise GoldenManifestError(
            f"golden manifest schema_version must be {GOLDEN_MANIFEST_SCHEMA}"
        )
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise GoldenManifestError("golden manifest scenarios must be a non-empty list")
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            raise GoldenManifestError(f"scenario {index} requires a string id")
        required_files = scenario.get("required_files")
        if not isinstance(required_files, list) or not all(
            isinstance(name, str) and name for name in required_files
        ):
            raise GoldenManifestError(
                f"scenario {scenario['id']} has invalid required_files"
            )
        if not isinstance(scenario.get("business_question"), str) or not scenario["business_question"]:
            raise GoldenManifestError(
                f"scenario {scenario['id']} requires a business_question"
            )
        focus = scenario.get("soft_dimension_focus", [])
        if not isinstance(focus, list) or not set(focus).issubset(ALLOWED_SOFT_DIMENSIONS):
            raise GoldenManifestError(
                f"scenario {scenario['id']} has invalid soft_dimension_focus"
            )
    return manifest
