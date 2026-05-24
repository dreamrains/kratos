import json

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryType
from data_agent.knowledge.retrieval import KnowledgeRetrievalService


def test_retrieval_enforces_total_context_budget(tmp_path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    for idx in range(6):
        library.create(
            title=f"GMV rule {idx}",
            domain="ecommerce",
            content="GMV " + ("very long rule " * 200),
            summary="GMV long rule",
            tags=["gmv"],
        )

    context = KnowledgeRetrievalService(root=root).retrieve(
        "GMV rule",
        domain="ecommerce",
        knowledge_limit=6,
        max_total_retrieval_chars=1200,
    )

    assert context.metadata["trimmed"] is True
    assert context.metadata["total_retrieval_chars"] <= 1200
    assert len(context.knowledge_items) < 6


def test_candidate_memory_not_retrieved_before_confirmation(tmp_path):
    root = tmp_path / "knowledge"
    MemoryStore(root).create_candidate(
        "Always use GMV.",
        domain="ecommerce",
        dedup_key="pref:gmv",
    )

    context = KnowledgeRetrievalService(root=root).retrieve("GMV", domain="ecommerce")

    assert context.memory_items == []


def test_budget_metadata_exists_for_empty_retrieval(tmp_path):
    context = KnowledgeRetrievalService(root=tmp_path / "knowledge").retrieve("nothing")

    assert context.metadata["knowledge_chars"] == 0
    assert context.metadata["memory_chars"] == 0
    assert context.metadata["evidence_chars"] == 0
    assert context.metadata["total_retrieval_chars"] == 0
    assert context.metadata["trimmed"] is False


def test_evidence_stays_out_by_default_and_until_budgeted(tmp_path):
    root = tmp_path / "knowledge"
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "sales"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [{"role": "user", "content": "Revenue evidence for Q1 and Q2."}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s1")
    service = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir)

    default_context = service.retrieve("Revenue", project_id="sales")
    requested_with_zero_budget = service.retrieve(
        "Revenue",
        project_id="sales",
        include_evidence=True,
        max_evidence_chars=0,
    )
    requested_with_budget = service.retrieve(
        "Revenue",
        project_id="sales",
        include_evidence=True,
        max_evidence_chars=500,
    )

    assert default_context.evidence_items == []
    assert requested_with_zero_budget.evidence_items == []
    assert requested_with_budget.evidence_items
    assert requested_with_budget.metadata["evidence_chars"] > 0


def test_include_evidence_without_budget_keeps_evidence_out(tmp_path):
    root = tmp_path / "knowledge"
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s2"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "support"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [{"role": "user", "content": "Churn evidence from a support cohort."}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s2")

    context = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir).retrieve(
        "Churn evidence",
        project_id="support",
        include_evidence=True,
    )

    assert context.evidence_items == []
    assert context.metadata["evidence_chars"] == 0


def test_budget_metadata_covers_rendered_prompt_context(tmp_path):
    root = tmp_path / "knowledge"
    sessions_dir = tmp_path / "sessions"
    KnowledgeLibrary(root).create(
        title='GMV <rule> & "policy"',
        domain="ecommerce",
        content='Use GMV & NMV <carefully>. "Quote" this snippet.',
        summary="GMV rendered escaping",
        tags=["gmv"],
    )
    memory = MemoryStore(root)
    memory_item = memory.create_candidate(
        'Remember GMV <returns> & "adjustments".',
        summary="GMV memory",
        memory_type=MemoryType.DOMAIN_FACT,
        domain="ecommerce",
        dedup_key="gmv-rendered-budget",
    )
    memory.confirm(memory_item.id)
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "sales"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [{"role": "user", "content": 'GMV evidence <includes> & "returns".'}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s1")
    service = KnowledgeRetrievalService(root=root, sessions_dir=sessions_dir)

    context = service.retrieve(
        "GMV",
        domain="ecommerce",
        project_id="sales",
        include_evidence=True,
        max_evidence_chars=500,
    )
    prompt_context = service.compose_prompt_context(context)

    assert context.knowledge_items
    assert context.memory_items
    assert context.evidence_items
    assert context.metadata["total_retrieval_chars"] >= len(prompt_context)


def test_knowledge_budget_counts_shared_section_wrapper_for_multiple_items(tmp_path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    first = library.create(
        title="GMV first shared wrapper",
        domain="ecommerce",
        content="GMV excludes cancelled orders.",
        summary="GMV excludes cancellations",
        tags=["gmv"],
    )
    second = library.create(
        title="GMV second shared wrapper",
        domain="ecommerce",
        content="GMV excludes refunded orders.",
        summary="GMV excludes refunds",
        tags=["gmv"],
    )
    service = KnowledgeRetrievalService(root=root)
    two_item_section_budget = len(service._compose_knowledge_section([first, second]))

    context = service.retrieve(
        "GMV excludes",
        domain="ecommerce",
        knowledge_limit=2,
        max_knowledge_chars=two_item_section_budget,
        max_total_retrieval_chars=two_item_section_budget,
    )

    assert {item.id for item in context.knowledge_items} == {first.id, second.id}
    assert context.metadata["knowledge_chars"] == two_item_section_budget
    assert context.metadata["total_retrieval_chars"] == two_item_section_budget


def test_conflict_section_budget_drops_memory_first_and_metadata_covers_prompt(tmp_path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    memory = MemoryStore(root)
    knowledge = library.create(
        title="GMV budget conflict rule",
        domain="ecommerce",
        content="GMV excludes cancelled orders.",
        summary="GMV excludes cancelled orders",
        tags=["gmv"],
    )
    memory_item = memory.create_candidate(
        "GMV includes all cancelled orders.",
        summary="GMV includes all cancelled orders",
        memory_type=MemoryType.DOMAIN_FACT,
        domain="ecommerce",
        confidence=0.9,
        dedup_key="gmv-conflict-budget",
    )
    confirmed_memory = memory.confirm(memory_item.id)
    assert confirmed_memory is not None
    service = KnowledgeRetrievalService(root=root)
    base_context_budget = len(service._compose_knowledge_section([knowledge])) + len("\n\n") + len(
        service._compose_memory_section([confirmed_memory])
    )

    context = service.retrieve(
        "GMV cancelled orders",
        domain="ecommerce",
        max_total_retrieval_chars=base_context_budget,
    )
    prompt_context = service.compose_prompt_context(context)

    assert [item.id for item in context.knowledge_items] == [knowledge.id]
    assert context.memory_items == []
    assert context.conflicts == []
    assert context.metadata["trimmed"] is True
    assert len(prompt_context) <= context.metadata["total_retrieval_chars"]
    assert context.metadata["total_retrieval_chars"] <= base_context_budget


def test_knowledge_budget_uses_rendered_snippet_not_full_content(tmp_path):
    root = tmp_path / "knowledge"
    long_tail = "x" * 4000
    KnowledgeLibrary(root).create(
        title="GMV snippet rule",
        domain="ecommerce",
        content=("GMV " * 300) + long_tail,
        summary="GMV long content",
        tags=["gmv"],
    )

    context = KnowledgeRetrievalService(root=root).retrieve(
        "GMV",
        domain="ecommerce",
        max_knowledge_chars=1800,
        max_total_retrieval_chars=1800,
    )

    assert len(context.knowledge_items) == 1


def test_budget_trimming_preserves_rank_prefix(tmp_path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    first = library.create(
        title="GMV first high rank",
        domain="ecommerce",
        content="GMV " * 12,
        summary="GMV GMV GMV GMV",
        tags=["gmv"],
    )
    second = library.create(
        title="GMV second over budget",
        domain="ecommerce",
        content=("GMV " * 8) + ("x" * 4000),
        summary="GMV GMV",
        tags=["gmv"],
    )
    third = library.create(
        title="GMV third small",
        domain="ecommerce",
        content="GMV",
        summary="GMV",
        tags=["gmv"],
    )
    service = KnowledgeRetrievalService(root=root)
    one_item_budget = len(
        service._compose_knowledge_section([first])
    ) + 20

    context = service.retrieve(
        "GMV",
        domain="ecommerce",
        knowledge_limit=3,
        max_knowledge_chars=one_item_budget,
        max_total_retrieval_chars=one_item_budget,
    )

    assert [item.id for item in context.knowledge_items] == [first.id]
    assert second.id not in [item.id for item in context.knowledge_items]
    assert third.id not in [item.id for item in context.knowledge_items]
