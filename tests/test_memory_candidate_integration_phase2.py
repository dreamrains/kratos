from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.session.history import save_session


def test_candidate_to_confirmed_retrieval_flow_with_budget(
    tmp_path: Path,
    monkeypatch,
):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)

    save_session(
        [{"role": "user", "content": "请记住：GMV 需要排除取消订单和退款订单。"}],
        "phase2_flow",
        extra_meta={"project_name": "ecommerce"},
    )

    store = MemoryStore(cfg.knowledge_dir)
    candidates = store.list(status="candidate")
    assert candidates
    assert candidates[0].source_evidence_ids

    before = KnowledgeRetrievalService().retrieve("GMV 如何计算", domain="ecommerce")
    assert before.memory_items == []

    store.confirm(candidates[0].id)
    after = KnowledgeRetrievalService().retrieve(
        "GMV 如何计算",
        domain="ecommerce",
        max_total_retrieval_chars=1200,
    )

    assert after.memory_items
    assert after.metadata["total_retrieval_chars"] <= 1200
