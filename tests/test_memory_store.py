from pathlib import Path

import pytest

from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryStatus, MemoryType


def test_create_confirm_reject_and_deprecate_memory(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    candidate = store.create_candidate(
        text="Use net revenue for ecommerce revenue analysis.",
        summary="Prefer net revenue.",
        memory_type=MemoryType.DOMAIN_FACT,
        confidence=0.72,
        source_session_id="s1",
        domain="ecommerce",
        tags=["metric"],
    )

    assert candidate.status == MemoryStatus.CANDIDATE
    assert candidate.type == MemoryType.DOMAIN_FACT
    assert candidate.source_session_id == "s1"
    assert candidate.domain == "ecommerce"
    assert candidate.tags == ["metric"]
    assert store.list(status=MemoryStatus.CANDIDATE.value)[0].id == candidate.id

    confirmed = store.confirm(candidate.id)
    assert confirmed is not None
    assert confirmed.status == MemoryStatus.CONFIRMED
    assert confirmed.confidence > candidate.confidence

    reject_candidate = store.create_candidate(text="Reject this memory.")
    rejected = store.reject(reject_candidate.id)
    assert rejected is not None
    assert rejected.status == MemoryStatus.REJECTED

    deprecated = store.deprecate(confirmed.id)
    assert deprecated is not None
    assert deprecated.status == MemoryStatus.DEPRECATED

    promote_candidate = store.create_candidate(text="Promote this memory.")
    promoted_base = store.confirm(promote_candidate.id)
    promoted = store.mark_promoted(promoted_base.id)
    assert promoted is not None
    assert promoted.status == MemoryStatus.PROMOTED


def test_confirmed_memory_search_excludes_candidates(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    store.create_candidate(
        text="Always inspect MCP config for tool startup failures.",
        summary="MCP startup troubleshooting.",
        memory_type=MemoryType.WORKFLOW_PATTERN,
        confidence=0.6,
    )

    assert store.search("MCP startup") == []
    candidate = store.list(status=MemoryStatus.CANDIDATE.value)[0]
    store.confirm(candidate.id)

    assert store.search("MCP startup")[0].id == candidate.id


def test_touch_used_updates_usage_metadata(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    item = store.create_candidate(
        text="Check workbook headers before analysis.",
        summary="Workbook header check.",
    )

    touched = store.touch_used(item.id)

    assert touched is not None
    assert touched.hit_count == 1
    assert touched.last_used_at


def test_invalid_memory_type_status_and_confidence_are_rejected(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    with pytest.raises(ValueError, match="memory_type"):
        store.create_candidate(text="Bad type.", memory_type="not-a-type")

    with pytest.raises(ValueError, match="confidence"):
        store.create_candidate(text="Bad confidence.", confidence=1.5)

    with pytest.raises(ValueError, match="confidence"):
        store.create_candidate(text="Bad confidence.", confidence="nan")

    with pytest.raises(ValueError, match="status"):
        store.list(status="not-a-status")


def test_json_list_fields_reject_strings_and_round_trip_lists(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    with pytest.raises(ValueError, match="tags"):
        store.create_candidate(text="Bad tags.", tags="metric")

    item = store.create_candidate(
        text="Keep source references.",
        source_message_ids=["m1", "m2"],
        source_tool_call_ids=["t1"],
        tags=["metric", "source"],
    )

    loaded = store.get(item.id)
    assert loaded is not None
    assert loaded.source_message_ids == ["m1", "m2"]
    assert loaded.source_tool_call_ids == ["t1"]
    assert loaded.tags == ["metric", "source"]


def test_search_domain_filter_limit_and_stable_order(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    older = store.confirm(
        store.create_candidate(
            text="Use net revenue in ecommerce reporting.",
            summary="net revenue",
            domain="ecommerce",
            confidence=0.8,
        ).id
    )
    newer = store.confirm(
        store.create_candidate(
            text="Use net revenue in ecommerce dashboards.",
            summary="net revenue",
            domain="ecommerce",
            confidence=0.8,
        ).id
    )
    store.confirm(
        store.create_candidate(
            text="Use net revenue in finance reporting.",
            summary="net revenue",
            domain="finance",
            confidence=0.95,
        ).id
    )

    assert store.search("net revenue", limit=0) == []
    expected = sorted([older, newer], key=lambda item: (item.updated_at, item.id), reverse=True)
    assert store.search("net revenue", domain="ecommerce", limit=10) == expected


def test_touch_used_missing_id_returns_none(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    assert store.touch_used("missing") is None


def test_terminal_statuses_cannot_be_confirmed(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    rejected = store.reject(store.create_candidate(text="Reject.").id)
    deprecated = store.deprecate(store.confirm(store.create_candidate(text="Deprecate.").id).id)
    promoted = store.mark_promoted(store.confirm(store.create_candidate(text="Promote.").id).id)

    assert store.confirm(rejected.id).status == MemoryStatus.REJECTED
    assert store.confirm(deprecated.id).status == MemoryStatus.DEPRECATED
    assert store.confirm(promoted.id).status == MemoryStatus.PROMOTED
