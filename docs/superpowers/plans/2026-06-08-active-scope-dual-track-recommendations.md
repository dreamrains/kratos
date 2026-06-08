# Active Scope Dual-Track Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build active-scope aware session side panel data and a dual-track recommendation model so chat and the side panel share one structured source without losing exploratory analysis value.

**Architecture:** Add active scope to `AnalysisSessionState`, then create a deterministic `route_capabilities` builder that classifies recommendations into executable and exploratory tracks. `build_trust_view` exposes active-scope filtered summaries plus session counts, while the Web side panel renders the result in Chinese-first tabs.

**Tech Stack:** Python dataclasses and JSON-friendly dicts, Flask API through the existing sessions blueprint, Alpine.js templates in `index.html`, static CSS in `app.css`, pytest string-contract and unit tests.

---

## File Structure

- Modify: `src/data_agent/agent/analysis_state.py`
  - Persist `active_scope`.
  - Add small mutator helpers for dataset, route, consulting, and artifact review modes.
  - Include compact active-scope and recommendation counts in `analysis_state_summary`.
- Create: `src/data_agent/agent/route_capabilities.py`
  - Build the shared executable/exploratory recommendation model from hydrated trust refs.
  - Keep outputs JSON-friendly and compact.
- Modify: `src/data_agent/agent/trust_view.py`
  - Use active scope and route capabilities.
  - Add `active_scope`, `scope_counts`, `recommendations`, and history-friendly collections.
  - Preserve backward-compatible top-level `datasets`, `routes`, `risks`, `verification`, and `hypotheses` keys.
- Modify: `src/data_agent/agent/analysis_entry.py`
  - Reuse the route capability builder for deterministic entry decisions where practical.
  - Keep current decision names stable.
- Modify: `src/data_agent/agent/method_playbooks.py`
  - Preserve original playbook recommendations, but store a classified shape when trust state is available.
- Modify: `src/data_agent/web/templates/index.html`
  - Rename the right panel conceptually to a session side panel.
  - Add tabs: `当前分析`, `数据与历史`, `产出与导出`.
  - Preserve export and artifact controls in `产出与导出`.
  - Add short `?` help popovers.
- Modify: `src/data_agent/web/static/js/app.js`
  - Add side-panel tab state and Chinese-first status labels.
  - Keep route click-to-fill behavior without auto-submit.
- Modify: `src/data_agent/web/static/css/app.css`
  - Add tab, help, and compact side-panel styles without changing the whole app theme.
- Modify tests:
  - `tests/test_analysis_state_v2.py`
  - `tests/test_route_capabilities.py`
  - `tests/test_trust_view.py`
  - `tests/test_trust_inspector_api.py`
  - `tests/test_trust_inspector_ui.py`
  - `tests/test_analysis_entry.py`
  - `tests/test_method_playbooks.py`

---

### Task 1: Active Scope State

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Test: `tests/test_analysis_state_v2.py`

- [ ] **Step 1: Write failing tests for active scope defaults, persistence, and mutators**

Add these tests near the existing trust-ref tests in `tests/test_analysis_state_v2.py`:

```python
def test_active_scope_defaults_and_roundtrip():
    state = AnalysisSessionState(session_id="s1")

    assert state.active_scope == {
        "active_dataset": "",
        "active_route": "",
        "active_goal": "",
        "active_mode": "consulting",
        "active_turn_id": "",
        "related_ref_ids": {},
        "updated_at": "",
    }

    state.set_active_dataset("orders", related_ref_id="contract_orders")
    restored = AnalysisSessionState.from_dict(state.to_dict(), "s1")

    assert restored.active_scope["active_dataset"] == "orders"
    assert restored.active_scope["active_route"] == ""
    assert restored.active_scope["active_mode"] == "data_loaded"
    assert restored.active_scope["related_ref_ids"] == {
        "dataset_contracts": ["contract_orders"]
    }


def test_active_scope_route_and_consulting_modes():
    state = AnalysisSessionState(session_id="s1")

    state.set_active_dataset("orders")
    state.set_active_route("cohort", goal="分析订单留存", related_ref_id="route_cohort")

    assert state.active_scope["active_dataset"] == "orders"
    assert state.active_scope["active_route"] == "cohort"
    assert state.active_scope["active_goal"] == "分析订单留存"
    assert state.active_scope["active_mode"] == "analysis"
    assert state.active_scope["related_ref_ids"]["route_proposals"] == ["route_cohort"]

    state.set_consulting_mode("讨论留存指标设计")

    assert state.active_scope["active_dataset"] == "orders"
    assert state.active_scope["active_route"] == ""
    assert state.active_scope["active_goal"] == "讨论留存指标设计"
    assert state.active_scope["active_mode"] == "consulting"
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
pytest tests/test_analysis_state_v2.py::test_active_scope_defaults_and_roundtrip tests/test_analysis_state_v2.py::test_active_scope_route_and_consulting_modes -q
```

Expected: FAIL because `AnalysisSessionState` has no `active_scope` or mutator helpers yet.

- [ ] **Step 3: Add active scope state and helpers**

In `src/data_agent/agent/analysis_state.py`, add:

```python
ACTIVE_MODES = {"consulting", "data_loaded", "analysis", "artifact_review"}
```

Add this field to `AnalysisSessionState`:

```python
    active_scope: dict[str, Any] = field(default_factory=lambda: {
        "active_dataset": "",
        "active_route": "",
        "active_goal": "",
        "active_mode": "consulting",
        "active_turn_id": "",
        "related_ref_ids": {},
        "updated_at": "",
    })
```

Add this helper near `_now()`:

```python
def _normalize_active_scope(value: Any) -> dict[str, Any]:
    scope = value if isinstance(value, dict) else {}
    mode = scope.get("active_mode") if scope.get("active_mode") in ACTIVE_MODES else "consulting"
    related = scope.get("related_ref_ids")
    return {
        "active_dataset": scope.get("active_dataset") if isinstance(scope.get("active_dataset"), str) else "",
        "active_route": scope.get("active_route") if isinstance(scope.get("active_route"), str) else "",
        "active_goal": scope.get("active_goal") if isinstance(scope.get("active_goal"), str) else "",
        "active_mode": mode,
        "active_turn_id": scope.get("active_turn_id") if isinstance(scope.get("active_turn_id"), str) else "",
        "related_ref_ids": related if isinstance(related, dict) else {},
        "updated_at": scope.get("updated_at") if isinstance(scope.get("updated_at"), str) else "",
    }
```

Update `from_dict()` and `to_dict()`:

```python
            active_scope=_normalize_active_scope(data.get("active_scope")),
```

```python
            "active_scope": _normalize_active_scope(self.active_scope),
```

Add methods on `AnalysisSessionState`:

```python
    def _active_related_refs(self) -> dict[str, list[str]]:
        refs = self.active_scope.get("related_ref_ids")
        return refs if isinstance(refs, dict) else {}

    def _add_active_ref(self, key: str, ref_id: str | None) -> None:
        if not ref_id:
            return
        refs = self._active_related_refs()
        values = refs.get(key)
        if not isinstance(values, list):
            values = []
        if ref_id not in values:
            values.append(ref_id)
        refs[key] = values
        self.active_scope["related_ref_ids"] = refs

    def set_active_dataset(self, dataset: str, related_ref_id: str | None = None) -> None:
        self.active_scope = _normalize_active_scope(self.active_scope)
        self.active_scope["active_dataset"] = dataset or ""
        self.active_scope["active_route"] = ""
        self.active_scope["active_mode"] = "data_loaded" if dataset else "consulting"
        self.active_scope["updated_at"] = _now()
        self._add_active_ref("dataset_contracts", related_ref_id)

    def set_active_route(
        self,
        route: str,
        goal: str = "",
        dataset: str = "",
        related_ref_id: str | None = None,
    ) -> None:
        self.active_scope = _normalize_active_scope(self.active_scope)
        if dataset:
            self.active_scope["active_dataset"] = dataset
        self.active_scope["active_route"] = route or ""
        self.active_scope["active_goal"] = goal or self.goal or ""
        self.active_scope["active_mode"] = "analysis" if route else self.active_scope["active_mode"]
        self.active_scope["updated_at"] = _now()
        self._add_active_ref("route_proposals", related_ref_id)

    def set_consulting_mode(self, goal: str = "") -> None:
        self.active_scope = _normalize_active_scope(self.active_scope)
        self.active_scope["active_route"] = ""
        self.active_scope["active_goal"] = goal or self.goal or ""
        self.active_scope["active_mode"] = "consulting"
        self.active_scope["updated_at"] = _now()
```

Update `add_dataset_contract_ref()`:

```python
    def add_dataset_contract_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        self.data_state = "data_loaded"
        item = self._upsert_ref(self.dataset_contracts, ref)
        dataset = item.get("dataset")
        if isinstance(dataset, str) and dataset:
            self.set_active_dataset(dataset, related_ref_id=item.get("id"))
        return item
```

- [ ] **Step 4: Run state tests**

Run:

```bash
pytest tests/test_analysis_state_v2.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/analysis_state.py tests/test_analysis_state_v2.py
git commit -m "Add active analysis scope state"
```

---

### Task 2: Route Capability Builder

**Files:**
- Create: `src/data_agent/agent/route_capabilities.py`
- Create: `tests/test_route_capabilities.py`

- [ ] **Step 1: Write failing tests for executable and exploratory tracks**

Create `tests/test_route_capabilities.py`:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.route_capabilities import build_route_capabilities


def test_builds_ready_executable_routes_for_active_dataset():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "orders",
            "supported_analyses": ["cohort", "funnel"],
            "unsupported_analyses": [
                {"type": "user_level_retention", "reason": "missing event history"}
            ],
        },
        {"dataset": "old_sales", "supported_analyses": ["trend"]},
    ]
    state.route_proposals = [
        {
            "id": "route_cohort",
            "dataset": "orders",
            "direction": "cohort",
            "label": "Cohort",
            "reason": "user id and order date exist",
            "limitations": ["descriptive only"],
            "evidence_requirements": ["user_id", "order_date"],
        },
        {"id": "route_old", "dataset": "old_sales", "direction": "trend"},
    ]

    model = build_route_capabilities(state)

    assert model["active_dataset"] == "orders"
    assert [item["route"] for item in model["executable"]] == ["cohort"]
    assert model["executable"][0]["category"] == "ready"
    assert model["executable"][0]["auto_submit"] is False
    assert model["exploratory"] == [
        {
            "id": "explore_orders_user_level_retention",
            "dataset": "orders",
            "analysis": "user_level_retention",
            "label": "user_level_retention",
            "category": "needs_more_data",
            "reason": "missing event history",
            "data_requirements": [],
            "value_if_available": "",
            "prompt": (
                'I want to explore "user_level_retention". Please tell me what data is missing, '
                "why the current data cannot verify it, and what dataset would be needed."
            ),
        }
    ]


def test_cleaning_confirmation_downgrades_executable_route():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.dataset_contracts = [{"dataset": "orders", "supported_analyses": ["cohort"]}]
    state.route_proposals = [
        {
            "id": "route_cohort",
            "dataset": "orders",
            "direction": "cohort",
            "label": "Cohort",
            "evidence_requirements": ["order_date"],
        }
    ]
    state.cleaning_logs = [
        {
            "dataset": "orders",
            "decisions": [
                {
                    "column": "order_date",
                    "decision_type": "needs_confirmation",
                    "impact": "date parsing changed values",
                }
            ],
        }
    ]

    model = build_route_capabilities(state)

    assert model["executable"][0]["category"] == "needs_confirmation"
    assert model["executable"][0]["risk_fields"] == ["order_date"]
    assert "Before running" in model["executable"][0]["prompt"]


def test_consulting_mode_hides_executable_routes_but_keeps_exploratory_context():
    state = AnalysisSessionState(session_id="s1")
    state.active_scope["active_mode"] = "consulting"
    state.last_recommended_paths = [
        {"id": "retention_lifecycle", "title": "Retention lifecycle", "data_requirements": ["user_id"]}
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["exploratory"][0]["category"] == "method_discussion"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_route_capabilities.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `route_capabilities.py`**

Create `src/data_agent/agent/route_capabilities.py` with:

```python
"""Shared dual-track recommendation model for chat and side panel."""

from __future__ import annotations

from typing import Any

from data_agent.agent.trust_view import _hydrate_refs


def build_route_capabilities(state: Any, limit: int = 4) -> dict[str, Any]:
    active_scope = _active_scope(state)
    active_dataset = _text(active_scope.get("active_dataset"))
    active_route = _text(active_scope.get("active_route"))
    active_mode = _text(active_scope.get("active_mode")) or "consulting"
    contracts = _hydrate_refs(_list_attr(state, "dataset_contracts"))
    routes = _hydrate_refs(_list_attr(state, "route_proposals"))
    cleaning_logs = _hydrate_refs(_list_attr(state, "cleaning_logs"))

    executable = []
    if active_mode != "consulting":
        for route in routes:
            if active_dataset and _text(route.get("dataset")) != active_dataset:
                continue
            item = _executable_item(route, cleaning_logs)
            if item:
                executable.append(item)
            if len(executable) >= limit:
                break

    return {
        "active_dataset": active_dataset,
        "active_route": active_route,
        "active_mode": active_mode,
        "executable": executable,
        "exploratory": _exploratory_items(contracts, state, active_dataset, active_mode, limit=limit),
        "counts": {
            "executable": len(executable),
            "exploratory": len(_exploratory_items(contracts, state, active_dataset, active_mode, limit=limit)),
        },
    }
```

Then add helpers in the same file:

```python
def _executable_item(route: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    direction = _text(route.get("direction"))
    if not direction:
        return None
    risk_fields = _required_field_risks(route, cleaning_logs)
    category = "needs_confirmation" if risk_fields else "ready"
    label = _text(route.get("label") or route.get("user_facing_label") or direction)
    return {
        "id": _text(route.get("id")) or f"exec_{_safe_id(_text(route.get('dataset')))}_{_safe_id(direction)}",
        "dataset": _text(route.get("dataset")),
        "route": direction,
        "direction": direction,
        "label": label,
        "category": category,
        "reason": _text(route.get("reason")),
        "limitations": _text_list(route.get("limitations")),
        "evidence_requirements": _text_list(route.get("evidence_requirements")),
        "risk_fields": risk_fields,
        "budget_level": _text(route.get("budget_level")),
        "prompt": _executable_prompt(direction, label, risk_fields),
        "auto_submit": False,
    }
```

```python
def _exploratory_items(
    contracts: list[dict[str, Any]],
    state: Any,
    active_dataset: str,
    active_mode: str,
    limit: int,
) -> list[dict[str, Any]]:
    items = []
    for contract in contracts:
        dataset = _text(contract.get("dataset"))
        if active_dataset and dataset != active_dataset:
            continue
        for unsupported in _raw_list(contract.get("unsupported_analyses")):
            analysis = _text(unsupported.get("type") or unsupported.get("analysis")) if isinstance(unsupported, dict) else _text(unsupported)
            if not analysis:
                continue
            reason = _text(unsupported.get("reason")) if isinstance(unsupported, dict) else ""
            requirements = _text_list(unsupported.get("required_data")) if isinstance(unsupported, dict) else []
            items.append({
                "id": f"explore_{_safe_id(dataset)}_{_safe_id(analysis)}",
                "dataset": dataset,
                "analysis": analysis,
                "label": analysis,
                "category": "needs_more_data",
                "reason": reason,
                "data_requirements": requirements,
                "value_if_available": _text(unsupported.get("value_if_available")) if isinstance(unsupported, dict) else "",
                "prompt": (
                    f'I want to explore "{analysis}". Please tell me what data is missing, '
                    "why the current data cannot verify it, and what dataset would be needed."
                ),
            })
            if len(items) >= limit:
                return items
    if active_mode == "consulting":
        for path in _list_attr(state, "last_recommended_paths")[:limit]:
            title = _text(path.get("title") or path.get("name") or path.get("id"))
            if title:
                items.append({
                    "id": _text(path.get("id")) or f"explore_{_safe_id(title)}",
                    "dataset": "",
                    "analysis": _text(path.get("id")) or title,
                    "label": title,
                    "category": "method_discussion",
                    "reason": _text(path.get("description")),
                    "data_requirements": _text_list(path.get("data_requirements")),
                    "value_if_available": "",
                    "prompt": f'Please discuss the analysis approach for "{title}" and what data would be required.',
                })
    return items[:limit]
```

```python
def _required_field_risks(route: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    route_dataset = _text(route.get("dataset"))
    requirements = set(_text_list(route.get("evidence_requirements")))
    risks = []
    for log in cleaning_logs:
        log_dataset = _text(log.get("dataset"))
        if route_dataset and log_dataset and route_dataset != log_dataset:
            continue
        decisions = log.get("decisions") if isinstance(log.get("decisions"), list) else [log]
        for decision in decisions:
            if not isinstance(decision, dict) or decision.get("decision_type") != "needs_confirmation":
                continue
            column = _text(decision.get("column") or decision.get("field"))
            if column and (not requirements or column in requirements):
                risks.append(column)
    return _dedupe(risks)
```

```python
def _executable_prompt(direction: str, label: str, risk_fields: list[str]) -> str:
    if risk_fields:
        return (
            f'Before running "{label or direction}", please clarify the assumptions for these fields: '
            + ", ".join(risk_fields)
            + ". Explain how the assumption affects the result."
        )
    return (
        f'Please analyze the current active dataset using the "{label or direction}" route. '
        "Explain key findings, evidence, limitations, and avoid claims beyond what the current data supports."
    )
```

```python
def _active_scope(state: Any) -> dict[str, Any]:
    scope = getattr(state, "active_scope", None)
    return scope if isinstance(scope, dict) else {}


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _raw_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _safe_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "item"


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
```

- [ ] **Step 4: Run route capability tests**

Run:

```bash
pytest tests/test_route_capabilities.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/route_capabilities.py tests/test_route_capabilities.py
git commit -m "Add dual-track route capabilities"
```

---

### Task 3: Trust View Active-Scope Filtering

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `tests/test_trust_view.py`
- Modify: `tests/test_trust_inspector_api.py`

- [ ] **Step 1: Write failing trust view tests**

Add to `tests/test_trust_view.py`:

```python
def test_trust_view_exposes_active_scope_counts_and_recommendations():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {"dataset": "old_sales", "row_count": 10, "supported_analyses": ["trend"]},
        {
            "dataset": "orders",
            "row_count": 20,
            "supported_analyses": ["cohort"],
            "unsupported_analyses": [{"type": "user_level_retention", "reason": "missing events"}],
        },
    ]
    state.route_proposals = [
        {"id": "old", "dataset": "old_sales", "direction": "trend"},
        {"id": "new", "dataset": "orders", "direction": "cohort", "label": "Cohort"},
    ]

    view = build_trust_view(state)

    assert view["active_scope"]["active_dataset"] == "orders"
    assert view["scope_counts"]["datasets"] == 2
    assert view["scope_counts"]["routes"] == 2
    assert [dataset["dataset"] for dataset in view["datasets"]] == ["orders"]
    assert [route["direction"] for route in view["routes"]] == ["cohort"]
    assert [route["route"] for route in view["recommendations"]["executable"]] == ["cohort"]
    assert view["recommendations"]["exploratory"][0]["analysis"] == "user_level_retention"


def test_trust_view_consulting_mode_hides_current_routes_but_keeps_history():
    state = AnalysisSessionState(session_id="s1")
    state.active_scope["active_mode"] = "consulting"
    state.route_proposals = [{"id": "route_old", "dataset": "sales", "direction": "trend"}]
    state.last_recommended_paths = [{"id": "metric_overview", "title": "Metric overview"}]

    view = build_trust_view(state)

    assert view["active_scope"]["active_mode"] == "consulting"
    assert view["routes"] == []
    assert view["history"]["routes"][0]["direction"] == "trend"
    assert view["recommendations"]["exploratory"][0]["category"] == "method_discussion"
```

Update empty-view expectations in `tests/test_trust_view.py` and `tests/test_trust_inspector_api.py` to include:

```python
"active_scope": {
    "active_dataset": "",
    "active_route": "",
    "active_goal": "",
    "active_mode": "consulting",
},
"scope_counts": {
    "datasets": 0,
    "routes": 0,
    "risks": 0,
    "hypothesis_sets": 0,
    "artifacts": 0,
},
"recommendations": {"executable": [], "exploratory": [], "counts": {"executable": 0, "exploratory": 0}},
"history": {"datasets": [], "routes": [], "risks": [], "hypotheses": []},
```

- [ ] **Step 2: Run failing trust view tests**

Run:

```bash
pytest tests/test_trust_view.py tests/test_trust_inspector_api.py -q
```

Expected: FAIL because `build_trust_view` has no active scope, recommendations, scope counts, or history.

- [ ] **Step 3: Update `build_trust_view`**

In `src/data_agent/agent/trust_view.py`, import:

```python
from data_agent.agent.route_capabilities import build_route_capabilities
```

Inside `build_trust_view()`, after hydrated refs:

```python
    active_scope = _active_scope(getattr(state, "active_scope", None))
    active_dataset = _text(active_scope.get("active_dataset"))
    active_mode = _text(active_scope.get("active_mode")) or "consulting"
    recommendations = build_route_capabilities(state)
```

Change summary construction:

```python
    all_routes = _route_cards(route_refs)
    all_risks = _risk_items(contracts, cleaning_logs)
    all_datasets = _dataset_summaries(contracts, previews)
    all_hypotheses = _hypothesis_summaries(hypothesis_sets, limit=12)

    datasets = _filter_by_dataset(all_datasets, active_dataset) if active_mode != "consulting" else []
    routes = _route_cards(recommendations.get("executable", []))
    risks = _filter_by_dataset(all_risks, active_dataset) if active_mode != "consulting" else []
    hypotheses = _filter_hypotheses(all_hypotheses, active_scope) if active_mode != "consulting" else []
```

Return additional keys:

```python
        "active_scope": {
            "active_dataset": active_dataset,
            "active_route": _text(active_scope.get("active_route")),
            "active_goal": _text(active_scope.get("active_goal")),
            "active_mode": active_mode,
        },
        "scope_counts": {
            "datasets": len(all_datasets),
            "routes": len(all_routes),
            "risks": len(all_risks),
            "hypothesis_sets": len(all_hypotheses),
            "artifacts": 0,
        },
        "recommendations": recommendations,
        "history": {
            "datasets": all_datasets,
            "routes": all_routes,
            "risks": all_risks,
            "hypotheses": all_hypotheses,
        },
```

Add helpers:

```python
def _active_scope(value: Any) -> dict[str, Any]:
    scope = value if isinstance(value, dict) else {}
    return {
        "active_dataset": _text(scope.get("active_dataset")),
        "active_route": _text(scope.get("active_route")),
        "active_goal": _text(scope.get("active_goal")),
        "active_mode": _text(scope.get("active_mode")) or "consulting",
    }


def _filter_by_dataset(items: list[dict[str, Any]], dataset: str) -> list[dict[str, Any]]:
    if not dataset:
        return items
    return [item for item in items if _text(item.get("dataset")) == dataset]


def _filter_hypotheses(items: list[dict[str, Any]], active_scope: dict[str, Any]) -> list[dict[str, Any]]:
    dataset = _text(active_scope.get("active_dataset"))
    route = _text(active_scope.get("active_route"))
    filtered = items
    if dataset:
        filtered = [item for item in filtered if _text(item.get("dataset")) == dataset]
    if route:
        filtered = [item for item in filtered if _text(item.get("route")) == route]
    return filtered[:3]
```

Update `_empty_view()` with the new keys shown in Step 1.

- [ ] **Step 4: Run trust tests**

Run:

```bash
pytest tests/test_trust_view.py tests/test_trust_inspector_api.py tests/test_route_capabilities.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/trust_view.py tests/test_trust_view.py tests/test_trust_inspector_api.py
git commit -m "Expose active-scope trust recommendations"
```

---

### Task 4: Chat Context Uses The Same Recommendation Source

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/agent/method_playbooks.py`
- Modify: `src/data_agent/agent/analysis_entry.py`
- Modify: `tests/test_method_playbooks.py`
- Modify: `tests/test_analysis_entry.py`
- Modify: `tests/test_prompt_system.py`

- [ ] **Step 1: Write failing tests for compact dual-track summary**

Add to `tests/test_prompt_system.py`:

```python
def test_analysis_state_summary_includes_dual_track_recommendation_counts():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "orders",
            "supported_analyses": ["cohort"],
            "unsupported_analyses": [{"type": "user_level_retention", "reason": "missing events"}],
        }
    ]
    state.route_proposals = [{"id": "route_cohort", "dataset": "orders", "direction": "cohort"}]

    summary = analysis_state_summary(state)

    assert "- active_scope: mode=data_loaded, dataset=orders, route=-" in summary
    assert "- recommendation_tracks: executable=1, exploratory=1" in summary
```

Add to `tests/test_analysis_entry.py`:

```python
def test_entry_decision_uses_active_dataset_for_vague_multi_dataset_routes():
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.route_proposals = [
        {"id": "old", "dataset": "sales", "direction": "trend"},
        {"id": "new", "dataset": "orders", "direction": "cohort"},
    ]

    decision = decide_analysis_entry("please analyze this dataset", _intent("guide_analysis"), state)

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "orders"
    assert decision["route"] == "cohort"
```

Use the existing helper style in `tests/test_analysis_entry.py` for `_intent`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_prompt_system.py::test_analysis_state_summary_includes_dual_track_recommendation_counts tests/test_analysis_entry.py::test_entry_decision_uses_active_dataset_for_vague_multi_dataset_routes -q
```

Expected: FAIL because summary and entry decision still use old session-wide route refs.

- [ ] **Step 3: Update summary and entry decision**

In `analysis_state.py`, import inside `analysis_state_summary()` to avoid circular import:

```python
    try:
        from data_agent.agent.route_capabilities import build_route_capabilities
        recommendation_model = build_route_capabilities(state)
    except Exception:
        recommendation_model = {"executable": [], "exploratory": []}
```

Append compact lines after `data_state`:

```python
    scope = _normalize_active_scope(state.active_scope)
    lines.append(
        "- active_scope: "
        f"mode={scope['active_mode']}, "
        f"dataset={scope['active_dataset'] or '-'}, "
        f"route={scope['active_route'] or '-'}"
    )
    lines.append(
        "- recommendation_tracks: "
        f"executable={len(recommendation_model.get('executable') or [])}, "
        f"exploratory={len(recommendation_model.get('exploratory') or [])}"
    )
```

In `analysis_entry.py`, import:

```python
from data_agent.agent.route_capabilities import build_route_capabilities
```

After blocked and unsupported retention checks, compute:

```python
    capability_model = build_route_capabilities(state)
    executable_routes = capability_model.get("executable") if isinstance(capability_model.get("executable"), list) else []
```

Use `executable_routes` for route inference:

```python
    route = _infer_requested_route(user_input, executable_routes)
    if not route and _text(getattr(intent, "clarity", "")) == "vague" and len(executable_routes) > 1:
        ...
    if not route and executable_routes:
        route = executable_routes[0]
```

Update route field reads to accept `route` or `direction`:

```python
            route=_text(route.get("route") or route.get("direction")),
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_prompt_system.py tests/test_analysis_entry.py tests/test_route_capabilities.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/analysis_state.py src/data_agent/agent/analysis_entry.py tests/test_prompt_system.py tests/test_analysis_entry.py
git commit -m "Unify chat context with route capabilities"
```

---

### Task 5: Session Side Panel Tabs And Chinese Labels

**Files:**
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/css/app.css`
- Modify: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Write failing UI contract tests**

Update `tests/test_trust_inspector_ui.py`:

```python
def test_session_side_panel_tabs_preserve_export_controls():
    html = _index_html()
    js = _app_js()

    assert "sessionSidePanelTab: 'current'" in js
    assert "当前分析" in html
    assert "数据与历史" in html
    assert "产出与导出" in html
    assert "x-show=\"sessionSidePanelTab === 'outputs'\"" in html
    assert "exportConversation('html')" in html
    assert "exportConversation('markdown')" in html
    assert "sessionArtifacts" in html


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
```

Update existing label expectations:

```python
expected_labels = {
    "empty": "空",
    "ready": "就绪",
    "ready_with_warnings": "有提醒",
    "pass_with_downgrades": "有降级",
    "fail": "失败",
    "blocked": "阻塞",
    "warning": "提醒",
    "unknown": "未知",
}
```

- [ ] **Step 2: Run failing UI tests**

Run:

```bash
pytest tests/test_trust_inspector_ui.py -q
```

Expected: FAIL because tabs, Chinese labels, and help text are not implemented.

- [ ] **Step 3: Add app state and helpers**

In `src/data_agent/web/static/js/app.js`, near existing trust state:

```javascript
        sessionSidePanelTab: 'current',
        trustHelpOpen: '',
```

Add methods:

```javascript
        trustHelpText(topic) {
            const help = {
                routes: '这是什么：当前数据结构支持的分析方向。为什么重要：它基于字段、粒度和风险判断，表示现在较适合继续的路径。你可以怎么做：点击后会填入输入框，你仍可以编辑。',
                risks: '这是什么：当前分析可能受到的数据质量、字段缺失或清洗决策影响。为什么重要：风险会限制结论强度。你可以怎么做：先确认字段或补充数据。',
                hypotheses: '这是什么：系统为分析保留主要解释、替代解释和基准解释。为什么重要：它帮助避免只验证单一结论。你可以怎么做：查看哪些假设有证据支持。',
                outputs: '这是什么：本会话生成的报告、图表和导出入口。为什么重要：产出不会被分析建议挤到下方。你可以怎么做：导出会话或打开已生成文件。'
            };
            return help[topic] || '';
        },
```

Update `trustStatusLabel()` labels to Chinese:

```javascript
            const labels = {
                empty: '空',
                ready: '就绪',
                ready_with_warnings: '有提醒',
                pass: '通过',
                pass_with_downgrades: '有降级',
                fail: '失败',
                blocked: '阻塞',
                warning: '提醒',
                proposed: '待验证',
                supported: '支持',
                inconclusive: '不确定',
                weakened: '减弱',
                unsupported_by_data: '数据不支持',
                unknown: '未知'
            };
```

- [ ] **Step 4: Refactor right panel markup into tabs**

In `src/data_agent/web/templates/index.html`, keep the existing `trust-inspector-panel` class for compatibility, but change the visible title to `会话侧栏`. Add tab buttons below the header:

```html
<div class="session-side-tabs" x-show="!trustInspectorCollapsed">
    <button type="button" class="session-side-tab" :class="{ 'is-active': sessionSidePanelTab === 'current' }" @click="sessionSidePanelTab = 'current'">当前分析</button>
    <button type="button" class="session-side-tab" :class="{ 'is-active': sessionSidePanelTab === 'history' }" @click="sessionSidePanelTab = 'history'">数据与历史</button>
    <button type="button" class="session-side-tab" :class="{ 'is-active': sessionSidePanelTab === 'outputs' }" @click="sessionSidePanelTab = 'outputs'">产出与导出</button>
</div>
```

Wrap current dataset/routes/hypotheses/risks/verification sections:

```html
<div x-show="sessionSidePanelTab === 'current'" class="space-y-5">
    ...
</div>
```

Move existing export conversation and artifact list sections into:

```html
<div x-show="sessionSidePanelTab === 'outputs'" class="space-y-5">
    ...
</div>
```

Add a history tab:

```html
<div x-show="sessionSidePanelTab === 'history'" class="space-y-5">
    <section class="trust-section">
        <h3 class="text-xs font-semibold text-stone-600 dark:text-stone-300">数据与历史</h3>
        <template x-for="(dataset, di) in ((trustView && trustView.history && trustView.history.datasets) || [])" :key="dataset.dataset || di">
            <div class="trust-data-item">
                <p class="text-xs font-medium text-stone-700 dark:text-stone-300 truncate" x-text="dataset.dataset"></p>
                <p class="text-[10px] text-stone-400" x-text="`${dataset.rows || 0} 行 · ${dataset.columns || 0} 列`"></p>
            </div>
        </template>
    </section>
</div>
```

Change route heading to:

```html
<h3 class="text-xs font-semibold text-stone-600 dark:text-stone-300">可直接分析</h3>
```

Add help buttons beside section titles:

```html
<button type="button" class="trust-help-btn" @click="trustHelpOpen = trustHelpOpen === 'routes' ? '' : 'routes'">?</button>
<p x-show="trustHelpOpen === 'routes'" class="trust-help-popover" x-text="trustHelpText('routes')"></p>
```

- [ ] **Step 5: Add CSS**

In `src/data_agent/web/static/css/app.css`:

```css
.session-side-tabs {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 4px;
    padding: 8px 12px;
    border-bottom: 1px solid rgb(231 229 228);
}

.dark .session-side-tabs {
    border-bottom-color: rgb(41 37 36);
}

.session-side-tab {
    min-height: 28px;
    border-radius: 6px;
    font-size: 11px;
    color: rgb(120 113 108);
}

.session-side-tab.is-active {
    background: rgb(245 245 244);
    color: rgb(41 37 36);
    font-weight: 600;
}

.dark .session-side-tab.is-active {
    background: rgb(41 37 36);
    color: rgb(231 229 228);
}

.trust-help-btn {
    width: 18px;
    height: 18px;
    border-radius: 999px;
    font-size: 11px;
    color: rgb(120 113 108);
}

.trust-help-btn:hover {
    background: rgb(245 245 244);
}

.trust-help-popover {
    margin-top: 6px;
    font-size: 11px;
    line-height: 1.5;
    color: rgb(87 83 78);
    overflow-wrap: anywhere;
}
```

- [ ] **Step 6: Run UI tests**

Run:

```bash
pytest tests/test_trust_inspector_ui.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/data_agent/web/static/js/app.js src/data_agent/web/templates/index.html src/data_agent/web/static/css/app.css tests/test_trust_inspector_ui.py
git commit -m "Add session side panel tabs"
```

---

### Task 6: Multi-Upload And Regression Fixtures

**Files:**
- Modify: `tests/test_trust_workflow_runtime.py`
- Modify: `tests/test_trustworthy_load_data_integration.py`
- Modify: `tests/test_trust_view.py`

- [ ] **Step 1: Add multi-upload active dataset regression**

Add to `tests/test_trustworthy_load_data_integration.py`:

```python
def test_second_dataset_becomes_active_without_deleting_first_dataset(tmp_path):
    state = AnalysisSessionState(session_id="multi_upload")

    first = state.add_dataset_contract_ref({"id": "contract_sales", "dataset": "sales"})
    second = state.add_dataset_contract_ref({"id": "contract_orders", "dataset": "orders"})

    assert first["dataset"] == "sales"
    assert second["dataset"] == "orders"
    assert [item["dataset"] for item in state.dataset_contracts] == ["sales", "orders"]
    assert state.active_scope["active_dataset"] == "orders"
    assert state.active_scope["active_mode"] == "data_loaded"
```

- [ ] **Step 2: Add 2 executable + 1 exploratory mismatch regression**

Add to `tests/test_trust_view.py`:

```python
def test_chat_three_panel_two_pattern_is_classified_not_conflicting():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "card_orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "card_orders",
            "supported_analyses": ["cohort", "funnel"],
            "unsupported_analyses": [
                {"type": "user_level_retention", "reason": "缺少用户级事件历史"}
            ],
        }
    ]
    state.route_proposals = [
        {"id": "route_cohort", "dataset": "card_orders", "direction": "cohort"},
        {"id": "route_funnel", "dataset": "card_orders", "direction": "funnel"},
    ]

    view = build_trust_view(state)

    assert len(view["recommendations"]["executable"]) == 2
    assert len(view["routes"]) == 2
    assert view["recommendations"]["exploratory"][0]["analysis"] == "user_level_retention"
    assert view["recommendations"]["exploratory"][0]["category"] == "needs_more_data"
```

- [ ] **Step 3: Run regression tests**

Run:

```bash
pytest tests/test_trustworthy_load_data_integration.py tests/test_trust_view.py tests/test_trust_workflow_runtime.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_trustworthy_load_data_integration.py tests/test_trust_view.py tests/test_trust_workflow_runtime.py
git commit -m "Add active-scope recommendation regressions"
```

---

### Task 7: Full Verification

**Files:**
- No source edits expected unless verification exposes a real issue.

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
pytest tests/test_analysis_state_v2.py tests/test_route_capabilities.py tests/test_trust_view.py tests/test_analysis_entry.py tests/test_prompt_system.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Web contract suite**

Run:

```bash
pytest tests/test_trust_inspector_api.py tests/test_trust_inspector_ui.py tests/test_web_gui.py tests/test_web_overhaul.py -q
```

Expected: PASS.

- [ ] **Step 3: Run trust workflow regression group**

Run:

```bash
pytest tests/test_trust_contracts.py tests/test_trust_workflow_runtime.py tests/test_trustworthy_workflow_mvp.py tests/test_trustworthy_load_data_integration.py -q
```

Expected: PASS.

- [ ] **Step 4: Inspect git status**

Run:

```bash
git status --short
```

Expected: only pre-existing untracked files remain. No modified tracked files should be left after commits.

---

## Self-Review

Spec coverage:

- Active scope state and update rules are covered by Tasks 1, 3, 4, and 6.
- Dual-track executable/exploratory recommendation rules are covered by Task 2 and Task 6.
- Chat and side panel source unification is covered by Tasks 3 and 4.
- Side panel tabs, Chinese labels, help, and export preservation are covered by Task 5.
- Multi-upload and consulting mode are covered by Tasks 2, 3, and 6.
- Context-budget compactness is covered by Task 4.

Placeholder scan:

- This plan intentionally avoids unfinished-marker language and vague "handle edge cases" instructions.
- Any implementation step that changes code includes concrete target code or exact expected behavior.

Type consistency:

- `active_scope.active_dataset`, `active_scope.active_route`, `active_scope.active_goal`, and `active_scope.active_mode` are used consistently across state, route capabilities, and trust view.
- Recommendation tracks consistently use `executable` and `exploratory`.
- Executable route items include both `route` and `direction` for compatibility with existing route-card code.
