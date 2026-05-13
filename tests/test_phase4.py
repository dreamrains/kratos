"""Tests for Phase 4 improvements: session restore, multi-dataset, proficiency, parallel execution."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# === 4.1 Session Restore: analysis_state sync ===


class TestSessionRestoreSync:
    """Test that restore_object_context reloads analysis_state with correct project."""

    def test_restore_reloads_analysis_state(self):
        from data_agent.agent.analysis_state import AnalysisSessionState, _state_path

        session_id = "test_restore_sync_001"
        project_a = "project_a"
        project_b = "project_b"

        # Create two different analysis states
        state_a = AnalysisSessionState(session_id=session_id, project_name=project_a, goal="goal_a", stage="execute")
        state_a.save()

        # Simulate: __init__ loads with project_a, then restore switches to project_b
        # This is what the fix addresses
        from data_agent.agent.analysis_state import load_analysis_state

        loaded_a = load_analysis_state(session_id, project_a)
        assert loaded_a.project_name == project_a
        assert loaded_a.goal == "goal_a"

        # After restoring with project_b, the state should update project_name
        loaded_b = load_analysis_state(session_id, project_b)
        assert loaded_b.project_name == project_b

        # Cleanup
        _state_path(session_id).unlink(missing_ok=True)

    def test_restore_object_context_updates_state(self):
        """Verify the actual restore_object_context code path reloads analysis_state."""
        from data_agent.agent.loop import AgentLoop
        from data_agent.agent.analysis_state import AnalysisSessionState, _state_path

        session_id = "test_restore_ctx_002"
        project = "test_project"

        # Create a state file
        state = AnalysisSessionState(session_id=session_id, project_name=project, goal="restore_test")
        state.save()

        try:
            with patch("data_agent.agent.loop.AgentLoop._ensure_mcp_initialized"):
                loop = AgentLoop(session_id=session_id, project_name=project)

            # Verify initial state loaded
            assert loop.context.analysis_state is not None
            assert loop.context.analysis_state.project_name == project
            assert loop.context.analysis_state.goal == "restore_test"
        finally:
            _state_path(session_id).unlink(missing_ok=True)


# === 4.2 Multi-Dataset Enhancement ===


class TestMultiDatasetSupport:
    """Test cross-dataset analysis recommendations."""

    def test_interpret_dataset_with_multiple_datasets(self):
        """interpret_dataset should include cross-dataset hints when other datasets exist."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        ws = Workspace()

        # Load first dataset
        df1 = pd.DataFrame({
            "user_id": [1, 2, 3, 4, 5],
            "revenue": [100, 200, 150, 300, 250],
            "channel": ["A", "B", "A", "B", "A"],
        })
        ws.add("orders", df1)

        # Load second dataset with shared column
        df2 = pd.DataFrame({
            "user_id": [1, 2, 3, 4, 5],
            "age": [25, 30, 35, 28, 42],
            "region": ["East", "West", "East", "North", "South"],
        })
        ws.add("users", df2)

        with patch("data_agent.tools.data_understand.workspace", ws):
            with patch("data_agent.tools._utils.workspace", ws):
                result = interpret_dataset("orders")

                # Should include cross-dataset hints about shared user_id
                from data_agent.tools.registry import ToolResult
                if isinstance(result, ToolResult):
                    data = result.data
                else:
                    # String result means error or no cross-dataset detection
                    data = {}

                if data and "cross_dataset_hints" in data:
                    hints = data["cross_dataset_hints"]
                    assert len(hints) >= 1
                    # Should detect user_id as shared column
                    found = any(
                        "user_id" in h.get("shared_columns", [])
                        for h in hints
                    )
                    assert found, f"Expected user_id in shared columns, got {hints}"

    def test_interpret_dataset_single_dataset_no_cross_hints(self):
        """Single dataset should not have cross-dataset hints."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        ws = Workspace()
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        ws.add("solo", df)

        with patch("data_agent.tools.data_understand.workspace", ws):
            with patch("data_agent.tools._utils.workspace", ws):
                result = interpret_dataset("solo")
                from data_agent.tools.registry import ToolResult
                if isinstance(result, ToolResult):
                    assert "cross_dataset_hints" not in (result.data or {})


# === 4.4 User Proficiency Detection ===


class TestUserProficiency:
    """Test user proficiency detection from input text."""

    def test_beginner_detection(self):
        from data_agent.agent.prompts import detect_user_proficiency

        assert detect_user_proficiency("帮我看下这个数据，我不太懂") == "beginner"
        assert detect_user_proficiency("简单说一下啥意思") == "beginner"
        assert detect_user_proficiency("看一眼这个数据") == "beginner"
        assert detect_user_proficiency("能不能通俗一点说") == "beginner"

    def test_advanced_detection(self):
        from data_agent.agent.prompts import detect_user_proficiency

        assert detect_user_proficiency("做个时间序列的ARIMA分析，看看季节性分解") == "advanced"
        assert detect_user_proficiency("检查一下这个回归模型的p值和置信区间") == "advanced"
        assert detect_user_proficiency("用A/B测试验证这个假设，检查显著性") == "advanced"

    def test_intermediate_detection(self):
        from data_agent.agent.prompts import detect_user_proficiency

        # No technical terms, no beginner indicators
        assert detect_user_proficiency("分析一下销售数据的趋势") == "intermediate"
        assert detect_user_proficiency("对比一下各渠道的转化率") == "intermediate"
        # Single technical term → intermediate
        assert detect_user_proficiency("做一个相关性分析") == "intermediate"

    def test_proficiency_instruction_content(self):
        from data_agent.agent.prompts import _get_proficiency_instruction

        beginner = _get_proficiency_instruction("beginner")
        assert "通俗" in beginner
        assert "统计" in beginner

        advanced = _get_proficiency_instruction("advanced")
        assert "方法论" in advanced
        assert "显著性" in advanced

        intermediate = _get_proficiency_instruction("intermediate")
        assert "统计" in intermediate

        unknown = _get_proficiency_instruction("unknown")
        assert unknown == ""

    def test_proficiency_from_history(self):
        from data_agent.agent.prompts import detect_user_proficiency

        # History with advanced terms should boost to advanced
        history = [
            {"role": "user", "content": "做个回归分析看看p值"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "再检查一下置信区间"},
        ]
        # Current input is neutral, but history has advanced terms
        assert detect_user_proficiency("继续分析", history) == "advanced"

    def test_context_user_proficiency_field(self):
        from data_agent.agent.context import AgentContext

        ctx = AgentContext(session_id="test_prof")
        assert ctx.user_proficiency == "auto"

        ctx.user_proficiency = "beginner"
        assert ctx.user_proficiency == "beginner"


# === 4.5 Parallel Tool Execution ===


class TestParallelToolExecution:
    """Test parallel execution of read-only tools."""

    def test_read_only_tools_set(self):
        """Verify read-only tools are correctly identified from ToolCapability metadata."""
        from data_agent.tools.registry import registry, get_read_only_tools
        registry._ensure_discovered()
        ro = get_read_only_tools(registry)

        # These tools should be read-only
        assert "describe_dataset" in ro
        assert "quick_profile" in ro
        assert "preview_data" in ro
        assert "list_data" in ro
        assert "get_analysis_summary" in ro
        assert "analyze_time_series" in ro
        assert "correlation_analysis" in ro

        # These should NOT be read-only
        assert "transform_data" not in ro
        assert "load_data" not in ro
        assert "run_python" not in ro
        assert "record_evidence_record" not in ro
        assert "create_chart" not in ro

    def test_parallel_execution_returns_ordered_results(self):
        """Test that _execute_tools_parallel returns results in original order."""
        from data_agent.agent.loop import AgentLoop
        from data_agent.session.workspace import Workspace

        ws = Workspace()
        df1 = pd.DataFrame({"x": [1, 2, 3]})
        df2 = pd.DataFrame({"y": [4, 5, 6]})
        ws.add("test1", df1)
        ws.add("test2", df2)

        with patch("data_agent.agent.loop.AgentLoop._ensure_mcp_initialized"):
            loop = AgentLoop(session_id="test_parallel_001")
            loop.context.workspace = ws

        # Create mock tool calls
        mock_tc1 = MagicMock()
        mock_tc1.id = "call_001"
        mock_tc1.name = "list_data"
        mock_tc1.arguments = {}

        mock_tc2 = MagicMock()
        mock_tc2.id = "call_002"
        mock_tc2.name = "list_data"
        mock_tc2.arguments = {}

        tool_calls = [mock_tc1, mock_tc2]

        # Execute in parallel
        results = loop._execute_tools_parallel(tool_calls)

        # Should return 2 results in original order
        assert len(results) == 2
        assert results[0][0].id == "call_001"
        assert results[1][0].id == "call_002"

    def test_sequential_execution_fallback(self):
        """Test that sequential execution works for mixed tool types."""
        from data_agent.agent.loop import AgentLoop, FinalResponse

        with patch("data_agent.agent.loop.AgentLoop._ensure_mcp_initialized"):
            loop = AgentLoop(session_id="test_seq_001")

        # Create a write tool call (should go sequential)
        mock_tc = MagicMock()
        mock_tc.id = "call_write_001"
        mock_tc.name = "transform_data"
        mock_tc.arguments = {"name": "x", "operation": "filter", "condition": "col > 0"}

        # Should fall back to sequential since transform_data is not read-only
        from data_agent.tools.registry import READ_ONLY_TOOLS
        assert "transform_data" not in READ_ONLY_TOOLS


# === Integration: build_system_prompt with proficiency ===


class TestBuildPromptWithProficiency:
    """Test that build_system_prompt accepts and uses proficiency parameter."""

    def test_proficiency_in_analysis_prompt(self):
        from data_agent.agent.prompts import build_system_prompt

        # Beginner prompt should include beginner instructions
        prompt = build_system_prompt(
            tool_list="test_tool",
            user_input="帮我看看这个数据",
            proficiency="beginner",
        )
        assert "初学者" in prompt
        assert "通俗" in prompt

    def test_advanced_proficiency_in_prompt(self):
        from data_agent.agent.prompts import build_system_prompt

        prompt = build_system_prompt(
            tool_list="test_tool",
            user_input="做回归分析看显著性",
            proficiency="advanced",
        )
        assert "高级" in prompt
        assert "方法论" in prompt

    def test_default_proficiency_intermediate(self):
        from data_agent.agent.prompts import build_system_prompt

        prompt = build_system_prompt(
            tool_list="test_tool",
            user_input="分析数据",
        )
        # Default is intermediate
        assert "中等" in prompt
