"""Comprehensive tests for knowledge library, memory store, and evidence store edge cases."""

import json
import math
from pathlib import Path

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import (
    EvidenceKind,
    KnowledgeSource,
    KnowledgeStatus,
    MemoryStatus,
    MemoryType,
)


# ── Knowledge Library ─────────────────────────────────────────────────


class TestKnowledgeLibraryList:
    def test_list_with_combined_domain_and_status(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        library.create("A", "ecommerce", "Content A")
        library.create("B", "ecommerce", "Content B")
        b_id = library.create("C", "general", "Content C").id
        library.deprecate(b_id)

        active_ecom = library.list(domain="ecommerce", status="active")
        assert len(active_ecom) == 2
        assert all(i.domain == "ecommerce" for i in active_ecom)

        deprecated_general = library.list(domain="general", status="deprecated")
        assert len(deprecated_general) == 1
        assert deprecated_general[0].id == b_id

    def test_list_no_filters_returns_all(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        library.create("A", "ecommerce", "Content A")
        library.create("B", "general", "Content B")

        all_items = library.list()
        assert len(all_items) == 2

    def test_list_empty_result(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        assert library.list(domain="nonexistent") == []


class TestKnowledgeLibrarySearch:
    def test_search_no_results(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        library.create("Metric", "general", "Revenue definition")
        assert library.search("xyzzy no match") == []

    def test_search_empty_query_terms_returns_empty(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        library.create("Metric", "general", "Revenue definition")
        assert library.search("   ") == []

    def test_search_respects_limit(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        for i in range(10):
            library.create(f"Revenue item {i}", "general", f"Revenue definition {i}")
        results = library.search("Revenue", limit=3)
        assert len(results) <= 3

    def test_search_chinese_content(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        library.create(
            "GMV定义",
            "ecommerce",
            "GMV = 已支付订单金额，排除取消订单。",
            summary="GMV指标定义",
            tags=["指标"],
        )
        results = library.search("GMV 排除")
        assert len(results) == 1
        assert "GMV" in results[0].title

    def test_search_finds_by_tag(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        library.create("Metric", "general", "Content", tags=["revenue", "kpi"])
        results = library.search("kpi")
        assert len(results) == 1


class TestKnowledgeLibraryEdgeCases:
    def test_create_with_empty_domain_falls_back_to_general(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create("Metric", "", "Content")
        assert item.domain == "general"

    def test_create_with_whitespace_domain_falls_back_to_general(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create("Metric", "   ", "Content")
        assert item.domain == "general"

    def test_create_with_source_memory_promotion(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create(
            "Promoted knowledge",
            "general",
            "Content from memory",
            source=KnowledgeSource.MEMORY_PROMOTION,
        )
        assert item.source == KnowledgeSource.MEMORY_PROMOTION

    def test_get_nonexistent_returns_none(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        assert library.get("kn_nonexistent") is None

    def test_update_nonexistent_returns_none(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        assert library.update("kn_nonexistent", content="x") is None

    def test_delete_nonexistent_returns_false(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        assert library.delete("kn_nonexistent") is False

    def test_update_preserves_tags(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create("Metric", "general", "Content", tags=["a", "b"])
        updated = library.update(item.id, summary="New summary")
        assert updated.tags == ["a", "b"]
        assert updated.summary == "New summary"

    def test_update_overrides_tags(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create("Metric", "general", "Content", tags=["old"])
        updated = library.update(item.id, tags=["new1", "new2"])
        assert updated.tags == ["new1", "new2"]

    def test_deprecate_nonexistent_returns_none(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        assert library.deprecate("kn_nonexistent") is None

    def test_restore_nonexistent_returns_none(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        assert library.restore("kn_nonexistent") is None

    def test_deprecated_item_content_still_readable(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create("Rule", "general", "Original content")
        library.deprecate(item.id)
        loaded = library.get(item.id)
        assert loaded is not None
        assert loaded.content == "Original content"
        assert loaded.status == KnowledgeStatus.DEPRECATED

    def test_create_chinese_title_and_domain(self, tmp_path: Path):
        library = KnowledgeLibrary(tmp_path / "knowledge")
        item = library.create("留存率定义", "游戏分析", "留存率 = 第N日回访用户数 / 新增用户数")
        assert item.domain == "游戏分析"
        assert "留存" in item.title


# ── Memory Store ──────────────────────────────────────────────────────


class TestMemoryStoreLifecycle:
    def test_mark_promoted_from_confirmed(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(
            text="Pattern discovered",
            memory_type=MemoryType.WORKFLOW_PATTERN,
            confidence=0.8,
        )
        store.confirm(item.id)
        promoted = store.mark_promoted(item.id)
        assert promoted.status == MemoryStatus.PROMOTED

    def test_mark_promoted_from_candidate_is_noop(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Still candidate", confidence=0.6)
        result = store.mark_promoted(item.id)
        assert result.status == MemoryStatus.CANDIDATE

    def test_reject_from_candidate(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Reject me", confidence=0.5)
        rejected = store.reject(item.id)
        assert rejected.status == MemoryStatus.REJECTED

    def test_reject_from_confirmed_is_noop(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Already confirmed", confidence=0.7)
        store.confirm(item.id)
        result = store.reject(item.id)
        assert result.status == MemoryStatus.CONFIRMED

    def test_deprecate_from_confirmed(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Deprecate me", confidence=0.7)
        store.confirm(item.id)
        result = store.deprecate(item.id)
        assert result.status == MemoryStatus.DEPRECATED

    def test_deprecate_from_candidate_is_noop(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Still candidate", confidence=0.5)
        result = store.deprecate(item.id)
        assert result.status == MemoryStatus.CANDIDATE


class TestMemoryStoreValidation:
    def test_confidence_zero_accepted(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Low confidence", confidence=0.0)
        assert item.confidence == 0.0

    def test_confidence_one_accepted(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="High confidence", confidence=1.0)
        assert item.confidence == 1.0

    def test_confidence_nan_rejected(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        try:
            store.create_candidate(text="NaN", confidence=float("nan"))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_confidence_infinity_rejected(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        try:
            store.create_candidate(text="Inf", confidence=float("inf"))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_confidence_above_one_rejected(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        try:
            store.create_candidate(text="Over", confidence=1.5)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_confidence_below_zero_rejected(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        try:
            store.create_candidate(text="Under", confidence=-0.1)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestMemoryStoreOptionalFields:
    def test_create_with_all_optional_fields(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(
            text="Full memory",
            summary="Full summary",
            memory_type=MemoryType.CORRECTION,
            confidence=0.85,
            source_session_id="session_123",
            source_message_ids=["msg_1", "msg_2"],
            source_tool_call_ids=["tool_1"],
            project_id="project_abc",
            domain="ecommerce",
            tags=["metric", "revenue"],
            promotion_target="knowledge",
        )
        assert item.source_session_id == "session_123"
        assert item.source_message_ids == ["msg_1", "msg_2"]
        assert item.source_tool_call_ids == ["tool_1"]
        assert item.project_id == "project_abc"
        assert item.domain == "ecommerce"
        assert item.tags == ["metric", "revenue"]
        assert item.promotion_target == "knowledge"
        assert item.type == MemoryType.CORRECTION


class TestMemoryStoreSearch:
    def test_search_empty_query_returns_empty(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        store.create_candidate(text="Something", confidence=0.7)
        assert store.search("   ") == []

    def test_search_with_domain_filter(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item_a = store.create_candidate(text="Ecommerce revenue", domain="ecommerce", confidence=0.8)
        store.create_candidate(text="Revenue metrics", domain="general", confidence=0.7)
        store.confirm(item_a.id)

        results = store.search("revenue", domain="ecommerce")
        assert len(results) == 1
        assert results[0].domain == "ecommerce"

    def test_search_zero_limit_returns_empty(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Revenue", confidence=0.8)
        store.confirm(item.id)
        assert store.search("Revenue", limit=0) == []

    def test_get_nonexistent_returns_none(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        assert store.get("mem_nonexistent") is None


class TestMemoryStoreConfirm:
    def test_confirm_caps_at_095(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="High", confidence=0.9)
        confirmed = store.confirm(item.id)
        assert confirmed.confidence == 0.95

    def test_confirm_already_confirmed_is_noop(self, tmp_path: Path):
        store = MemoryStore(tmp_path / "knowledge")
        item = store.create_candidate(text="Once", confidence=0.6)
        first = store.confirm(item.id)
        second = store.confirm(first.id)
        assert second.status == MemoryStatus.CONFIRMED
        assert second.confidence == first.confidence


# ── Evidence Store ────────────────────────────────────────────────────


class TestEvidenceStoreGet:
    def test_get_returns_indexed_record(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_name": "test"}),
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Hello world"}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")
        record = store.get("ev_s1_0")
        assert record is not None
        assert record.session_id == "s1"
        assert "Hello world" in record.content

    def test_get_nonexistent_returns_none(self, tmp_path: Path):
        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=tmp_path / "sessions")
        assert store.get("ev_nonexistent_0") is None


class TestEvidenceStoreEdgeCases:
    def test_index_empty_session_returns_zero(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "empty"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text("{}")
        (session_dir / "conversation.json").write_text("[]")

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        assert store.index_session("empty") == 0

    def test_index_session_skips_non_dict_messages(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "mixed"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text("{}")
        (session_dir / "conversation.json").write_text(
            json.dumps([
                {"role": "user", "content": "Valid"},
                "not a dict",
                42,
                {"role": "assistant", "content": "Also valid"},
            ]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        count = store.index_session("mixed")
        assert count == 2

    def test_index_multiple_sessions(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        for sid in ("s1", "s2"):
            d = sessions_dir / sid
            d.mkdir(parents=True)
            (d / "meta.json").write_text(
                json.dumps({"session_id": sid, "project_name": "proj"}),
            )
            (d / "conversation.json").write_text(
                json.dumps([{"role": "user", "content": f"Message in {sid}"}]),
            )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        assert store.index_session("s1") == 1
        assert store.index_session("s2") == 1

        results = store.search("Message")
        assert len(results) == 2

    def test_search_without_project_filter(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_name": "alpha"}),
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Revenue analysis"}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")

        results = store.search("Revenue", project_id="")
        assert len(results) == 1

    def test_search_wrong_project_returns_empty(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_name": "alpha"}),
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Revenue analysis"}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")

        results = store.search("Revenue", project_id="wrong_project")
        assert results == []

    def test_index_session_with_chinese_content(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "cn_session"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "cn_session", "project_name": "游戏分析"}),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([
                {"role": "user", "content": "请分析游戏A的留存率"},
                {"role": "assistant", "content": "正在分析留存数据，DAU环比增长15%"},
            ], ensure_ascii=False),
            encoding="utf-8",
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        count = store.index_session("cn_session")
        assert count == 2

        results = store.search("留存率", project_id="游戏分析")
        assert len(results) >= 1
        assert "留存" in results[0].content

    def test_index_nonexistent_session_returns_zero(self, tmp_path: Path):
        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=tmp_path / "sessions")
        assert store.index_session("nonexistent") == 0

    def test_index_session_with_project_id_meta(self, tmp_path: Path):
        """Test that project_id field in meta.json is also read."""
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_id": "my_project"}),
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Hello"}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")

        record = store.get("ev_s1_0")
        assert record.project_id == "my_project"

    def test_search_empty_query_returns_empty(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text("{}")
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Hello"}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")
        assert store.search("   ") == []

    def test_search_zero_limit_returns_empty(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text("{}")
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Hello"}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")
        assert store.search("Hello", limit=0) == []

    def test_message_with_non_string_content(self, tmp_path: Path):
        """Test that messages with dict/list content are JSON-serialized."""
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text("{}")
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "assistant", "content": {"type": "text", "text": "Nested"}}]),
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        count = store.index_session("s1")
        assert count == 1
        record = store.get("ev_s1_0")
        assert "Nested" in record.content

    def test_reindex_session_updates_evidence(self, tmp_path: Path):
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text("{}", encoding="utf-8")
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Version 1"}]),
            encoding="utf-8",
        )

        store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
        store.index_session("s1")
        assert store.search("Version 1")

        (session_dir / "conversation.json").write_text(
            json.dumps([
                {"role": "user", "content": "Version 2 updated"},
                {"role": "assistant", "content": "Version 2 confirmed"},
            ]),
            encoding="utf-8",
        )
        store.index_session("s1")

        results = store.search("Version")
        assert len(results) == 2
        summaries = [r.summary for r in results]
        assert any("Version 2 updated" in s for s in summaries)
        assert any("Version 2 confirmed" in s for s in summaries)
        # Old evidence should be gone
        assert not any("Version 1" in s for s in summaries)
