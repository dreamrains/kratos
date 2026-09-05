# tests/replay/test_real_shape_projection.py
"""Real-shape replay: recorded tool payloads must survive evidence binding.

These fixtures come from consumed real-Provider batches (see fixtures
README).  A projection crash or a dropped native statistics source here
is the offline signal that used to cost one real batch to discover.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_agent.tools.evidence_statistics import bind_computed_statistics

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))
pytestmark = pytest.mark.skipif(not FIXTURES, reason="no replay fixtures generated yet")


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
def test_recorded_shapes_bind_without_crashing(fixture, monkeypatch):
    import hashlib

    from data_agent.tools import result_reference

    recorded = json.loads(fixture.read_text(encoding="utf-8"))["turns"]
    lookup, receipts = {}, []
    for index, turn in enumerate(recorded):
        receipt_id = f"replay_{index:03d}"
        digest = hashlib.sha256(json.dumps(
            turn["structured_result"], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        lookup[f"tool_outputs/{receipt_id}_detail.json"] = (
            turn["structured_result"], {"receipt_id": receipt_id})
        receipts.append({"id": receipt_id, "tool_call_id": receipt_id,
                         "tool_name": turn["tool"], "arguments": {},
                         "structured_result_sha256": digest})
    # bind_computed_statistics 在函数体内 import，patch 模块属性即生效。
    monkeypatch.setattr(result_reference, "load_result_reference", lambda ref: lookup[ref])

    payload = {"claim": "replay", "metrics": {"reported": 1}}
    bind_computed_statistics(payload, receipts)
    assert payload["computed_statistics_sources"], \
        f"{fixture.stem}: recorded shapes must bind as evidence sources"
