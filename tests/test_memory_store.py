from pathlib import Path

import pytest

from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryStatus, MemoryType


def test_create_confirm_reject_and_deprecate_memory(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    item = store.create_candidate(
        text="Use net revenue for ecommerce revenue analysis.",
        summary="Prefer net revenue.",
        memory_type=MemoryType.DOMAIN_FACT,
        confidence=0.72,
        source_session_id="s1",
        domain="ecommerce",
        tags=["metric"],
    )

    assert item.status == MemoryStatus.CANDIDATE
    assert item.type == MemoryType.DOMAIN_FACT
    assert item.source_session_id == "s1"
    assert item.domain == "ecommerce"
    assert item.tags == ["metric"]
    assert store.list(status=MemoryStatus.CANDIDATE.value)[0].id == item.id

    confirmed = store.confirm(item.id)
    assert confirmed is not None
    assert confirmed.status == MemoryStatus.CONFIRMED
    assert confirmed.confidence > item.confidence

    rejected = store.reject(item.id)
    assert rejected is not None
    assert rejected.status == MemoryStatus.REJECTED

    deprecated = store.deprecate(item.id)
    assert deprecated is not None
    assert deprecated.status == MemoryStatus.DEPRECATED


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

    with pytest.raises(ValueError, match="status"):
        store.list(status="not-a-status")
