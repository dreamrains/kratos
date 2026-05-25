from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.agent.loop import AgentLoop
from types import SimpleNamespace


def test_retrieval_prefers_requested_domain(tmp_path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    library.create(
        title="电商 GMV",
        domain="ecommerce",
        content="GMV excludes canceled orders.",
        summary="GMV口径",
    )
    library.create(
        title="游戏 留存",
        domain="game",
        content="Retention means next-day active users.",
        summary="留存口径",
    )

    service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
    context = service.retrieve("GMV 如何计算", domain="ecommerce")

    assert [item.domain for item in context.knowledge_items] == ["ecommerce"]


def test_query_normalization_keeps_chinese_metric_terms(tmp_path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    library.create(
        title="留存率口径",
        domain="game",
        content="留存率 = 次日活跃用户 / 当日新增用户。",
        summary="留存率",
        tags=["留存率"],
    )

    service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
    context = service.retrieve("帮我分析一下这个数据，我需要知道留存率和付费转化率的关系", domain="game")

    assert context.knowledge_items
    assert context.knowledge_items[0].title == "留存率口径"


def test_agent_loop_infers_retrieval_domain_from_project_and_question():
    loop = AgentLoop.__new__(AgentLoop)
    loop.context = SimpleNamespace(project_name="游戏分析")

    assert loop._infer_retrieval_domain("请分析留存率和付费率") == "game"

    loop.context = SimpleNamespace(project_name="")
    assert loop._infer_retrieval_domain("GMV 需要排除退款吗") == "ecommerce"
