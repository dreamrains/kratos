from data_agent.knowledge.models import (
    ConflictSeverity,
    EvidenceKind,
    KnowledgeStatus,
    MemoryStatus,
    MemoryType,
    RetrievedContext,
)


def test_model_enums_have_phase1_values():
    assert KnowledgeStatus.ACTIVE.value == "active"
    assert KnowledgeStatus.DEPRECATED.value == "deprecated"
    assert MemoryStatus.CANDIDATE.value == "candidate"
    assert MemoryStatus.CONFIRMED.value == "confirmed"
    assert MemoryType.DOMAIN_FACT.value == "domain_fact"
    assert EvidenceKind.MESSAGE.value == "message"
    assert ConflictSeverity.BLOCKING.value == "blocking"


def test_retrieved_context_defaults_to_empty_sections():
    context = RetrievedContext()

    assert context.knowledge_items == []
    assert context.memory_items == []
    assert context.evidence_items == []
    assert context.conflicts == []
