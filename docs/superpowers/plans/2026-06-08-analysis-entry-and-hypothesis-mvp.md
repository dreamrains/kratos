# Analysis Entry And Hypothesis MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic analysis entry decision layer and a small hypothesis MVP that turns each supported analysis request into explicit, evidence-bound competing hypotheses.

**Architecture:** Add focused backend modules under `data_agent.agent`: one module decides whether a user request can proceed from current trust state, one module owns hypothesis records and artifact persistence, and existing runtime glue calls them at safe points. Store compact refs in `AnalysisSessionState`, persist full hypothesis details as JSON artifacts, and hydrate refs only in view/synthesis helpers.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing `AnalysisSessionState`, `TurnIntent`, `trust_view`, `trust_workflow_runtime`, `verification`, and session artifact helpers.

---

## Scope

This plan implements the first useful Phase 2 loop:

```text
user request + trust state
-> analysis entry decision
-> hypothesis set with competing explanations
-> evidence-to-hypothesis status update
-> compact Trust Inspector visibility
-> synthesis context helper
```

Out of scope:

- no new statistical algorithms
- no LLM-based hypothesis generation in the MVP
- no full hypothesis editor
- no auto-run from Trust Inspector
- no rich hypothesis tree UI
- no domain playbook library

## File Structure

- Create: `src/data_agent/agent/analysis_entry.py`
  - Responsibility: deterministic request gating from user intent and hydrated trust state.
  - Public functions:
    - `decide_analysis_entry(user_input, intent, state) -> dict`
  - Private helpers:
    - `_hydrate_refs(items)`
    - `_infer_requested_route(user_input, routes)`
    - `_route_options(routes)`
    - `_required_field_risks(route, cleaning_logs)`

- Create: `tests/test_analysis_entry.py`
  - Unit tests for supported route, vague route choice, unsupported retention, cleaning confirmation, and blocked quality.

- Modify: `src/data_agent/agent/analysis_state.py`
  - Add `hypothesis_sets: list[dict[str, Any]]`.
  - Include it in `from_dict()` and `to_dict()`.
  - Add `add_hypothesis_set_ref(ref)`.

- Create: `src/data_agent/agent/hypotheses.py`
  - Responsibility: deterministic hypothesis generation, persistence, hydration, and evidence status updates.
  - Public functions:
    - `build_hypothesis_set(user_input, entry_decision, state) -> dict`
    - `persist_hypothesis_set(session_id, hypothesis_set) -> dict`
    - `hydrate_hypothesis_refs(refs) -> list[dict]`
    - `update_hypotheses_from_evidence(hypothesis_set, evidence_records) -> dict`
  - Private helpers:
    - `_route_templates(route)`
    - `_field_roles(contract)`
    - `_verification_level(requirements, contract)`
    - `_status_summary(hypotheses)`
    - `_artifact_path(session_id, hypothesis_set_id)`

- Create: `tests/test_hypotheses.py`
  - Unit tests for generation, verifiability, persistence, hydration, and status update.

- Modify: `src/data_agent/agent/trust_workflow_runtime.py`
  - Add `maybe_create_hypothesis_set(user_input, intent, state) -> dict | None`.
  - Call `decide_analysis_entry(...)` and `build_hypothesis_set(...)`.
  - Persist compact refs through `state.add_hypothesis_set_ref(...)`.
  - Keep failures non-fatal.

- Modify: `tests/test_trust_workflow_runtime.py`
  - Add runtime tests for creating one hypothesis set and skipping duplicates.

- Modify: `src/data_agent/agent/trust_view.py`
  - Include a compact `hypotheses` section in the trust view.
  - Hydrate hypothesis refs to show status counts and top 2 claims.

- Modify: `tests/test_trust_view.py`
  - Add view-model tests for compact hypothesis display and malformed refs.

- Modify: `src/data_agent/web/static/js/app.js`
  - Render hypothesis summary if returned by `/trust`.

- Modify: `src/data_agent/web/templates/index.html`
  - Add a compact Hypotheses section inside Trust Inspector.

- Modify: `tests/test_trust_inspector_ui.py`
  - Add structure tests for the Hypotheses section.

- Optional later integration:
  - Modify: `src/data_agent/agent/loop.py`
    - Call `maybe_create_hypothesis_set(...)` after intent refinement and before synthesis policy injection.
  - Add focused loop tests only after helper behavior is stable.

---

### Task 1: Analysis Entry Decision Layer

**Files:**
- Create: `src/data_agent/agent/analysis_entry.py`
- Create: `tests/test_analysis_entry.py`

- [ ] **Step 1: Write failing tests for deterministic entry decisions**

Create `tests/test_analysis_entry.py`:

```python
from data_agent.agent.analysis_entry import decide_analysis_entry
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent


def _intent(intent_type="directed_analysis", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "clear",
        "data_state": "data_loaded",
        "analysis_stage": "execute",
        "recommended_action": "run_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


def _state():
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.dataset_contracts = [{
        "id": "duc_sales",
        "dataset": "sales",
        "quality": {"status": "ready", "score": 96},
        "field_roles": {
            "date": ["date"],
            "metrics": ["revenue", "orders"],
            "dimensions": ["channel"],
            "ids": ["user_id"],
        },
        "supported_analyses": ["trend", "period_compare", "dimension_decomposition"],
        "unsupported_analyses": [],
    }]
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "limitations": ["Descriptive trend only"],
            "evidence_requirements": ["date", "metric"],
        },
        {
            "id": "route_compare",
            "dataset": "sales",
            "direction": "period_compare",
            "limitations": ["Requires comparable periods"],
            "evidence_requirements": ["date", "metric", "period coverage"],
        },
    ]
    return state


def test_supported_trend_request_returns_direct_analysis():
    decision = decide_analysis_entry("show revenue trend", _intent(), _state())

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "sales"
    assert decision["route"] == "trend"
    assert decision["confidence"] == "medium"
    assert decision["required_user_action"] == ""
    assert decision["limitations"] == ["Descriptive trend only"]
    assert decision["evidence_requirements"] == ["date", "metric"]


def test_vague_request_with_multiple_routes_returns_clarify_intent():
    vague = _intent(
        "intent_negotiation",
        clarity="vague",
        analysis_stage="discover",
        recommended_action="guide_analysis",
    )

    decision = decide_analysis_entry("help me analyze this data", vague, _state())

    assert decision["decision"] == "clarify_intent"
    assert decision["route"] == ""
    assert decision["required_user_action"] == "choose_analysis_route"
    assert decision["route_options"] == [
        {"direction": "trend", "label": "trend", "dataset": "sales"},
        {"direction": "period_compare", "label": "period_compare", "dataset": "sales"},
    ]


def test_unsupported_retention_request_returns_request_data():
    state = _state()
    state.dataset_contracts[0]["unsupported_analyses"] = [
        {"type": "user_level_retention", "reason": "aggregate grain and missing user id"}
    ]

    decision = decide_analysis_entry("analyze cohort retention", _intent(), state)

    assert decision["decision"] == "request_data"
    assert decision["route"] == ""
    assert decision["required_user_action"] == "provide_user_level_retention_data"
    assert decision["limitations"] == ["aggregate grain and missing user id"]


def test_cleaning_confirmation_on_required_field_returns_clarify_intent():
    state = _state()
    state.cleaning_logs = [{
        "dataset": "sales",
        "decisions": [{
            "column": "date",
            "decision_type": "needs_confirmation",
            "impact": "Date parsing changed the original column type",
        }],
    }]

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert decision["required_user_action"] == "confirm_cleaning_decision"
    assert decision["risk_fields"] == ["date"]


def test_blocked_quality_returns_blocked():
    state = _state()
    state.dataset_contracts[0]["quality"] = {
        "status": "blocked",
        "block_issues": ["date column has no usable values"],
    }

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "blocked"
    assert decision["required_user_action"] == "resolve_data_quality"
    assert decision["limitations"] == ["date column has no usable values"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_analysis_entry.py -q
```

Expected:

- FAIL because `data_agent.agent.analysis_entry` does not exist.

- [ ] **Step 3: Implement minimal decision module**

Create `src/data_agent/agent/analysis_entry.py`:

```python
"""Deterministic analysis entry decisions from user intent and trust state."""

from __future__ import annotations

from typing import Any

from data_agent.agent.trust_view import _hydrate_refs


_RETENTION_KEYWORDS = ("retention", "cohort", "留存")
_ROUTE_KEYWORDS = {
    "trend": ("trend", "time series", "趋势", "走势"),
    "period_compare": ("period", "compare", "comparison", "环比", "同比", "对比"),
    "dimension_decomposition": ("segment", "dimension", "breakdown", "分维", "归因"),
}


def decide_analysis_entry(user_input: str, intent: Any, state: Any) -> dict[str, Any]:
    contracts = _hydrate_refs(_list_attr(state, "dataset_contracts"))
    routes = _hydrate_refs(_list_attr(state, "route_proposals"))
    cleaning_logs = _hydrate_refs(_list_attr(state, "cleaning_logs"))

    blocked = _blocked_contract(contracts)
    if blocked:
        return _decision(
            "blocked",
            dataset=_text(blocked.get("dataset")),
            reason="Data quality blocks formal analysis.",
            required_user_action="resolve_data_quality",
            limitations=_quality_blocks(blocked),
        )

    unsupported_retention = _unsupported_retention(contracts)
    if _mentions_retention(user_input) and unsupported_retention:
        return _decision(
            "request_data",
            reason="The loaded data cannot support user-level retention analysis.",
            required_user_action="provide_user_level_retention_data",
            limitations=_unsupported_reasons(unsupported_retention),
        )

    route = _infer_requested_route(user_input, routes)
    if not route and _text(getattr(intent, "clarity", "")) == "vague" and len(routes) > 1:
        return _decision(
            "clarify_intent",
            reason="Multiple data-supported analysis routes are available.",
            required_user_action="choose_analysis_route",
            route_options=_route_options(routes),
        )
    if not route and routes:
        route = routes[0]

    if route:
        risk_fields = _required_field_risks(route, cleaning_logs)
        if risk_fields:
            return _decision(
                "clarify_intent",
                dataset=_text(route.get("dataset")),
                route=_text(route.get("direction")),
                reason="A required field has a cleaning decision that needs confirmation.",
                required_user_action="confirm_cleaning_decision",
                risk_fields=risk_fields,
                limitations=_text_list(route.get("limitations")),
                evidence_requirements=_text_list(route.get("evidence_requirements")),
            )
        return _decision(
            "direct_analysis",
            dataset=_text(route.get("dataset")),
            route=_text(route.get("direction")),
            reason="The request matches a supported data route.",
            confidence="medium",
            limitations=_text_list(route.get("limitations")),
            evidence_requirements=_text_list(route.get("evidence_requirements")),
        )

    return _decision(
        "clarify_intent",
        reason="No supported analysis route can be selected deterministically.",
        required_user_action="clarify_analysis_goal",
    )


def _decision(decision: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "decision": decision,
        "reason": "",
        "dataset": "",
        "route": "",
        "confidence": "low",
        "required_user_action": "",
        "limitations": [],
        "evidence_requirements": [],
        "route_options": [],
        "risk_fields": [],
    }
    payload.update(overrides)
    return payload


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _blocked_contract(contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for contract in contracts:
        quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
        if quality.get("status") == "blocked":
            return contract
    return None


def _quality_blocks(contract: dict[str, Any]) -> list[str]:
    quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
    return _text_list(quality.get("block_issues"))


def _unsupported_retention(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for contract in contracts:
        for unsupported in contract.get("unsupported_analyses") or []:
            if isinstance(unsupported, dict) and unsupported.get("type") == "user_level_retention":
                matches.append(unsupported)
    return matches


def _unsupported_reasons(items: list[dict[str, Any]]) -> list[str]:
    return [_text(item.get("reason")) for item in items if _text(item.get("reason"))]


def _mentions_retention(user_input: str) -> bool:
    text = (user_input or "").lower()
    return any(keyword in text for keyword in _RETENTION_KEYWORDS)


def _infer_requested_route(user_input: str, routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = (user_input or "").lower()
    for route in routes:
        direction = _text(route.get("direction"))
        keywords = _ROUTE_KEYWORDS.get(direction, (direction,))
        if any(keyword and keyword in text for keyword in keywords):
            return route
    return None


def _route_options(routes: list[dict[str, Any]]) -> list[dict[str, str]]:
    options = []
    for route in routes[:4]:
        direction = _text(route.get("direction"))
        options.append({
            "direction": direction,
            "label": _text(route.get("label") or route.get("user_facing_label") or direction),
            "dataset": _text(route.get("dataset")),
        })
    return options


def _required_field_risks(route: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    requirements = set(_text_list(route.get("evidence_requirements")))
    risky_fields = []
    for log in cleaning_logs:
        if _text(log.get("dataset")) and _text(route.get("dataset")) and _text(log.get("dataset")) != _text(route.get("dataset")):
            continue
        for decision in log.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            if decision.get("decision_type") != "needs_confirmation":
                continue
            column = _text(decision.get("column") or decision.get("field"))
            if column and (column in requirements or _route_requires_field_kind(route, column)):
                risky_fields.append(column)
    return _dedupe(risky_fields)


def _route_requires_field_kind(route: dict[str, Any], column: str) -> bool:
    requirements = set(_text_list(route.get("evidence_requirements")))
    direction = _text(route.get("direction"))
    if column.lower() == "date" and ("date" in requirements or direction in {"trend", "period_compare"}):
        return True
    return False


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


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

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_analysis_entry.py -q
```

Expected:

- PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/data_agent/agent/analysis_entry.py tests/test_analysis_entry.py
git commit -m "Add deterministic analysis entry decisions"
```

---

### Task 2: Hypothesis State Refs

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `tests/test_analysis_state_v2.py`

- [ ] **Step 1: Write failing state persistence test**

Append to `tests/test_analysis_state_v2.py`:

```python
from data_agent.agent.analysis_state import AnalysisSessionState


def test_hypothesis_set_refs_round_trip_in_analysis_state():
    state = AnalysisSessionState(session_id="hyp_state")
    stored = state.add_hypothesis_set_ref({
        "id": "hyps_sales_trend",
        "dataset": "sales",
        "route": "trend",
        "count": 3,
        "status_summary": {"proposed": 3},
        "artifact_path": "sessions/hyp_state/tool_outputs/hypotheses_sales_trend.json",
    })

    assert stored["id"] == "hyps_sales_trend"

    restored = AnalysisSessionState.from_dict(state.to_dict(), "hyp_state")

    assert restored.hypothesis_sets == [{
        "id": "hyps_sales_trend",
        "dataset": "sales",
        "route": "trend",
        "count": 3,
        "status_summary": {"proposed": 3},
        "artifact_path": "sessions/hyp_state/tool_outputs/hypotheses_sales_trend.json",
        "created_at": stored["created_at"],
    }]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_analysis_state_v2.py::test_hypothesis_set_refs_round_trip_in_analysis_state -q
```

Expected:

- FAIL because `add_hypothesis_set_ref` and `hypothesis_sets` do not exist.

- [ ] **Step 3: Add state field and ref method**

Modify `src/data_agent/agent/analysis_state.py`:

```python
hypothesis_sets: list[dict[str, Any]] = field(default_factory=list)
```

In `from_dict()` add:

```python
hypothesis_sets=list(data.get("hypothesis_sets") or []),
```

In `to_dict()` add:

```python
"hypothesis_sets": self.hypothesis_sets,
```

Add method near other trust ref methods:

```python
def add_hypothesis_set_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
    return self._upsert_ref(self.hypothesis_sets, ref)
```

- [ ] **Step 4: Run state tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_analysis_state_v2.py -q
```

Expected:

- PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/data_agent/agent/analysis_state.py tests/test_analysis_state_v2.py
git commit -m "Add hypothesis refs to analysis state"
```

---

### Task 3: Hypothesis Generation And Persistence

**Files:**
- Create: `src/data_agent/agent/hypotheses.py`
- Create: `tests/test_hypotheses.py`

- [ ] **Step 1: Write failing hypothesis generation tests**

Create `tests/test_hypotheses.py`:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.hypotheses import build_hypothesis_set


def _state():
    state = AnalysisSessionState(session_id="hyp_tests", data_state="data_loaded")
    state.dataset_contracts = [{
        "id": "duc_sales",
        "dataset": "sales",
        "grain": "daily_aggregate",
        "field_roles": {
            "date": ["date"],
            "metrics": ["revenue", "orders"],
            "rate_metrics": ["conversion_rate"],
            "dimensions": ["channel"],
            "ids": [],
        },
        "quality": {"status": "ready", "score": 96},
    }]
    return state


def test_period_compare_generates_competing_hypotheses_with_requirements():
    entry = {
        "decision": "direct_analysis",
        "dataset": "sales",
        "route": "period_compare",
        "evidence_requirements": ["date", "metric", "period coverage"],
    }

    hypothesis_set = build_hypothesis_set("why did revenue change?", entry, _state())

    assert hypothesis_set["dataset"] == "sales"
    assert hypothesis_set["route"] == "period_compare"
    assert len(hypothesis_set["hypotheses"]) == 4
    assert [item["status"] for item in hypothesis_set["hypotheses"]] == [
        "proposed",
        "proposed",
        "proposed",
        "proposed",
    ]
    assert hypothesis_set["hypotheses"][0]["verification_level"] == "verifiable"
    assert hypothesis_set["hypotheses"][0]["evidence_requirements"][0] == {
        "kind": "metric",
        "field": "revenue",
        "required": True,
    }
    assert "alternative" in hypothesis_set["hypotheses"][1]["tags"]
    assert "baseline" in hypothesis_set["hypotheses"][-1]["tags"]


def test_retention_hypothesis_is_not_verifiable_without_user_grain():
    entry = {
        "decision": "request_data",
        "dataset": "sales",
        "route": "user_level_retention",
        "limitations": ["aggregate grain and missing user IDs"],
    }

    hypothesis_set = build_hypothesis_set("analyze retention", entry, _state())

    assert len(hypothesis_set["hypotheses"]) == 1
    assert hypothesis_set["hypotheses"][0]["status"] == "unsupported_by_data"
    assert hypothesis_set["hypotheses"][0]["verification_level"] == "not_verifiable"
    assert hypothesis_set["status_summary"] == {"unsupported_by_data": 1}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_hypotheses.py -q
```

Expected:

- FAIL because `data_agent.agent.hypotheses` does not exist.

- [ ] **Step 3: Implement deterministic hypothesis generation**

Create `src/data_agent/agent/hypotheses.py` with:

```python
"""Deterministic hypothesis records for adversarial analysis checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from data_agent.config import get_config
from data_agent.agent.trust_view import _hydrate_refs


def build_hypothesis_set(user_input: str, entry_decision: dict[str, Any], state: Any) -> dict[str, Any]:
    dataset = _text(entry_decision.get("dataset")) or _first_dataset(state)
    route = _text(entry_decision.get("route"))
    contracts = _hydrate_refs(_list_attr(state, "dataset_contracts"))
    contract = _contract_for_dataset(contracts, dataset)
    hypotheses = _route_hypotheses(user_input, dataset, route, contract, entry_decision)
    set_id = _stable_id("hyps", {"dataset": dataset, "route": route, "claims": [h["claim"] for h in hypotheses]})
    return {
        "id": set_id,
        "dataset": dataset,
        "route": route,
        "source_decision": entry_decision,
        "hypotheses": hypotheses,
        "status_summary": _status_summary(hypotheses),
    }


def persist_hypothesis_set(session_id: str, hypothesis_set: dict[str, Any]) -> dict[str, Any]:
    path = _artifact_path(session_id, _text(hypothesis_set.get("id")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hypothesis_set, ensure_ascii=False, indent=2), encoding="utf-8")
    hypotheses = hypothesis_set.get("hypotheses") if isinstance(hypothesis_set.get("hypotheses"), list) else []
    return {
        "id": hypothesis_set.get("id"),
        "dataset": hypothesis_set.get("dataset"),
        "route": hypothesis_set.get("route"),
        "count": len([item for item in hypotheses if isinstance(item, dict)]),
        "status_summary": hypothesis_set.get("status_summary") or {},
        "artifact_path": str(path),
    }


def hydrate_hypothesis_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _hydrate_refs(refs)


def update_hypotheses_from_evidence(
    hypothesis_set: dict[str, Any],
    evidence_records: list[dict[str, Any]],
) -> dict[str, Any]:
    updated = dict(hypothesis_set)
    hypotheses = []
    for hypothesis in hypothesis_set.get("hypotheses") or []:
        if not isinstance(hypothesis, dict):
            continue
        item = dict(hypothesis)
        support = _matching_evidence(item, evidence_records)
        item["supporting_evidence_ids"] = [record["id"] for record in support if record.get("id")]
        if item.get("status") != "unsupported_by_data":
            if support:
                item["status"] = "supported"
            elif item.get("verification_level") == "not_verifiable":
                item["status"] = "unsupported_by_data"
            else:
                item["status"] = "inconclusive"
        hypotheses.append(item)
    updated["hypotheses"] = hypotheses
    updated["status_summary"] = _status_summary(hypotheses)
    return updated


def _route_hypotheses(
    user_input: str,
    dataset: str,
    route: str,
    contract: dict[str, Any],
    entry_decision: dict[str, Any],
) -> list[dict[str, Any]]:
    if route == "user_level_retention" or entry_decision.get("decision") == "request_data":
        return [_hypothesis(
            dataset,
            route or "user_level_retention",
            "The requested retention pattern requires user-level event history.",
            [{"kind": "id", "field": "user_id", "required": True}],
            "not_verifiable",
            status="unsupported_by_data",
            limitations=_text_list(entry_decision.get("limitations")),
            tags=["unsupported"],
        )]

    metric = _first_role(contract, "metrics") or _first_role(contract, "rate_metrics") or "metric"
    rate = _first_role(contract, "rate_metrics")
    date = _first_role(contract, "date") or "date"
    dimension = _first_role(contract, "dimensions")

    base_requirements = [
        {"kind": "metric", "field": metric, "required": True},
        {"kind": "time_comparison", "field": date, "required": route in {"trend", "period_compare"}},
    ]
    hypotheses = [
        _hypothesis(
            dataset,
            route,
            f"{metric} changed because the primary metric moved across the selected time window.",
            base_requirements,
            _verification_level(base_requirements, contract),
            tags=["primary"],
        )
    ]
    if rate:
        req = [
            {"kind": "rate_metric", "field": rate, "required": True},
            {"kind": "time_comparison", "field": date, "required": True},
        ]
        hypotheses.append(_hypothesis(
            dataset,
            route,
            f"{metric} changed because {rate} changed.",
            req,
            _verification_level(req, contract),
            tags=["alternative"],
        ))
    if dimension:
        req = [
            {"kind": "metric", "field": metric, "required": True},
            {"kind": "segment", "field": dimension, "required": True},
        ]
        hypotheses.append(_hypothesis(
            dataset,
            route,
            f"{metric} changed because the mix across {dimension} changed.",
            req,
            _verification_level(req, contract),
            tags=["alternative"],
        ))
    hypotheses.append(_hypothesis(
        dataset,
        route,
        f"The observed {metric} movement may reflect seasonality, sampling, or random fluctuation.",
        base_requirements,
        _verification_level(base_requirements, contract),
        tags=["baseline"],
    ))
    return hypotheses[:4]


def _hypothesis(
    dataset: str,
    route: str,
    claim: str,
    requirements: list[dict[str, Any]],
    verification_level: str,
    *,
    status: str = "proposed",
    limitations: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": _stable_id("hyp", {"dataset": dataset, "route": route, "claim": claim}),
        "dataset": dataset,
        "route": route,
        "claim": claim,
        "status": status,
        "verification_level": verification_level,
        "evidence_requirements": requirements,
        "supporting_evidence_ids": [],
        "conflicting_evidence_ids": [],
        "limitations": limitations or [],
        "tags": tags or [],
    }


def _verification_level(requirements: list[dict[str, Any]], contract: dict[str, Any]) -> str:
    available = _available_fields(contract)
    required = [req for req in requirements if req.get("required")]
    missing = [req for req in required if _text(req.get("field")) not in available]
    if not missing:
        return "verifiable"
    if len(missing) < len(required):
        return "partially_verifiable"
    return "not_verifiable"


def _matching_evidence(hypothesis: dict[str, Any], evidence_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claim_tokens = set(_text(hypothesis.get("claim")).lower().split())
    matches = []
    for record in evidence_records:
        if not isinstance(record, dict):
            continue
        text = _text(record.get("claim") or record.get("summary")).lower()
        if claim_tokens and len(claim_tokens & set(text.split())) >= 3:
            matches.append(record)
    return matches


def _status_summary(hypotheses: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for hypothesis in hypotheses:
        status = _text(hypothesis.get("status"))
        if status:
            summary[status] = summary.get(status, 0) + 1
    return summary


def _artifact_path(session_id: str, hypothesis_set_id: str) -> Path:
    return get_config().sessions_resolved / session_id / "tool_outputs" / f"{hypothesis_set_id}.json"


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _contract_for_dataset(contracts: list[dict[str, Any]], dataset: str) -> dict[str, Any]:
    for contract in contracts:
        if _text(contract.get("dataset")) == dataset:
            return contract
    return contracts[0] if contracts else {}


def _first_dataset(state: Any) -> str:
    contracts = _list_attr(state, "dataset_contracts")
    return _text(contracts[0].get("dataset")) if contracts else ""


def _first_role(contract: dict[str, Any], role: str) -> str:
    roles = contract.get("field_roles") if isinstance(contract.get("field_roles"), dict) else {}
    values = roles.get(role)
    if isinstance(values, list) and values:
        return _text(values[0])
    return ""


def _available_fields(contract: dict[str, Any]) -> set[str]:
    roles = contract.get("field_roles") if isinstance(contract.get("field_roles"), dict) else {}
    fields = set()
    for values in roles.values():
        if isinstance(values, list):
            fields.update(_text(value) for value in values if _text(value))
    return fields


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
```

- [ ] **Step 4: Add persistence and status update tests**

Append to `tests/test_hypotheses.py`:

```python
from data_agent.config import get_config
from data_agent.agent.hypotheses import (
    hydrate_hypothesis_refs,
    persist_hypothesis_set,
    update_hypotheses_from_evidence,
)


def test_hypothesis_set_persists_as_artifact_and_hydrates(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        hypothesis_set = build_hypothesis_set(
            "why did revenue change?",
            {"decision": "direct_analysis", "dataset": "sales", "route": "period_compare"},
            _state(),
        )

        ref = persist_hypothesis_set("s1", hypothesis_set)
        hydrated = hydrate_hypothesis_refs([ref])

        assert ref["count"] == len(hypothesis_set["hypotheses"])
        assert hydrated[0]["id"] == hypothesis_set["id"]
        assert hydrated[0]["hypotheses"][0]["claim"] == hypothesis_set["hypotheses"][0]["claim"]
    finally:
        cfg.sessions_dir = old_sessions


def test_update_hypotheses_from_evidence_marks_supported_and_inconclusive():
    hypothesis_set = build_hypothesis_set(
        "why did revenue change?",
        {"decision": "direct_analysis", "dataset": "sales", "route": "period_compare"},
        _state(),
    )
    evidence = [{
        "id": "ev_primary",
        "claim": hypothesis_set["hypotheses"][0]["claim"],
        "dataset": "sales",
    }]

    updated = update_hypotheses_from_evidence(hypothesis_set, evidence)

    assert updated["hypotheses"][0]["status"] == "supported"
    assert updated["hypotheses"][0]["supporting_evidence_ids"] == ["ev_primary"]
    assert updated["hypotheses"][1]["status"] == "inconclusive"
    assert updated["status_summary"]["supported"] == 1
    assert updated["status_summary"]["inconclusive"] >= 1
```

- [ ] **Step 5: Run hypothesis tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_hypotheses.py -q
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/data_agent/agent/hypotheses.py tests/test_hypotheses.py
git commit -m "Add deterministic hypothesis MVP"
```

---

### Task 4: Runtime Hypothesis Creation

**Files:**
- Modify: `src/data_agent/agent/trust_workflow_runtime.py`
- Modify: `tests/test_trust_workflow_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Append to `tests/test_trust_workflow_runtime.py`:

```python
from data_agent.agent.hypotheses import hydrate_hypothesis_refs
from data_agent.agent.trust_workflow_runtime import maybe_create_hypothesis_set


def test_runtime_creates_hypothesis_set_from_direct_entry_decision(tmp_path, monkeypatch):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "evidence_requirements": ["date", "metric"],
        }]

        ref = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)

        assert ref is not None
        assert state.hypothesis_sets == [ref]
        hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)
        assert hydrated[0]["route"] == "trend"
        assert len(hydrated[0]["hypotheses"]) >= 2
    finally:
        cfg.sessions_dir = old_sessions


def test_runtime_skips_duplicate_hypothesis_set_for_same_route(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_dup", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{"dataset": "sales", "direction": "trend"}]

        first = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)
        second = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)

        assert first is not None
        assert second is None
        assert len(state.hypothesis_sets) == 1
    finally:
        cfg.sessions_dir = old_sessions
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py -q
```

Expected:

- FAIL because `maybe_create_hypothesis_set` does not exist.

- [ ] **Step 3: Implement runtime helper**

Modify `src/data_agent/agent/trust_workflow_runtime.py`:

```python
def maybe_create_hypothesis_set(user_input: str, intent: TurnIntent, state: Any) -> dict[str, Any] | None:
    """Create one compact hypothesis set for a runnable analysis route."""
    try:
        from data_agent.agent.analysis_entry import decide_analysis_entry
        from data_agent.agent.hypotheses import build_hypothesis_set, persist_hypothesis_set

        decision = decide_analysis_entry(user_input, intent, state)
        if decision.get("decision") not in {"direct_analysis", "exploratory_only", "request_data"}:
            return None
        dataset = str(decision.get("dataset") or "")
        route = str(decision.get("route") or "")
        if _has_hypothesis_set(state, dataset, route):
            return None
        hypothesis_set = build_hypothesis_set(user_input, decision, state)
        ref = persist_hypothesis_set(str(getattr(state, "session_id", "")), hypothesis_set)
        add_ref = getattr(state, "add_hypothesis_set_ref", None)
        if callable(add_ref):
            stored = add_ref(ref)
        else:
            refs = getattr(state, "hypothesis_sets", None)
            if isinstance(refs, list):
                refs.append(ref)
            stored = ref
        save = getattr(state, "save", None)
        if callable(save):
            save()
        return stored
    except Exception as exc:
        logger.warning(
            "Hypothesis set creation skipped",
            extra={"extra_data": {"error": str(exc), "user_input": (user_input or "")[:200]}},
        )
        return None


def _has_hypothesis_set(state: Any, dataset: str, route: str) -> bool:
    for ref in _list_attr(state, "hypothesis_sets"):
        if str(ref.get("dataset") or "") == dataset and str(ref.get("route") or "") == route:
            return True
    return False
```

- [ ] **Step 4: Run runtime tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py -q
```

Expected:

- PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/data_agent/agent/trust_workflow_runtime.py tests/test_trust_workflow_runtime.py
git commit -m "Create hypothesis sets in trust runtime"
```

---

### Task 5: Trust View Hypothesis Summary

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `tests/test_trust_view.py`

- [ ] **Step 1: Write failing view tests**

Append to `tests/test_trust_view.py`:

```python
def test_trust_view_includes_compact_hypothesis_summary(tmp_path):
    hypothesis_path = tmp_path / "hypotheses.json"
    hypothesis_path.write_text(
        """
{
  "id": "hyps_sales_trend",
  "dataset": "sales",
  "route": "trend",
  "status_summary": {"supported": 1, "inconclusive": 1},
  "hypotheses": [
    {"id": "h1", "claim": "Revenue changed because orders changed.", "status": "supported"},
    {"id": "h2", "claim": "Revenue changed because channel mix changed.", "status": "inconclusive"},
    {"id": "h3", "claim": "Revenue movement is random fluctuation.", "status": "inconclusive"}
  ]
}
""",
        encoding="utf-8",
    )
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.hypothesis_sets = [{
        "id": "hyps_sales_trend",
        "dataset": "sales",
        "route": "trend",
        "count": 3,
        "artifact_path": str(hypothesis_path),
    }]

    view = build_trust_view(state)

    assert view["hypotheses"] == [{
        "id": "hyps_sales_trend",
        "dataset": "sales",
        "route": "trend",
        "count": 3,
        "status_summary": {"supported": 1, "inconclusive": 1},
        "top_claims": [
            {"claim": "Revenue changed because orders changed.", "status": "supported"},
            {"claim": "Revenue changed because channel mix changed.", "status": "inconclusive"},
        ],
    }]
```

- [ ] **Step 2: Run view tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_view.py::test_trust_view_includes_compact_hypothesis_summary -q
```

Expected:

- FAIL because `hypotheses` is missing from the view.

- [ ] **Step 3: Add compact hypothesis view builder**

Modify `src/data_agent/agent/trust_view.py`:

```python
hypothesis_sets = _hydrate_refs(_list_attr(state, "hypothesis_sets"))
hypotheses = _hypothesis_summaries(hypothesis_sets)

return {
    "status": status,
    "session_id": session_id or _text(getattr(state, "session_id", "")),
    "updated_at": _text(getattr(state, "updated_at", "")),
    "datasets": datasets,
    "routes": routes,
    "risks": risks,
    "verification": verification,
    "hypotheses": hypotheses,
}
```

Add `hypotheses: []` to `_empty_view`.

Add helper:

```python
def _hypothesis_summaries(hypothesis_sets: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    summaries = []
    for item in hypothesis_sets:
        item_id = _text(item.get("id"))
        if not item_id:
            continue
        hypotheses = _list_items(item.get("hypotheses"))
        summaries.append({
            "id": item_id,
            "dataset": _text(item.get("dataset")),
            "route": _text(item.get("route")),
            "count": _count_value(item.get("count"), hypotheses),
            "status_summary": item.get("status_summary") if isinstance(item.get("status_summary"), dict) else {},
            "top_claims": [
                {"claim": _text(hypothesis.get("claim")), "status": _text(hypothesis.get("status"))}
                for hypothesis in hypotheses[:2]
                if _text(hypothesis.get("claim"))
            ],
        })
        if len(summaries) >= limit:
            break
    return summaries
```

- [ ] **Step 4: Update existing empty-view tests**

Modify tests that assert exact empty views to include:

```python
"hypotheses": [],
```

- [ ] **Step 5: Run trust view and API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_view.py tests\test_trust_inspector_api.py -q
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/data_agent/agent/trust_view.py tests/test_trust_view.py tests/test_trust_inspector_api.py
git commit -m "Show hypothesis summaries in trust view"
```

---

### Task 6: Trust Inspector Hypothesis UI

**Files:**
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Write failing UI structure tests**

Append to `tests/test_trust_inspector_ui.py`:

```python
def test_trust_inspector_contains_hypothesis_section(web_index_html):
    assert "trust-hypotheses" in web_index_html
    assert "hypotheses" in web_index_html
    assert "top_claims" in web_index_html
```

If the existing test file does not expose `web_index_html`, follow the local fixture pattern in that file and load `src/data_agent/web/templates/index.html` directly.

- [ ] **Step 2: Run UI tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_inspector_ui.py -q
```

Expected:

- FAIL because the template does not contain a hypothesis section.

- [ ] **Step 3: Add compact Hypotheses section**

In `src/data_agent/web/templates/index.html`, inside the Trust Inspector panel after routes or risks, add:

```html
<section class="trust-section" data-testid="trust-hypotheses">
  <div class="trust-section__header">
    <h3>Hypotheses</h3>
  </div>
  <template x-if="trustView.hypotheses && trustView.hypotheses.length">
    <div class="trust-list">
      <template x-for="set in trustView.hypotheses" :key="set.id">
        <div class="trust-item">
          <div class="trust-item__title" x-text="set.route || set.dataset"></div>
          <div class="trust-item__meta" x-text="formatHypothesisSummary(set)"></div>
          <template x-for="claim in set.top_claims" :key="claim.claim">
            <div class="trust-item__note">
              <span x-text="claim.status"></span>
              <span x-text="claim.claim"></span>
            </div>
          </template>
        </div>
      </template>
    </div>
  </template>
  <template x-if="!trustView.hypotheses || !trustView.hypotheses.length">
    <p class="trust-empty">No hypothesis set yet.</p>
  </template>
</section>
```

- [ ] **Step 4: Add JS formatter**

In `src/data_agent/web/static/js/app.js`, add to the Alpine component:

```javascript
formatHypothesisSummary(set) {
  const summary = set?.status_summary || {};
  const parts = Object.entries(summary)
    .filter(([, value]) => Number(value) > 0)
    .map(([key, value]) => `${key}: ${value}`);
  if (parts.length) return parts.join(" | ");
  const count = Number(set?.count || 0);
  return count ? `${count} proposed` : "No evaluated hypotheses";
},
```

- [ ] **Step 5: Run UI tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_inspector_ui.py -q
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js tests/test_trust_inspector_ui.py
git commit -m "Render hypothesis summaries in Trust Inspector"
```

---

### Task 7: Runtime Integration Checkpoint

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Modify: `tests/test_execution_control.py` or closest existing loop test file

- [ ] **Step 1: Locate current trust runtime calls**

Run:

```powershell
rg "refine_turn_intent_with_state|maybe_verify_turn_claims|_maybe_inject_synthesis_policy|_prepare_analysis_turn" src\data_agent\agent\loop.py tests
```

Expected:

- Find existing intent refinement and verification hooks.

- [ ] **Step 2: Write focused failing loop test**

Append to `tests/test_execution_control.py`:

```python
def test_synthesis_policy_injection_creates_hypothesis_set_before_policy(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        intent = TurnIntent(
            intent_type="directed_analysis",
            clarity="clear",
            data_state="data_loaded",
            analysis_stage="execute",
            recommended_action="run_analysis",
            execution_readiness="ready",
            reason="test",
            ambiguities=[],
        )
        workspace_obj = Workspace()
        ctx = AgentContext(session_id="loop_hyp_before_synthesis", workspace=workspace_obj)
        state = AnalysisSessionState(session_id="loop_hyp_before_synthesis")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "evidence_requirements": ["date", "metric"],
        }]
        state.evidence_records = [{
            "id": "ev_1",
            "claim": "Revenue changed across the selected period",
            "result_summary": "Revenue moved from 100 to 120.",
            "confidence": "high",
            "dataset": "sales",
            "sample_size": 20,
            "time_scope": "2026-01-01 to 2026-01-20",
            "calculation_method": "trend comparison",
            "method_detail": "compare daily revenue values",
            "limitations": "Descriptive trend only",
            "method": "descriptive",
        }]
        ctx.analysis_state = state
        ctx.user_quality_requirements = ""
        loop = AgentLoop(client=object(), session_id="loop_hyp_before_synthesis")
        loop.context = ctx
        loop._last_turn_intent = intent
        loop._reset_turn_tracking()

        with use_agent_context(ctx):
            loop._maybe_inject_synthesis_policy("show revenue trend")

        assert state.hypothesis_sets
        assert state.hypothesis_sets[-1]["dataset"] == "sales"
        assert state.hypothesis_sets[-1]["route"] == "trend"
        assert loop._turn_synthesis_policy_injected is True
    finally:
        cfg.sessions_dir = old_sessions
```

- [ ] **Step 3: Run the focused loop test to verify failure**

Run the single test with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py::test_synthesis_policy_injection_creates_hypothesis_set_before_policy -q
```

Expected:

- FAIL because loop does not call `maybe_create_hypothesis_set`.

- [ ] **Step 4: Integrate helper in the loop**

In `src/data_agent/agent/loop.py`, after intent refinement and state loading but before final synthesis policy derivation, call:

```python
from data_agent.agent.trust_workflow_runtime import maybe_create_hypothesis_set

maybe_create_hypothesis_set(user_input, self.context.turn_intent, state)
```

Guard it the same way existing trust runtime calls are guarded:

- catch exceptions at helper level
- do not crash the conversation
- do not create duplicate hypothesis refs

- [ ] **Step 5: Run loop and trust runtime tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py tests\test_execution_control.py -q
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/data_agent/agent/loop.py tests/test_execution_control.py
git commit -m "Integrate hypothesis creation into analysis loop"
```

---

### Task 8: Final Verification And Real-Data Probe

**Files:**
- No required production file changes.

- [ ] **Step 1: Run focused Phase 2 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_analysis_entry.py tests\test_hypotheses.py tests\test_trust_workflow_runtime.py tests\test_trust_view.py tests\test_trust_inspector_api.py tests\test_trust_inspector_ui.py -q
```

Expected:

- PASS.

- [ ] **Step 2: Run existing trust workflow regression suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_web_workbench_parity.py tests\test_trustworthy_workflow_mvp.py tests\test_trust_workflow_runtime.py tests\test_execution_control.py -q
```

Expected:

- PASS.

- [ ] **Step 3: Probe existing real-data sessions**

Run:

```powershell
@'
from data_agent.agent.analysis_state import load_analysis_state
from data_agent.agent.trust_view import build_trust_view

for sid in ["trust_test_game_b_retention", "trust_test_savings_card"]:
    state = load_analysis_state(sid)
    view = build_trust_view(state, sid)
    print("SESSION", sid)
    print("datasets", [(d["dataset"], d["rows"], d["columns"]) for d in view["datasets"]])
    print("routes", [(r["dataset"], r["direction"]) for r in view["routes"]])
    print("risks", [(r["source"], r["field"]) for r in view["risks"][:5]])
    print("hypotheses", view.get("hypotheses", []))
'@ | .\.venv\Scripts\python.exe -
```

Expected:

- Existing datasets and risks still render.
- `hypotheses` is an empty list for old sessions unless a hypothesis set has been generated.

- [ ] **Step 4: Create one synthetic hypothesis set probe**

Run a small script using existing state and helpers:

```powershell
@'
from data_agent.agent.analysis_state import load_analysis_state
from data_agent.agent.intent import TurnIntent
from data_agent.agent.trust_workflow_runtime import maybe_create_hypothesis_set
from data_agent.agent.trust_view import build_trust_view

state = load_analysis_state("trust_test_game_b_retention")
intent = TurnIntent(
    intent_type="directed_analysis",
    clarity="clear",
    data_state="data_loaded",
    analysis_stage="execute",
    recommended_action="run_analysis",
    execution_readiness="ready",
    reason="probe",
    ambiguities=[],
)
maybe_create_hypothesis_set("show retention trend", intent, state)
view = build_trust_view(state, "trust_test_game_b_retention")
print(view["hypotheses"])
'@ | .\.venv\Scripts\python.exe -
```

Expected:

- Prints at least one compact hypothesis set.
- The view remains valid.

- [ ] **Step 5: Final status check**

Run:

```powershell
git status --short --branch
```

Expected:

- Only intended changes are committed.
- Pre-existing unrelated untracked files may remain.

---

## Completion Criteria

The implementation is complete when:

- The entry decision layer can deterministically return `direct_analysis`, `clarify_intent`, `request_data`, `exploratory_only`, or `blocked`.
- Hypothesis sets contain 2 to 4 competing explanations for supported routes.
- Unsupported analyses create explicit `unsupported_by_data` hypotheses instead of disappearing.
- Each hypothesis has evidence requirements and a verifiability label.
- Evidence records can update hypothesis status to `supported`, `inconclusive`, or `unsupported_by_data`.
- Compact refs are stored in `AnalysisSessionState`.
- Full hypothesis details persist as JSON artifacts.
- Trust Inspector shows compact hypothesis status without becoming a wizard.
- Existing Trust Inspector and trust workflow regression tests still pass.

## Notes For Implementers

- Preserve the existing read-only behavior of `/api/sessions/<session_id>/trust`.
- Do not call LLMs from `analysis_entry.py` or `hypotheses.py`.
- Keep deterministic templates small. This MVP is a reasoning skeleton, not a domain playbook.
- Use the existing artifact hydration pattern from `trust_view.py` to protect context budget.
- Treat the hypothesis system as the project's first explicit adversarial-analysis mechanism: every primary explanation should be shown alongside alternatives or a baseline explanation.
