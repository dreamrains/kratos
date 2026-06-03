# Trustworthy Loop Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the trustworthy analysis workflow building blocks to the real `AgentLoop` so normal turns refine intent from loaded data and verify recorded evidence before final synthesis.

**Architecture:** Add one small runtime glue module, `data_agent.agent.trust_workflow_runtime`, that owns deterministic intent refinement and verification report creation. Keep `loop.py` responsible for sequencing only: call refinement during turn preparation and call verification before deriving the synthesis policy.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing `AnalysisSessionState`, `TurnIntent`, `refine_intent_with_data`, `verify_analysis_claims`, and `AgentLoop` test harnesses.

---

## File Structure

- Create: `src/data_agent/agent/trust_workflow_runtime.py`
  - Responsibility: runtime-safe glue around intent refinement and verification.
  - Public functions:
    - `refine_turn_intent_with_state(user_input, intent, state) -> TurnIntent`
    - `maybe_verify_turn_claims(user_input, state, *, force=False) -> dict | None`
  - Private helpers:
    - `_list_attr(state, name)`
    - `_extract_claims(evidence_records)`
    - `_evidence_signature(state, evidence_records)`
    - `_compact_verification_ref(report, signature)`
    - `_latest_verification_signature(state)`

- Modify: `src/data_agent/agent/loop.py`
  - Import runtime helpers inside methods to keep import cost low.
  - In `_prepare_analysis_turn`, load state before storing intent and refine the base intent with trustworthy state refs.
  - In `_reset_turn_tracking`, reset `_turn_verification_injected`.
  - In `_maybe_inject_synthesis_policy`, create a verification report before calling `derive_synthesis_policy`.

- Create: `tests/test_trust_workflow_runtime.py`
  - Covers helper behavior without constructing the full agent loop.

- Modify: `tests/test_execution_control.py`
  - Adds loop-level regression tests for refined intent and verification-aware synthesis injection.

---

### Task 1: Runtime Intent Refinement Helper

**Files:**
- Create: `src/data_agent/agent/trust_workflow_runtime.py`
- Test: `tests/test_trust_workflow_runtime.py`

- [ ] **Step 1: Write failing runtime intent refinement tests**

Create `tests/test_trust_workflow_runtime.py` with these tests and shared helpers:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.trust_workflow_runtime import refine_turn_intent_with_state


def _intent(intent_type="intent_negotiation", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "vague",
        "data_state": "data_loaded",
        "analysis_stage": "discover",
        "recommended_action": "guide_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


def test_runtime_refines_vague_intent_with_state_routes():
    state = AnalysisSessionState(session_id="runtime_refine_routes")
    state.route_proposals = [
        {"id": "route_trend", "label": "Revenue trend", "direction": "trend"},
        {"id": "route_compare", "label": "Period compare", "direction": "period_compare"},
    ]

    refined = refine_turn_intent_with_state("help me explore this dataset", _intent(), state)

    assert refined.recommended_action == "guide_analysis"
    assert refined.ambiguities[-1]["field"] == "analysis_route"
    assert refined.ambiguities[-1]["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
        {"label": "Period compare", "direction": "period_compare"},
    ]


def test_runtime_marks_unsupported_retention_request_as_insufficient_data():
    state = AnalysisSessionState(session_id="runtime_refine_retention")
    state.dataset_contracts = [{
        "id": "contract_orders",
        "unsupported_analyses": [
            {"type": "user_level_retention", "reason": "missing user id"},
        ],
    }]
    base = _intent(
        "directed_analysis",
        clarity="clear",
        analysis_stage="execute",
        recommended_action="run_analysis",
    )

    refined = refine_turn_intent_with_state("analyze cohort retention", base, state)

    assert refined.clarity == "clarification_needed"
    assert refined.recommended_action == "request_data"
    assert refined.execution_readiness == "insufficient_data"
    assert refined.ambiguities[-1]["field"] == "unsupported_analysis"


def test_runtime_refinement_falls_back_when_state_refs_are_malformed():
    class MalformedState:
        dataset_contracts = {"not": "a list"}
        route_proposals = {"not": "a list"}

    base = _intent()

    refined = refine_turn_intent_with_state("help me explore", base, MalformedState())

    assert refined is base
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py -q
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'data_agent.agent.trust_workflow_runtime'`.

- [ ] **Step 3: Implement the runtime refinement helper**

Create `src/data_agent/agent/trust_workflow_runtime.py`:

```python
"""Runtime glue for trustworthy analysis workflow integration."""

from __future__ import annotations

from typing import Any

from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.utils.logging import get_logger


logger = get_logger("trust_workflow_runtime")


def refine_turn_intent_with_state(user_input: str, intent: TurnIntent, state: Any) -> TurnIntent:
    """Refine a turn intent using trustworthy state refs without breaking the loop."""

    try:
        return refine_intent_with_data(
            user_input=user_input,
            intent=intent,
            dataset_contracts=_list_attr(state, "dataset_contracts"),
            route_proposals=_list_attr(state, "route_proposals"),
        )
    except Exception as exc:
        logger.warning(
            "Trust workflow intent refinement skipped",
            extra={"extra_data": {"error": str(exc)}},
        )
        return intent


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
```

- [ ] **Step 4: Run runtime refinement tests**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run existing intent refinement tests**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_intent_refinement.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src\data_agent\agent\trust_workflow_runtime.py tests\test_trust_workflow_runtime.py
git commit -m "feat: add trust workflow runtime refinement"
```

Expected: commit succeeds.

---

### Task 2: Runtime Verification Report Helper

**Files:**
- Modify: `src/data_agent/agent/trust_workflow_runtime.py`
- Modify: `tests/test_trust_workflow_runtime.py`

- [ ] **Step 1: Add failing verification runtime tests**

Append to `tests/test_trust_workflow_runtime.py`:

```python
from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims


def test_runtime_generates_compact_verification_report_from_evidence_records():
    state = AnalysisSessionState(session_id="runtime_verify")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12% from 100 to 112",
        "confidence": "high",
        "limitations": [],
    }]
    state.route_proposals = [{"id": "route_trend", "direction": "trend"}]

    ref = maybe_verify_turn_claims("summarize revenue", state)

    assert ref is not None
    assert ref["id"].startswith("verify_")
    assert ref["overall_status"] == "pass"
    assert ref["claim_count"] == 1
    assert ref["failed_count"] == 0
    assert ref["downgraded_count"] == 0
    assert ref["evidence_signature"] == "ev_1|routes:route_trend|cleaning:"
    assert state.verification_reports[-1] == ref


def test_runtime_verification_deduplicates_latest_evidence_signature():
    state = AnalysisSessionState(session_id="runtime_verify_dedupe")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12%",
        "confidence": "high",
    }]

    first = maybe_verify_turn_claims("summarize revenue", state)
    second = maybe_verify_turn_claims("summarize revenue again", state)

    assert first is not None
    assert second is None
    assert len(state.verification_reports) == 1


def test_runtime_verification_skips_when_no_claims_are_available():
    state = AnalysisSessionState(session_id="runtime_verify_empty")
    state.evidence_records = [{"id": "ev_no_claim", "result_summary": "summary only"}]

    ref = maybe_verify_turn_claims("summarize", state)

    assert ref is None
    assert state.verification_reports == []


def test_runtime_verification_force_overrides_signature_dedupe():
    state = AnalysisSessionState(session_id="runtime_verify_force")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12%",
        "confidence": "high",
    }]

    first = maybe_verify_turn_claims("summarize revenue", state)
    second = maybe_verify_turn_claims("summarize revenue again", state, force=True)

    assert first is not None
    assert second is not None
    assert len(state.verification_reports) == 1
    assert state.verification_reports[-1]["id"] == second["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `maybe_verify_turn_claims`.

- [ ] **Step 3: Implement verification helper and private helpers**

Replace `src/data_agent/agent/trust_workflow_runtime.py` with:

```python
"""Runtime glue for trustworthy analysis workflow integration."""

from __future__ import annotations

from typing import Any

from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.agent.verification import verify_analysis_claims
from data_agent.utils.logging import get_logger


logger = get_logger("trust_workflow_runtime")


def refine_turn_intent_with_state(user_input: str, intent: TurnIntent, state: Any) -> TurnIntent:
    """Refine a turn intent using trustworthy state refs without breaking the loop."""

    try:
        return refine_intent_with_data(
            user_input=user_input,
            intent=intent,
            dataset_contracts=_list_attr(state, "dataset_contracts"),
            route_proposals=_list_attr(state, "route_proposals"),
        )
    except Exception as exc:
        logger.warning(
            "Trust workflow intent refinement skipped",
            extra={"extra_data": {"error": str(exc)}},
        )
        return intent


def maybe_verify_turn_claims(user_input: str, state: Any, *, force: bool = False) -> dict[str, Any] | None:
    """Create one compact verification report for recorded evidence claims."""

    try:
        evidence_records = _list_attr(state, "evidence_records")
        claims = _extract_claims(evidence_records)
        if not claims:
            return None

        signature = _evidence_signature(state, evidence_records)
        if not force and _latest_verification_signature(state) == signature:
            return None

        report = verify_analysis_claims(
            claims=claims,
            evidence_records=evidence_records,
            route_proposals=_list_attr(state, "route_proposals"),
            cleaning_logs=_list_attr(state, "cleaning_logs"),
        )
        ref = _compact_verification_ref(report, signature)
        add_ref = getattr(state, "add_verification_report_ref", None)
        if callable(add_ref):
            stored = add_ref(ref)
        else:
            reports = getattr(state, "verification_reports", None)
            if isinstance(reports, list):
                reports.append(ref)
            stored = ref
        save = getattr(state, "save", None)
        if callable(save):
            save()
        return stored
    except Exception as exc:
        logger.warning(
            "Trust workflow verification skipped",
            extra={"extra_data": {"error": str(exc), "user_input": (user_input or "")[:200]}},
        )
        return None


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_claims(evidence_records: list[dict[str, Any]]) -> list[str]:
    claims: list[str] = []
    for record in evidence_records:
        claim = record.get("claim")
        if isinstance(claim, str) and claim.strip():
            claims.append(claim.strip())
    return claims


def _evidence_signature(state: Any, evidence_records: list[dict[str, Any]]) -> str:
    evidence_ids = [str(record.get("id") or index) for index, record in enumerate(evidence_records)]
    route_ids = [str(route.get("id")) for route in _list_attr(state, "route_proposals") if route.get("id")]
    cleaning_ids = [str(log.get("id")) for log in _list_attr(state, "cleaning_logs") if log.get("id")]
    return "|".join(evidence_ids) + "|routes:" + ",".join(route_ids) + "|cleaning:" + ",".join(cleaning_ids)


def _latest_verification_signature(state: Any) -> str | None:
    reports = _list_attr(state, "verification_reports")
    if not reports:
        return None
    signature = reports[-1].get("evidence_signature")
    return str(signature) if signature else None


def _compact_verification_ref(report: dict[str, Any], signature: str) -> dict[str, Any]:
    checks = report.get("claim_checks") if isinstance(report, dict) else []
    if not isinstance(checks, list):
        checks = []
    failed_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "fail")
    downgraded_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "downgraded")
    return {
        "id": "verify_" + str(report.get("id") or "")[:16],
        "source_report_id": report.get("id"),
        "overall_status": report.get("overall_status", "unknown"),
        "claim_count": len(checks),
        "failed_count": failed_count,
        "downgraded_count": downgraded_count,
        "evidence_signature": signature,
        "route_proposal_ids": list(report.get("route_proposal_ids") or []),
    }
```

- [ ] **Step 4: Run runtime tests**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Run verification and state tests**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_verification_layer.py tests\test_analysis_state_v2.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add src\data_agent\agent\trust_workflow_runtime.py tests\test_trust_workflow_runtime.py
git commit -m "feat: add runtime verification reports"
```

Expected: commit succeeds.

---

### Task 3: Loop Intent Refinement Integration

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Modify: `tests/test_execution_control.py`

- [ ] **Step 1: Add failing loop intent refinement regression test**

Append this test to `tests/test_execution_control.py`:

```python
def test_prepare_analysis_turn_stores_refined_intent_from_route_proposals(monkeypatch):
    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)
    monkeypatch.setattr(AnalysisFlowController, "activate_tool_groups", lambda self, registry, intent, state, user_input: [])

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_refined_intent", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_refined_intent")
    state.route_proposals = [{"id": "route_trend", "label": "Revenue trend", "direction": "trend"}]
    ctx.analysis_state = state
    loop = AgentLoop(client=object(), session_id="loop_refined_intent")
    loop.context = ctx

    with use_agent_context(ctx):
        loop._prepare_analysis_turn("help me explore this dataset")

    assert loop.context.turn_intent.ambiguities[-1]["field"] == "analysis_route"
    assert loop._last_turn_intent.ambiguities[-1]["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
    ]
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py::test_prepare_analysis_turn_stores_refined_intent_from_route_proposals -q
```

Expected: FAIL because `_prepare_analysis_turn` stores the unrefined intent.

- [ ] **Step 3: Modify `_prepare_analysis_turn` to refine after state load**

In `src/data_agent/agent/loop.py`, change the middle of `_prepare_analysis_turn` from:

```python
        intent = plan_turn_intent(user_input, session_ctx)
        self.context.turn_intent = intent
        self._last_turn_intent = intent
        controller = AnalysisFlowController(self.session_id, self.context.project_name)
        self._flow_controller = controller
        state = self.context.analysis_state if self.context.analysis_state is not None else controller.load_state()
        self.context.analysis_state = state
        controller.prepare_turn(state, intent, user_input=user_input, dataset_profile=session_ctx)
```

to:

```python
        intent = plan_turn_intent(user_input, session_ctx)
        controller = AnalysisFlowController(self.session_id, self.context.project_name)
        self._flow_controller = controller
        state = self.context.analysis_state if self.context.analysis_state is not None else controller.load_state()
        self.context.analysis_state = state
        try:
            from data_agent.agent.trust_workflow_runtime import refine_turn_intent_with_state

            intent = refine_turn_intent_with_state(user_input, intent, state)
        except Exception as exc:
            logger.warning(
                "Trust workflow loop intent refinement skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
        self.context.turn_intent = intent
        self._last_turn_intent = intent
        controller.prepare_turn(state, intent, user_input=user_input, dataset_profile=session_ctx)
```

- [ ] **Step 4: Run the loop intent test**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py::test_prepare_analysis_turn_stores_refined_intent_from_route_proposals -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run focused loop and intent suites**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py tests\test_intent_refinement.py tests\test_trust_workflow_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src\data_agent\agent\loop.py tests\test_execution_control.py
git commit -m "feat: refine loop intent with trust workflow state"
```

Expected: commit succeeds.

---

### Task 4: Loop Verification Before Synthesis Integration

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Modify: `tests/test_execution_control.py`

- [ ] **Step 1: Add failing verification-before-synthesis loop test**

Append this test to `tests/test_execution_control.py`:

```python
def test_synthesis_policy_injection_creates_verification_report_first(monkeypatch):
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
    ctx = AgentContext(session_id="loop_verify_before_synthesis", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_verify_before_synthesis")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention follows a power-law curve",
        "result_summary": "R(t)=0.1917*t^(-0.7335), R2=0.9743",
        "confidence": "high",
        "limitations": "Aggregated data only",
        "method": "log-linear least squares",
    }]
    ctx.analysis_state = state
    ctx.user_quality_requirements = ""
    loop = AgentLoop(client=object(), session_id="loop_verify_before_synthesis")
    loop.context = ctx
    loop._last_turn_intent = intent
    loop._reset_turn_tracking()

    with use_agent_context(ctx):
        loop._maybe_inject_synthesis_policy("summarize the retention formula")

    assert state.verification_reports
    assert state.verification_reports[-1]["overall_status"] == "pass"
    assert loop._turn_verification_injected is True
    assert loop._turn_synthesis_policy_injected is True
    assert "<synthesis_policy" in loop._turn_synthesis_policy_instruction
```

- [ ] **Step 2: Add failing verification downgrade policy test**

Append this test to `tests/test_execution_control.py`:

```python
def test_synthesis_policy_instruction_reflects_failed_runtime_verification(monkeypatch):
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
    ctx = AgentContext(session_id="loop_failed_verification_policy", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_failed_verification_policy")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention rose 500%",
        "result_summary": "Retention fell from 30% to 20%",
        "confidence": "high",
    }]
    ctx.analysis_state = state
    ctx.user_quality_requirements = ""
    loop = AgentLoop(client=object(), session_id="loop_failed_verification_policy")
    loop.context = ctx
    loop._last_turn_intent = intent
    loop._reset_turn_tracking()

    with use_agent_context(ctx):
        loop._maybe_inject_synthesis_policy("summarize retention")

    assert state.verification_reports[-1]["overall_status"] == "fail"
    assert "verification status fail" in loop._turn_synthesis_policy_instruction.lower()
    assert "decision_recommendation" in loop._turn_synthesis_policy_instruction
    assert "suppressed" in loop._turn_synthesis_policy_instruction.lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py::test_synthesis_policy_injection_creates_verification_report_first tests\test_execution_control.py::test_synthesis_policy_instruction_reflects_failed_runtime_verification -q
```

Expected: FAIL because `_maybe_inject_synthesis_policy` does not create verification reports and `_turn_verification_injected` does not exist.

- [ ] **Step 4: Reset turn verification tracking**

In `src/data_agent/agent/loop.py`, change `_reset_turn_tracking` from:

```python
    def _reset_turn_tracking(self) -> None:
        self._turn_tools_used = []
        self._turn_loaded_data = False
        self._turn_final_guard_injected = False
        self._turn_synthesis_policy_injected = False
        self._turn_synthesis_policy_instruction = ""
```

to:

```python
    def _reset_turn_tracking(self) -> None:
        self._turn_tools_used = []
        self._turn_loaded_data = False
        self._turn_final_guard_injected = False
        self._turn_verification_injected = False
        self._turn_synthesis_policy_injected = False
        self._turn_synthesis_policy_instruction = ""
```

- [ ] **Step 5: Call verification helper before deriving synthesis policy**

In `src/data_agent/agent/loop.py`, insert this block in `_maybe_inject_synthesis_policy` after the `if not evidence: return` guard and before importing `synthesis_policy`:

```python
        if not getattr(self, "_turn_verification_injected", False):
            try:
                from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims

                maybe_verify_turn_claims(user_input, state)
                self._turn_verification_injected = True
            except Exception as exc:
                logger.warning(
                    "Trust workflow loop verification skipped",
                    extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
                )
```

- [ ] **Step 6: Run new loop verification tests**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py::test_synthesis_policy_injection_creates_verification_report_first tests\test_execution_control.py::test_synthesis_policy_instruction_reflects_failed_runtime_verification -q
```

Expected: `2 passed`.

- [ ] **Step 7: Run focused synthesis and loop suites**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_execution_control.py tests\test_synthesis_policy.py tests\test_verification_layer.py tests\test_trust_workflow_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add src\data_agent\agent\loop.py tests\test_execution_control.py
git commit -m "feat: verify evidence before loop synthesis"
```

Expected: commit succeeds.

---

### Task 5: Final Integration Verification

**Files:**
- Modify only if tests expose a real defect in changed files.

- [ ] **Step 1: Run the trustworthy workflow focused suite**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_trust_workflow_runtime.py tests\test_intent_refinement.py tests\test_verification_layer.py tests\test_synthesis_policy.py tests\test_analysis_state_v2.py tests\test_trustworthy_workflow_mvp.py tests\test_execution_control.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the prior core suite from the MVP phase**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\trustworthy-analysis-workflow\src'; D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests\test_trust_contracts.py tests\test_trustworthy_load_data_integration.py tests\test_trustworthy_workflow_mvp.py tests\test_prompt_system.py tests\test_analysis_state_v2.py tests\test_intent_refinement.py tests\test_verification_layer.py tests\test_synthesis_policy.py tests\test_execution_control.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Inspect Git diff**

Run:

```powershell
git diff --stat
git diff -- src\data_agent\agent\loop.py src\data_agent\agent\trust_workflow_runtime.py tests\test_trust_workflow_runtime.py tests\test_execution_control.py
```

Expected:

- `loop.py` only contains small calls into runtime glue plus `_turn_verification_injected`.
- `trust_workflow_runtime.py` contains deterministic glue only.
- Tests cover runtime helpers and loop integration.

- [ ] **Step 4: Commit any verification fix**

If Step 1 or Step 2 required a code fix, run:

```powershell
git add src\data_agent\agent\loop.py src\data_agent\agent\trust_workflow_runtime.py tests\test_trust_workflow_runtime.py tests\test_execution_control.py
git commit -m "fix: stabilize trust workflow loop integration"
```

Expected: commit succeeds when there are fix changes. If there are no changes, no commit is needed.

---

## Self-Review

Spec coverage:

- Apply `refine_intent_with_data(...)` after base intent classification in the real loop: Task 3.
- Generate one verification report before final synthesis when the turn has evidence: Task 4.
- Store verification report references in `AnalysisSessionState`: Task 2 and Task 4.
- Ensure `derive_synthesis_policy(...)` sees latest verification status: Task 4.
- Add loop-level or near-loop regression tests: Tasks 1, 2, 3, and 4.
- Keep Web UI cards, human report pages, LLM verification, new methods, and broad loop refactors out of this phase: File Structure and tasks only touch runtime glue, loop, and tests.

Type consistency:

- `refine_turn_intent_with_state(user_input, intent, state) -> TurnIntent` is introduced in Task 1 and called with the same signature in Task 3.
- `maybe_verify_turn_claims(user_input, state, *, force=False) -> dict[str, Any] | None` is introduced in Task 2 and called with the same signature in Task 4.
- `AnalysisSessionState.add_verification_report_ref(...)` already exists and is used by the runtime helper.
- `_turn_verification_injected` is reset before being used.
