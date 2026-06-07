# Trust Inspector MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only Web Trust Inspector that summarizes data readiness, recommended analysis routes, risk boundaries, and latest verification status for the current session.

**Architecture:** Keep trust formatting in a dedicated backend view-model builder, expose it through one read-only Flask endpoint, and let the existing Alpine app render the returned model. The chat remains the primary workflow; route clicks fill the existing composer and never auto-send.

**Tech Stack:** Python 3, Flask, pytest, Alpine.js, existing Tailwind utility classes, existing Web static CSS.

---

## File Structure

- Create `src/data_agent/agent/trust_view.py`: converts `AnalysisSessionState` refs into a stable frontend view model.
- Create `tests/test_trust_view.py`: unit tests for empty state, datasets, routes, risks, verification, and malformed refs.
- Modify `src/data_agent/web/blueprints/sessions.py`: add `GET /api/sessions/<session_id>/trust`.
- Create `tests/test_trust_inspector_api.py`: Flask API tests for missing state, populated state, and no mutation.
- Modify `src/data_agent/web/static/js/app.js`: add Trust Inspector state, loader, route selection, labels, and refresh hooks.
- Modify `src/data_agent/web/templates/index.html`: add the right-side Trust Inspector panel and refresh action.
- Modify `src/data_agent/web/static/css/app.css`: add compact inspector layout classes and responsive collapse behavior.
- Create `tests/test_trust_inspector_ui.py`: HTML/JS/CSS contract tests that match the current Web test style.

## API Contract

`GET /api/sessions/<session_id>/trust` returns this shape:

```json
{
  "status": "empty",
  "session_id": "example",
  "updated_at": "",
  "datasets": [],
  "routes": [],
  "risks": [],
  "verification": null
}
```

The endpoint must not call LLMs, run tools, create files, or mutate `analysis_state.json`.

---

### Task 1: Backend Trust View Builder

**Files:**
- Create: `src/data_agent/agent/trust_view.py`
- Create: `tests/test_trust_view.py`

- [ ] **Step 1: Write failing builder tests**

Create `tests/test_trust_view.py`:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view


def test_build_trust_view_empty_state():
    view = build_trust_view(None, session_id="missing")

    assert view == {
        "status": "empty",
        "session_id": "missing",
        "updated_at": "",
        "datasets": [],
        "routes": [],
        "risks": [],
        "verification": None,
    }


def test_build_trust_view_summarizes_dataset_contract_and_preview():
    state = AnalysisSessionState(session_id="s1", updated_at="2026-06-07 10:00:00")
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "row_count": 1200,
        "column_count": 8,
        "quality": {"status": "ready", "score": 96, "warnings": []},
        "field_roles": {
            "date": ["order_date"],
            "metrics": ["revenue"],
            "dimensions": ["channel", "city"],
        },
        "supported_analyses": ["trend", "period_compare"],
    }]
    state.preview_digests = [{
        "id": "preview_orders",
        "dataset": "orders",
        "notable_patterns": ["channel: 3 distinct values"],
    }]

    view = build_trust_view(state)

    assert view["status"] == "ready"
    assert view["datasets"] == [{
        "dataset": "orders",
        "rows": 1200,
        "columns": 8,
        "quality_status": "ready",
        "quality_score": 96,
        "key_fields": ["order_date", "revenue", "channel", "city"],
        "supported_analyses": ["trend", "period_compare"],
        "preview_notes": ["channel: 3 distinct values"],
    }]


def test_build_trust_view_limits_routes_and_generates_editable_prompts():
    state = AnalysisSessionState(session_id="s1")
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "orders",
            "direction": "trend",
            "label": "Revenue trend",
            "reason": "Time column and revenue metric are available.",
            "limitations": ["Descriptive trend only"],
            "budget_level": "light",
        },
        {"id": "route_compare", "dataset": "orders", "direction": "period_compare"},
        {"id": "route_dimension", "dataset": "orders", "direction": "dimension_decomposition"},
        {"id": "route_rate", "dataset": "orders", "direction": "rate_analysis"},
        {"id": "route_extra", "dataset": "orders", "direction": "correlation"},
    ]

    view = build_trust_view(state)

    assert [item["id"] for item in view["routes"]] == [
        "route_trend",
        "route_compare",
        "route_dimension",
        "route_rate",
    ]
    assert view["routes"][0]["prompt"].startswith("Please analyze the current dataset")
    assert "trend" in view["routes"][0]["prompt"]
    assert view["routes"][0]["auto_submit"] is False


def test_build_trust_view_extracts_risks_from_contracts_and_cleaning_logs():
    state = AnalysisSessionState(session_id="s1")
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "quality": {
            "status": "blocked",
            "block_issues": ["date column is missing"],
            "warnings": ["revenue has nulls"],
        },
        "unsupported_analyses": [
            {"type": "user_level_retention", "reason": "missing user id"},
        ],
    }]
    state.cleaning_logs = [{
        "id": "clean_orders",
        "dataset": "orders",
        "decisions": [
            {
                "column": "revenue",
                "decision_type": "needs_confirmation",
                "impact": "May change aggregate values",
            },
            {
                "column": "date",
                "decision_type": "blocked",
                "impact": "Blocks dependent analysis",
            },
        ],
    }]

    view = build_trust_view(state)

    assert view["risks"] == [
        {
            "severity": "blocked",
            "source": "data_quality",
            "dataset": "orders",
            "field": "",
            "message": "date column is missing",
        },
        {
            "severity": "warning",
            "source": "data_quality",
            "dataset": "orders",
            "field": "",
            "message": "revenue has nulls",
        },
        {
            "severity": "warning",
            "source": "unsupported_analysis",
            "dataset": "orders",
            "field": "user_level_retention",
            "message": "missing user id",
        },
        {
            "severity": "warning",
            "source": "cleaning",
            "dataset": "orders",
            "field": "revenue",
            "message": "May change aggregate values",
        },
        {
            "severity": "blocked",
            "source": "cleaning",
            "dataset": "orders",
            "field": "date",
            "message": "Blocks dependent analysis",
        },
    ]


def test_build_trust_view_uses_latest_verification_report_counts():
    state = AnalysisSessionState(session_id="s1")
    state.verification_reports = [
        {"id": "verify_old", "overall_status": "pass", "claim_count": 1},
        {
            "id": "verify_new",
            "overall_status": "pass_with_downgrades",
            "claim_count": 3,
            "failed_count": 0,
            "downgraded_count": 1,
            "evidence_signature": "ev_1|routes:route_trend|cleaning:",
            "created_at": "2026-06-07 10:30:00",
        },
    ]

    view = build_trust_view(state)

    assert view["verification"] == {
        "id": "verify_new",
        "status": "pass_with_downgrades",
        "claim_count": 3,
        "failed_count": 0,
        "downgraded_count": 1,
        "evidence_signature": "ev_1|routes:route_trend|cleaning:",
        "created_at": "2026-06-07 10:30:00",
    }


def test_build_trust_view_skips_malformed_refs():
    class MalformedState:
        session_id = "bad"
        updated_at = "2026-06-07 10:00:00"
        dataset_contracts = {"not": "a list"}
        preview_digests = [{"dataset": "orders"}, "bad preview"]
        route_proposals = ["bad route", {"id": "route_ok", "direction": "trend"}]
        cleaning_logs = "bad cleaning"
        verification_reports = ["bad verification"]
        data_state = "data_loaded"

    view = build_trust_view(MalformedState())

    assert view["status"] == "ready"
    assert view["datasets"] == []
    assert [route["id"] for route in view["routes"]] == ["route_ok"]
    assert view["risks"] == []
    assert view["verification"] is None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
pytest tests/test_trust_view.py -q
```

Expected:

```text
ERROR tests/test_trust_view.py
ModuleNotFoundError: No module named 'data_agent.agent.trust_view'
```

- [ ] **Step 3: Implement the trust view builder**

Create `src/data_agent/agent/trust_view.py`:

```python
"""Frontend view model for the Web Trust Inspector."""

from __future__ import annotations

from typing import Any


def build_trust_view(state: Any, session_id: str | None = None) -> dict[str, Any]:
    """Return a compact, read-only trust summary for a session."""

    sid = session_id or str(getattr(state, "session_id", "") or "")
    if state is None:
        return _empty_view(sid)

    datasets = _dataset_summaries(_list_attr(state, "dataset_contracts"), _list_attr(state, "preview_digests"))
    routes = _route_cards(_list_attr(state, "route_proposals"))
    risks = _risk_items(_list_attr(state, "dataset_contracts"), _list_attr(state, "cleaning_logs"))
    verification = _verification_summary(_list_attr(state, "verification_reports"))
    data_state = getattr(state, "data_state", "")
    status = "ready" if datasets or routes or risks or verification or data_state == "data_loaded" else "empty"

    return {
        "status": status,
        "session_id": sid,
        "updated_at": str(getattr(state, "updated_at", "") or ""),
        "datasets": datasets,
        "routes": routes,
        "risks": risks,
        "verification": verification,
    }


def _empty_view(session_id: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "session_id": session_id,
        "updated_at": "",
        "datasets": [],
        "routes": [],
        "risks": [],
        "verification": None,
    }


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return str(value)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _field_names(value: Any) -> list[str]:
    names: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            item = item.get("column") or item.get("name")
        text = _text(item)
        if text and text not in names:
            names.append(text)
    return names


def _dataset_summaries(contracts: list[dict[str, Any]], previews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preview_by_dataset = {
        str(item.get("dataset")): item
        for item in previews
        if item.get("dataset")
    }
    summaries: list[dict[str, Any]] = []
    for contract in contracts:
        dataset = _text(contract.get("dataset") or contract.get("name") or contract.get("id"))
        quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
        roles = contract.get("field_roles") if isinstance(contract.get("field_roles"), dict) else {}
        key_fields: list[str] = []
        for role_name in ("date", "metrics", "rate_metrics", "dimensions", "ids"):
            for field_name in _field_names(roles.get(role_name)):
                if field_name not in key_fields:
                    key_fields.append(field_name)
                if len(key_fields) >= 6:
                    break
            if len(key_fields) >= 6:
                break
        preview = preview_by_dataset.get(dataset, {})
        summaries.append({
            "dataset": dataset,
            "rows": contract.get("row_count"),
            "columns": contract.get("column_count"),
            "quality_status": _first_non_empty(contract.get("quality_status"), quality.get("status"), "unknown"),
            "quality_score": quality.get("score"),
            "key_fields": key_fields,
            "supported_analyses": _field_names(contract.get("supported_analyses"))[:6],
            "preview_notes": _field_names(preview.get("notable_patterns"))[:3],
        })
    return summaries


def _route_cards(routes: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for route in routes:
        direction = _text(route.get("direction"))
        if not direction:
            continue
        dataset = _text(route.get("dataset"))
        label = _first_non_empty(route.get("label"), direction.replace("_", " ").title())
        item = {
            "id": _first_non_empty(route.get("id"), f"route_{len(cards) + 1}"),
            "dataset": dataset,
            "direction": direction,
            "label": label,
            "reason": _text(route.get("reason") or route.get("evidence_basis")),
            "limitations": _field_names(route.get("limitations"))[:3],
            "budget_level": _text(route.get("budget_level") or "standard"),
            "prompt": _route_prompt(dataset, direction, label),
            "auto_submit": False,
        }
        cards.append(item)
        if len(cards) >= limit:
            break
    return cards


def _route_prompt(dataset: str, direction: str, label: str) -> str:
    dataset_part = f" for `{dataset}`" if dataset else ""
    return (
        f"Please analyze the current dataset{dataset_part} using the recommended "
        f"{direction} route ({label}). Include key metric changes, evidence basis, "
        "sample size, method limits, and a decision-oriented summary."
    )


def _risk_items(contracts: list[dict[str, Any]], cleaning_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for contract in contracts:
        dataset = _text(contract.get("dataset") or contract.get("name"))
        quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
        for issue in _field_names(quality.get("block_issues")):
            risks.append(_risk("blocked", "data_quality", dataset, "", issue))
        for warning in _field_names(quality.get("warnings")):
            risks.append(_risk("warning", "data_quality", dataset, "", warning))
        for item in _as_list(contract.get("unsupported_analyses")):
            if not isinstance(item, dict):
                continue
            risks.append(_risk(
                "warning",
                "unsupported_analysis",
                dataset,
                _text(item.get("type")),
                _first_non_empty(item.get("reason"), item.get("message"), item.get("type")),
            ))

    for log in cleaning_logs:
        dataset = _text(log.get("dataset"))
        for decision in _as_list(log.get("decisions")):
            if not isinstance(decision, dict):
                continue
            decision_type = _text(decision.get("decision_type"))
            if decision_type not in {"needs_confirmation", "blocked"}:
                continue
            risks.append(_risk(
                "blocked" if decision_type == "blocked" else "warning",
                "cleaning",
                dataset,
                _text(decision.get("column")),
                _first_non_empty(decision.get("impact"), decision.get("reason"), decision_type),
            ))
    return risks[:12]


def _risk(severity: str, source: str, dataset: str, field: str, message: str) -> dict[str, str]:
    return {
        "severity": severity,
        "source": source,
        "dataset": dataset,
        "field": field,
        "message": message,
    }


def _verification_summary(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not reports:
        return None
    report = reports[-1]
    return {
        "id": _text(report.get("id")),
        "status": _text(report.get("overall_status") or report.get("status") or "unknown"),
        "claim_count": int(report.get("claim_count") or len(_as_list(report.get("claim_checks")))),
        "failed_count": int(report.get("failed_count") or 0),
        "downgraded_count": int(report.get("downgraded_count") or 0),
        "evidence_signature": _text(report.get("evidence_signature")),
        "created_at": _text(report.get("created_at") or report.get("timestamp")),
    }
```

- [ ] **Step 4: Run builder tests and commit**

Run:

```powershell
pytest tests/test_trust_view.py -q
```

Expected:

```text
6 passed
```

Commit:

```powershell
git add src/data_agent/agent/trust_view.py tests/test_trust_view.py
git commit -m "feat: add trust inspector view model"
```

---

### Task 2: Read-Only Trust API

**Files:**
- Modify: `src/data_agent/web/blueprints/sessions.py`
- Create: `tests/test_trust_inspector_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_trust_inspector_api.py`:

```python
import json

from data_agent.config import get_config
from data_agent.session.task_manager import task_manager


def _use_tmp_state(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    old_tasks_dir = task_manager._dir
    cfg.sessions_dir = tmp_path / "sessions"
    task_manager._dir = tmp_path / "tasks"
    task_manager.reset_for_testing()
    return cfg, old_sessions, old_tasks_dir


def _restore_state(cfg, old_sessions, old_tasks_dir):
    cfg.sessions_dir = old_sessions
    task_manager._dir = old_tasks_dir
    task_manager._next_id_val = 0


def test_trust_endpoint_returns_empty_for_missing_state(tmp_path):
    cfg, old_sessions, old_tasks_dir = _use_tmp_state(tmp_path)
    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get("/api/sessions/missing_session/trust")

        assert resp.status_code == 200
        assert resp.get_json() == {
            "status": "empty",
            "session_id": "missing_session",
            "updated_at": "",
            "datasets": [],
            "routes": [],
            "risks": [],
            "verification": None,
        }
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir)


def test_trust_endpoint_returns_populated_view(tmp_path):
    cfg, old_sessions, old_tasks_dir = _use_tmp_state(tmp_path)
    session_id = "trust_api"
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "analysis_state.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "data_state": "data_loaded",
                "dataset_contracts": [{
                    "id": "duc_orders",
                    "dataset": "orders",
                    "row_count": 10,
                    "column_count": 3,
                    "quality": {"status": "ready", "score": 90},
                    "field_roles": {"date": ["date"], "metrics": ["gmv"]},
                }],
                "route_proposals": [{
                    "id": "route_trend",
                    "dataset": "orders",
                    "direction": "trend",
                }],
                "verification_reports": [{
                    "id": "verify_1",
                    "overall_status": "pass",
                    "claim_count": 1,
                }],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get(f"/api/sessions/{session_id}/trust")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ready"
        assert body["datasets"][0]["dataset"] == "orders"
        assert body["routes"][0]["direction"] == "trend"
        assert body["verification"]["status"] == "pass"
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir)


def test_trust_endpoint_does_not_mutate_analysis_state_file(tmp_path):
    cfg, old_sessions, old_tasks_dir = _use_tmp_state(tmp_path)
    session_id = "trust_no_mutation"
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "analysis_state.json"
    payload = {"session_id": session_id, "data_state": "data_loaded"}
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    before = state_file.read_text(encoding="utf-8")

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get(f"/api/sessions/{session_id}/trust")

        assert resp.status_code == 200
        assert state_file.read_text(encoding="utf-8") == before
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir)
```

- [ ] **Step 2: Run API tests and confirm endpoint is missing**

Run:

```powershell
pytest tests/test_trust_inspector_api.py -q
```

Expected:

```text
FAILED tests/test_trust_inspector_api.py::test_trust_endpoint_returns_empty_for_missing_state
assert 404 == 200
```

- [ ] **Step 3: Add the API route**

In `src/data_agent/web/blueprints/sessions.py`, add this route after `get_analysis_state` and before `reset_session_analysis_state`:

```python
@sessions_bp.get("/sessions/<session_id>/trust")
def get_session_trust_view(session_id: str):
    """Return a read-only trust summary for the Web Trust Inspector."""
    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.agent.trust_view import build_trust_view

    state = load_analysis_state(session_id)
    return jsonify(build_trust_view(state, session_id=session_id))
```

- [ ] **Step 4: Run API and builder tests, then commit**

Run:

```powershell
pytest tests/test_trust_view.py tests/test_trust_inspector_api.py -q
```

Expected:

```text
9 passed
```

Commit:

```powershell
git add src/data_agent/web/blueprints/sessions.py tests/test_trust_inspector_api.py
git commit -m "feat: expose trust inspector api"
```

---

### Task 3: Frontend Trust State And Refresh Hooks

**Files:**
- Modify: `src/data_agent/web/static/js/app.js`
- Create: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Write failing JS contract tests**

Create `tests/test_trust_inspector_ui.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "data_agent" / "web" / "static" / "js" / "app.js"
HTML = ROOT / "src" / "data_agent" / "web" / "templates" / "index.html"
CSS = ROOT / "src" / "data_agent" / "web" / "static" / "css" / "app.css"


def test_trust_inspector_js_state_and_loader_contract():
    js = JS.read_text(encoding="utf-8")

    assert "trustInspectorCollapsed: false" in js
    assert "trustView: null" in js
    assert "trustLoading: false" in js
    assert "trustError: ''" in js
    assert "async loadTrustView(sessionId = this.currentSessionId)" in js
    assert "fetch(`/api/sessions/${sessionId}/trust`)" in js
    assert "selectTrustRoute(route)" in js
    assert "this.inputText = route.prompt" in js


def test_select_trust_route_does_not_auto_send():
    js = JS.read_text(encoding="utf-8")
    start = js.index("selectTrustRoute(route)")
    end = js.index("trustStatusLabel(status)", start)
    method_body = js[start:end]

    assert "this.inputText = route.prompt" in method_body
    assert "sendMessage(" not in method_body


def test_trust_view_refresh_hooks_are_registered():
    js = JS.read_text(encoding="utf-8")

    assert "this.loadTrustView(sessionId)" in js
    assert "this.loadTrustView()" in js
    assert "case 'turn_end':" in js
```

- [ ] **Step 2: Run JS contract tests and confirm they fail**

Run:

```powershell
pytest tests/test_trust_inspector_ui.py -q
```

Expected:

```text
FAILED tests/test_trust_inspector_ui.py::test_trust_inspector_js_state_and_loader_contract
assert 'trustInspectorCollapsed: false' in js
```

- [ ] **Step 3: Add Trust Inspector Alpine state**

In `src/data_agent/web/static/js/app.js`, near existing `analysisState: null`, insert:

```javascript
        analysisState: null,
        trustInspectorCollapsed: false,
        trustView: null,
        trustLoading: false,
        trustError: '',
```

In `newSession()`, after `this.analysisState = null;`, insert:

```javascript
            this.trustView = null;
            this.trustError = '';
```

In `switchSession(sessionId)`, extend the existing `Promise.all` block to include `loadTrustView`:

```javascript
            await Promise.all([
                this.loadAnalysisState(sessionId),
                this.loadTrustView(sessionId),
                this.loadSessionArtifacts(sessionId),
                this.loadTasks(),
            ]);
```

- [ ] **Step 4: Add loader, route selection, and labels**

In `src/data_agent/web/static/js/app.js`, add these methods after `loadAnalysisState(...)`:

```javascript
        async loadTrustView(sessionId = this.currentSessionId) {
            if (!sessionId || sessionId === '_pending_') {
                this.trustView = null;
                this.trustError = '';
                return;
            }
            this.trustLoading = true;
            this.trustError = '';
            try {
                const res = await fetch(`/api/sessions/${sessionId}/trust`);
                if (!res.ok) throw new Error('trust view request failed');
                const data = await res.json();
                if (sessionId === this.currentSessionId) this.trustView = data;
            } catch {
                if (sessionId === this.currentSessionId) {
                    this.trustView = null;
                    this.trustError = 'Trust status unavailable';
                }
            } finally {
                if (sessionId === this.currentSessionId) this.trustLoading = false;
            }
        },

        selectTrustRoute(route) {
            if (!route || !route.prompt) return;
            this.inputText = route.prompt;
        },

        trustStatusLabel(status) {
            const labels = {
                empty: 'No data',
                ready: 'Ready',
                pass: 'Verified',
                pass_with_downgrades: 'Cautious',
                fail: 'Needs review',
                blocked: 'Blocked',
                warning: 'Warning',
                unknown: 'Unknown',
            };
            return labels[status] || status || 'Unknown';
        },

        trustStatusClass(status) {
            if (['pass', 'ready'].includes(status)) return 'trust-pill-ok';
            if (['pass_with_downgrades', 'warning'].includes(status)) return 'trust-pill-warn';
            if (['fail', 'blocked'].includes(status)) return 'trust-pill-blocked';
            return 'trust-pill-muted';
        },
```

- [ ] **Step 5: Refresh trust view after turns complete**

In the `_handleEvent` `case 'turn_end':` branch, inside `if (isCurrentSession) { ... }`, add:

```javascript
                        this.loadTrustView();
```

The surrounding block should read:

```javascript
                    if (isCurrentSession) {
                        this.isLoading = false;
                        this.turns = [...state.turns];
                        this.loadTrustView();
                        this._scrollToBottom();
                        requestAnimationFrame(() => {
                            const el = document.getElementById('messages-container');
                            if (el) this._renderMermaidInElement(el);
                        });
                    }
```

- [ ] **Step 6: Run JS contract tests and commit**

Run:

```powershell
pytest tests/test_trust_inspector_ui.py -q
```

Expected:

```text
3 passed
```

Commit:

```powershell
git add src/data_agent/web/static/js/app.js tests/test_trust_inspector_ui.py
git commit -m "feat: add trust inspector frontend state"
```

---

### Task 4: Right-Side Trust Inspector Panel

**Files:**
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/css/app.css`
- Modify: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Add failing HTML and CSS contract tests**

Append these tests to `tests/test_trust_inspector_ui.py`:

```python
def test_trust_inspector_markup_contract():
    html = HTML.read_text(encoding="utf-8")

    assert "trust-inspector-panel" in html
    assert "trustView.datasets" in html
    assert "trustView.routes" in html
    assert "trustView.risks" in html
    assert "trustView.verification" in html
    assert "@click=\"selectTrustRoute(route)\"" in html
    assert "trustInspectorCollapsed" in html


def test_trust_inspector_css_contract():
    css = CSS.read_text(encoding="utf-8")

    assert ".trust-inspector-panel" in css
    assert ".trust-section" in css
    assert ".trust-route-item" in css
    assert ".trust-risk-item" in css
    assert ".trust-pill-ok" in css
    assert ".trust-pill-warn" in css
    assert ".trust-pill-blocked" in css
```

- [ ] **Step 2: Run UI tests and confirm HTML/CSS assertions fail**

Run:

```powershell
pytest tests/test_trust_inspector_ui.py -q
```

Expected:

```text
FAILED tests/test_trust_inspector_ui.py::test_trust_inspector_markup_contract
FAILED tests/test_trust_inspector_ui.py::test_trust_inspector_css_contract
```

- [ ] **Step 3: Add Trust Inspector markup**

In `src/data_agent/web/templates/index.html`, replace the current workbench aside opening:

```html
    <!-- Workbench Panel -->
    <aside class="hidden xl:flex w-80 shrink-0 border-l border-stone-200 dark:border-stone-800 workbench-panel flex-col">
```

with:

```html
    <!-- Trust Inspector / Workbench Panel -->
    <aside class="hidden xl:flex shrink-0 border-l border-stone-200 dark:border-stone-800 workbench-panel trust-inspector-panel flex-col"
           :class="trustInspectorCollapsed ? 'w-14' : 'w-[22rem]'">
```

Inside the aside header button group, replace the refresh button with:

```html
                <button @click="trustInspectorCollapsed = !trustInspectorCollapsed"
                        class="p-1.5 rounded-lg hover:bg-stone-200/60 dark:hover:bg-stone-800 text-stone-400 transition-colors"
                        title="Toggle trust inspector">
                    <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-180': trustInspectorCollapsed }" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
                </button>
                <button @click="loadAnalysisState(); loadTrustView(); loadSessionArtifacts(); loadTasks()"
                        class="p-1.5 rounded-lg hover:bg-stone-200/60 dark:hover:bg-stone-800 text-stone-400 transition-colors"
                        title="Refresh">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v6h6M20 20v-6h-6M5 19a9 9 0 0014-3M19 5A9 9 0 005 8"/></svg>
                </button>
```

At the start of the aside scroll body, before the current "Conversation Export" block, insert:

```html
            <!-- Trust Inspector -->
            <div x-show="!trustInspectorCollapsed" class="space-y-4">
                <div class="trust-section">
                    <div class="flex items-center justify-between mb-2">
                        <h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider">Trust Inspector</h3>
                        <span class="trust-pill" :class="trustStatusClass(trustView && trustView.status)" x-text="trustStatusLabel(trustView && trustView.status)"></span>
                    </div>
                    <p x-show="trustLoading" class="text-xs text-stone-400">Loading trust status...</p>
                    <p x-show="trustError" class="text-xs text-red-500" x-text="trustError"></p>
                    <p x-show="!trustLoading && !trustError && (!trustView || trustView.status === 'empty')" class="text-xs text-stone-400">
                        Load data to view trustworthy analysis status.
                    </p>
                </div>

                <div class="trust-section" x-show="trustView && trustView.datasets && trustView.datasets.length">
                    <h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Data</h3>
                    <template x-for="dataset in trustView.datasets" :key="dataset.dataset">
                        <div class="trust-data-row">
                            <div class="flex items-center justify-between gap-2">
                                <p class="text-xs font-medium text-stone-700 dark:text-stone-300 truncate" x-text="dataset.dataset"></p>
                                <span class="trust-pill" :class="trustStatusClass(dataset.quality_status)" x-text="trustStatusLabel(dataset.quality_status)"></span>
                            </div>
                            <p class="text-[11px] text-stone-400 mt-1">
                                <span x-text="dataset.rows || '-'"></span> rows ·
                                <span x-text="dataset.columns || '-'"></span> columns
                            </p>
                            <p class="text-[11px] text-stone-500 dark:text-stone-400 truncate mt-1" x-text="(dataset.key_fields || []).join(', ')"></p>
                        </div>
                    </template>
                </div>

                <div class="trust-section" x-show="trustView && trustView.routes && trustView.routes.length">
                    <h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Recommended Routes</h3>
                    <div class="space-y-1.5">
                        <template x-for="route in trustView.routes" :key="route.id">
                            <button @click="selectTrustRoute(route)" class="trust-route-item" type="button">
                                <div class="flex items-center justify-between gap-2">
                                    <span class="text-xs font-medium text-stone-700 dark:text-stone-300 truncate" x-text="route.label"></span>
                                    <span class="text-[10px] text-stone-400" x-text="route.budget_level"></span>
                                </div>
                                <p class="text-[11px] text-stone-400 mt-1 truncate" x-text="route.direction"></p>
                                <p x-show="route.reason" class="text-[11px] text-stone-500 dark:text-stone-400 mt-1 line-clamp-2" x-text="route.reason"></p>
                            </button>
                        </template>
                    </div>
                </div>

                <div class="trust-section" x-show="trustView && trustView.risks && trustView.risks.length">
                    <h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Risk Boundaries</h3>
                    <template x-for="risk in trustView.risks" :key="risk.source + risk.dataset + risk.field + risk.message">
                        <div class="trust-risk-item" :class="'trust-risk-' + risk.severity">
                            <div class="flex items-center justify-between gap-2">
                                <span class="text-[10px] uppercase text-stone-400" x-text="risk.source"></span>
                                <span class="trust-pill" :class="trustStatusClass(risk.severity)" x-text="trustStatusLabel(risk.severity)"></span>
                            </div>
                            <p class="text-xs text-stone-700 dark:text-stone-300 mt-1" x-text="risk.message"></p>
                            <p class="text-[11px] text-stone-400 mt-1" x-text="[risk.dataset, risk.field].filter(Boolean).join(' · ')"></p>
                        </div>
                    </template>
                </div>

                <div class="trust-section" x-show="trustView">
                    <h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Verification</h3>
                    <template x-if="trustView && trustView.verification">
                        <div>
                            <div class="flex items-center justify-between gap-2">
                                <span class="trust-pill" :class="trustStatusClass(trustView.verification.status)" x-text="trustStatusLabel(trustView.verification.status)"></span>
                                <span class="text-[10px] text-stone-400" x-text="trustView.verification.claim_count + ' claims'"></span>
                            </div>
                            <p class="text-[11px] text-stone-400 mt-2">
                                Failed: <span x-text="trustView.verification.failed_count"></span> ·
                                Downgraded: <span x-text="trustView.verification.downgraded_count"></span>
                            </p>
                        </div>
                    </template>
                    <p x-show="trustView && !trustView.verification" class="text-xs text-stone-400">No evidence verification yet.</p>
                </div>
            </div>
```

- [ ] **Step 4: Add compact inspector CSS**

Append this CSS to `src/data_agent/web/static/css/app.css`:

```css
/* Trust Inspector */
.trust-inspector-panel {
    transition: width 0.18s ease;
}

.trust-section {
    border-bottom: 1px solid #e7e5e4;
    padding-bottom: 1rem;
}

.dark .trust-section {
    border-bottom-color: #292524;
}

.trust-data-row,
.trust-route-item,
.trust-risk-item {
    display: block;
    width: 100%;
    text-align: left;
    border-radius: 6px;
    border: 1px solid #e7e5e4;
    background: rgba(255, 255, 255, 0.45);
    padding: 0.625rem 0.75rem;
}

.dark .trust-data-row,
.dark .trust-route-item,
.dark .trust-risk-item {
    border-color: #292524;
    background: rgba(28, 25, 23, 0.45);
}

.trust-route-item {
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
}

.trust-route-item:hover {
    border-color: #0d9488;
    background: #f0fdfa;
}

.dark .trust-route-item:hover {
    border-color: #2dd4bf;
    background: rgba(45, 212, 191, 0.06);
}

.trust-risk-item {
    margin-bottom: 0.375rem;
}

.trust-risk-blocked {
    border-left: 3px solid #dc2626;
}

.trust-risk-warning {
    border-left: 3px solid #d97706;
}

.trust-pill {
    display: inline-flex;
    align-items: center;
    min-height: 1.25rem;
    padding: 0.125rem 0.375rem;
    border-radius: 999px;
    font-size: 10px;
    line-height: 1;
    white-space: nowrap;
}

.trust-pill-ok {
    color: #047857;
    background: #d1fae5;
}

.trust-pill-warn {
    color: #92400e;
    background: #fef3c7;
}

.trust-pill-blocked {
    color: #991b1b;
    background: #fee2e2;
}

.trust-pill-muted {
    color: #57534e;
    background: #f5f5f4;
}

.dark .trust-pill-ok {
    color: #6ee7b7;
    background: rgba(6, 95, 70, 0.28);
}

.dark .trust-pill-warn {
    color: #fbbf24;
    background: rgba(146, 64, 14, 0.28);
}

.dark .trust-pill-blocked {
    color: #fca5a5;
    background: rgba(127, 29, 29, 0.32);
}

.dark .trust-pill-muted {
    color: #d6d3d1;
    background: #292524;
}
```

- [ ] **Step 5: Run UI tests and commit**

Run:

```powershell
pytest tests/test_trust_inspector_ui.py -q
```

Expected:

```text
5 passed
```

Commit:

```powershell
git add src/data_agent/web/templates/index.html src/data_agent/web/static/css/app.css tests/test_trust_inspector_ui.py
git commit -m "feat: render trust inspector panel"
```

---

### Task 5: Integration Verification

**Files:**
- Verify only; no planned source edits.

- [ ] **Step 1: Run focused Trust Inspector test set**

Run:

```powershell
pytest tests/test_trust_view.py tests/test_trust_inspector_api.py tests/test_trust_inspector_ui.py -q
```

Expected:

```text
14 passed
```

- [ ] **Step 2: Run adjacent workflow regression tests**

Run:

```powershell
pytest tests/test_web_workbench_parity.py tests/test_trustworthy_workflow_mvp.py tests/test_trust_workflow_runtime.py tests/test_execution_control.py -q
```

Expected:

```text
all selected tests pass
```

The exact pass count may change if tests are added in parallel; there must be no failures.

- [ ] **Step 3: Inspect working tree**

Run:

```powershell
git status --short
```

Expected source changes after Task 4 commits:

```text
no tracked Trust Inspector implementation files are unstaged
```

Existing unrelated untracked files may remain, including `.superpowers/`, old `docs/superpowers/plans/2026-05...`, old `docs/superpowers/specs/2026-05...`, and `workspace/`.

- [ ] **Step 4: Final implementation commit if verification required a fix**

If Task 5 uncovered and fixed a defect, commit only the files touched by that fix:

```powershell
git add src/data_agent/agent/trust_view.py src/data_agent/web/blueprints/sessions.py src/data_agent/web/static/js/app.js src/data_agent/web/templates/index.html src/data_agent/web/static/css/app.css tests/test_trust_view.py tests/test_trust_inspector_api.py tests/test_trust_inspector_ui.py
git commit -m "fix: stabilize trust inspector integration"
```

If Task 5 did not require edits, skip this commit step.

---

## Self-Review

**Spec coverage:**
- Read-only Web API: Task 2.
- Right-side Trust Inspector panel: Task 4.
- Data overview from dataset contracts and previews: Task 1 and Task 4.
- Recommended routes limited to 2-4 and route click fills composer: Task 1, Task 3, and Task 4.
- Risk boundaries from data quality, unsupported analyses, and cleaning logs: Task 1 and Task 4.
- Latest verification status summary: Task 1 and Task 4.
- Refresh on session switch and turn end: Task 3.
- No LLM calls, no tool execution, no AgentLoop changes, no auto-submit: Task 1, Task 2, Task 3, and API mutation test.

**Type consistency:**
- Backend response keys are `status`, `session_id`, `updated_at`, `datasets`, `routes`, `risks`, and `verification`.
- Frontend state keys are `trustInspectorCollapsed`, `trustView`, `trustLoading`, and `trustError`.
- Route click consumes `route.prompt`, sets `inputText`, and does not call `sendMessage`.

**Verification commands:**
- `pytest tests/test_trust_view.py -q`
- `pytest tests/test_trust_inspector_api.py -q`
- `pytest tests/test_trust_inspector_ui.py -q`
- `pytest tests/test_web_workbench_parity.py tests/test_trustworthy_workflow_mvp.py tests/test_trust_workflow_runtime.py tests/test_execution_control.py -q`
