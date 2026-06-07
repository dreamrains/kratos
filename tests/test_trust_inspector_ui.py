import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _app_js() -> str:
    return (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def _method_body(js: str, name: str, async_method: bool = False) -> str:
    prefix = "async " if async_method else ""
    match = re.search(rf"{prefix}{name}\([^)]*\) {{(?P<body>.*?)\n        }},", js, re.S)
    assert match, f"{name} method not found"
    return match.group("body")


def test_trust_inspector_state_and_loader_contract():
    js = _app_js()

    assert "trustInspectorCollapsed: false" in js
    assert "trustView: null" in js
    assert "trustLoading: false" in js
    assert "trustError: ''" in js
    assert "async loadTrustView(sessionId = this.currentSessionId)" in js
    assert "fetch(`/api/sessions/${sessionId}/trust`)" in js


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
