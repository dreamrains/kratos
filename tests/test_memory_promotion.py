from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import KnowledgeSource, MemoryStatus


def test_memory_promotes_to_knowledge_with_traceable_source(tmp_path):
    root = tmp_path / "knowledge"
    memory = MemoryStore(root)
    library = KnowledgeLibrary(root)
    item = memory.create_candidate(
        text="GMV must exclude canceled and refunded orders.",
        summary="GMV口径",
        domain="ecommerce",
        tags=["gmv"],
        source_session_id="s1",
    )
    memory.confirm(item.id)

    knowledge = memory.promote_to_knowledge(
        item.id,
        library=library,
        title="GMV 口径",
        summary="GMV 排除取消与退款订单",
    )
    promoted = memory.get(item.id)

    assert knowledge is not None
    assert knowledge.source == KnowledgeSource.MEMORY_PROMOTION
    assert knowledge.domain == "ecommerce"
    assert "GMV" in knowledge.content
    assert promoted.status == MemoryStatus.PROMOTED
    assert promoted.promotion_target == knowledge.id


def test_memory_edit_and_candidate_delete(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    item = store.create_candidate("Use gross revenue.", domain="ecommerce", confidence=0.6)

    updated = store.update(
        item.id,
        text="Use net revenue.",
        summary="Revenue preference",
        confidence=0.8,
        tags=["revenue"],
    )

    assert updated.text == "Use net revenue."
    assert updated.summary == "Revenue preference"
    assert updated.confidence == 0.8
    assert updated.tags == ["revenue"]
    assert store.delete_candidate(item.id) is True
    assert store.get(item.id) is None
