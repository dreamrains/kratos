"""Comprehensive tests for Web UI Overhaul (Phase 1-5).
Covers: bug fixes, CLI feature parity, UI/UX, workbench redesign, visual polish.
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def client():
    from data_agent.web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def html(client):
    return client.get("/").data.decode("utf-8")


@pytest.fixture
def js(client):
    return client.get("/static/js/app.js").data.decode("utf-8")


@pytest.fixture
def css(client):
    return client.get("/static/css/app.css").data.decode("utf-8")


@pytest.fixture
def sessions(client):
    resp = client.get("/api/sessions")
    return resp.get_json()


# =====================================================
# Phase 1: Critical Bug Fixes
# =====================================================


class TestArtifactFileServing:
    """1.1 Fix artifact/report/export 404."""

    def test_sessions_path_returns_404_not_403(self, client):
        """sessions/ prefixed paths should resolve to sessions_resolved, return 404 if file missing."""
        resp = client.get("/api/files/sessions/nonexist/charts/test.html")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "File not found"

    def test_sessions_path_no_access_denied(self, client):
        """sessions/ paths should NOT return 403 (access denied)."""
        resp = client.get("/api/files/sessions/nonexist/test.html")
        assert resp.status_code != 403

    def test_project_path_still_works(self, client):
        """Non-sessions paths should still use project_resolved."""
        resp = client.get("/api/files/data/nonexist.csv")
        assert resp.status_code == 404


class TestMermaidChartRendering:
    """1.2 Fix mermaid/chart rendering."""

    def test_mermaid_typeof_guard(self, js):
        assert "typeof mermaid" in js

    def test_mutation_observer_setup(self, js):
        assert "_setupRenderObserver" in js
        assert "_setupRenderObserver()" in js  # Called in init

    def test_observer_uses_mutationobserver(self, js):
        assert "new MutationObserver" in js

    def test_render_guard_for_undefined_mermaid(self, js):
        """Guard should check mermaid is defined before rendering."""
        # Find the method definition (async _renderMermaidInElement)
        idx = js.find("async _renderMermaidInElement(el)")
        if idx < 0:
            idx = js.find("_renderMermaidInElement(el)")
        assert idx > 0
        # Check guard is inside the method body
        method_text = js[idx : idx + 3000]
        assert "typeof mermaid" in method_text


class TestSessionSorting:
    """1.3 Fix session sorting by time."""

    def test_sessions_returned_as_list(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_sessions_sorted_by_saved_at_desc(self, sessions):
        if len(sessions) <= 1:
            pytest.skip("Need >1 session to verify sorting")
        dates = [s.get("saved_at", "") for s in sessions]
        for i in range(len(dates) - 1):
            if dates[i] and dates[i + 1]:
                assert dates[i] >= dates[i + 1], (
                    f"Sessions not sorted: {dates[i]} should >= {dates[i+1]}"
                )


class TestTaskListUpdate:
    """1.4 Fix task list not updating."""

    def test_task_polling_in_js(self, js):
        assert "setInterval" in js
        assert "5000" in js

    def test_task_polling_can_stop_when_no_active_tasks(self, js):
        assert "_desiredTaskPollMs" in js
        assert "return 0;" in js
        assert "case 'task_update'" in js
        assert "_debouncedLoadTasks()" in js

    def test_visibilitychange_listener(self, js):
        assert "visibilitychange" in js

    def test_tasks_api_with_session_filter(self, client):
        resp = client.get("/api/tasks?session_id=test")
        assert resp.status_code == 200

    def test_frontend_uses_default_active_task_scope(self, js):
        assert "fetch('/api/tasks' + query)" in js
        assert "case 'task_update'" in js
        assert "_debouncedLoadTasks()" in js


class TestPopoverOverflow:
    """1.5 Fix popover overflow for bottom items."""

    def test_popover_viewport_detection(self, js):
        assert "viewportHeight" in js
        assert "requestAnimationFrame" in js

    def test_popover_above_button_logic(self, js):
        assert "rect.top - ph" in js
        assert "global-popover" in js


# =====================================================
# Phase 2: CLI Feature Parity
# =====================================================


class TestRewindUI:
    """2.1 Interactive rewind UI."""

    def test_rewind_modal_data_property(self, js):
        assert "rewindModal" in js

    def test_show_rewind_dialog_method(self, js):
        assert "showRewindDialog" in js

    def test_do_rewind_method(self, js):
        assert "doRewind" in js

    def test_rewind_info_api_call(self, js):
        assert "/rewind-info" in js

    def test_rewind_modal_html(self, html):
        assert "Rewind Conversation" in html
        assert "rewindModal.show" in html
        assert "selectedRound" in html

    def test_rewind_button_in_topbar(self, html):
        assert "showRewindDialog()" in html

    def test_rewind_button_on_user_messages(self, html):
        # Old direct rewindToRound replaced with showRewindDialog
        assert "showRewindDialog()" in html

    def test_rewind_info_endpoint_exists(self, client, sessions):
        if not sessions:
            pytest.skip("Need a session")
        sid = sessions[0]["session_id"]
        resp = client.get(f"/api/sessions/{sid}/rewind-info")
        assert resp.status_code == 200

    def test_show_toast_after_rewind(self, js):
        assert "showToast" in js
        assert "已回滚到 Round" in js


class TestCompactFocus:
    """2.2 Enhanced compact with focus parameter."""

    def test_compact_dialog_data(self, js):
        assert "compactDialog" in js

    def test_do_compact_method(self, js):
        assert "doCompact" in js

    def test_compact_dialog_html(self, html):
        assert "Compress Context" in html
        assert "compactDialog.focus" in html

    def test_focus_input_placeholder(self, html):
        assert "key findings" in html or "focus" in html

    def test_backend_accepts_focus_param(self):
        """Verify commands.py reads focus from request body."""
        from data_agent.web.blueprints.commands import compact_context
        import inspect
        source = inspect.getsource(compact_context)
        assert "focus" in source


# =====================================================
# Phase 3: UI/UX Improvements
# =====================================================


class TestThinkingAnimation:
    """3.1 Dynamic analyzing status animation."""

    def test_thinking_states_array(self, js):
        assert "_thinkingStates" in js
        assert "思考中" in js
        assert "分析数据" in js
        assert "生成洞察" in js

    def test_start_thinking_cycle(self, js):
        assert "_startThinkingCycle" in js

    def test_stop_thinking_cycle(self, js):
        assert "_stopThinkingCycle" in js

    def test_thinking_cycle_on_llm_call_start(self, js):
        assert "_startThinkingCycle(turn)" in js

    def test_thinking_cycle_stops_on_sse_end(self, js):
        assert "_stopThinkingCycle()" in js

    def test_pulsing_dot_html(self, html):
        assert "animate-ping" in html
        assert "bg-blue-400" in html
        assert "bg-blue-500" in html

    def test_chinese_fallback_text(self, html):
        assert "思考中" in html


class TestSessionIndicator:
    """3.2 Session processing indicator in sidebar."""

    def test_session_loading_check(self, html):
        assert "_sessionStates[s.session_id]" in html

    def test_ping_animation_class(self, html):
        assert "animate-ping" in html


class TestTaskPanelBehavior:
    """3.3 Task panel default collapsed + auto behavior."""

    def test_tasks_default_collapsed(self, js):
        assert "tasksExpanded: false" in js

    def test_auto_expand_on_in_progress(self, js):
        assert "tasksExpanded = true" in js

    def test_auto_collapse_on_all_done(self, js):
        assert "setTimeout" in js
        assert "tasksExpanded = false" in js


class TestExportReply:
    """3.4 Per-reply export button."""

    def test_export_single_reply_method(self, js):
        assert "exportSingleReply" in js

    def test_html_export_with_blob(self, js):
        assert "text/html" in js
        assert "URL.createObjectURL" in js

    def test_markdown_export_via_clipboard(self, js):
        assert "已复制 Markdown 到剪贴板" in js

    def test_export_popover_html(self, html):
        assert "Export as HTML" in html
        assert "Copy as Markdown" in html


class TestLineSpacing:
    """3.5 Unified response line spacing."""

    def test_prose_font_size(self, css):
        assert "font-size: 0.875rem" in css

    def test_prose_p_margin(self, css):
        assert "margin-top: 0.625em" in css
        assert "margin-bottom: 0.625em" in css


# =====================================================
# Phase 4: Workbench Redesign
# =====================================================


class TestWorkbenchRedesign:
    """4.1-4.3 Workbench simplified to single Outputs panel."""

    def test_outputs_panel_header(self, html):
        assert ">Outputs<" in html or "Outputs" in html

    def test_no_workbench_tab_in_js(self, js):
        assert "workbenchTab" not in js

    def test_no_analysis_state_grid(self, html):
        assert "Analysis State" not in html

    def test_no_workflow_tasks_in_workbench(self, html):
        assert "Workflow Tasks" not in html

    def test_report_generation_section(self, html):
        assert "Generate Report" in html

    def test_conversation_export_section(self, html):
        assert "Export Conversation" in html

    def test_artifacts_section_unlimited(self, html):
        assert "Artifacts" in html
        assert "sessionArtifacts.slice(0, 8)" not in html

    def test_analysis_stage_indicator(self, html):
        assert "analysisSummary.stage" in html

    def test_stage_color_coding(self, html):
        assert "bg-green-500" in html
        assert "bg-blue-500" in html

    def test_artifact_open_link(self, html):
        assert "group-hover/art:text-brand" in html


# =====================================================
# Phase 5: Visual Polish
# =====================================================


class TestVisualPolish:
    """5.1-5.3 Empty state, scrollbar, dark mode."""

    def test_gradient_empty_state(self, html):
        assert "from-blue-50" in html
        assert "to-indigo-100" in html

    def test_prompt_suggestions(self, html):
        assert "Analyze the trends" in html
        assert "What insights" in html
        assert "Create a visualization" in html

    def test_suggestions_set_input_text(self, html):
        assert "inputText = " in html

    def test_firefox_scrollbar(self, css):
        assert "scrollbar-width: thin" in css

    def test_sidebar_active_state(self, css):
        assert ":active" in css

    def test_mermaid_dark_mode_observer(self, html):
        assert "MutationObserver" in html


# =====================================================
# Regression: Core features still work
# =====================================================


class TestCoreRegression:
    """Ensure existing features are not broken."""

    def test_homepage_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Data Agent" in resp.data

    def test_capabilities_api(self, client):
        resp = client.get("/api/capabilities")
        assert resp.status_code == 200

    def test_models_api(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200

    def test_projects_api(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200

    def test_static_js(self, client):
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200

    def test_static_css(self, client):
        resp = client.get("/static/css/app.css")
        assert resp.status_code == 200

    def test_alpinejs_loaded(self, html):
        assert "alpinejs" in html

    def test_tailwind_loaded(self, html):
        assert "tailwindcss" in html

    def test_marked_loaded(self, html):
        assert "marked" in html

    def test_mermaid_loaded(self, html):
        assert "mermaid" in html

    def test_highlightjs_loaded(self, html):
        assert "highlight" in html

    def test_chat_input_exists(self, html):
        assert "inputBox" in html
        assert "sendMessage()" in html

    def test_file_upload_exists(self, html):
        assert "uploadFile" in html

    def test_pause_button_exists(self, html):
        assert "interruptTurn()" in html

    def test_confirmation_dialog_exists(self, html):
        assert "confirmation" in html
        assert "Submit" in html

    def test_config_modal_exists(self, html):
        assert "configModal" in html

    def test_artifacts_modal_exists(self, html):
        assert "artifactsModal" in html

    def test_sessions_list_in_sidebar(self, html):
        assert "sessionSearch" in html

    def test_projects_section_in_sidebar(self, html):
        assert "Projects" in html

    def test_js_syntax_valid(self):
        """Verify JS file is syntactically valid."""
        import subprocess
        result = subprocess.run(
            ["node", "-c", "src/data_agent/web/static/js/app.js"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    def test_python_artifacts_syntax(self):
        import ast
        for f in [
            "src/data_agent/web/blueprints/artifacts.py",
            "src/data_agent/web/blueprints/commands.py",
            "src/data_agent/session/history.py",
        ]:
            with open(f, encoding="utf-8") as fh:
                ast.parse(fh.read())
