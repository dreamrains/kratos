from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryType
from data_agent.knowledge.retrieval import KnowledgeRetrievalService, _cjk_bigrams, _query_terms


def test_query_terms_extract_chinese_metric_words():
    terms = _query_terms("帮我分析一下这个数据，我需要知道留存率和付费转化率的关系")

    assert "留存率" in terms
    assert "付费转化率" in terms


def test_cjk_bigrams_uses_real_chinese_range():
    grams = _cjk_bigrams("排除退款订单")

    assert "排除" in grams
    assert "退款" in grams


def test_chinese_conflict_detection_uses_real_markers(tmp_path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    memory = MemoryStore(tmp_path / "knowledge")
    library.create(
        title="GMV 口径",
        domain="ecommerce",
        content="GMV 排除取消订单。",
        summary="GMV 排除取消订单",
    )
    item = memory.create_candidate(
        text="GMV 包含所有订单。",
        summary="GMV 包含所有订单",
        memory_type=MemoryType.DOMAIN_FACT,
        domain="ecommerce",
        confidence=0.8,
    )
    memory.confirm(item.id)

    context = KnowledgeRetrievalService(root=tmp_path / "knowledge").retrieve(
        "GMV 口径",
        domain="ecommerce",
    )

    assert context.conflicts
    assert context.conflicts[0].severity.value == "review"
