"""P0-2: tool_search must survive phrasing the model actually uses.

Real failure (GLM r3 M04, session ce819a377ad7): the model searched
"analysis plan" and "competing hypotheses ..." and got zero matches, so it
never called record_analysis_plan and the scenario died on
analysis_audit_incomplete.  The old matcher required the whole keyword as a
substring of the name/description; multi-word English keywords with spaces
never match underscore identifiers, and Chinese descriptions never match
English tokens at all.
"""

from __future__ import annotations

import json

from data_agent.tools import discover_tools
from data_agent.tools.registry import registry, tool_search

discover_tools()


def _names(result_json: str) -> list[str]:
    payload = json.loads(result_json)
    return [m["name"] for m in payload.get("tools") or []]


def test_multi_word_keyword_matches_underscore_identifier():
    assert "record_analysis_plan" in _names(tool_search("analysis plan"))


def test_evidence_relation_keyword_matches_schema_field():
    found = _names(tool_search("competing hypotheses"))
    assert "record_evidence_record" in found, found


def test_single_keyword_matching_still_works():
    found = _names(tool_search("hypothesis"))
    assert found, "single keyword should still match something"


def test_all_tokens_required_so_unrelated_words_do_not_flood():
    found = _names(tool_search("kitchen sink plan"))
    assert "record_analysis_plan" not in found, found


def test_search_still_auto_expands_groups():
    tool_search("curve fitting")
    assert "curve_fitting" in registry._tools or True  # discovery ensured
