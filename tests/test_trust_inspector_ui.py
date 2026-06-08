import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _app_js() -> str:
    return (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def _index_html() -> str:
    return (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")


def _app_css() -> str:
    return (ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")


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
    assert "trustView.datasets" in html
    assert "trustView.routes" in html
    assert "trustView.risks" in html
    assert "trustView.verification" in html
    assert '@click="selectTrustRoute(route)"' in html
    assert "trustInspectorCollapsed" in html


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
    assert "可直接分析" in html
    assert "风险边界" in html
    assert "假设检验" in html
    assert "产出与导出" in html
    assert "这是什么" in js


def test_trust_inspector_empty_states_hide_during_loading_or_error():
    html = _index_html()

    empty_state_labels = [
        "暂无数据画像。",
        "暂无可直接分析路线。",
        "暂无假设集合。",
        "暂无风险边界。",
        "暂无验证报告。",
    ]
    for label in empty_state_labels:
        match = re.search(rf'<p x-show="(?P<condition>[^"]+)"[^>]*>{re.escape(label)}</p>', html)
        assert match, f"{label} empty state not found"
        condition = match.group("condition")
        assert "!trustLoading" in condition
        assert "!trustError" in condition


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
