from pathlib import Path

import pytest

from scripts.acceptance.real_data_manifest import REFERENCE_DATA_AVAILABLE, REFERENCE_DATA_DIR

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.session.history import save_session


TEST_DOC_DIR = REFERENCE_DATA_DIR


def _configure(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


@pytest.mark.skipif(not REFERENCE_DATA_AVAILABLE, reason="canonical reference data is not installed")
def test_candidate_memory_stays_out_of_prompt_until_confirmed(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    save_session(
        [{"role": "user", "content": "请记住：游戏付费分析默认同时看付费率、ARPU 和 ARPPU。"}],
        "payment_memory_candidate",
        extra_meta={"project_name": "game"},
    )

    service = KnowledgeRetrievalService()
    before = service.retrieve("游戏付费分析 ARPU ARPPU", domain="game", max_total_retrieval_chars=1200)

    assert before.memory_items == []
    assert "<memory_hints" not in service.compose_prompt_context(before)

    store = MemoryStore(cfg.knowledge_dir)
    candidate = store.list(status="candidate")[0]
    store.confirm(candidate.id)

    after = service.retrieve("游戏付费分析 ARPU ARPPU", domain="game", max_total_retrieval_chars=1200)
    prompt = service.compose_prompt_context(after)

    assert after.memory_items
    assert "<memory_hints" in prompt
    assert len(prompt) <= after.metadata["total_retrieval_chars"]
    assert after.metadata["total_retrieval_chars"] <= 1200


@pytest.mark.skipif(not REFERENCE_DATA_AVAILABLE, reason="canonical reference data is not installed")
def test_evidence_requires_explicit_budget_for_real_data_session(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    save_session(
        [
            {"role": "user", "content": "分析省钱卡订单.xlsx 的售价与购买情况。"},
            {"role": "assistant", "content": "订单文件包含支付金额、支付时间和创建时间字段。"},
        ],
        "savings_card_evidence_budget",
        extra_meta={"project_name": "savings-card-q2"},
    )

    service = KnowledgeRetrievalService(sessions_dir=cfg.sessions_resolved)
    without_budget = service.retrieve(
        "省钱卡 支付金额 支付时间",
        project_id="savings-card-q2",
        include_evidence=True,
    )
    with_budget = service.retrieve(
        "省钱卡 支付金额 支付时间",
        project_id="savings-card-q2",
        include_evidence=True,
        max_evidence_chars=1000,
    )

    assert without_budget.evidence_items == []
    assert with_budget.evidence_items
