from __future__ import annotations

import json
from pathlib import Path

from data_agent.agent import execution_control, loop
from data_agent.tools import discover_tools
from data_agent.tools.registry import DEFAULT_TOOL_CAPABILITIES, TOOL_GROUPS, registry


ROOT = Path(__file__).resolve().parents[1]
TOOL_MANIFEST = ROOT / "tests" / "acceptance" / "tool_surface_manifest.json"
FAILURE_INDEX = ROOT / "tests" / "acceptance" / "failure_acceptance_index.json"


def _tool_manifest() -> dict:
    return json.loads(TOOL_MANIFEST.read_text(encoding="utf-8"))


def test_registered_tool_surface_matches_reviewed_manifest_exactly():
    discover_tools()
    manifest = _tool_manifest()
    assert manifest["schema_version"] == "tool_surface_manifest.v1"
    assert set(registry.tool_names) == set(manifest["tools"])
    assert len(registry.tool_names) == len(set(manifest["tools"])) == 73


def test_static_tool_references_resolve_to_registered_tools():
    discover_tools()
    registered = set(registry.tool_names)
    grouped = set().union(*TOOL_GROUPS.values())
    referenced = (
        grouped
        | set(DEFAULT_TOOL_CAPABILITIES)
        | set(loop._SUBSTANTIVE_TOOLS)
        | set(execution_control._META_TOOLS)
        | execution_control.TurnExecutionState._fallback_resolution_tools()
    )
    assert referenced - registered == set()


def test_removed_or_never_registered_tools_have_no_runtime_references():
    removed = set(_tool_manifest()["removed_tools"]) | {"record_insight_record"}
    offenders: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        matched = sorted(name for name in removed if name in text)
        if matched:
            offenders.append(f"{path.relative_to(ROOT)}: {matched}")
    assert offenders == []


def test_failure_acceptance_index_covers_f01_through_f33_without_false_closure():
    payload = json.loads(FAILURE_INDEX.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "failure_acceptance_index.v1"
    items = payload["items"]
    assert [item["id"] for item in items] == [f"F{number:02d}" for number in range(1, 34)]
    assert all(item["tests"] for item in items)
    assert all(
        (ROOT / test_path).is_file()
        for item in items
        for test_path in item["tests"]
    )
    guarded = {item["id"] for item in items if item["slice0_status"] == "contract_guard"}
    assert guarded == {"F26", "F27", "F28"}
    assert all(item["target_slice"] > 0 for item in items if item["slice0_status"] == "characterized")
