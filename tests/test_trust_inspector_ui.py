import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _app_js() -> str:
    return (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def _index_html() -> str:
    return (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")


def _app_css() -> str:
    return (ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")


def _run_workbench_formatters(files):
    script = r"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const app = chatApp();
const files = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(files.map((file) => ({
    label: app.formatWorkbenchAssignmentLabel(file),
    status: app.workbenchDecisionStatus(file),
    style: app.trustStatusClass(app.workbenchDecisionStatus(file)),
    reason: app.formatWorkbenchFileReason(file),
}))));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(ROOT / "src/data_agent/web/static/js/app.js"),
            json.dumps(files, ensure_ascii=False),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _run_relationship_diagnostic_formatters(diagnostics):
    script = r"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const app = chatApp();
const diagnostics = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(diagnostics.map((diagnostic) =>
    app.formatRelationshipDiagnosticMeta(diagnostic)
)));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(ROOT / "src/data_agent/web/static/js/app.js"),
            json.dumps(diagnostics, ensure_ascii=False),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _run_file_decision_keys(files):
    html = _index_html()
    loop = re.search(
        r'<template x-for="\(file, index\) in workbenchContext\(\)\.file_decisions" '
        r':key="(?P<expression>[^"]+)">',
        html,
    )
    assert loop, "file decision loop with indexed key not found"
    script = r"""
const files = JSON.parse(process.argv[1]);
const expression = process.argv[2];
const keyFor = new Function('file', 'index', `return ${expression};`);
process.stdout.write(JSON.stringify(files.map((file, index) => keyFor(file, index))));
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps(files), loop.group("expression")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _method_body(js: str, name: str, async_method: bool = False) -> str:
    prefix = "async " if async_method else ""
    match = re.search(rf"{prefix}{name}\([^)]*\) {{(?P<body>.*?)\n        }},", js, re.S)
    assert match, f"{name} method not found"
    return match.group("body")


def _assert_object_mapping(body: str, key: str, value: str) -> None:
    assert re.search(rf"\b{key}: '{re.escape(value)}'", body), f"{key} mapping missing"


def _assert_current_session_assignment(body: str, assignment: str) -> None:
    pattern = rf"if \(sessionId === this\.currentSessionId\) {{(?P<guard_body>.*?)}}"
    guarded_blocks = [match.group("guard_body") for match in re.finditer(pattern, body, re.S)]
    assert any(assignment in block for block in guarded_blocks), f"{assignment} not current-session guarded"


def test_trust_inspector_state_and_loader_contract():
    js = _app_js()

    assert "trustInspectorCollapsed: false" in js
    assert "trustView: null" in js
    assert "trustLoading: false" in js
    assert "trustError: ''" in js
    assert "async loadTrustView(sessionId = this.currentSessionId)" in js
    assert "fetch(`/api/sessions/${sessionId}/trust`)" in js


def test_new_session_clears_trust_inspector_state():
    js = _app_js()
    body = _method_body(js, "newSession", async_method=True)

    assert "this.trustView = null" in body
    assert "this.trustError = ''" in body


def test_delete_active_session_clears_trust_inspector_state():
    js = _app_js()
    body = _method_body(js, "deleteSession", async_method=True)

    pattern = r"if \(this\.currentSessionId === sessionId\) {(?P<guard_body>.*?)\n            }"
    match = re.search(pattern, body, re.S)
    assert match, "active session delete branch not found"
    guard_body = match.group("guard_body")
    assert "this.trustView = null;" in guard_body
    assert "this.trustLoading = false;" in guard_body
    assert "this.trustError = '';" in guard_body


def test_load_trust_view_guards_stale_session_updates():
    js = _app_js()
    body = _method_body(js, "loadTrustView", async_method=True)

    stale_session_guard = "if (sessionId !== this.currentSessionId) return;"
    assert stale_session_guard in body
    guard_index = body.index(stale_session_guard)
    assert guard_index < body.index("this.trustView = null;", guard_index)
    assert guard_index < body.index("this.trustLoading = true;", guard_index)
    assert guard_index < body.index("this.trustError = '';", guard_index)
    assert guard_index < body.index("fetch(`/api/sessions/${sessionId}/trust`)")
    _assert_current_session_assignment(body, "this.trustView = data;")
    _assert_current_session_assignment(body, "this.trustLoading = false;")
    assert "this.trustView = null" in body
    assert "this.trustError = 'Trust status unavailable'" in body


def test_trust_status_label_contract():
    js = _app_js()
    body = _method_body(js, "trustStatusLabel")

    expected_labels = {
        "empty": "空",
        "clear": "无需确认",
        "needs_confirmation": "待确认",
        "not_run": "尚未验证",
        "ready": "就绪",
        "ready_with_warnings": "有提醒",
        "pass": "通过",
        "pass_with_downgrades": "有降级",
        "fail": "失败",
        "blocked": "阻塞",
        "warning": "提醒",
        "proposed": "待验证",
        "supported": "支持",
        "inconclusive": "不确定",
        "weakened": "减弱",
        "unsupported_by_data": "数据不支持",
        "unknown": "未知",
    }
    for key, value in expected_labels.items():
        _assert_object_mapping(body, key, value)


def test_trust_status_class_contract():
    js = _app_js()
    body = _method_body(js, "trustStatusClass")

    expected_classes = {
        "clear": "trust-pill-ok",
        "needs_confirmation": "trust-pill-warn",
        "not_run": "trust-pill-muted",
        "ready": "trust-pill-ok",
        "ready_with_warnings": "trust-pill-warn",
        "pass": "trust-pill-ok",
        "pass_with_downgrades": "trust-pill-warn",
        "warning": "trust-pill-warn",
        "fail": "trust-pill-blocked",
        "blocked": "trust-pill-blocked",
        "unknown": "trust-pill-muted",
    }
    for key, value in expected_classes.items():
        _assert_object_mapping(body, key, value)
    assert "|| classes.unknown" in body


def test_trust_route_selection_prefills_without_auto_submit():
    js = _app_js()
    body = _method_body(js, "selectTrustRoute")

    assert "selectTrustRoute(route)" in js
    assert "this.inputText = route.prompt" in body
    assert "sendMessage(" not in body


def test_trust_inspector_refresh_hooks_are_present():
    js = _app_js()

    assert "this.loadTrustView(sessionId)" in js
    assert "this.loadTrustView()" in js
    assert "case 'turn_end':" in js


def test_trust_inspector_panel_markup_contract():
    html = _index_html()

    assert "trust-inspector-panel" in html
    assert "session-side-tabs" in html
    assert "sessionSidePanelTab" in html
    assert "workbench.current_context" in html
    assert "workbench.confirmations" in html
    assert "workbench.trust_evidence" in html
    assert "trustView.history.routes" in html
    assert "trustView.risks" in html
    assert "workbenchTrustEvidence()" in html
    assert '@click="selectTrustRoute(route)"' in html
    assert "trustInspectorCollapsed" in html


def test_workbench_uses_context_confirmation_trust_sections():
    html = _index_html()

    assert "workbench.current_context" in html
    assert "workbench.confirmations" in html
    assert "workbench.trust_evidence" in html
    assert "当前上下文" in html
    assert "待确认事项" in html
    assert "可信证据" in html


def test_trust_inspector_contains_hypothesis_section():
    html = _index_html()
    js = _app_js()

    assert 'data-testid="trust-hypotheses"' in html
    assert "trustView.hypotheses" in html
    assert "top_claims" in html
    assert "formatHypothesisSummary(set)" in html
    assert "formatHypothesisSummary(set)" in js


def test_trust_inspector_labels_hypothesis_statuses():
    js = _app_js()

    assert "proposed: '待验证'" in js
    assert "supported: '支持'" in js
    assert "inconclusive: '不确定'" in js
    assert "unsupported_by_data: '数据不支持'" in js
    assert "supported: 'trust-pill-ok'" in js
    assert "unsupported_by_data: 'trust-pill-blocked'" in js


def test_session_side_panel_tabs_preserve_export_controls():
    html = _index_html()
    js = _app_js()

    assert "sessionSidePanelTab: 'current'" in js
    assert "当前分析" in html
    assert "数据与历史" in html
    assert "产出与导出" in html
    assert "x-show=\"sessionSidePanelTab === 'outputs'\"" in html
    assert 'role="tablist"' not in html

    outputs_match = re.search(
        r'<div x-show="sessionSidePanelTab === \'outputs\'">(?P<body>.*?)<!-- Artifacts -->'
        r'\s*<div x-show="sessionSidePanelTab === \'outputs\'">(?P<artifacts>.*?)</div>\s*</div>\s*</aside>',
        html,
        re.S,
    )
    assert outputs_match, "outputs tab content not found"
    outputs_body = outputs_match.group("body") + outputs_match.group("artifacts")
    assert "exportConversation('html')" in outputs_body
    assert "exportConversation('markdown')" in outputs_body
    assert "sessionArtifacts" in outputs_body


def test_session_side_panel_uses_chinese_trust_labels_and_help():
    html = _index_html()
    js = _app_js()

    assert "Session Side Panel" not in html
    assert "trustHelpText" in js
    assert "当前上下文" in html
    assert "待确认事项" in html
    assert "可信证据" in html
    assert "风险边界" in html
    assert "假设检验" in html
    assert "产出与导出" in html
    assert "这是什么" in js


def test_trust_routes_explain_items_and_budget_labels():
    html = _index_html()
    js = _app_js()

    assert "formatRouteBudgetLabel(route.budget_level)" in html
    assert "formatRouteReason(route)" in html
    assert "formatRouteLimitations(route)" in html
    assert "trustRouteHelpText(route)" in html
    assert "trust-route-detail" in html
    assert "route-help-" in html

    assert "formatRouteBudgetLabel(level)" in js
    assert "轻量" in js
    assert "标准" in js
    assert "深入" in js
    assert "trustRouteHelpText(route)" in js
    assert "为什么推荐" in js
    assert "适合回答" in js


def test_trust_routes_show_confirmation_gate_instead_of_candidate_routes():
    html = _index_html()
    js = _app_js()

    assert "trustConfirmationGate()" in js
    assert "需要先确认信息" in html
    assert "workbenchConfirmations()" in html
    assert "return this.workbenchConfirmations();" in js
    assert "trustConfirmationPending()" in html
    assert "trustConfirmationPending()" in js


def test_trust_long_lists_use_reusable_show_more_controls():
    html = _index_html()
    js = _app_js()

    assert "expandedListCounts: {}" in js
    assert "visibleListItems(key, items, defaultLimit = 6)" in js
    assert "hiddenListCount(key, items, defaultLimit = 6)" in js
    assert "showMoreListItems(key, items, step = 6, defaultLimit = 6)" in js
    assert "collapseListItems(key)" in js
    assert "visibleListItems('historyRoutes'" in html
    assert "hiddenListCount('historyRoutes'" in html
    assert "showMoreListItems('historyRoutes'" in html
    assert "collapseListItems('historyRoutes')" in html
    assert "再展示" in html
    assert "收起" in html


def test_current_data_and_verification_have_help_text():
    html = _index_html()
    js = _app_js()

    assert "trustHelpText('currentContext')" in html
    assert "trustHelpText('confirmations')" in html
    assert "trustHelpText('trustEvidence')" in html
    assert "当前分析目标" in js
    assert "继续分析前需要用户确认" in js
    assert "当前会话中的验证状态" in js


def test_history_routes_share_route_explanations():
    html = _index_html()

    assert "trustHelpText('historyRoutes')" in html
    assert "history-route-help-" in html
    assert "trustRouteHelpText(route)" in html
    assert "formatRouteLimitations(route)" in html


def test_current_data_uses_unified_file_decisions_and_folded_relationship_diagnostics():
    html = _index_html()
    js = _app_js()

    assert 'x-for="(file, index) in workbenchContext().file_decisions"' in html
    assert ':key="(file.file_id || file.dataset || file.filename || \'file\') + \':\' + index"' in html
    assert "workbenchContext().file_decisions.length" in html
    assert "formatWorkbenchAssignmentLabel(file)" in html
    assert "formatWorkbenchFileReason(file)" in html
    assert "workbenchDecisionStatus(file)" in html
    assert "<details" in html
    assert "技术关系说明" in html
    assert "workbenchRelationshipDiagnostics()" in html
    assert "trustView.active_bundle" not in html
    assert "formatActiveBundleSummary(trustView.active_bundle)" not in html
    assert "active_bundle.files" not in html
    assert "formatBundleFileSummary(file)" not in html
    assert "relationship_status" not in html

    assert "formatWorkbenchAssignmentLabel(file)" in js
    assert "formatWorkbenchFileReason(file)" in js
    assert "workbenchDecisionStatus(file)" in js
    assert "formatActiveBundleSummary(bundle)" not in js
    assert "formatBundleFileSummary(file)" not in js
    assert "formatWorkbenchFiles(files)" not in js
    assert "formatFileRelationshipSummary(relationship)" not in js
    assert "formatFileRelationshipMeta(relationship)" not in js
    assert "formatFileRelationshipEvidence(relationship)" not in js
    assert "formatFileRelationshipUncertainty(relationship)" not in js
    assert "formatRelationshipMode(mode)" in js
    for label in ("文件可用", "本次使用", "本次不需要", "需要你选择", "暂不可用"):
        assert label in js
    assert "暂无说明" in js
    assert "${taskCount} 个分析任务" in js
    assert "confirmed: '已确认'" in js
    assert "linked: '已关联'" in js
    assert "possibly_linked: '可能关联'" in js
    assert "available: '可用'" in js
    assert "excluded: '已排除'" in js
    assert "confirmed: 'trust-pill-ok'" in js
    assert "possibly_linked: 'trust-pill-warn'" in js


def test_workbench_file_helpers_map_contract_states_without_green_unknown_fallbacks():
    formatted = _run_workbench_formatters([
        {
            "eligibility": "unavailable",
            "assignment": "not_needed",
            "reason_code": "load_failed",
            "reason": "  后端原始说明  ",
            "task_refs": ["task_a", "task_b"],
        },
        {
            "eligibility": "eligible",
            "assignment": "available",
            "reason": "可用于后续任务",
        },
        {
            "eligibility": "eligible",
            "assignment": "used",
            "reason": "原始 reason",
        },
        {
            "eligibility": "eligible",
            "assignment": "not_needed",
            "reason": "",
            "task_refs": [],
        },
        {
            "eligibility": "eligible",
            "assignment": "needs_decision",
            "reason": "存在同名文件",
        },
        None,
        {},
        {"eligibility": "eligible", "assignment": "future_state"},
    ])

    assert formatted == [
        {
            "label": "暂不可用",
            "status": "unavailable",
            "style": "trust-pill-blocked",
            "reason": "后端原始说明 / 2 个分析任务",
        },
        {
            "label": "文件可用",
            "status": "available",
            "style": "trust-pill-ok",
            "reason": "可用于后续任务",
        },
        {
            "label": "本次使用",
            "status": "used",
            "style": "trust-pill-ok",
            "reason": "原始 reason",
        },
        {
            "label": "本次不需要",
            "status": "not_needed",
            "style": "trust-pill-muted",
            "reason": "暂无说明",
        },
        {
            "label": "需要你选择",
            "status": "needs_decision",
            "style": "trust-pill-warn",
            "reason": "存在同名文件",
        },
        {
            "label": "状态未知",
            "status": "unknown",
            "style": "trust-pill-muted",
            "reason": "暂无说明",
        },
        {
            "label": "状态未知",
            "status": "unknown",
            "style": "trust-pill-muted",
            "reason": "暂无说明",
        },
        {
            "label": "状态未知",
            "status": "unknown",
            "style": "trust-pill-muted",
            "reason": "暂无说明",
        },
    ]


def test_relationship_diagnostic_meta_formats_known_mode_without_empty_separator():
    formatted = _run_relationship_diagnostic_formatters([
        {
            "file_ids": ["orders", "users"],
            "relationship_mode": "include_in_active_bundle",
        },
        {
            "file_ids": ["orders"],
            "relationship_mode": "",
        },
        {
            "file_ids": ["users"],
            "relationship_mode": "future_mode",
        },
    ])

    assert formatted[0] == (
        "orders、users / 合并分析 / 仅供参考 / "
        "可用于后续合并、关联或映射时的技术判断。"
    )
    assert formatted[1] == (
        "orders / 仅供参考 / 可用于后续合并、关联或映射时的技术判断。"
    )
    assert formatted[2] == (
        "users / 仅供参考 / 可用于后续合并、关联或映射时的技术判断。"
    )
    assert all(" /  / " not in item for item in formatted)


def test_file_decision_keys_are_unique_when_identity_fields_are_missing():
    files = [
        {"reason_code": "missing_file_identity"},
        {"reason_code": "missing_file_identity"},
    ]

    keys = _run_file_decision_keys(files)

    assert keys == ["file:0", "file:1"]
    assert len(keys) == len(set(keys))
    assert all(keys)


def test_trust_risk_messages_are_localized_in_ui():
    html = _index_html()
    js = _app_js()

    assert "formatRiskMessage(risk.message)" in html
    assert "formatRiskMessage(message)" in js
    assert "相关性不代表因果关系" in js
    assert "未识别到可用于分组拆解的维度字段" in js
    assert "当前数据粒度偏汇总" in js


def test_trust_inspector_empty_states_hide_during_loading_or_error():
    html = _index_html()

    empty_state_labels = [
        "暂无数据画像。",
        "暂无待确认事项。",
        "暂无假设集合。",
        "暂无风险边界。",
    ]
    for label in empty_state_labels:
        match = re.search(rf'<p x-show="(?P<condition>[^"]+)"[^>]*>{re.escape(label)}</p>', html)
        assert match, f"{label} empty state not found"
        condition = match.group("condition")
        assert "!trustLoading" in condition
        assert "!trustError" in condition


def test_not_run_trust_evidence_shows_explanation_and_hides_counts():
    html = _index_html()

    assert "尚未产生可验证的分析声明" in html
    assert 'workbenchTrustEvidence().status === \'not_run\'' in html
    assert 'workbenchTrustEvidence().status !== \'not_run\'' in html
    assert "暂无可信证据。" not in html


def test_trust_inspector_panel_css_contract():
    css = _app_css()

    expected_selectors = [
        ".trust-inspector-panel",
        ".trust-section",
        ".trust-route-item",
        ".trust-risk-item",
        ".trust-pill-ok",
        ".trust-pill-warn",
        ".trust-pill-blocked",
        ".session-side-tabs",
        ".session-side-tab",
        ".trust-help-btn",
        ".trust-help-popover",
    ]
    for selector in expected_selectors:
        assert selector in css
    assert "overflow-wrap: anywhere" in css
