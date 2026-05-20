from data_agent.tools.registry import TOOL_GROUPS, registry
from data_agent.tools import discover_tools


DEPRECATED_REPORT_TOOLS = {
    "generate_report",
    "generate_analysis_brief",
    "generate_formal_report",
}


def test_deprecated_report_tools_are_not_in_normal_report_group():
    assert TOOL_GROUPS["report"] == {"export_conversation"}
    assert DEPRECATED_REPORT_TOOLS <= TOOL_GROUPS["deprecated_report_artifacts"]


def test_deprecated_report_tools_are_not_active_by_default():
    discover_tools()
    registry.reset_groups()

    active_names = {tool["name"] for tool in registry.active_definitions()}

    assert "export_conversation" not in active_names
    assert DEPRECATED_REPORT_TOOLS.isdisjoint(active_names)
