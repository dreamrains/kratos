# Workbench 行动看板（结论先行主视图）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "action board" conclusion-first primary view to the Workbench (已确认 / 仍不确定 / 建议下一步 / 为什么可以信任), state-derived, with the agent's full answer expandable, and demote the existing 4 diagnostic quadrants to a collapsible drill-down.

**Architecture:** A read-only projection. Backend: a new `build_action_board(state)` in `workbench_view.py` derives the 4 sub-sections from existing state (`evidence_records`, `verification_reports`, `route_capabilities`, data brief); `build_workbench_view` exposes it as `workbench.action_board`, and `build_trust_view` adds `workbench.full_answer` (last assistant message read from the saved conversation via `load_session` — no runtime change). Frontend: new `actionBoard()`/`fullAnswer()` Alpine helpers + a primary action-board block + an expandable full-answer block at the top of the `'current'` tab; the 4 existing sections move into a `<details>` drill-down. No new tab, no runtime/agent change.

**Tech Stack:** Python, pytest, Flask, Alpine.js + Tailwind (existing), marked.js (existing, `renderMarkdown`).

## Global Constraints

- **No runtime change.** Do not modify `loop.py` / `synthesis_policy.py` / tools. `action_board`/`full_answer` are read-only projections. (Spec §1, §7.)
- **No total score, non-blocking.** The action board only displays; it never gates behavior. (Spec §3.)
- **Reuse, don't rebuild.** Extend `build_workbench_view`; reuse `build_route_capabilities`, `build_user_data_brief`, `_flatten_limitations`, `_text`/`_int_value`, `renderMarkdown`. (Spec §7.)
- **`full_answer` source = saved conversation.** Read the last `assistant` message via `data_agent.session.history.load_session`; never store it on state. `null` when absent. (Spec §4.)
- **Display-only directions.** `next_steps` route items must not auto-submit chat (consistent with existing display-only route suggestions). (Spec §5.)
- **Mobile deferred.** Do not restructure the tab grid or add responsive work. (Spec §1.)
- **Lists capped at ≤6** to prevent noise; empty lists are valid. (Spec §3.)
- **Windows / UTF-8.** Chinese content throughout; `encoding="utf-8"` on file I/O.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/data_agent/agent/workbench_view.py` | Modify | Add `build_action_board(state)`; expose `action_board` in `build_workbench_view`. |
| `src/data_agent/agent/trust_view.py` | Modify | Add `full_answer` (last assistant from `load_session`) to the workbench; extend `_has_workbench_content`. |
| `src/data_agent/web/static/js/app.js` | Modify | Add `actionBoard()` / `fullAnswer()` helpers + `expandedFullAnswer` state. |
| `src/data_agent/web/templates/index.html` | Modify | Add action-board block + full-answer expand at top of `'current'` tab; wrap the 4 sections in a `<details>` drill-down. |
| `src/data_agent/web/static/css/app.css` | Modify | Minor: action-board card styling (reuse `.workbench-item`). |
| `tests/test_multifile_workbench_view.py` | Modify | `build_action_board` unit tests; update the existing workbench-key-set contract assertion. |
| `tests/test_trust_view.py` | Modify | `full_answer` derivation tests. |
| `tests/test_web_workbench_replacement.py` | Modify | Frontend substring contract tests for action board / full answer / drill-down. |
| `tests/test_web_workbench_action_board.py` | Create | HTTP test: `/api/sessions/<id>/trust` returns `action_board` + `full_answer` (new coverage). |

---

## Task 1: `build_action_board(state)` read model (pure, state-derived)

**Files:**
- Modify: `src/data_agent/agent/workbench_view.py` (add `build_action_board` + `_empty_action_board`)
- Test: `tests/test_multifile_workbench_view.py` (append)

**Interfaces:**
- Consumes: `state.evidence_records` (`[{claim, confidence, dataset, result_summary, limitations}]`), `state.verification_reports` (last item: `{overall_status, claim_count, failed_count, downgraded_count}`), `build_route_capabilities(state)` → `{executable, exploratory}`, `_data_understanding_section(state)` (brief with `unanswerable_questions`, `needed_confirmations`, `datasets`). Reuses module helpers `_list_attr`, `_list_items`, `_text_list`, `_text`, `_int_value`, `_flatten_limitations`.
- Produces: `build_action_board(state, *, capabilities=None) -> dict` → `{"confirmed":[...≤6], "uncertain":[...≤6], "next_steps":[...≤6], "trust_basis":{...}}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_multifile_workbench_view.py`:

```python
from types import SimpleNamespace

from data_agent.agent.workbench_view import build_action_board


def _ab_state(evidence, verification=None, route_proposals=None, bundles=None):
    return SimpleNamespace(
        evidence_records=evidence,
        verification_reports=verification or [],
        route_proposals=route_proposals or [],
        data_understanding_bundles=bundles or [],
        file_relationships=[],
        goal="评估省钱卡业务",
        data_state="data_loaded",
    )


def test_action_board_confirmed_and_uncertain_by_confidence():
    state = _ab_state(
        [
            {"claim": "购卡后消费下降30%", "confidence": "high", "dataset": "orders",
             "result_summary": "-30%", "limitations": []},
            {"claim": "复购意愿弱", "confidence": "medium", "dataset": "orders",
             "result_summary": "复购低", "limitations": ["样本仅1月"]},
            {"claim": "优惠券驱动复购", "confidence": "speculative", "dataset": "vouchers",
             "result_summary": "不确定", "limitations": []},
        ],
        verification=[{"overall_status": "pass_with_downgrades", "claim_count": 3,
                       "failed_count": 0, "downgraded_count": 1}],
    )
    ab = build_action_board(state)
    confirmed_claims = [c["claim"] for c in ab["confirmed"]]
    assert confirmed_claims == ["购卡后消费下降30%", "复购意愿弱"]  # high before medium
    assert ab["confirmed"][0]["confidence"] == "high"
    uncertain_labels = [u["label"] for u in ab["uncertain"]]
    assert "优惠券驱动复购" in uncertain_labels          # low/speculative claim
    assert any(u["reason"] == "limitation" for u in ab["uncertain"])  # limitation surfaced
    assert ab["uncertain"][-1]["label"] == "样本仅1月"
    tb = ab["trust_basis"]
    assert tb["evidence_count"] == 3
    assert tb["verification_status"] == "pass_with_downgrades"
    assert tb["downgraded_count"] == 1
    assert tb["failed_count"] == 0


def test_action_board_next_steps_from_routes_and_confirmations():
    state = _ab_state(
        [{"claim": "x", "confidence": "high", "dataset": "d", "result_summary": "", "limitations": []}],
        bundles=[{"id": "b1", "data_fingerprint": "f", "datasets": [{"dataset": "d"}],
                  "supported_questions": [], "unsupported_questions": ["还需渠道成本"],
                  "needed_confirmations": ["确认对比口径"]}],
        route_proposals=[],  # build_route_capabilities returns empty without real route shape
    )
    ab = build_action_board(state)
    # datasets_used derived from the brief; confirmations surface as next_steps
    assert "d" in ab["trust_basis"]["datasets_used"]
    kinds = {n["kind"] for n in ab["next_steps"]}
    assert "confirmation" in kinds


def test_action_board_empty_when_state_none():
    ab = build_action_board(None)
    assert ab["confirmed"] == [] and ab["uncertain"] == [] and ab["next_steps"] == []
    assert ab["trust_basis"]["verification_status"] == "not_run"
    assert ab["trust_basis"]["evidence_count"] == 0
```

> Note: `build_route_capabilities` and `build_user_data_brief` (via `_data_understanding_section`) read state defensively; empty `route_proposals` yields empty route directions, and a minimal bundle yields `datasets_used` + `needed_confirmations`. If `SimpleNamespace` lacks an attribute these helpers require, add it to `_ab_state` with a sensible empty default — the test must stay deterministic and not require a live agent.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_multifile_workbench_view.py -v -k action_board`
Expected: FAIL — `ImportError: cannot import name 'build_action_board'`.

- [ ] **Step 3: Implement `build_action_board`**

Add to `src/data_agent/agent/workbench_view.py` (below `build_multifile_workbench_view`):

```python
_ACTION_CONFIDENCE_ORDER = {"high": 0, "medium": 1}


def build_action_board(state: Any, *, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
    """Conclusion-first primary view: 已确认 / 仍不确定 / 建议下一步 / 为什么可以信任.

    Read-only projection from existing state. No total score, never blocks.
    """
    if state is None:
        return _empty_action_board()

    if capabilities is None:
        capabilities = build_route_capabilities(state)
    brief = _data_understanding_section(state)
    evidence = _list_attr(state, "evidence_records")
    verification_reports = _list_attr(state, "verification_reports")
    latest_verification = verification_reports[-1] if verification_reports else {}

    confirmed: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for item in evidence:
        claim = _text(item.get("claim"))
        if not claim:
            continue
        confidence = _text(item.get("confidence")) or "medium"
        if confidence in {"high", "medium"}:
            confirmed.append({
                "claim": claim,
                "confidence": confidence,
                "dataset": _text(item.get("dataset")),
                "summary": _text(item.get("result_summary")),
            })
        else:
            uncertain.append({
                "label": claim,
                "reason": "low_confidence",
                "detail": _text(item.get("result_summary")),
            })
    confirmed.sort(key=lambda e: _ACTION_CONFIDENCE_ORDER.get(e["confidence"], 2))
    confirmed = confirmed[:6]

    for limitation in _flatten_limitations(evidence):
        uncertain.append({"label": limitation, "reason": "limitation", "detail": limitation})
    for question in _text_list(brief.get("unanswerable_questions")):
        uncertain.append({"label": question, "reason": "data_gap", "detail": question})
    uncertain = uncertain[:6]

    next_steps: list[dict[str, Any]] = []
    for item in _list_items(capabilities.get("executable")) + _list_items(capabilities.get("exploratory")):
        direction = _text(item.get("direction") or item.get("route"))
        if not direction:
            continue
        next_steps.append({
            "direction": direction,
            "reason": _text(item.get("reason")) or "; ".join(_text_list(item.get("support_reasons"))),
            "kind": "route",
            "auto_submit": False,
        })
    for confirmation in _text_list(brief.get("needed_confirmations")):
        next_steps.append({"direction": confirmation, "reason": confirmation, "kind": "confirmation"})
    next_steps = next_steps[:6]

    trust_basis = {
        "evidence_count": len(evidence),
        "verified_claim_count": _int_value(
            latest_verification.get("claim_count"), fallback=len(evidence)
        ),
        "failed_count": _int_value(latest_verification.get("failed_count")),
        "downgraded_count": _int_value(latest_verification.get("downgraded_count")),
        "verification_status": _text(
            latest_verification.get("overall_status")
            or latest_verification.get("status")
            or "not_run"
        ),
        "datasets_used": [
            _text(d.get("dataset"))
            for d in _list_items(brief.get("datasets"))
            if _text(d.get("dataset"))
        ],
    }
    return {
        "confirmed": confirmed,
        "uncertain": uncertain,
        "next_steps": next_steps,
        "trust_basis": trust_basis,
    }


def _empty_action_board() -> dict[str, Any]:
    return {
        "confirmed": [],
        "uncertain": [],
        "next_steps": [],
        "trust_basis": {
            "evidence_count": 0,
            "verified_claim_count": 0,
            "failed_count": 0,
            "downgraded_count": 0,
            "verification_status": "not_run",
            "datasets_used": [],
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_multifile_workbench_view.py -v -k action_board`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/workbench_view.py tests/test_multifile_workbench_view.py
git commit -m "feat(workbench): action board read model (confirmed/uncertain/next_steps/trust_basis)"
```

---

## Task 2: Expose `action_board` + `full_answer` in the contract

**Files:**
- Modify: `src/data_agent/agent/workbench_view.py` (`build_workbench_view` — add `action_board`)
- Modify: `src/data_agent/agent/trust_view.py` (add `full_answer` via `load_session`; extend `_has_workbench_content`)
- Test: `tests/test_multifile_workbench_view.py` (update key-set assertion), `tests/test_trust_view.py` (full_answer tests)

**Interfaces:**
- Produces: `build_workbench_view(state)` now returns `{"action_board", "multifile_analysis", "details"}`. `build_trust_view(state, session_id)` sets `workbench["full_answer"]` (`str | None`).

- [ ] **Step 1: Write/extend the failing tests**

In `tests/test_multifile_workbench_view.py`, find the existing contract assertion (the test that asserts `set(view["workbench"]) == {"multifile_analysis", "details"}`) and update it to:

```python
    assert set(view["workbench"]) == {"action_board", "multifile_analysis", "details", "full_answer"}
    assert set(view["workbench"]["action_board"]) == {"confirmed", "uncertain", "next_steps", "trust_basis"}
```

Append to `tests/test_trust_view.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace


def _write_session(tmp_path, session_id, messages):
    sdir = tmp_path / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "meta.json").write_text(json.dumps({"project_name": "p"}, ensure_ascii=False), encoding="utf-8")
    (sdir / "conversation.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages),
        encoding="utf-8",
    )


def test_full_answer_is_last_assistant_message(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.agent.trust_view import build_trust_view

    monkeypatch.setattr(config, "_config", AgentConfig(SESSIONS_DIR=tmp_path / "sessions"))
    _write_session(tmp_path, "s1", [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "旧答案"},
        {"role": "user", "content": "再问"},
        {"role": "assistant", "content": "## 最新结论\n收入下降"},
    ])
    state = SimpleNamespace(evidence_records=[], verification_reports=[],
                            data_understanding_bundles=[], route_proposals=[],
                            file_relationships=[], goal="", data_state="data_loaded")
    view = build_trust_view(state, session_id="s1")
    assert view["workbench"]["full_answer"].startswith("## 最新结论")
    assert "收入下降" in view["workbench"]["full_answer"]


def test_full_answer_none_when_no_session_or_empty(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.agent.trust_view import build_trust_view

    monkeypatch.setattr(config, "_config", AgentConfig(SESSIONS_DIR=tmp_path / "sessions"))
    state = SimpleNamespace(evidence_records=[], verification_reports=[],
                            data_understanding_bundles=[], route_proposals=[],
                            file_relationships=[], goal="", data_state="data_loaded")
    assert build_trust_view(state, session_id="missing")["workbench"]["full_answer"] is None
    assert build_trust_view(state, session_id="")["workbench"]["full_answer"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_multifile_workbench_view.py tests/test_trust_view.py -v`
Expected: FAIL — workbench key set mismatch / `full_answer` KeyError.

- [ ] **Step 3: Expose `action_board` in `build_workbench_view`**

In `src/data_agent/agent/workbench_view.py`, edit `build_workbench_view`. The `state is None` branch becomes:

```python
    if state is None:
        return {
            "action_board": build_action_board(None),
            "multifile_analysis": build_multifile_workbench_view(None, capabilities={}),
            "details": _details_section(None, {}, {}),
        }
```

And the main return becomes:

```python
    return {
        "action_board": build_action_board(state, capabilities=capabilities),
        "multifile_analysis": build_multifile_workbench_view(state, capabilities=capabilities),
        "details": _details_section(state, scope_plan, confirmation),
    }
```

(`capabilities` is already computed at the top of `build_workbench_view`; pass it through so `build_action_board` doesn't recompute.)

- [ ] **Step 4: Add `full_answer` in `build_trust_view`**

In `src/data_agent/agent/trust_view.py`, edit `build_trust_view` to populate `full_answer`, and add the helper:

```python
def build_trust_view(state: Any, session_id: str | None = None) -> dict[str, Any]:
    """Return the current Workbench without legacy Trust Inspector projections."""
    workbench = build_workbench_view(state)
    workbench["full_answer"] = _latest_full_answer(session_id)
    if state is None:
        return _view(
            status="empty",
            session_id=session_id or "",
            updated_at="",
            workbench=workbench,
        )

    status = "ready" if _has_workbench_content(state, workbench) else "empty"
    return _view(
        status=status,
        session_id=session_id or _text(getattr(state, "session_id", "")),
        updated_at=_text(getattr(state, "updated_at", "")),
        workbench=workbench,
    )


def _latest_full_answer(session_id: str | None) -> str | None:
    """Last assistant message from the saved conversation. None if unavailable.

    Read-only: never writes to state. Source = data_agent.session.history.load_session.
    """
    if not session_id:
        return None
    try:
        from data_agent.session.history import load_session

        session = load_session(session_id)
    except Exception:
        return None
    if not session:
        return None
    for message in reversed(session.get("messages") or []):
        if message.get("role") == "assistant":
            content = _text(message.get("content"))
            if content:
                return content
    return None
```

Then extend `_has_workbench_content` so a populated action board marks the view ready. Add before the final `return bool(...)`:

```python
    action = workbench.get("action_board") or {}
    if action.get("confirmed") or action.get("uncertain") or action.get("next_steps"):
        return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_multifile_workbench_view.py tests/test_trust_view.py tests/test_web_workbench_replacement.py -v`
Expected: PASS (contract now includes `action_board` + `full_answer`; existing tests still green).

- [ ] **Step 6: Commit**

```bash
git add src/data_agent/agent/workbench_view.py src/data_agent/agent/trust_view.py tests/test_multifile_workbench_view.py tests/test_trust_view.py
git commit -m "feat(workbench): expose action_board and full_answer in the trust/workbench contract"
```

---

## Task 3: HTTP test — `/api/sessions/<id>/trust` returns `action_board` + `full_answer`

**Files:**
- Create: `tests/test_web_workbench_action_board.py`

**Interfaces:** Consumes Task 2's contract. Produces: confidence that the endpoint serves both new fields end-to-end (this endpoint had no HTTP-level coverage before).

- [ ] **Step 1: Write the test**

Create `tests/test_web_workbench_action_board.py`:

```python
"""HTTP contract: the trust endpoint serves action_board + full_answer."""

import json

from data_agent.web.app import create_app


def _seed_session(tmp_path, session_id, messages):
    sdir = tmp_path / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "meta.json").write_text(json.dumps({"project_name": "p"}, ensure_ascii=False), encoding="utf-8")
    (sdir / "conversation.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages),
        encoding="utf-8",
    )
    # minimal analysis_state.json so the endpoint loads a non-None state
    state = {
        "session_id": session_id,
        "evidence_records": [
            {"claim": "收入下降", "confidence": "high", "dataset": "d", "result_summary": "-10%", "limitations": []},
        ],
        "verification_reports": [],
        "data_understanding_bundles": [],
        "route_proposals": [],
        "file_relationships": [],
        "data_state": "data_loaded",
    }
    (sdir / "analysis_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def test_trust_endpoint_returns_action_board_and_full_answer(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig

    monkeypatch.setattr(config, "_config", AgentConfig(SESSIONS_DIR=tmp_path / "sessions"))
    _seed_session(tmp_path, "s1", [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "## 结论\n收入下降"},
    ])

    client = create_app().test_client()
    resp = client.get("/api/sessions/s1/trust")
    assert resp.status_code == 200
    data = resp.get_json()
    workbench = data["workbench"]
    assert set(["action_board", "full_answer", "multifile_analysis", "details"]).issubset(workbench.keys())
    assert workbench["action_board"]["confirmed"][0]["claim"] == "收入下降"
    assert workbench["full_answer"].startswith("## 结论")
```

> If `create_app` lives elsewhere (e.g. `data_agent.web.create_app`), adjust the import to match the existing `tests/test_web_workbench_parity.py` pattern — copy the app-construction import verbatim from that file.

- [ ] **Step 2: Run test to verify it passes (no new backend work needed — Task 2 wired it)**

Run: `uv run pytest tests/test_web_workbench_action_board.py -v`
Expected: PASS. (If the app factory import differs, fix the import only.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_workbench_action_board.py
git commit -m "test(workbench): trust endpoint serves action_board and full_answer"
```

---

## Task 4: Frontend — action board primary view + full-answer expand + demote 4 sections

**Files:**
- Modify: `src/data_agent/web/static/js/app.js` (add `actionBoard()`, `fullAnswer()`, `expandedFullAnswer`)
- Modify: `src/data_agent/web/templates/index.html` (action board block + full-answer block at top of `'current'` tab; wrap the 4 sections in `<details>`)
- Modify: `src/data_agent/web/static/css/app.css` (minor action-board card styling)
- Test: `tests/test_web_workbench_replacement.py` (extend substring assertions)

**Interfaces:** Consumes `workbench.action_board` and `workbench.full_answer` (Task 2). Produces the user-facing primary view.

- [ ] **Step 1: Write the failing frontend contract tests**

Append to `tests/test_web_workbench_replacement.py` (reuse its existing `_index_html()` / `_app_js()` helpers — do not redefine them):

```python
def test_action_board_is_primary_surface_with_helpers():
    html = _index_html()
    js = _app_js()
    assert 'data-testid="action-board"' in html
    assert 'data-testid="action-board-confirmed"' in html
    assert 'data-testid="action-board-uncertain"' in html
    assert 'data-testid="action-board-next-steps"' in html
    assert "actionBoard()" in js and "workbench?.action_board" in js


def test_full_answer_block_uses_markdown_render():
    html = _index_html()
    js = _app_js()
    assert 'data-testid="workbench-full-answer"' in html
    assert "fullAnswer()" in js and "workbench?.full_answer" in js
    assert "renderMarkdown(fullAnswer()" in html


def test_four_sections_demoted_to_drill_down():
    html = _index_html()
    assert 'data-testid="workbench-breakdown"' in html
    # the 4 primary sections still exist, now inside the breakdown <details>
    for testid in (
        "multifile-data-understanding",
        "multifile-relationships",
        "multifile-analysis-directions",
        "multifile-answer-coverage",
    ):
        assert f'data-testid="{testid}"' in html
```

Also: the existing test that asserts `html.count("workbench-primary-section") == 4` must be updated to `== 5` (the action board is also a primary section) — find it in `test_web_workbench_replacement.py` and change the `4` to `5`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_web_workbench_replacement.py -v`
Expected: FAIL — the new `action-board` / `workbench-full-answer` / `workbench-breakdown` substrings are absent; the `== 4` count assertion fails once the block is added.

- [ ] **Step 3: Add the JS helpers + state**

In `src/data_agent/web/static/js/app.js`:
- In the `chatApp()` state object (near the other `sessionSidePanelTab`/`trustView` declarations, ~line 76-81), add:

```javascript
        expandedFullAnswer: false,
```

- Alongside the other `multifile*()` accessor helpers (near `multifileWorkbench()` ~line 1226), add:

```javascript
    actionBoard()   { return this.trustView?.workbench?.action_board || {}; }
    fullAnswer()    { return this.trustView?.workbench?.full_answer || ''; }
```

- [ ] **Step 4: Add the action-board + full-answer blocks to the template**

In `src/data_agent/web/templates/index.html`, locate the `'current'` tab body container (`<div class="flex-1 overflow-y-auto p-4 space-y-5" ...>`, ~line 534). Insert this block as its **first child**, before the existing 4 `<section class="trust-section workbench-primary-section" data-testid="multifile-...">` sections:

```html
        <!-- 行动看板（结论先行主视图） -->
        <section class="trust-section workbench-primary-section" data-testid="action-board"
                 x-show="sessionSidePanelTab === 'current'">
          <h4 class="text-sm font-semibold ...">结论与下一步</h4>

          <div class="grid grid-cols-1 gap-3 mt-2">
            <div data-testid="action-board-confirmed">
              <div class="text-xs font-semibold ...">已确认</div>
              <template x-for="(c, i) in actionBoard().confirmed" :key="'conf-'+i">
                <div class="workbench-item">
                  <div class="text-sm font-medium" x-text="c.claim"></div>
                  <div class="text-xs ..."><span x-text="c.confidence"></span><span x-show="c.dataset"> · </span><span x-text="c.dataset"></span></div>
                </div>
              </template>
              <div x-show="!actionBoard().confirmed.length" class="text-xs ...">暂无已确认结论</div>
            </div>

            <div data-testid="action-board-uncertain">
              <div class="text-xs font-semibold ...">仍不确定</div>
              <template x-for="(u, i) in actionBoard().uncertain" :key="'unc-'+i">
                <div class="workbench-item">
                  <div class="text-sm" x-text="u.label"></div>
                  <div class="text-xs ..." x-text="u.reason"></div>
                </div>
              </template>
              <div x-show="!actionBoard().uncertain.length" class="text-xs ...">暂无不确定项</div>
            </div>

            <div data-testid="action-board-next-steps">
              <div class="text-xs font-semibold ...">建议下一步</div>
              <template x-for="(n, i) in actionBoard().next_steps" :key="'ns-'+i">
                <div class="workbench-item">
                  <div class="text-sm" x-text="n.direction"></div>
                  <div class="text-xs ..." x-text="n.kind"></div>
                </div>
              </template>
              <div x-show="!actionBoard().next_steps.length" class="text-xs ...">暂无建议</div>
            </div>

            <div data-testid="action-board-trust" class="text-xs ...">
              <span x-text="`${actionBoard().trust_basis.evidence_count||0} 条证据`"></span>
              · 验证
              <span x-text="actionBoard().trust_basis.verification_status || '未运行'"></span>
            </div>
          </div>
        </section>

        <!-- 完整分析（可展开） -->
        <section class="trust-section" data-testid="workbench-full-answer"
                 x-show="sessionSidePanelTab === 'current'">
          <button type="button" class="text-sm font-semibold ..." @click="expandedFullAnswer = !expandedFullAnswer">
            <span x-text="expandedFullAnswer ? '收起完整分析' : '查看完整分析'"></span>
          </button>
          <div x-show="expandedFullAnswer" x-cloak
               class="prose prose-sm dark:prose-invert max-w-none leading-7 mt-2"
               x-html="renderMarkdown(fullAnswer(), null)"></div>
          <div x-show="!fullAnswer()" class="text-xs ...">暂无完整分析</div>
        </section>
```

- [ ] **Step 5: Demote the 4 sections into a collapsible drill-down**

Still in `index.html`, wrap the existing 4 `<section ... data-testid="multifile-...">` blocks (data-understanding, relationships, analysis-directions, answer-coverage) in a single `<details>`:

```html
        <details class="trust-section" data-testid="workbench-breakdown"
                 x-show="sessionSidePanelTab === 'current'">
          <summary class="text-sm font-semibold ... cursor-pointer">数据明细（下钻）</summary>
          <div class="space-y-4 mt-2">
            <!-- ...the 4 existing <section data-testid="multifile-..."> blocks, unchanged... -->
          </div>
        </details>
```

Do not modify the 4 inner sections' content — only relocate them inside `<details>`. Keep their `x-show="sessionSidePanelTab === 'current'"` guards.

- [ ] **Step 6: Minor CSS (reuse existing tokens)**

In `src/data_agent/web/static/css/app.css`, the `.workbench-item` class already styles bordered cards — reuse it (no new class needed). If the action-board grid needs spacing, add only:

```css
.action-board-grid { display: grid; grid-template-columns: 1fr; gap: 0.75rem; }
```

and add `action-board-grid` to the `<div class="grid grid-cols-1 gap-3 mt-2">` from Step 4 if Tailwind utility classes are insufficient. (Prefer the existing Tailwind utilities; only add this if needed.)

- [ ] **Step 7: Run frontend tests + JS syntax check**

Run: `uv run pytest tests/test_web_workbench_replacement.py tests/test_multifile_workbench_view.py tests/test_trust_view.py tests/test_web_workbench_action_board.py -v`
Expected: PASS.
Run: `node -c src/data_agent/web/static/js/app.js`
Expected: no output, exit 0.

- [ ] **Step 8: Commit**

```bash
git add src/data_agent/web/static/js/app.js src/data_agent/web/templates/index.html src/data_agent/web/static/css/app.css tests/test_web_workbench_replacement.py
git commit -m "feat(workbench): action board primary view with full-answer expand and drill-down"
```

---

## Execution Order

Sequential: Task 1 → Task 2 → Task 3 → Task 4. (Task 3 depends on Task 2's contract; Task 4 depends on Tasks 2–3's API shape.)

## Completion Criteria

- `build_action_board(state)` derives confirmed/uncertain/next_steps/trust_basis from fixture state (unit tests green).
- `build_workbench_view` returns `action_board`; `build_trust_view` returns `full_answer` (last assistant) + marks `ready` when the action board has content.
- `/api/sessions/<id>/trust` returns `action_board` + `full_answer` (HTTP test green — new coverage).
- Frontend renders the action board as the primary block of the `'current'` tab, with an expandable full-answer (markdown via `renderMarkdown`), and the 4 sections collapsed under `workbench-breakdown`; existing web workbench tests updated and green.
- Non-slippage: no change to `loop.py` / `synthesis_policy.py` / tools (`rg "action_board|full_answer|build_action_board" src/data_agent/agent/loop.py src/data_agent/agent/synthesis_policy.py` returns nothing); `next_steps` route items are display-only (`auto_submit: false`).

## Self-Review Notes

- **Spec coverage:** §3 derivation → Task 1 (`build_action_board`); §4 API (`action_board` + `full_answer`) → Task 2 + Task 3; §5 frontend (primary action board, full-answer expand, 4 sections → drill-down, display-only) → Task 4; §6 testing → each task's TDD steps; §1/§7 non-goals (no runtime change, mobile deferred, reuse) → Global Constraints + non-slippage check.
- **Type consistency:** `build_action_board` returns `{confirmed, uncertain, next_steps, trust_basis}`; Task 1 tests, Task 2 contract assertion, and Task 4 frontend all reference these exact keys. `full_answer` is `str | None` everywhere (helper, contract, HTTP, frontend `fullAnswer()`). `actionBoard()`/`fullAnswer()` helper names match the frontend tests and the `multifile*()` helper convention.
- **Existing-test impact:** Task 2 updates the workbench key-set assertion (`{"multifile_analysis","details"}` → adds `action_board`,`full_answer`); Task 4 updates the `workbench-primary-section` count (`4` → `5`). Both called out in-task.
