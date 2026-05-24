from data_agent.tools.registry import registry

# Import module so native knowledge tools register before assertions.
import data_agent.tools.knowledge_tools  # noqa: F401


def test_old_domain_experience_tools_are_not_agent_facing():
    names = set(registry.tool_names)

    assert "search_knowledge" in names
    assert "create_memory_candidate" in names
    assert "show_domain_knowledge" not in names
    assert "set_domain" not in names
    assert "show_experience_log" not in names
    assert "confirm_experience" not in names
