"""Comprehensive tests for Web UI Overhaul (Phase 1-5).
Covers: bug fixes, CLI feature parity, UI/UX, workbench redesign, visual polish.
"""

import json
import pytest
import sys
import os
from pathlib import Path

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


def test_management_center_shell_exists(html, js, css):
    assert "managementCenter" in html
    assert "mgmt-nav" in html
    assert "loadManagementSection" in js
    assert "mgmt-overlay" in css
    assert "mgmt-drawer" in css


def test_management_center_uses_chinese_settings_interaction(html, js):
    assert "返回应用" in html
    assert "技能" in html
    assert "MCP 服务器" in html
    assert "知识库" in html
    assert "记忆" in html
    assert "会话搜索" in html
    assert "添加技能" in html
    assert "添加服务器" in html
    assert "openSkillDrawer" in js
    assert "openMcpDrawer" in js


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

    def test_interactive_chart_references_render_inline(self, js, html):
        assert r"\[\[chart:" in js
        assert "_replaceChartReferences" in js
        assert "inline-chart-artifact" in js
        assert "renderMarkdown(turn.content, turn)" in html

    def test_unreferenced_charts_render_after_markdown_as_supplemental(self, html, js):
        assert "Supplemental charts" in html or "补充图表" in html
        assert "supplementalArtifacts(turn)" in html
        assert "supplementalArtifacts(turn)" in js

    def test_tool_result_chart_saved_updates_live_artifacts(self, js):
        assert "_chartArtifactFromText" in js
        assert "_addTurnArtifact" in js
        assert "this._chartArtifactFromText(web.summary || web.content || '')" in js

    def test_chart_reference_matching_tolerates_hash_drift(self, js):
        assert "_stripChartHash" in js
        assert "startsWith(normalizedBase)" in js

    def test_chart_reference_matching_reports_ambiguous_fuzzy_matches(self, js):
        assert "_chartArtifactMatches" in js
        assert "status: 'ambiguous'" in js
        assert "Chart reference is ambiguous" in js

    def test_chart_references_can_resolve_session_level_artifacts(self, js):
        assert "_chartSearchArtifacts(turn)" in js
        assert "this.sessionArtifacts" in js
        assert "_replaceChartReferences(text, turn)" in js

    def test_live_artifact_updates_are_scoped_to_current_session(self, js):
        assert "_artifactBelongsToSession" in js
        assert "sessionId === this.currentSessionId" in js
        assert "this._addTurnArtifact(turn, art, sessionId)" in js

    def test_data_backed_mermaid_charts_are_blocked(self, js):
        assert "_isDataBackedMermaid" in js
        assert "xychart-beta" in js
        assert "Data-backed Mermaid charts are blocked" in js


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
        assert "Rewind Conversation" in html or "回退对话" in html
        assert "rewindModal.show" in html
        assert "selectedRound" in html

    def test_rewind_button_in_topbar(self, html):
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


    def test_live_user_turn_round_index_is_one_based(self, js):
        assert "roundIndex: this._countUserTurns(state.turns) + 1" in js

    def test_rewind_persists_truncated_history(self, tmp_path: Path, monkeypatch):
        from data_agent import config as config_module
        from data_agent.config import AgentConfig
        from data_agent.session.history import load_session, save_session
        from data_agent.web.app import create_app

        cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
        monkeypatch.setattr(config_module, "_config", cfg)

        session_id = "rewind_persist"
        save_session(
            [
                {"role": "user", "content": "round 1"},
                {"role": "assistant", "content": "answer 1"},
                {"role": "user", "content": "round 2"},
                {"role": "assistant", "content": "answer 2"},
                {"role": "user", "content": "round 3"},
                {"role": "assistant", "content": "answer 3"},
            ],
            session_id,
        )

        app = create_app()
        app.config["TESTING"] = True
        response = app.test_client().post(f"/api/sessions/{session_id}/rewind", json={"round": 2})

        assert response.status_code == 200
        persisted = load_session(session_id)
        assert [m["content"] for m in persisted["messages"]] == ["round 1", "answer 1"]

    def test_save_session_can_intentionally_truncate_for_rewind(self, tmp_path: Path, monkeypatch):
        from data_agent import config as config_module
        from data_agent.config import AgentConfig
        from data_agent.session.history import load_session, save_session

        cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
        monkeypatch.setattr(config_module, "_config", cfg)

        session_id = "rewind_save"
        save_session(
            [
                {"role": "user", "content": "round 1"},
                {"role": "assistant", "content": "answer 1"},
                {"role": "user", "content": "round 2"},
                {"role": "assistant", "content": "answer 2"},
            ],
            session_id,
        )

        save_session(
            [{"role": "user", "content": "round 1"}, {"role": "assistant", "content": "answer 1"}],
            session_id,
            merge_protect=False,
        )

        persisted = load_session(session_id)
        assert [m["content"] for m in persisted["messages"]] == ["round 1", "answer 1"]


class TestCompactFocus:
    """2.2 Enhanced compact with focus parameter."""

    def test_compact_dialog_data(self, js):
        assert "compactDialog" in js

    def test_do_compact_method(self, js):
        assert "doCompact" in js

    def test_compact_dialog_html(self, html):
        assert "Compress Context" in html or "压缩上下文" in html
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
        assert "_startThinkingCycle(turn, sessionId, state)" in js
        assert "_thinkingTimerOwner" in js

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

    def test_markdown_export_downloads_md_file(self, js):
        assert "text/markdown" in js
        assert "reply.md" in js
        assert "已复制 Markdown 到剪贴板" not in js

    def test_export_popover_html(self, html):
        assert "exportSingleReply(turns[parseInt(activePopover.slice(7))], 'html')" in html
        assert "exportSingleReply(turns[parseInt(activePopover.slice(7))], 'markdown')" in html
        assert "Copy as Markdown" not in html


class TestLineSpacing:
    """3.5 Unified response line spacing."""

    def test_prose_font_size(self, css):
        assert "font-size: 0.875rem" in css

    def test_prose_p_margin(self, css):
        assert "margin-top: 0.625em" in css
        assert "margin-bottom: 0.625em" in css


class TestComposerAndKratosIcons:
    """Chat composer alignment and requested Kratos icon replacements."""

    def test_composer_alignment_styles(self, html, css):
        assert "composer-input" in html
        assert "composer-actions" in html
        assert ".composer-input" in css
        assert "min-height: 3.5rem" in css
        assert "top: 50%" in css

    def test_kratos_icons_are_used_for_requested_actions(self, html):
        assert "icons/kratos-export.svg" in html
        assert "icons/kratos-compress.svg" in html
        assert "icons/kratos-rewind.svg" in html
        assert "kratos-icon-export" in html
        assert "kratos-icon-compact" in html
        assert "kratos-icon-rewind" in html

    def test_kratos_icon_assets_are_served(self, client):
        for filename in [
            "kratos-export.svg",
            "kratos-compress.svg",
            "kratos-rewind.svg",
        ]:
            resp = client.get(f"/static/icons/{filename}")
            assert resp.status_code == 200
            assert resp.mimetype == "image/svg+xml"


# =====================================================
# Phase 4: Workbench Redesign
# =====================================================


class TestWorkbenchRedesign:
    """4.1-4.3 Workbench simplified to single Outputs panel."""

    def test_outputs_panel_header(self, html):
        assert ">Outputs<" in html or "Outputs" in html or "输出" in html or "产出物" in html

    def test_no_workbench_tab_in_js(self, js):
        assert "workbenchTab" not in js

    def test_no_analysis_state_grid(self, html):
        assert "Analysis State" not in html

    def test_no_workflow_tasks_in_workbench(self, html):
        assert "Workflow Tasks" not in html

    def test_report_generation_section(self, html):
        assert "生成报告" not in html
        assert "generateSessionReport(" not in html
        assert "generate_analysis_brief" not in html
        assert "generate_formal_report" not in html

    def test_conversation_export_section(self, html):
        assert "exportConversation('html')" in html
        assert "exportConversation('markdown')" in html
        assert "exportConversation('pdf')" not in html

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
        assert "Analyze the trends" in html or "分析趋势" in html or "分析数据趋势" in html
        assert "What insights" in html or "有什么洞察" in html or "你能发现什么洞察" in html
        assert "Create a visualization" in html or "创建可视化" in html or "创建数据可视化" in html

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
        assert "Submit" in html or "提交" in html

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


class TestConfirmationRuntimeRestore:
    def test_session_load_restores_active_confirmation(self, js):
        assert "_restoreActiveConfirmation" in js
        assert "data.active_confirmation" in js
        assert "_confirmationFromPayload(data.active_confirmation)" in js

    def test_resume_payload_uses_runtime_confirmation_contract(self, js):
        assert "confirmation_id: confirmation.confirmation_id" in js
        assert "expected_version: confirmation.version" in js
        assert "idempotency_key: confirmation._idempotencyKey" in js
        assert "suspension_id: suspensionId" not in js


class TestConfirmationWorkbenchWording:
    def test_workbench_distinguishes_workflow_notes_from_active_confirmations(self, html, js):
        assert "workflow_notes" in js
        assert "workbenchConfirmation()" in js
        assert "workflow_notes" not in html


class TestAnalysisProgressNarration:
    """Task 11 — safe live progress narration reaches the browser without leaking findings."""

    def test_frontend_handles_analysis_progress_without_appending_final_text(self, js):
        assert "case 'analysis_progress':" in js
        assert "turn.analysisProgress" in js
        # Scope to the case body so the assertion is robust to other handlers.
        start = js.index("case 'analysis_progress':")
        end = js.index("break;", start)
        block = js[start:end]
        assert "turn.thinkingText = data.label" in block
        assert "this._renderMessages()" not in block
        assert "this.turns = [...state.turns]" in block
        # No mutation of the final answer text inside the progress handler.
        assert "turn.content +=" not in block
        assert "turn.content =" not in block
