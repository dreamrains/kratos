from data_agent import config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.session.history import save_session


def test_save_session_indexes_evidence(tmp_path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)

    session_id = "auto_index_cn"
    save_session(
        [
            {"role": "user", "content": "请记住 GMV 需要排除取消订单"},
            {"role": "assistant", "content": "已确认该业务口径。"},
        ],
        session_id,
        extra_meta={"project_name": "ecommerce"},
    )

    records = EvidenceStore(cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved).search(
        "GMV",
        project_id="ecommerce",
    )

    assert len(records) >= 1
    assert records[0].session_id == session_id
    assert "GMV" in records[0].content
