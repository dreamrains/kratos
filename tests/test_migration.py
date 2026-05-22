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
