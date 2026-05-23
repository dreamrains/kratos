"""Comprehensive tests for Retrieval Service and end-to-end integration workflows."""

import json
from pathlib import Path

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryStatus, MemoryType
from data_agent.knowledge.retrieval import KnowledgeRetrievalService


# ── Retrieval Service Comprehensive ──────────────────────────────────


class TestRetrievalComposition:
    def test_compose_with_evidence_section(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_name": "test"}),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Revenue analysis for Q1"}]),
            encoding="utf-8",
        )

        store = EvidenceStore(root, sessions_dir=sessions_dir)
        store.index_session("s1")

        service = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir)
        context = service.retrieve("Revenue", project_id="test", include_evidence=True)
        prompt = service.compose_prompt_context(context)

        assert "<session_evidence" in prompt
        assert "s1" in prompt
        assert "</session_evidence>" in prompt

    def test_compose_with_conflict_section(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        memory = MemoryStore(root)

        library.create(
            title="GMV definition",
            domain="ecommerce",
            content="GMV excludes canceled orders.",
            summary="GMV rule",
        )
        candidate = memory.create_candidate(
            text="GMV includes all orders.",
            summary="Conflicting GMV memory",
            memory_type=MemoryType.DOMAIN_FACT,
            confidence=0.8,
            domain="ecommerce",
        )
        memory.confirm(candidate.id)

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("How to calculate GMV", domain="ecommerce")
        prompt = service.compose_prompt_context(context)

        assert "<knowledge_conflicts" in prompt
        assert "conflicts with" in prompt
        assert "</knowledge_conflicts>" in prompt

    def test_compose_empty_context_returns_empty_string(self, tmp_path: Path):
        service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
        context = service.retrieve("nonexistent xyzzy query")
        prompt = service.compose_prompt_context(context)
        assert prompt == ""

    def test_compose_only_knowledge_section(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        library.create("Rule", "general", "Revenue definition")

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("Revenue")
        prompt = service.compose_prompt_context(context)

        assert "<retrieved_knowledge" in prompt
        assert "<memory_hints" not in prompt
        assert "<session_evidence" not in prompt

    def test_compose_only_memory_section(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        memory = MemoryStore(root)
        item = memory.create_candidate(text="Revenue preference", confidence=0.8)
        memory.confirm(item.id)

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("Revenue")
        prompt = service.compose_prompt_context(context)

        assert "<memory_hints" in prompt
        assert "<retrieved_knowledge" not in prompt


class TestRetrievalDomainFilter:
    def test_retrieve_with_domain_filter(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        library.create("Ecom rule", "ecommerce", "Ecommerce revenue rule")
        library.create("Game rule", "gaming", "Gaming retention rule")

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("rule", domain="ecommerce")

        assert len(context.knowledge_items) == 1
        assert context.knowledge_items[0].domain == "ecommerce"

    def test_retrieve_without_domain_finds_all(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        library.create("Rule A", "ecommerce", "Revenue rule")
        library.create("Rule B", "gaming", "Retention rule")

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("rule")
        assert len(context.knowledge_items) == 2


class TestRetrievalConflictDetection:
    def test_no_conflict_when_agreeing(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        memory = MemoryStore(root)

        library.create(
            title="Revenue rule",
            domain="general",
            content="Revenue = total sales amount.",
            summary="Revenue definition",
        )
        candidate = memory.create_candidate(
            text="Revenue is the total sales amount.",
            summary="Revenue understanding",
            confidence=0.7,
        )
        memory.confirm(candidate.id)

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("Revenue")
        assert context.conflicts == []

    def test_conflict_with_english_markers(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        memory = MemoryStore(root)

        library.create(
            title="Active users",
            domain="general",
            content="Active users exclude dormant accounts.",
            summary="Active user definition",
        )
        candidate = memory.create_candidate(
            text="Active users include all registered accounts.",
            summary="Active user memory",
            confidence=0.6,
        )
        memory.confirm(candidate.id)

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("active users")
        assert len(context.conflicts) == 1
        assert context.conflicts[0].severity.value == "review"

    def test_chinese_conflict_markers(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        memory = MemoryStore(root)

        library.create(
            title="GMV定义",
            domain="ecommerce",
            content="GMV排除取消订单。",
            summary="GMV指标定义",
        )
        candidate = memory.create_candidate(
            text="GMV包含所有订单。",
            summary="GMV记忆",
            confidence=0.7,
            domain="ecommerce",
        )
        memory.confirm(candidate.id)

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("GMV", domain="ecommerce")
        assert len(context.conflicts) == 1


class TestRetrievalHTMLEscaping:
    def test_html_in_knowledge_content_is_escaped(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        library.create(
            title="<script>alert('xss')</script>",
            domain="general",
            content="Test <b>bold</b> & 'quotes' \"double\"",
        )

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("Test")
        prompt = service.compose_prompt_context(context)

        assert "<script>" not in prompt
        assert "&lt;script&gt;" in prompt
        assert "&lt;b&gt;" in prompt
        assert "&amp;" in prompt

    def test_html_in_memory_text_is_escaped(self, tmp_path: Path):
        root = tmp_path / "knowledge"
        memory = MemoryStore(root)
        item = memory.create_candidate(
            text="<img src=x onerror=alert(1)>Malicious",
            confidence=0.7,
        )
        memory.confirm(item.id)

        service = KnowledgeRetrievalService(root=root)
        context = service.retrieve("Malicious")
        prompt = service.compose_prompt_context(context)

        assert "<img" not in prompt
        assert "&lt;img" in prompt


class TestRetrievalNormalization:
    def test_query_normalization_removes_special_chars(self, tmp_path: Path):
        service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
        from data_agent.knowledge.retrieval import _normalize_query
        assert _normalize_query("Hello, World! 123") == "hello world 123"
        assert _normalize_query("GMV指标-定义") == "gmv指标 定义"


class TestRetrievalMetadata:
    def test_retrieve_metadata_includes_query_info(self, tmp_path: Path):
        service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
        context = service.retrieve("test query", domain="ecommerce", project_id="p1")
        assert context.metadata["query"] == "test query"
        assert context.metadata["domain"] == "ecommerce"
        assert context.metadata["project_id"] == "p1"
        assert context.metadata["include_evidence"] is False


# ── End-to-End Integration ───────────────────────────────────────────


class TestEndToEndWorkflow:
    def test_full_knowledge_memory_evidence_workflow(self, tmp_path: Path):
        """Test complete workflow: create knowledge, create memory, index evidence, retrieve all."""
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"

        # 1. Create formal knowledge
        library = KnowledgeLibrary(root)
        kn = library.create(
            title="GMV定义",
            domain="ecommerce",
            content="GMV = 已支付订单金额，排除取消订单。",
            summary="GMV指标定义",
            tags=["指标", "营收"],
        )
        assert kn.status.value == "active"

        # 2. Create memory candidate and confirm
        memory = MemoryStore(root)
        mem = memory.create_candidate(
            text="电商分析中应使用净收入而非总收入",
            summary="净收入偏好",
            memory_type=MemoryType.DOMAIN_FACT,
            confidence=0.8,
            domain="ecommerce",
            source_session_id="s1",
            tags=["营收"],
        )
        assert mem.status.value == "candidate"

        confirmed = memory.confirm(mem.id)
        assert confirmed.status.value == "confirmed"
        assert confirmed.confidence > mem.confidence

        # 3. Index session evidence
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps(
                {"session_id": "s1", "project_name": "ecommerce_analysis"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps(
                [
                    {"role": "user", "content": "请分析GMV指标"},
                    {"role": "assistant", "content": "GMV按渠道分析，排除取消订单后的净收入"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        evidence = EvidenceStore(root, sessions_dir=sessions_dir)
        count = evidence.index_session("s1")
        assert count == 2

        # 4. Retrieve everything together
        service = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir)
        context = service.retrieve(
            "GMV 营收",
            domain="ecommerce",
            project_id="ecommerce_analysis",
            include_evidence=True,
        )

        assert len(context.knowledge_items) >= 1
        assert len(context.memory_items) >= 1
        assert len(context.evidence_items) >= 1

        # 5. Compose prompt context
        prompt = service.compose_prompt_context(context)
        assert "<retrieved_knowledge" in prompt
        assert "<memory_hints" in prompt
        assert "<session_evidence" in prompt

    def test_knowledge_deprecation_then_restore_workflow(self, tmp_path: Path):
        """Test deprecating and restoring knowledge items."""
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)

        # Create, deprecate, verify hidden, restore, verify visible
        item = library.create("Old rule", "general", "Use the old calculation")
        library.deprecate(item.id)

        assert library.search("old calculation") == []
        assert library.search("old calculation", include_deprecated=True)[0].id == item.id

        library.restore(item.id)
        assert library.search("old calculation")[0].id == item.id

    def test_memory_lifecycle_all_transitions(self, tmp_path: Path):
        """Test all memory status transitions."""
        root = tmp_path / "knowledge"
        memory = MemoryStore(root)

        # Candidate -> Confirmed
        item = memory.create_candidate(text="Pattern A", confidence=0.7)
        assert item.status == MemoryStatus.CANDIDATE

        confirmed = memory.confirm(item.id)
        assert confirmed.status == MemoryStatus.CONFIRMED

        # Confirmed -> Promoted
        promoted = memory.mark_promoted(item.id)
        assert promoted.status == MemoryStatus.PROMOTED

        # A second item: Candidate -> Rejected
        item2 = memory.create_candidate(text="Pattern B", confidence=0.5)
        rejected = memory.reject(item2.id)
        assert rejected.status == MemoryStatus.REJECTED

        # A third item: Candidate -> Confirmed -> Deprecated
        item3 = memory.create_candidate(text="Pattern C", confidence=0.6)
        memory.confirm(item3.id)
        deprecated = memory.deprecate(item3.id)
        assert deprecated.status == MemoryStatus.DEPRECATED

    def test_knowledge_update_preserves_searchability(self, tmp_path: Path):
        """Test that updating knowledge preserves search functionality."""
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)

        item = library.create("Metric", "general", "Old definition of revenue")
        library.update(item.id, content="New definition of revenue and profit")

        results = library.search("profit")
        assert len(results) == 1
        assert "profit" in results[0].content

    def test_evidence_reindex_preserves_search(self, tmp_path: Path):
        """Test that reindexing a session updates evidence correctly."""
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1"}),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Version 1 message"}]),
            encoding="utf-8",
        )

        evidence = EvidenceStore(root, sessions_dir=sessions_dir)
        evidence.index_session("s1")

        results = evidence.search("Version")
        assert len(results) == 1
        assert "Version 1" in results[0].summary

        # Update the conversation
        (session_dir / "conversation.json").write_text(
            json.dumps([
                {"role": "user", "content": "Version 2 updated"},
                {"role": "assistant", "content": "Version 2 confirmed"},
            ]),
            encoding="utf-8",
        )
        evidence.index_session("s1")

        results = evidence.search("Version")
        assert len(results) == 2
        summaries = [r.summary for r in results]
        assert any("Version 2 updated" in s for s in summaries)
        assert not any("Version 1" in s for s in summaries)

    def test_touch_used_tracks_memory_utilization(self, tmp_path: Path):
        """Test that touch_used properly tracks usage statistics."""
        root = tmp_path / "knowledge"
        memory = MemoryStore(root)
        item = memory.create_candidate(text="Frequently used", confidence=0.7)
        memory.confirm(item.id)

        assert memory.get(item.id).hit_count == 0
        assert memory.get(item.id).last_used_at == ""

        touched = memory.touch_used(item.id)
        assert touched.hit_count == 1
        assert touched.last_used_at != ""

        touched2 = memory.touch_used(item.id)
        assert touched2.hit_count == 2


# ── Real Data Integration ─────────────────────────────────────────────


class TestRealDataIntegration:
    def test_index_real_session_structure(self, tmp_path: Path):
        """Test indexing a session with real-world structure."""
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"

        session_dir = sessions_dir / "game_analysis_001"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps(
                {
                    "session_id": "game_analysis_001",
                    "project_name": "游戏分析",
                    "saved_at": "2026-05-23 10:30:00",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps(
                [
                    {"role": "user", "content": "请分析游戏A的留存数据"},
                    {"role": "assistant", "content": "我来分析游戏A的留存情况。从数据来看，次日留存率为45%，七日留存率为22%，三十日留存率为8%。"},
                    {"role": "user", "content": "和游戏B对比怎么样？"},
                    {"role": "assistant", "content": "游戏B的次日留存率为52%，高于游戏A。但游戏A的付费转化率更高，达到3.5%。"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        evidence = EvidenceStore(root, sessions_dir=sessions_dir)
        count = evidence.index_session("game_analysis_001")
        assert count == 4

        # Search for retention-related evidence
        results = evidence.search("留存", project_id="游戏分析")
        assert len(results) >= 2

        # Search for revenue-related evidence
        results = evidence.search("付费 转化", project_id="游戏分析")
        assert len(results) >= 1

    def test_knowledge_with_chinese_domain_and_tags(self, tmp_path: Path):
        """Test knowledge items with Chinese domains and tags."""
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)

        item = library.create(
            title="次日留存率定义",
            domain="游戏分析",
            content="次日留存率 = 第2日回访用户数 / 新增用户数 × 100%",
            summary="游戏留存指标",
            tags=["留存", "指标", "游戏"],
        )

        assert item.domain == "游戏分析"
        assert "留存" in item.tags

        results = library.search("留存率", domain="游戏分析")
        assert len(results) == 1

        results = library.search("指标")
        assert len(results) == 1

    def test_memory_with_chinese_domain(self, tmp_path: Path):
        """Test memory items with Chinese domains."""
        root = tmp_path / "knowledge"
        memory = MemoryStore(root)

        item = memory.create_candidate(
            text="游戏分析中，用户通常先关注留存率再关注付费转化率",
            summary="游戏分析流程偏好",
            memory_type=MemoryType.WORKFLOW_PATTERN,
            confidence=0.75,
            domain="游戏分析",
            tags=["留存", "付费"],
        )
        memory.confirm(item.id)

        results = memory.search("留存 付费", domain="游戏分析")
        assert len(results) == 1

    def test_full_chinese_workflow(self, tmp_path: Path):
        """Complete workflow with Chinese content: knowledge + memory + evidence + retrieval."""
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"

        # Create knowledge
        library = KnowledgeLibrary(root)
        library.create(
            title="ARPU定义",
            domain="游戏分析",
            content="ARPU = 总收入 / 活跃用户数，不包含自然流量收入。",
            summary="ARPU指标定义",
            tags=["指标"],
        )

        # Create and confirm memory
        memory = MemoryStore(root)
        mem = memory.create_candidate(
            text="ARPU计算包含所有收入来源。",
            summary="ARPU计算方法",
            memory_type=MemoryType.DOMAIN_FACT,
            confidence=0.7,
            domain="游戏分析",
        )
        memory.confirm(mem.id)

        # Index evidence
        session_dir = sessions_dir / "s_cn"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s_cn", "project_name": "游戏分析"}),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps(
                [
                    {"role": "user", "content": "请计算ARPU"},
                    {"role": "assistant", "content": "ARPU = 总收入 / 活跃用户数"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        EvidenceStore(root, sessions_dir=sessions_dir).index_session("s_cn")

        # Retrieve with conflict detection
        service = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir)
        context = service.retrieve(
            "ARPU 计算方法",
            domain="游戏分析",
            project_id="游戏分析",
            include_evidence=True,
        )

        assert len(context.knowledge_items) >= 1
        assert len(context.evidence_items) >= 1
        # Knowledge says "不包含" but memory says "包含所有" -> conflict
        assert len(context.conflicts) >= 1

        prompt = service.compose_prompt_context(context)
        assert "<retrieved_knowledge" in prompt
        assert "<knowledge_conflicts" in prompt
        assert "<session_evidence" in prompt
