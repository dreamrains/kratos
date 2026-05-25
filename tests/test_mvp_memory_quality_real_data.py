from pathlib import Path

import pytest

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.session.history import save_session


TEST_DOC_DIR = Path("reference/test_doc")


def _configure(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_ordinary_real_data_analysis_does_not_create_memory_candidates(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    data_file = TEST_DOC_DIR / "游戏B留存.xlsx"

    save_session(
        [
            {
                "role": "user",
                "content": f"请分析这个留存文件：{data_file.name}，重点看次日留存和7日留存趋势。",
            },
            {
                "role": "assistant",
                "content": "已读取字段：日期、日活跃、日新增、1天后、7天后，并准备做趋势分析。",
            },
        ],
        "ordinary_retention_analysis",
        extra_meta={"project_name": "game-retention-review"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert candidates == []


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_explicit_metric_memory_from_real_data_session_has_traceable_source(
    tmp_path: Path,
    monkeypatch,
):
    cfg = _configure(tmp_path, monkeypatch)

    save_session(
        [
            {
                "role": "user",
                "content": "请记住：游戏留存分析默认先看次日留存、7日留存，再结合日新增判断投放质量。",
            }
        ],
        "remember_game_retention_flow",
        extra_meta={"project_name": "game"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert len(candidates) == 1
    assert candidates[0].reason
    assert candidates[0].source_evidence_ids
    assert candidates[0].domain == "game"


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_user_correction_from_order_data_requires_review(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)

    save_session(
        [
            {
                "role": "user",
                "content": "纠正一下：省钱卡订单分析里的支付金额应该按支付时间归属，不按创建时间归属。",
            }
        ],
        "order_metric_correction",
        extra_meta={"project_name": "savings-card-q2"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert len(candidates) == 1
    assert candidates[0].needs_review is True
    assert candidates[0].type.value == "correction"
    assert candidates[0].project_id == "savings-card-q2"
    assert candidates[0].domain == "general"
