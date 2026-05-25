"""Tests using real data files from test_doc directory for evidence and knowledge workflows."""

import json
from pathlib import Path

import pytest

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryType
from data_agent.knowledge.retrieval import KnowledgeRetrievalService

TEST_DOC_DIR = Path("D:/Project/Daily/data-agent/reference/test_doc")


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="test_doc directory not found")
class TestRealDataFiles:
    def test_real_data_files_exist(self):
        """Verify all expected test data files are accessible."""
        files = list(TEST_DOC_DIR.glob("*.xlsx"))
        assert len(files) >= 5
        file_names = [f.stem for f in files]
        assert any("游戏" in n for n in file_names)
        assert any("省钱卡" in n for n in file_names)

    def test_create_knowledge_from_real_domain(self, tmp_path: Path):
        """Test creating knowledge items that match real data domains."""
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)

        # Knowledge about game analytics metrics
        kn = library.create(
            title="游戏留存率定义",
            domain="游戏分析",
            content=(
                "次日留存率 = 第2日回访用户数 / 首日新增用户数 × 100%\n"
                "七日留存率 = 第7日回访用户数 / 首日新增用户数 × 100%\n"
                "留存率是衡量游戏质量和用户粘性的核心指标。"
            ),
            summary="游戏留存率指标计算方法",
            tags=["留存率", "游戏", "指标"],
        )

        assert kn.domain == "游戏分析"
        assert kn.status.value == "active"

        # Knowledge about revenue metrics
        kn2 = library.create(
            title="游戏内购收入定义",
            domain="游戏分析",
            content=(
                "内购收入 = 付费用户消费金额总和\n"
                "ARPPU = 内购收入 / 付费用户数\n"
                "付费转化率 = 付费用户数 / 活跃用户数 × 100%"
            ),
            summary="游戏内购收入和付费指标定义",
            tags=["内购", "收入", "ARPPU", "付费转化率"],
        )

        results = library.search("留存率 游戏", domain="游戏分析")
        assert len(results) >= 1
        assert any("留存" in r.content for r in results)

        results = library.search("付费 ARPPU")
        assert len(results) == 1

    def test_create_memory_from_game_analysis_pattern(self, tmp_path: Path):
        """Test creating memory items from game analysis workflows."""
        root = tmp_path / "knowledge"
        memory = MemoryStore(root)

        # Memory about analysis preference
        mem = memory.create_candidate(
            text="游戏数据分析中，通常先分析留存数据，再分析付费数据，最后分析ROI",
            summary="游戏分析标准流程",
            memory_type=MemoryType.WORKFLOW_PATTERN,
            confidence=0.85,
            domain="游戏分析",
            tags=["留存", "付费", "ROI"],
        )
        memory.confirm(mem.id)

        # Memory about banner data usage
        mem2 = memory.create_candidate(
            text="Banner汇总数据用于分析广告展示效果和点击率",
            summary="Banner数据用途",
            memory_type=MemoryType.DOMAIN_FACT,
            confidence=0.7,
            domain="游戏分析",
            tags=["Banner", "广告"],
        )
        memory.confirm(mem2.id)

        results = memory.search("留存 付费", domain="游戏分析")
        assert len(results) >= 1

        results = memory.search("Banner")
        assert len(results) >= 1

    def test_simulated_session_with_real_data_context(self, tmp_path: Path):
        """Test evidence indexing with a simulated session about real data analysis."""
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"

        # Create a session that simulates analyzing game retention data
        session_dir = sessions_dir / "game_retention_analysis"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps(
                {
                    "session_id": "game_retention_analysis",
                    "project_name": "游戏分析",
                    "saved_at": "2026-05-23 14:30:00",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps(
                [
                    {"role": "user", "content": "请分析游戏B的留存数据，包括次日留存、七日留存和月留存"},
                    {"role": "assistant", "content": "我来分析游戏B的留存情况。首先加载留存数据文件 游戏B留存.xlsx。"},
                    {"role": "user", "content": "和游戏A的Banner数据对比一下展示效果"},
                    {"role": "assistant", "content": "游戏A的Banner汇总数据显示展示量较高，但点击率需要结合激励视频数据综合评估。"},
                    {"role": "user", "content": "还需要看内购数据"},
                    {"role": "assistant", "content": "游戏A内购数据显示付费转化率为3.5%，ARPPU为45元。建议结合省钱卡用户流水分析付费用户画像。"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        evidence = EvidenceStore(root, sessions_dir=sessions_dir)
        count = evidence.index_session("game_retention_analysis")
        assert count == 6

        # Search for retention-related evidence
        results = evidence.search("留存", project_id="游戏分析")
        assert len(results) >= 2

        # Search for revenue-related evidence
        results = evidence.search("内购 ARPPU 付费", project_id="游戏分析")
        assert len(results) >= 1

        # Search across all domains
        results = evidence.search("Banner")
        assert len(results) >= 1

    def test_full_retrieval_with_real_data_context(self, tmp_path: Path):
        """Test full retrieval workflow with real data domain context."""
        root = tmp_path / "knowledge"
        sessions_dir = tmp_path / "sessions"

        # Create knowledge
        library = KnowledgeLibrary(root)
        library.create(
            title="省钱卡订单分析规则",
            domain="省钱卡",
            content="省钱卡订单数据用于分析用户购买行为，不包含退款订单。",
            summary="省钱卡订单数据规则",
            tags=["省钱卡", "订单"],
        )

        # Create conflicting memory
        memory = MemoryStore(root)
        mem = memory.create_candidate(
            text="省钱卡订单数据包含所有订单记录，包括退款订单。",
            summary="省钱卡订单数据范围",
            memory_type=MemoryType.DOMAIN_FACT,
            confidence=0.6,
            domain="省钱卡",
        )
        memory.confirm(mem.id)

        # Create evidence session
        session_dir = sessions_dir / "savings_card"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "savings_card", "project_name": "省钱卡"}),
            encoding="utf-8",
        )
        (session_dir / "conversation.json").write_text(
            json.dumps(
                [
                    {"role": "user", "content": "分析省钱卡订单数据"},
                    {"role": "assistant", "content": "省钱卡订单数据分析完成，共12345条订单记录"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        EvidenceStore(root, sessions_dir=sessions_dir).index_session("savings_card")

        # Full retrieval with conflict detection
        service = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir)
        context = service.retrieve(
            "省钱卡 订单 退款",
            domain="省钱卡",
            project_id="省钱卡",
            include_evidence=True,
            max_evidence_chars=1000,
        )

        # Knowledge should be found
        assert len(context.knowledge_items) >= 1

        # Memory should be found
        assert len(context.memory_items) >= 1

        # Evidence should be found
        assert len(context.evidence_items) >= 1

        # Conflict should be detected (不包含 vs 包含所有)
        assert len(context.conflicts) >= 1

        # Prompt context should be well-formed
        prompt = service.compose_prompt_context(context)
        assert "<retrieved_knowledge" in prompt
        assert "<memory_hints" in prompt
        assert "<session_evidence" in prompt
        assert "<knowledge_conflicts" in prompt

    def test_cross_domain_knowledge_and_memory(self, tmp_path: Path):
        """Test that knowledge and memory from different domains don't interfere."""
        root = tmp_path / "knowledge"
        library = KnowledgeLibrary(root)
        memory = MemoryStore(root)

        # Game domain knowledge
        library.create(
            title="游戏互推效果指标",
            domain="游戏分析",
            content="互推效果通过点击率、转化率和新增用户数衡量。",
            tags=["互推", "转化"],
        )

        # Savings card domain knowledge
        library.create(
            title="省钱卡用户流水分析",
            domain="省钱卡",
            content="用户流水数据包含充值和消费记录。",
            tags=["流水", "充值"],
        )

        # Game domain memory
        game_mem = memory.create_candidate(
            text="游戏互推数据通常需要和Banner数据结合分析",
            summary="互推分析建议",
            memory_type=MemoryType.WORKFLOW_PATTERN,
            confidence=0.7,
            domain="游戏分析",
        )
        memory.confirm(game_mem.id)

        # Search only in game domain
        service = KnowledgeRetrievalService(root=root)
        game_context = service.retrieve("互推 转化", domain="游戏分析")
        assert all(i.domain == "游戏分析" for i in game_context.knowledge_items)
        assert all(m.domain == "游戏分析" for m in game_context.memory_items)

        # Search only in savings card domain
        card_context = service.retrieve("流水 充值", domain="省钱卡")
        assert all(i.domain == "省钱卡" for i in card_context.knowledge_items)
