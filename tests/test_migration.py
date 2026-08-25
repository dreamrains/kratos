def test_collects_legacy_project_knowledge_for_review(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.migration import collect_legacy_project_knowledge_for_review

    old_cfg = config._config
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    try:
        cfg = config.get_config()
        legacy = cfg.objects_dir / "legacy_obj" / "knowledge"
        legacy.mkdir(parents=True)
        (legacy / "project_rules.md").write_text("legacy rule", encoding="utf-8")

        result = collect_legacy_project_knowledge_for_review()

        assert result["copied_count"] == 1
        review_file = cfg.workspace_resolved / "migration-review" / "project-knowledge" / "objects" / "legacy_obj" / "project_rules.md"
        assert review_file.read_text(encoding="utf-8") == "legacy rule"
        assert (legacy / "project_rules.md").exists()
    finally:
        config._config = old_cfg


def test_route_a_migration_dry_run_hashes_sources_and_artifacts_without_writing(tmp_path, monkeypatch):
    import json

    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.migration import audit_route_a_migration

    monkeypatch.setattr(config, "_config", AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions"))
    source = tmp_path / "input.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    sdir = tmp_path / "sessions" / "migrate_dry"
    sdir.mkdir(parents=True)
    (sdir / "workspace_meta.json").write_text(json.dumps({"sales": {"source_path": str(source)}}), encoding="utf-8")
    artifact = sdir / "evidence.json"
    artifact.write_text('{"claim":"ok"}', encoding="utf-8")
    (sdir / "analysis_state.json").write_text(json.dumps({"evidence_records": [{"artifact_path": "evidence.json"}]}), encoding="utf-8")
    before = (sdir / "workspace_meta.json").read_text(encoding="utf-8")

    audit = audit_route_a_migration()

    assert audit["mode"] == "dry_run"
    assert audit["summary"]["datasets"] == 1
    assert audit["summary"]["identities_missing"] == 1
    assert audit["summary"]["artifact_references"] == 1
    assert audit["summary"]["missing_artifact_references"] == 0
    assert audit["sessions"][0]["datasets"][0]["source_hash"].startswith("sha256:")
    assert audit["sessions"][0]["artifact_references"][0]["content_hash"].startswith("sha256:")
    assert (sdir / "workspace_meta.json").read_text(encoding="utf-8") == before
    assert not (sdir / "migration_status.json").exists()


def test_route_a_migration_marks_missing_original_read_only_and_never_rehydrates_backup(tmp_path, monkeypatch):
    import json
    import pandas as pd

    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.migration import apply_route_a_migration, read_session_migration_status
    from data_agent.session.workspace import workspace

    monkeypatch.setattr(config, "_config", AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions"))
    session_id = "missing_original"
    sdir = tmp_path / "sessions" / session_id
    (sdir / "data").mkdir(parents=True)
    (sdir / "meta.json").write_text(json.dumps({"session_id": session_id}), encoding="utf-8")
    (sdir / "workspace_meta.json").write_text(json.dumps({"sales": {"source_path": str(tmp_path / "gone.csv"), "source_fmt": "csv"}}), encoding="utf-8")
    pd.DataFrame({"value": [1, 2]}).to_pickle(sdir / "data" / "sales.pkl")

    result = apply_route_a_migration()

    assert result["applied"]["read_only_statuses"] == 1
    assert read_session_migration_status(session_id)["mode"] == "read_only_missing_original"
    from data_agent.agent.loop import AgentLoop
    workspace.remove("sales")
    loop = AgentLoop(session_id=session_id)
    loop._restore_workspace()
    assert workspace.get("sales") is None


def test_route_a_migration_writes_identity_only_when_original_is_available(tmp_path, monkeypatch):
    import json

    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.migration import apply_route_a_migration, read_session_migration_status

    monkeypatch.setattr(config, "_config", AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions"))
    source = tmp_path / "orders.csv"
    source.write_text("order_id\n1\n", encoding="utf-8")
    sdir = tmp_path / "sessions" / "available_original"
    sdir.mkdir(parents=True)
    (sdir / "workspace_meta.json").write_text(json.dumps({"orders": {"source_path": str(source)}}), encoding="utf-8")

    result = apply_route_a_migration()
    migrated = json.loads((sdir / "workspace_meta.json").read_text(encoding="utf-8"))

    assert result["applied"]["identity_records"] == 1
    assert migrated["orders"]["data_identity"]["role"] == "raw"
    assert migrated["orders"]["data_identity"]["fingerprint"].startswith("sha256:")
    assert read_session_migration_status("available_original")["mode"] == "identity_migrated"
