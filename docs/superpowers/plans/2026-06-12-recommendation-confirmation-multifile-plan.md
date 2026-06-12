# Recommendation, Confirmation, And Multi-File Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make analysis recommendations evidence-scoped, make every visible confirmation answerable, and introduce a compact multi-file analysis scope plan that protects downstream analysis quality.

**Architecture:** Reuse the existing trustworthy-analysis flow instead of creating a parallel system. `route_capabilities` becomes stricter about recommendation support, `pending_confirmations` becomes the single user-answerable confirmation source, and a new focused scope-planning module builds compact multi-file decisions from existing `data_pool`, `active_bundle`, and file relationship metadata.

**Tech Stack:** Python 3.12+, pytest, existing `AnalysisSessionState`, existing Flask/Web trust view APIs, no new external dependencies.

---

## File Structure

Create or modify these files:

- Modify: `src/data_agent/agent/route_capabilities.py`
  - Add recommendation support status: `supported`, `supported_with_limits`, `needs_confirmation`, `needs_more_data`, `out_of_scope`.
  - Keep existing `executable` and `exploratory` shape compatible, but add support metadata.
- Modify: `src/data_agent/agent/analysis_entry.py`
  - Use the stricter route capability model before returning direct analysis.
  - Prevent routes outside current data scope from being treated as executable.
- Modify: `src/data_agent/agent/method_playbooks.py`
  - Ensure method confirmations include a user-facing question, options, blocking reason, and state updates.
- Modify: `src/data_agent/tools/data_io.py`
  - When file relationship confirmation is required, create an answerable pending confirmation instead of only setting `file_relationships.requires_confirmation`.
- Modify: `src/data_agent/agent/question_need_detector.py`
  - Keep relationship questions concrete and tied to pending confirmation state.
- Create: `src/data_agent/agent/multi_file_scope.py`
  - Build compact analysis scope plans from current state.
  - Classify files as included, excluded, supporting, pending, or needing more data.
  - Add field/entity alias and grain helpers without broad semantic-layer scope.
- Modify: `src/data_agent/agent/trust_view.py`
  - Expose `analysis_scope_plan` and only show confirmation items that have real pending confirmation records.
- Modify: `src/data_agent/web/templates/index.html`
  - De-emphasize side-panel route actions; keep route information as support/explanation only.
- Modify: `src/data_agent/web/static/js/app.js`
  - Avoid presenting route cards as a duplicate primary action surface.
- Test: `tests/test_route_capabilities.py`
- Test: `tests/test_analysis_entry.py`
- Test: `tests/test_question_need_detector.py`
- Test: `tests/test_data_bundle.py`
- Create: `tests/test_multi_file_scope.py`
- Modify: `tests/test_trust_view.py`
- Modify: `tests/test_trust_inspector_ui.py`

---

### Task 1: Add Recommendation Support Guard

**Files:**
- Modify: `src/data_agent/agent/route_capabilities.py`
- Modify: `src/data_agent/agent/analysis_entry.py`
- Test: `tests/test_route_capabilities.py`
- Test: `tests/test_analysis_entry.py`

- [ ] **Step 1: Write failing route capability tests**

Add these tests to `tests/test_route_capabilities.py`:

```python
def test_executable_route_carries_data_supported_basis():
    state = AnalysisSessionState(session_id="support_guard", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {
            "date": ["order_date"],
            "metrics": ["revenue"],
            "dimensions": ["channel"],
            "ids": ["user_id"],
        },
        "supported_analyses": ["trend"],
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "orders",
        "direction": "trend",
        "label": "Revenue trend",
        "reason": "date and revenue fields exist",
        "evidence_requirements": ["order_date", "revenue"],
    }]

    model = build_route_capabilities(state)

    route = model["executable"][0]
    assert route["support_status"] == "supported"
    assert route["support_basis"] == "data_supported"
    assert route["support_reasons"] == ["date and revenue fields exist"]
    assert route["missing_requirements"] == []
```

Add this test to the same file:

```python
def test_route_missing_required_fields_becomes_exploratory_not_executable():
    state = AnalysisSessionState(session_id="support_guard_missing", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
        "unsupported_analyses": [],
    }]
    state.route_proposals = [{
        "id": "route_retention",
        "dataset": "orders",
        "direction": "cohort",
        "label": "Retention",
        "reason": "retention may answer lifecycle questions",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["exploratory"][0]["category"] == "needs_more_data"
    assert model["exploratory"][0]["support_status"] == "needs_more_data"
    assert model["exploratory"][0]["missing_requirements"] == ["user_id", "event_date"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
pytest tests/test_route_capabilities.py::test_executable_route_carries_data_supported_basis tests/test_route_capabilities.py::test_route_missing_required_fields_becomes_exploratory_not_executable -q
```

Expected: fail because `support_status`, `support_basis`, `support_reasons`, and missing-requirement demotion do not exist yet.

- [ ] **Step 3: Implement route support metadata**

In `src/data_agent/agent/route_capabilities.py`, add helper functions near `_executable_routes`:

```python
def _contract_for_dataset(contracts: list[dict[str, Any]], dataset: str) -> dict[str, Any]:
    for contract in contracts:
        if _text(contract.get("dataset")) == dataset:
            return contract
    return {}


def _available_fields(contract: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    roles = contract.get("field_roles") if isinstance(contract.get("field_roles"), dict) else {}
    for value in roles.values():
        fields.update(_text_list(value))
    fields.update(_text_list(contract.get("columns")))
    fields.update(_text_list(contract.get("key_fields")))
    fields.update(_text_list(contract.get("time_fields")))
    return {field for field in fields if field}


def _route_support(
    route: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    required = _required_fields(route)
    available = _available_fields(contract)
    missing = [field for field in required if field and field not in available]
    limitations = _text_list(route.get("limitations"))
    if missing:
        return {
            "support_status": "needs_more_data",
            "support_basis": "data_needed",
            "support_reasons": [_text(route.get("reason"))] if _text(route.get("reason")) else [],
            "missing_requirements": missing,
        }
    return {
        "support_status": "supported_with_limits" if limitations else "supported",
        "support_basis": "data_supported",
        "support_reasons": [_text(route.get("reason"))] if _text(route.get("reason")) else [],
        "missing_requirements": [],
    }
```

Change `build_route_capabilities` to pass contracts into `_executable_routes`:

```python
executable, route_gate, demoted = _executable_routes(routes, cleaning_logs, contracts, active_dataset, limit)
exploratory = demoted + _unsupported_exploratory(contracts, active_dataset, max(limit - len(demoted), 0))
```

Change `_executable_routes` signature and loop:

```python
def _executable_routes(
    routes: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    active_dataset: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []
    gate_risk_fields: list[str] = []
    gate_routes: list[str] = []
    for route in routes:
        dataset = _text(route.get("dataset"))
        if active_dataset and dataset != active_dataset:
            continue
        direction = _text(route.get("direction") or route.get("route"))
        if not direction:
            continue
        risk_fields = _required_field_risks(route, cleaning_logs)
        if risk_fields:
            gate_risk_fields.extend(risk_fields)
            gate_routes.append(direction)
            continue
        contract = _contract_for_dataset(contracts, dataset)
        support = _route_support(route, contract)
        if support["support_status"] == "needs_more_data":
            demoted.append({
                "id": _text(route.get("id")) or f"explore_{len(demoted) + 1}",
                "dataset": dataset,
                "analysis": direction,
                "label": _text(route.get("label")) or direction,
                "category": "needs_more_data",
                "reason": _text(route.get("reason")),
                "data_requirements": support["missing_requirements"],
                "value_if_available": "",
                "prompt": (
                    f'I want to explore "{direction}". Please tell me what data is missing, '
                    "why the current data cannot verify it, and what dataset would be needed."
                ),
                **support,
            })
            continue
```

When appending executable route, merge `support`:

```python
items.append({
    "id": _text(route.get("id")) or f"route_{len(items) + 1}",
    "dataset": dataset,
    "route": direction,
    "direction": direction,
    "label": _text(route.get("label")) or direction,
    "category": "ready",
    "reason": _text(route.get("reason")),
    "limitations": _text_list(route.get("limitations")),
    "evidence_requirements": _text_list(route.get("evidence_requirements")),
    "risk_fields": risk_fields,
    "budget_level": _text(route.get("budget_level")),
    "prompt": _route_prompt(route, risk_fields),
    "auto_submit": False,
    **support,
})
```

Return:

```python
return items, route_confirmation_gate(
    risk_fields=gate_risk_fields,
    affected_routes=gate_routes,
), demoted
```

- [ ] **Step 4: Update analysis entry tests**

Add this test to `tests/test_analysis_entry.py`:

```python
def test_decide_analysis_entry_does_not_execute_route_missing_required_data():
    state = AnalysisSessionState(session_id="entry_guard", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [{
        "id": "route_cohort",
        "dataset": "orders",
        "direction": "cohort",
        "label": "Retention",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    decision = decide_analysis_entry("analyze retention", _intent("directed_analysis"), state)

    assert decision["decision"] == "request_data"
    assert decision["required_user_action"] == "provide_required_data"
    assert decision["limitations"] == ["user_id", "event_date"]
```

- [ ] **Step 5: Implement analysis entry guard**

In `src/data_agent/agent/analysis_entry.py`, after `capability_routes = _executable_routes_from_capabilities(state)`, also read exploratory routes from capabilities:

```python
capability_model = _route_capability_model(state)
capability_routes = capability_model.get("executable") if capability_model else None
capability_exploratory = capability_model.get("exploratory") if capability_model else []
```

Add helper:

```python
def _route_capability_model(state: Any) -> dict[str, Any] | None:
    try:
        from data_agent.agent.route_capabilities import build_route_capabilities
    except ImportError:
        return None
    model = build_route_capabilities(state)
    return model if isinstance(model, dict) else None
```

Before final fallback `clarify_intent`, add:

```python
    missing_route = _infer_requested_exploratory_route(user_input, capability_exploratory)
    if missing_route:
        return _decision(
            "request_data",
            dataset=_text(missing_route.get("dataset")),
            route=_text(missing_route.get("analysis")),
            reason="The requested analysis is relevant but not supported by the current data scope.",
            required_user_action="provide_required_data",
            limitations=_text_list(missing_route.get("missing_requirements") or missing_route.get("data_requirements")),
        )
```

Add helper:

```python
def _infer_requested_exploratory_route(user_input: str, routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = _text(user_input).lower()
    for route in routes:
        analysis = _text(route.get("analysis")).lower()
        label = _text(route.get("label")).lower()
        if analysis and analysis in text:
            return route
        if label and label in text:
            return route
    if _mentions_retention(user_input):
        for route in routes:
            if _text(route.get("analysis")) in {"cohort", "retention", "user_level_retention"}:
                return route
    return None
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
pytest tests/test_route_capabilities.py tests/test_analysis_entry.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src/data_agent/agent/route_capabilities.py src/data_agent/agent/analysis_entry.py tests/test_route_capabilities.py tests/test_analysis_entry.py
git commit -m "feat: guard analysis recommendations by data support"
```

---

### Task 2: Repair Confirmation Contract

**Files:**
- Modify: `src/data_agent/agent/method_playbooks.py`
- Modify: `src/data_agent/tools/data_io.py`
- Modify: `src/data_agent/agent/question_need_detector.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Test: `tests/test_method_playbooks.py`
- Test: `tests/test_data_bundle.py`
- Test: `tests/test_question_need_detector.py`
- Test: `tests/test_trust_view.py`

- [ ] **Step 1: Write failing tests for method confirmation completeness**

Add to `tests/test_method_playbooks.py`:

```python
def test_method_confirmation_is_answerable_when_selection_requires_confirmation():
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.method_playbooks import choose_playbook, apply_selection_to_state
    from data_agent.agent.intent import TurnIntent

    state = AnalysisSessionState(session_id="method_confirm", data_state="data_loaded")
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )

    selection = choose_playbook("predict user churn next month", intent, has_data=True)
    apply_selection_to_state(state, selection)

    pending = state.pending_confirmations[0]
    assert pending["status"] == "pending"
    assert pending["confirmation_type"] == "method_confirmation"
    assert pending["question"]
    assert pending["options"]
    assert pending["blocking_reason"]
    assert pending["state_updates"]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
pytest tests/test_method_playbooks.py::test_method_confirmation_is_answerable_when_selection_requires_confirmation -q
```

Expected: fail because current method confirmations lack question/options/state updates.

- [ ] **Step 3: Implement answerable method confirmations**

In `src/data_agent/agent/method_playbooks.py`, add:

```python
def _method_confirmation_question(selection: PlaybookSelection) -> str:
    title = selection.primary_playbook_id.replace("_", " ")
    return (
        f"本次分析将使用 {title} 方法。该方法会影响指标口径、时间窗口或结论强度。"
        "请确认是否按该方法继续，或先补充目标和口径。"
    )


def _method_confirmation_options() -> list[dict[str, str]]:
    return [
        {
            "label": "按此方法继续",
            "value": "confirm_method",
            "description": "使用当前方法计划继续，但结论仍会按证据强度标注限制。",
        },
        {
            "label": "先补充目标口径",
            "value": "clarify_method_scope",
            "description": "暂停执行，先说明目标指标、时间窗口或比较对象。",
        },
    ]
```

Update `apply_selection_to_state` pending confirmation:

```python
state.add_confirmation({
    "id": confirmation_id,
    "confirmation_type": selection.analysis_spec.get("confirmation_policy", {}).get("confirmation_type", "method_confirmation"),
    "question": _method_confirmation_question(selection),
    "options": _method_confirmation_options(),
    "blocking_reason": selection.analysis_spec.get("confirmation_policy", {}).get("blocking_reason", "method confirmation required"),
    "related_spec_id": selection.analysis_spec.get("id", ""),
    "state_updates": json.dumps({
        "stage": "method_confirmation",
        "method_confirmation": {
            "playbook_id": selection.primary_playbook_id,
            "analysis_spec_id": selection.analysis_spec.get("id", ""),
        },
    }, ensure_ascii=False),
    "source": "method_playbook",
    "status": "pending",
})
```

Import `json` at the top of the file.

- [ ] **Step 4: Write failing test for file relationship confirmation creation**

Add to `tests/test_data_bundle.py`:

```python
def test_register_loaded_data_creates_pending_confirmation_for_uncertain_relationship(tmp_path, monkeypatch):
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.tools import data_io

    state = AnalysisSessionState(session_id="file_confirm", data_state="data_loaded")
    state.data_pool = [{
        "file_id": "file_old",
        "filename": "orders.xlsx",
        "dataset": "orders",
        "key_fields": ["user_id"],
        "status": "loaded",
    }]
    state.set_active_bundle({
        "bundle_id": "bundle_old",
        "file_ids": ["file_old"],
        "dataset_names": ["orders"],
    })
    monkeypatch.setattr(data_io, "_save_trust_state", lambda *_args, **_kwargs: None)

    data_io._register_loaded_data_bundle(
        state=state,
        session_id="file_confirm",
        source=str(tmp_path / "activity.xlsx"),
        dataset="activity",
        df_columns=["user_id", "event_time"],
        row_count=10,
        field_roles={"ids": ["user_id"], "date": ["event_time"]},
        contract={"time_range": {}},
        user_input="analyze revenue",
    )

    assert state.pending_confirmations
    pending = state.pending_confirmations[0]
    assert pending["confirmation_type"] == "file_relationship_confirmation"
    assert pending["question"]
    assert pending["options"]
    assert "file_relationship_confirmation" in pending["state_updates"]
```

If `_register_loaded_data_bundle` signature differs, adapt the test to the existing private helper parameters by reading its definition before editing.

- [ ] **Step 5: Implement file relationship pending confirmation**

In `src/data_agent/tools/data_io.py`, add helper near `_register_loaded_data_bundle`:

```python
def _add_file_relationship_confirmation(state: Any, relationship: dict[str, Any]) -> None:
    relationship_id = str(relationship.get("relationship_id") or relationship.get("id") or "")
    if not relationship_id:
        return
    confirmation_id = f"confirm_{relationship_id}"
    if any(item.get("id") == confirmation_id and item.get("status", "pending") == "pending" for item in state.pending_confirmations):
        return
    confirmation_type = relationship.get("confirmation_type") or "file_relationship_confirmation"
    state.add_confirmation({
        "id": confirmation_id,
        "confirmation_type": confirmation_type,
        "question": _file_relationship_question(relationship, confirmation_type),
        "options": _file_relationship_options(confirmation_type),
        "blocking_reason": _file_relationship_reason(relationship),
        "state_updates": json.dumps({
            "stage": "scope",
            "file_relationship_confirmation": {
                "relationship_id": relationship_id,
            },
        }, ensure_ascii=False),
        "source": "file_relationship",
        "status": "pending",
    })
```

Add local question helpers or import/reuse equivalent logic from `question_need_detector` only if it does not create circular imports. Prefer local helpers to avoid coupling:

```python
def _file_relationship_reason(relationship: dict[str, Any]) -> str:
    uncertainties = relationship.get("uncertainties") if isinstance(relationship.get("uncertainties"), list) else []
    return str(uncertainties[0]) if uncertainties else "多个数据文件之间的关系尚未确认，可能影响本次分析范围。"


def _file_relationship_question(relationship: dict[str, Any], confirmation_type: str) -> str:
    if confirmation_type == "file_exclusion_confirmation":
        return "新上传的数据文件可能不属于当前分析目标。请确认是否纳入本轮分析。"
    return "新上传的数据文件可能与当前分析目标有关，但关系尚不确定。请确认这些文件应如何参与本轮分析。"


def _file_relationship_options(confirmation_type: str) -> list[dict[str, str]]:
    if confirmation_type == "file_exclusion_confirmation":
        return [
            {"label": "纳入当前分析", "value": "include_in_active_bundle", "description": "将新文件视为当前分析目标的一部分。"},
            {"label": "暂不纳入", "value": "exclude_from_active_bundle", "description": "本轮分析先不使用该文件。"},
        ]
    return [
        {"label": "一起分析", "value": "include_in_active_bundle", "description": "把这些文件放入同一分析范围。"},
        {"label": "分开分析", "value": "separate_bundle", "description": "将新文件与当前分析范围分开处理。"},
        {"label": "只分析最新文件", "value": "latest_only", "description": "本轮只使用最新上传的数据文件。"},
    ]
```

In the `if relationship.get("requires_confirmation"):` block, call:

```python
_add_file_relationship_confirmation(state, relationship)
```

- [ ] **Step 6: Ensure trust view shows only answerable confirmations**

Add to `tests/test_trust_view.py`:

```python
def test_trust_view_does_not_show_orphaned_relationship_as_actionable_confirmation():
    state = AnalysisSessionState(session_id="trust_orphan", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_orphan",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
    }]

    view = build_trust_view(state)

    assert view["file_relationships"][0]["requires_confirmation"] is True
    assert view["recommendations"]["confirmation_gate"]["status"] == "clear"
```

Add:

```python
def test_trust_view_confirmation_gate_comes_from_pending_confirmation():
    state = AnalysisSessionState(session_id="trust_pending", data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "confirm_rel",
        "status": "pending",
        "confirmation_type": "file_relationship_confirmation",
        "question": "是否按 user_id 关联？",
        "blocking_reason": "字段别名会影响分析范围",
    }]

    view = build_trust_view(state)

    assert view["recommendations"]["confirmation_gate"]["status"] == "needs_confirmation"
    assert view["recommendations"]["confirmation_gate"]["question"] == "是否按 user_id 关联？"
```

- [ ] **Step 7: Run focused tests**

```powershell
pytest tests/test_method_playbooks.py tests/test_data_bundle.py tests/test_question_need_detector.py tests/test_trust_view.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add src/data_agent/agent/method_playbooks.py src/data_agent/tools/data_io.py src/data_agent/agent/question_need_detector.py src/data_agent/agent/trust_view.py tests/test_method_playbooks.py tests/test_data_bundle.py tests/test_question_need_detector.py tests/test_trust_view.py
git commit -m "fix: make confirmation states answerable"
```

---

### Task 3: Add Multi-File Scope Planner

**Files:**
- Create: `src/data_agent/agent/multi_file_scope.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Test: `tests/test_multi_file_scope.py`
- Test: `tests/test_trust_view.py`

- [ ] **Step 1: Write tests for field canonicalization and grain detection**

Create `tests/test_multi_file_scope.py` with:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.multi_file_scope import (
    canonical_entity_fields,
    infer_file_grain,
    build_analysis_scope_plan,
)


def test_canonical_entity_fields_recognize_user_aliases():
    profile = {
        "file_id": "coupon",
        "filename": "代金券明细订单.xlsx",
        "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
        "key_fields": [],
        "time_fields": ["核销时间"],
    }

    fields = canonical_entity_fields(profile)

    assert fields["user"] == ["主用户ID", "产品用户ID"]
    assert fields["coupon"] == ["优惠券ID"]
    assert fields["time"] == ["核销时间"]


def test_infer_file_grain_prefers_order_level_when_order_id_exists():
    profile = {
        "file_id": "orders",
        "columns": ["order_id", "user_id", "paid_at", "amount"],
        "key_fields": ["order_id", "user_id"],
        "time_fields": ["paid_at"],
    }

    assert infer_file_grain(profile)["grain"] == "order_level"
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
pytest tests/test_multi_file_scope.py::test_canonical_entity_fields_recognize_user_aliases tests/test_multi_file_scope.py::test_infer_file_grain_prefers_order_level_when_order_id_exists -q
```

Expected: fail because `multi_file_scope.py` does not exist.

- [ ] **Step 3: Implement canonicalization and grain helpers**

Create `src/data_agent/agent/multi_file_scope.py`:

```python
"""Compact multi-file analysis scope planning."""

from __future__ import annotations

from typing import Any


USER_ALIASES = {"user_id", "userid", "uid", "用户id", "用户ID", "用户_id", "主用户ID", "产品用户ID", "会员ID", "会员id"}
ORDER_ALIASES = {"order_id", "订单ID", "订单id", "订单号", "订单编号"}
COUPON_ALIASES = {"coupon_id", "优惠券ID", "优惠券id", "代金券ID", "代金券id"}
TIME_ALIASES = {"paid_at", "pay_time", "event_time", "支付时间", "下单时间", "核销时间", "日期", "时间"}


def canonical_entity_fields(profile: dict[str, Any]) -> dict[str, list[str]]:
    fields = _profile_fields(profile)
    return {
        "user": _matches(fields, USER_ALIASES),
        "order": _matches(fields, ORDER_ALIASES),
        "coupon": _matches(fields, COUPON_ALIASES),
        "time": _matches(fields, TIME_ALIASES),
    }


def infer_file_grain(profile: dict[str, Any]) -> dict[str, str]:
    entities = canonical_entity_fields(profile)
    filename = _text(profile.get("filename") or profile.get("dataset"))
    lowered = filename.lower()
    if entities["order"]:
        grain = "order_level"
    elif entities["coupon"] and entities["user"]:
        grain = "coupon_usage_level"
    elif entities["user"] and not entities["order"]:
        grain = "user_level"
    elif "留存" in filename or "retention" in lowered:
        grain = "cohort_aggregate"
    else:
        grain = "unknown"
    return {"grain": grain, "reason": _grain_reason(grain)}


def _profile_fields(profile: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in ("columns", "key_fields", "time_fields"):
        value = profile.get(key)
        if isinstance(value, list):
            fields.extend(_text(item) for item in value)
    return _dedupe([field for field in fields if field])


def _matches(fields: list[str], aliases: set[str]) -> list[str]:
    normalized_aliases = {_normalize(item) for item in aliases}
    return [field for field in fields if _normalize(field) in normalized_aliases]


def _normalize(value: Any) -> str:
    return _text(value).replace(" ", "").replace("_", "").lower()


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _grain_reason(grain: str) -> str:
    return {
        "order_level": "contains an order identifier",
        "coupon_usage_level": "contains coupon and user identifiers",
        "user_level": "contains user identifiers without order identifiers",
        "cohort_aggregate": "filename suggests cohort or retention aggregate data",
        "unknown": "no stable entity grain detected",
    }.get(grain, "no stable entity grain detected")
```

- [ ] **Step 4: Write tests for scope plan**

Append to `tests/test_multi_file_scope.py`:

```python
def test_scope_plan_includes_relevant_user_files_and_excludes_unrelated_game_file():
    state = AnalysisSessionState(session_id="scope_plan", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [
        {
            "file_id": "orders",
            "filename": "省钱卡订单.xlsx",
            "dataset": "省钱卡订单",
            "columns": ["order_id", "user_id", "支付时间", "实收金额"],
            "key_fields": ["order_id", "user_id"],
            "time_fields": ["支付时间"],
        },
        {
            "file_id": "coupon",
            "filename": "代金券明细订单.xlsx",
            "dataset": "代金券明细订单",
            "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
            "key_fields": [],
            "time_fields": ["核销时间"],
        },
        {
            "file_id": "game",
            "filename": "游戏互推.xlsx",
            "dataset": "游戏互推",
            "columns": ["设备ID", "游戏", "留存"],
            "key_fields": ["设备ID"],
        },
    ]
    state.set_active_bundle({
        "bundle_id": "bundle_orders",
        "file_ids": ["orders"],
        "dataset_names": ["省钱卡订单"],
    })

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["included_files"]] == ["orders", "coupon"]
    assert [item["file_id"] for item in plan["excluded_files"]] == ["game"]
    assert plan["scope_status"] == "needs_confirmation"
    assert any("主用户ID" in assumption for assumption in plan["assumptions"])
```

- [ ] **Step 5: Implement scope plan**

Append to `src/data_agent/agent/multi_file_scope.py`:

```python
def build_analysis_scope_plan(state: Any, user_goal: str = "") -> dict[str, Any]:
    data_pool = _list_attr(state, "data_pool")
    goal = _text(user_goal) or _text(getattr(state, "goal", ""))
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    assumptions: list[str] = []

    for profile in data_pool:
        summary = _file_scope_summary(profile)
        decision = _file_goal_decision(profile, goal)
        if decision == "exclude":
            excluded.append({**summary, "reason": "文件主题与当前目标不匹配。"})
        else:
            included.append({**summary, "reason": "文件主题或用户实体与当前目标相关。"})
            entities = canonical_entity_fields(profile)
            if entities["user"] and not any(field == "user_id" for field in entities["user"]):
                assumptions.append(f"{summary['filename']} 的 {', '.join(entities['user'])} 可能对应用户实体。")
                pending.append(summary)

    scope_status = "needs_confirmation" if pending else "ready"
    return {
        "scope_status": scope_status,
        "goal": goal,
        "included_files": included,
        "excluded_files": excluded,
        "pending_files": pending,
        "assumptions": assumptions,
        "context_budget": {
            "prompt_strategy": "compact_scope_plan",
            "file_count": len(data_pool),
        },
    }


def _file_scope_summary(profile: dict[str, Any]) -> dict[str, Any]:
    grain = infer_file_grain(profile)
    return {
        "file_id": _text(profile.get("file_id") or profile.get("id")),
        "filename": _text(profile.get("filename") or profile.get("name")),
        "dataset": _text(profile.get("dataset") or profile.get("dataset_name")),
        "grain": grain["grain"],
        "entities": canonical_entity_fields(profile),
    }


def _file_goal_decision(profile: dict[str, Any], goal: str) -> str:
    text = " ".join([
        _text(profile.get("filename")),
        _text(profile.get("dataset")),
        " ".join(_profile_fields(profile)),
    ])
    if any(token in text for token in ("游戏", "互推", "retention")) and not any(token in goal for token in ("游戏", "互推", "留存")):
        return "exclude"
    if any(token in text for token in ("省钱卡", "订单", "代金券", "优惠券", "用户", "user", "order", "coupon")):
        return "include"
    return "exclude"


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
```

- [ ] **Step 6: Expose scope plan in trust view**

Add to `tests/test_trust_view.py`:

```python
def test_trust_view_exposes_analysis_scope_plan():
    state = AnalysisSessionState(session_id="trust_scope", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [{
        "file_id": "orders",
        "filename": "省钱卡订单.xlsx",
        "dataset": "省钱卡订单",
        "columns": ["order_id", "user_id", "支付时间"],
        "key_fields": ["order_id", "user_id"],
        "time_fields": ["支付时间"],
    }]

    view = build_trust_view(state)

    assert view["analysis_scope_plan"]["scope_status"] == "ready"
    assert view["analysis_scope_plan"]["included_files"][0]["file_id"] == "orders"
```

In `src/data_agent/agent/trust_view.py`, import and use the planner:

```python
from data_agent.agent.multi_file_scope import build_analysis_scope_plan
```

Inside `build_trust_view`, after `file_relationships`:

```python
analysis_scope_plan = build_analysis_scope_plan(
    state,
    user_goal=_text(active_scope.get("active_goal")) or _text(getattr(state, "goal", "")),
)
```

Add to the returned dict:

```python
"analysis_scope_plan": analysis_scope_plan,
```

Add `"analysis_scope_plan": None` to `_empty_view`.

- [ ] **Step 7: Run focused tests**

```powershell
pytest tests/test_multi_file_scope.py tests/test_trust_view.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add src/data_agent/agent/multi_file_scope.py src/data_agent/agent/trust_view.py tests/test_multi_file_scope.py tests/test_trust_view.py
git commit -m "feat: add multi-file analysis scope plan"
```

---

### Task 4: Reframe Side Workbench Output

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Test: `tests/test_trust_view.py`
- Test: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Write backend contract test for workbench sections**

Add to `tests/test_trust_view.py`:

```python
def test_trust_view_provides_workbench_context_not_route_selection_surface():
    state = AnalysisSessionState(session_id="workbench", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [{
        "file_id": "orders",
        "filename": "省钱卡订单.xlsx",
        "dataset": "省钱卡订单",
        "columns": ["order_id", "user_id", "支付时间"],
        "key_fields": ["order_id", "user_id"],
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "省钱卡订单",
        "direction": "trend",
        "label": "趋势分析",
    }]

    view = build_trust_view(state)

    assert set(view["workbench"].keys()) == {"current_context", "confirmations", "trust_evidence"}
    assert view["workbench"]["current_context"]["goal"] == "评估省钱卡是否值得继续运营"
    assert "routes" not in view["workbench"]
```

- [ ] **Step 2: Implement workbench view model**

In `src/data_agent/agent/trust_view.py`, add:

```python
def _workbench_summary(
    state: Any,
    analysis_scope_plan: dict[str, Any] | None,
    confirmation_gate: dict[str, Any],
    verification: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = analysis_scope_plan or {}
    return {
        "current_context": {
            "goal": _text(plan.get("goal")) or _text(getattr(state, "goal", "")),
            "scope_status": _text(plan.get("scope_status")),
            "included_files": plan.get("included_files") if isinstance(plan.get("included_files"), list) else [],
            "excluded_files": plan.get("excluded_files") if isinstance(plan.get("excluded_files"), list) else [],
            "assumptions": plan.get("assumptions") if isinstance(plan.get("assumptions"), list) else [],
        },
        "confirmations": {
            "status": confirmation_gate.get("status", "clear") if isinstance(confirmation_gate, dict) else "clear",
            "question": confirmation_gate.get("question", "") if isinstance(confirmation_gate, dict) else "",
            "blocking_reason": confirmation_gate.get("blocking_reason", "") if isinstance(confirmation_gate, dict) else "",
        },
        "trust_evidence": verification or {
            "status": "not_run",
            "claim_count": 0,
            "failed_count": 0,
            "downgraded_count": 0,
        },
    }
```

In `build_trust_view`, after `recommendations` and `verification`, add:

```python
workbench = _workbench_summary(
    state,
    analysis_scope_plan,
    recommendations.get("confirmation_gate") if isinstance(recommendations, dict) else {},
    verification,
)
```

Add to return:

```python
"workbench": workbench,
```

Add empty `workbench` shape to `_empty_view`.

- [ ] **Step 3: Write UI tests that route actions are not primary**

Add to `tests/test_trust_inspector_ui.py`:

```python
def test_workbench_uses_context_confirmation_trust_sections():
    html = Path("src/data_agent/web/templates/index.html").read_text(encoding="utf-8")

    assert "workbench.current_context" in html
    assert "workbench.confirmations" in html
    assert "workbench.trust_evidence" in html
```

If the test file does not import `Path`, add:

```python
from pathlib import Path
```

- [ ] **Step 4: Update Web template and JS**

In `src/data_agent/web/templates/index.html`, change the right-side primary sections so they bind to:

```html
trustView.workbench.current_context
trustView.workbench.confirmations
trustView.workbench.trust_evidence
```

Keep existing history/routes data behind a collapsed detail area. Do not remove backend route fields in this task.

In `src/data_agent/web/static/js/app.js`, update any helper that assumes current route cards are primary so it handles missing or empty `trustView.routes` without errors.

- [ ] **Step 5: Run UI/backend tests**

```powershell
pytest tests/test_trust_view.py tests/test_trust_inspector_ui.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add src/data_agent/agent/trust_view.py src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js tests/test_trust_view.py tests/test_trust_inspector_ui.py
git commit -m "feat: reframe workbench as analysis context"
```

---

### Task 5: Regression Scenarios From Real Sessions

**Files:**
- Create: `tests/test_multifile_regressions.py`
- Modify only implementation files needed to make tests pass.

- [ ] **Step 1: Add regression tests for known failure modes**

Create `tests/test_multifile_regressions.py`:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.multi_file_scope import build_analysis_scope_plan
from data_agent.agent.route_capabilities import build_route_capabilities
from data_agent.agent.trust_view import build_trust_view


def test_coupon_user_aliases_do_not_become_independent_file_scope():
    state = AnalysisSessionState(session_id="a4237f2cee72", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [
        {
            "file_id": "orders",
            "filename": "0201到0510购卡用户付费数据.xlsx",
            "dataset": "购卡用户付费数据",
            "columns": ["order_id", "user_id", "支付时间", "实收金额"],
            "key_fields": ["order_id"],
            "time_fields": ["支付时间"],
        },
        {
            "file_id": "coupon",
            "filename": "代金券明细订单.xlsx",
            "dataset": "代金券明细订单",
            "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
            "key_fields": [],
            "time_fields": ["核销时间"],
        },
    ]

    plan = build_analysis_scope_plan(state, state.goal)

    assert [item["file_id"] for item in plan["included_files"]] == ["orders", "coupon"]
    assert plan["scope_status"] == "needs_confirmation"
    assert plan["assumptions"]


def test_pending_method_confirmation_is_visible_as_answerable_gate():
    state = AnalysisSessionState(session_id="6ed6b0a043fb", data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "method_retention_lifecycle",
        "status": "pending",
        "confirmation_type": "method_confirmation",
        "question": "是否按留存生命周期方法继续？",
        "blocking_reason": "该方法需要确认目标和窗口",
    }]

    view = build_trust_view(state)

    gate = view["recommendations"]["confirmation_gate"]
    assert gate["status"] == "needs_confirmation"
    assert gate["question"] == "是否按留存生命周期方法继续？"


def test_unsupported_retention_is_data_needed_not_directly_executable():
    state = AnalysisSessionState(session_id="route_guard", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [{
        "id": "route_retention",
        "dataset": "orders",
        "direction": "cohort",
        "label": "留存分析",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["exploratory"][0]["support_status"] == "needs_more_data"
```

- [ ] **Step 2: Run regression tests**

```powershell
pytest tests/test_multifile_regressions.py -q
```

Expected: pass after Tasks 1-4.

- [ ] **Step 3: Run broader suite**

```powershell
pytest tests/test_route_capabilities.py tests/test_analysis_entry.py tests/test_question_need_detector.py tests/test_data_bundle.py tests/test_multi_file_scope.py tests/test_trust_view.py tests/test_trust_inspector_ui.py tests/test_multifile_regressions.py -q
```

Expected: pass. If failures appear, fix the smallest contract mismatch and rerun the failed file first.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_multifile_regressions.py
git commit -m "test: cover multi-file scope regression cases"
```

---

## Self-Review

Spec coverage:

- Recommendation validity contract: Task 1 and Task 5.
- Existing capability reuse: Tasks 1, 2, and 4 modify existing modules rather than adding parallel engines.
- Confirmation contract: Task 2.
- Multi-file role, relationship, and scope plan: Task 3 and Task 5.
- Side workbench as information companion: Task 4.
- Context budget: Task 3 includes compact `context_budget` and no schema dumping into prompts.

Known implementation constraint:

- The first scope planner intentionally uses deterministic alias and theme rules. It is not a full semantic layer. This matches the current phase and should be expanded only after these contracts pass real-file regression tests.
