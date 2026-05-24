import json

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
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
