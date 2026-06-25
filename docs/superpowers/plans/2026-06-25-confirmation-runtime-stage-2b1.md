# Confirmation Runtime Stage 2B-1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the direct `ask_user_question` path through the durable Confirmation Runtime so visible questions, answers, and final-response blocking use one authoritative state machine.

**Architecture:** Add a small adapter layer between legacy direct-question signals and the Stage 2A domain kernel. Keep `UserConfirmationRequired` as the in-process signal from the tool registry to Agent Loop, but replace root-level suspension persistence and arbitrary `state_updates` application with `ConfirmationService`, registered resolution actions, and service-backed SSE/resume payloads. Leave advisory/gating producers such as multi-file relationships and recommendation panels unchanged for Stage 2B-2.

**Tech Stack:** Python 3.12, existing Flask SSE endpoints, Stage 2A `data_agent.agent.confirmation` package, pytest, standard-library JSON/hashlib/pathlib/threading.

---

## File Map

- Create `src/data_agent/agent/confirmation/runtime.py`: service factory, direct-question adapter, payload conversion, final-blocker helpers, and action registration.
- Modify `src/data_agent/agent/confirmation/__init__.py`: export runtime adapter contracts only if they are stable public helpers.
- Modify `src/data_agent/agent/loop.py`: replace direct-question `SuspensionManager` production writes/loads with runtime-backed request/checkpoint/respond; add final guard before normal final responses.
- Modify `src/data_agent/web/blueprints/chat.py`: accept `confirmation_id`, `expected_version`, and `idempotency_key` while keeping existing `suspension_id` input as an alias for the transition period.
- Create `tests/test_confirmation_runtime.py`: direct-question adapter and action tests.
- Modify `tests/test_interaction.py`: preserve tool-level `UserConfirmationRequired` behavior, not storage behavior.
- Modify `tests/test_execution_control.py`: auto-suspend and final-guard expectations.
- Modify `tests/test_comprehensive_analysis_flow.py`: replace `SuspensionManager` production-path tests with runtime-backed direct-question tests.
- Modify or add Web/SSE tests around `/chat/resume` payload shape where existing fixtures cover it.
- Modify `docs/superpowers/specs/2026-06-25-confirmation-runtime-stage-2b1-design.md`: record Stage 2B-1 verification after all gates pass.

## Task 1: Runtime Adapter for Direct Questions

**Files:**
- Create: `src/data_agent/agent/confirmation/runtime.py`
- Test: `tests/test_confirmation_runtime.py`

- [x] **Step 1: Write failing adapter tests**

Add tests that describe the new adapter API:

```python
def test_direct_question_candidate_uses_stable_identity(tmp_path):
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate
    from data_agent.agent.loop import UserConfirmationRequired

    ucc = UserConfirmationRequired(
        question="Which metric should be used?",
        options=[
            {"label": "Revenue", "value": "revenue"},
            {"label": "Orders", "value": "orders"},
        ],
        confirmation_type="metric_scope",
        blocking_reason="Metric choice changes the calculation.",
        related_spec_id="spec_1",
    )

    first = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=3,
        request=ucc,
    )
    second = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=3,
        request=ucc,
    )

    assert first.confirmation_id == second.confirmation_id
    assert first.decision_key == second.decision_key
    assert first.operation == "direct_user_question"
    assert first.resolution_action == "record_confirmation_answer"
    assert first.blocking_surfaces == ("agent_turn",)
```

Also test:

```python
def test_multi_select_candidate_uses_multi_select_answer_mode():
    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Pick analyses",
            options=[{"label": "Trend", "value": "trend"}],
            multi_select=True,
            confirmation_type="follow_up_choice",
        ),
    )
    assert candidate.answer_mode == AnswerMode.MULTI_SELECT


def test_free_text_candidate_rejects_missing_question():
    with pytest.raises(ConfirmationContractError):
        build_direct_question_candidate(
            session_id="session_1",
            turn_id="turn_1",
            message_version=1,
            request=UserConfirmationRequired(question="", options=[]),
        )
```

- [x] **Step 2: Run and verify RED**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_runtime.py -q
```

Expected: import failure for `data_agent.agent.confirmation.runtime`.

- [x] **Step 3: Implement direct-question adapter**

Create `runtime.py` with:

```python
def build_direct_question_candidate(
    *,
    session_id: str,
    turn_id: str,
    message_version: int,
    request: UserConfirmationRequired,
) -> QuestionCandidate:
    identity = _direct_question_identity(session_id, turn_id, message_version, request)
    options = _normalise_options(request.options)
    mode = (
        AnswerMode.FREE_TEXT
        if not options
        else AnswerMode.MULTI_SELECT
        if request.multi_select
        else AnswerMode.SINGLE_SELECT
    )
    return QuestionCandidate(
        confirmation_id=f"direct_{identity[:24]}",
        session_id=session_id,
        turn_id=turn_id,
        decision_key=f"{session_id}:direct_user_question:{identity}",
        source="ask_user_question",
        operation="direct_user_question",
        question=request.question,
        decision_impact=request.blocking_reason or "The current agent turn cannot continue without this answer.",
        answer_mode=mode,
        options=options,
        blocking_surfaces=("agent_turn",),
        skippable=True,
        resolution_action=_resolution_action_for(request),
        resolution_params=_resolution_params_for(request),
        data_version=f"messages:{message_version}",
        spec_version=request.related_spec_id or "",
    )

def confirmation_record_to_suspended_event(record: ConfirmationRecord) -> dict[str, Any]:
    return {
        "type": "suspended",
        "confirmation_id": record.confirmation_id,
        "suspension_id": record.confirmation_id,
        "version": record.version,
        "question": record.question,
        "options": [option.to_dict() for option in record.options],
        "context": "",
        "multi_select": record.answer_mode == AnswerMode.MULTI_SELECT,
        "confirmation_type": record.resolution_params.get("confirmation_type", ""),
        "blocking_reason": record.decision_impact,
        "related_task_id": int(record.resolution_params.get("related_task_id") or 0),
        "related_spec_id": record.resolution_params.get("related_spec_id", ""),
    }

def confirmation_record_to_loop_result(record: ConfirmationRecord, snapshot: dict[str, Any]) -> SuspendedForConfirmation:
    event = confirmation_record_to_suspended_event(record)
    return SuspendedForConfirmation(
        suspension_id=record.confirmation_id,
        confirmation_id=record.confirmation_id,
        version=record.version,
        question=record.question,
        options=event["options"],
        context=event["context"],
        snapshot=snapshot,
        multi_select=event["multi_select"],
        confirmation_type=event["confirmation_type"],
        blocking_reason=event["blocking_reason"],
        related_task_id=event["related_task_id"],
        related_spec_id=event["related_spec_id"],
    )
```

Implementation rules:

- normalize option values from `value`, then `label`;
- use `AnswerMode.FREE_TEXT` only when no options exist;
- use `AnswerMode.MULTI_SELECT` when `request.multi_select` is true;
- derive a SHA-256 identity from session, turn, message version, question, options, confirmation type, related task/spec IDs, and safe normalized state-update shape;
- generate IDs with safe prefixes such as `direct_<first_24_hex_chars>`;
- set `resolution_action` to `record_confirmation_answer` unless a safe typed action is recognized;
- do not apply or trust raw `state_updates`.

- [x] **Step 4: Run and verify GREEN**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_runtime.py tests/test_confirmation_models.py tests/test_confirmation_policy.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit adapter**

```powershell
git add src/data_agent/agent/confirmation/runtime.py tests/test_confirmation_runtime.py
git commit -m "feat: adapt direct questions to confirmation runtime"
```

## Task 2: Registered Resolution Actions

**Files:**
- Modify: `src/data_agent/agent/confirmation/runtime.py`
- Test: `tests/test_confirmation_runtime.py`

- [ ] **Step 1: Write failing action tests**

Add tests:

```python
def test_runtime_registers_record_confirmation_answer_action(tmp_path):
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.actions import ResolutionContext

    registry = build_action_registry()
    receipt = registry.apply(
        "record_confirmation_answer",
        ResolutionContext("session_1", "cf_1", {"question": "Metric?"}),
        "revenue",
        "cf_1:answer_1",
    )

    assert receipt.status == "succeeded"
    assert receipt.output["answer"] == "revenue"


def test_runtime_rejects_unsafe_state_update_action():
    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Proceed?",
            options=[{"label": "Yes", "value": "yes"}],
            state_updates='{"arbitrary": {"nested": "write"}}',
        ),
    )
    assert candidate.resolution_action == "record_confirmation_answer"
```

- [ ] **Step 2: Run and verify RED**

Run `pytest tests/test_confirmation_runtime.py -q`.

Expected: missing `build_action_registry` or missing action behavior.

- [ ] **Step 3: Implement runtime action registry**

Add:

```python
def build_action_registry() -> ResolutionActionRegistry:
    registry = ResolutionActionRegistry()
    registry.register("record_confirmation_answer", _record_confirmation_answer)
    registry.register("set_analysis_stage", _set_analysis_stage, validator=_validate_stage_action)
    registry.register("confirm_method", _confirm_method, validator=_validate_method_confirmation)
    registry.register("resolve_file_relationship", _resolve_file_relationship, validator=_validate_file_relationship)
    return registry
```

For Stage 2B-1, `record_confirmation_answer` must always be safe and side-effect-light. The other actions may delegate to existing `AnalysisSessionState.apply_state_updates()` only through strict parameter shapes:

```python
{"stage": "scope", "data_state": "data_loaded"}
{"method_confirmation": {"analysis_spec_id": "spec_1", "playbook_id": "forecast_basic"}}
{"file_relationship_confirmation": {"relationship_id": "rel_orders_history"}}
```

Any unrecognized payload must fall back to `record_confirmation_answer`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_runtime.py tests/test_confirmation_actions.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit actions**

```powershell
git add src/data_agent/agent/confirmation/runtime.py tests/test_confirmation_runtime.py
git commit -m "feat: register direct confirmation actions"
```

## Task 3: Agent Loop Creation Cutover

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Modify: `tests/test_comprehensive_analysis_flow.py`
- Modify: `tests/test_execution_control.py`

- [ ] **Step 1: Write failing creation-path tests**

Add a streaming test:

```python
def test_streaming_direct_question_persists_confirmation_not_suspension_file(tmp_path, monkeypatch):
    from data_agent.agent.loop import AgentLoop, UserConfirmationRequired
    from data_agent.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", str(tmp_path), raising=False)
    loop = AgentLoop(client=FakeAskQuestionClient(), session_id="direct_q")

    events = list(loop.stream_turn("ask before proceeding"))

    suspended = next(event for event in events if event["type"] == "suspended")
    assert suspended["confirmation_id"]
    assert suspended["version"] >= 2
    assert (tmp_path / "direct_q" / "confirmations" / "events.jsonl").exists()
    assert not list(tmp_path.glob("suspension_*.json"))
```

`FakeAskQuestionClient` should emit one tool call to `ask_user_question` with a concrete question and options. If existing test helpers already model tool calls, reuse those helpers.

Also add a non-streaming test:

```python
def test_run_turn_direct_question_returns_runtime_backed_suspension(tmp_path, monkeypatch):
    loop = AgentLoop(client=FakeAskQuestionClient(), session_id="direct_q_sync")
    result = loop.run_turn("ask before proceeding")
    assert result.suspension_id.startswith("direct_")
    assert result.confirmation_type == "metric_scope"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_comprehensive_analysis_flow.py::TestConversationFlow::test_streaming_direct_question_persists_confirmation_not_suspension_file tests/test_comprehensive_analysis_flow.py::TestConversationFlow::test_run_turn_direct_question_returns_runtime_backed_suspension -q
```

Expected: failure because current code writes root-level suspension files and does not expose `confirmation_id`/`version`.

- [ ] **Step 3: Implement creation cutover**

In `AgentLoop`, add helpers:

```python
def _confirmation_runtime(self) -> ConfirmationService:
    if not hasattr(self, "_direct_confirmation_service"):
        self._direct_confirmation_service = ConfirmationService(
            get_config().sessions_resolved,
            action_registry=build_action_registry(),
        )
    return self._direct_confirmation_service

def _suspend_for_confirmation_request(
    self,
    request: UserConfirmationRequired,
    *,
    tool_call_id: str | None = None,
) -> SuspendedForConfirmation:
    candidate = build_direct_question_candidate(
        session_id=self.session_id,
        turn_id=getattr(self, "_current_turn_id", "") or "turn",
        message_version=len(self.messages),
        request=request,
    )
    result = self._confirmation_runtime().request(candidate)
    if result.record is None:
        raise RuntimeError(result.reason)
    record = self._confirmation_runtime().checkpoint(self.session_id)
    if record is None:
        raise RuntimeError("confirmation checkpoint did not return the requested record")
    return confirmation_record_to_loop_result(record, {"messages": self._serialize_messages()})
```

Use `build_direct_question_candidate()`, `ConfirmationService.request()`, and `ConfirmationService.checkpoint()`. Stop calling `SuspensionManager.save()` in:

- `_maybe_auto_suspend_for_required_question()`;
- `_process_tool_calls()`;
- `_execute_single_tool()`.

Keep the `SuspendedForConfirmation` dataclass as the loop result, but add fields if needed:

```python
confirmation_id: str = ""
version: int = 0
```

Set `suspension_id` equal to `confirmation_id` during this transition so existing clients can keep sending `suspension_id`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_comprehensive_analysis_flow.py tests/test_execution_control.py tests/test_confirmation_runtime.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit creation cutover**

```powershell
git add src/data_agent/agent/loop.py tests/test_comprehensive_analysis_flow.py tests/test_execution_control.py
git commit -m "feat: persist direct questions through confirmation service"
```

## Task 4: Resume Cutover and Idempotency

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/web/blueprints/chat.py`
- Modify: `tests/test_comprehensive_analysis_flow.py`
- Modify: Web/SSE resume tests if the existing fixture covers `/api/chat/resume`

- [ ] **Step 1: Write failing resume tests**

Add:

```python
def test_resume_direct_question_resolves_confirmation_record(tmp_path, monkeypatch):
    loop = AgentLoop(client=FakeAskThenFinishClient(), session_id="resume_q")
    suspended = next(event for event in loop.stream_turn("ask") if event["type"] == "suspended")

    events = list(loop.resume_turn_streaming(
        suspended["confirmation_id"],
        "revenue",
        expected_version=suspended["version"],
        idempotency_key="answer_1",
    ))

    record = loop._confirmation_runtime().get("resume_q", suspended["confirmation_id"])
    assert record.status == ConfirmationStatus.RESOLVED
    assert any(event["type"] == "text_delta" for event in events)
```

Add duplicate/stale tests:

```python
def test_duplicate_resume_applies_action_once(tmp_path):
    loop = AgentLoop(client=FakeAskThenFinishClient(), session_id="resume_q_dup")
    suspended = next(event for event in loop.stream_turn("ask") if event["type"] == "suspended")
    confirmation_id = suspended["confirmation_id"]
    version = suspended["version"]
    first = list(loop.resume_turn_streaming(confirmation_id, "revenue", expected_version=version, idempotency_key="answer_1"))
    second = list(loop.resume_turn_streaming(confirmation_id, "revenue", expected_version=version, idempotency_key="answer_1"))
    assert not any(event["type"] == "error" for event in second)


def test_stale_resume_does_not_continue_turn(tmp_path):
    loop = AgentLoop(client=FakeAskThenFinishClient(), session_id="resume_q_stale")
    suspended = next(event for event in loop.stream_turn("ask") if event["type"] == "suspended")
    confirmation_id = suspended["confirmation_id"]
    version = suspended["version"]
    events = list(loop.resume_turn_streaming(confirmation_id, "orders", expected_version=version - 1, idempotency_key="answer_2"))
    assert any(event["type"] == "error" for event in events)
```

- [ ] **Step 2: Run and verify RED**

Run the new resume tests. Expected: current `resume_turn_streaming` signature and `SuspensionManager.load()` behavior fail.

- [ ] **Step 3: Implement service-backed resume**

Update `resume_turn_streaming` signature to accept optional:

```python
expected_version: int | None = None
idempotency_key: str | None = None
```

Load the record from `ConfirmationService`, validate/answer through `respond()`, build the structured response message from the record, and do not call `SuspensionManager.load()` or `remove()`.

Update `/api/chat/resume` to read:

```python
confirmation_id = data.get("confirmation_id") or data.get("suspension_id")
expected_version = data.get("expected_version")
idempotency_key = data.get("idempotency_key") or f"resume_{uuid.uuid4().hex}"
```

Return validation/version/action errors through the SSE error path without continuing the turn.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_comprehensive_analysis_flow.py tests/test_sse_reactivity.py tests/test_web_gui.py -q
```

Expected: pytest-compatible tests pass; script-style tests may need native execution if they are not pytest-safe.

- [ ] **Step 5: Commit resume cutover**

```powershell
git add src/data_agent/agent/loop.py src/data_agent/web/blueprints/chat.py tests/test_comprehensive_analysis_flow.py tests/test_sse_reactivity.py tests/test_web_gui.py
git commit -m "feat: answer direct confirmations through runtime"
```

## Task 5: Final Guard and Legacy Production Path Removal

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Modify: `tests/test_execution_control.py`
- Modify: `tests/test_comprehensive_analysis_flow.py`

- [ ] **Step 1: Write failing final-guard tests**

Add:

```python
def test_final_text_is_blocked_when_confirmation_is_suspended(tmp_path):
    loop = AgentLoop(client=FakeFinalClient("done"), session_id="guard_q")
    service = loop._confirmation_runtime()
    service.request(_candidate_for_guard("guard_q"))
    active = service.checkpoint("guard_q")

    result = loop.run_turn("finish now")

    assert isinstance(result, SuspendedForConfirmation)
    assert result.confirmation_id == active.confirmation_id
```

Add failed-state guard:

```python
def test_failed_confirmation_blocks_final_text(tmp_path):
    loop = AgentLoop(client=FakeFinalClient("done"), session_id="guard_failed")
    registry = ResolutionActionRegistry()
    registry.register("fail_action", lambda context, answer: (_ for _ in ()).throw(RuntimeError("boom")))
    service = ConfirmationService(tmp_path, action_registry=registry)
    loop._direct_confirmation_service = service
    service.request(_candidate_for_guard("guard_failed", resolution_action="fail_action"))
    active = service.checkpoint("guard_failed")
    with pytest.raises(ConfirmationResolutionFailed):
        service.respond("guard_failed", active.confirmation_id, "yes", active.version, "answer_1")
    assert service.get("guard_failed", active.confirmation_id).status == ConfirmationStatus.FAILED
    result = loop.run_turn("finish now")
    assert "confirmation" in result.content.lower() or isinstance(result, SuspendedForConfirmation)
```

- [ ] **Step 2: Run and verify RED**

Run the final-guard tests. Expected: current loop can return final text without consulting the new service.

- [ ] **Step 3: Implement final guard**

Add:

```python
def _blocking_confirmation(self) -> ConfirmationRecord | None:
    return self._confirmation_runtime().checkpoint(self.session_id)

def _guard_final_response(self) -> SuspendedForConfirmation | None:
    record = self._blocking_confirmation()
    if record is None:
        return None
    return confirmation_record_to_loop_result(record, {"messages": self._serialize_messages()})
```

Call this guard before each normal final return in `_loop_impl`, `stream_turn`, and `resume_turn_streaming`. It must not create new questions; it only surfaces existing records.

Remove production calls to `SuspensionManager` from direct question paths. Keep the class only if historical tests still import it.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_execution_control.py tests/test_comprehensive_analysis_flow.py tests/test_confirmation_runtime.py tests/test_confirmation_service.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit final guard**

```powershell
git add src/data_agent/agent/loop.py tests/test_execution_control.py tests/test_comprehensive_analysis_flow.py
git commit -m "feat: block final responses on direct confirmations"
```

## Task 6: Regression Gate and Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-06-25-confirmation-runtime-stage-2b1-design.md`
- Modify: `docs/superpowers/plans/2026-06-25-confirmation-runtime-stage-2b1.md`

- [ ] **Step 1: Run complete confirmation suites**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
$files = Get-ChildItem tests -Filter 'test_confirmation_*.py' | ForEach-Object { $_.FullName }
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest $files tests/test_interaction.py tests/test_execution_control.py tests/test_comprehensive_analysis_flow.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run Web/SSE targeted checks**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_sse_reactivity.py tests/test_web_workbench_parity.py tests/test_web_overhaul.py -q
```

If a file is script-style rather than pytest-safe, run it with:

```powershell
D:\Project\Daily\data-agent\.venv\Scripts\python.exe tests/<script_file>.py
```

Expected: zero failures, or documented pre-existing script-style behavior.

- [ ] **Step 3: Run static checks**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m compileall -q src\data_agent\agent\confirmation src\data_agent\agent\loop.py src\data_agent\web\blueprints\chat.py
git diff --check
git status --short
```

Expected: compile and diff checks pass.

- [ ] **Step 4: Run pytest-compatible project suite**

Use the same explicit module-list style as Stage 2A:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
$excluded = @('test_comparability.py','test_sse_reactivity.py','test_v91.py','test_web_gui.py','test_tools_comprehensive.py','test_v10_new.py')
$files = Get-ChildItem tests -File -Filter 'test_*.py' | Where-Object { $_.Name -notin $excluded } | ForEach-Object { $_.FullName }
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest $files -q -p no:cacheprovider --basetemp .pytest-tmp-stage2b1
```

Expected: zero failures.

- [ ] **Step 5: Record verification**

Append a Stage 2B-1 verification section to the design document with exact test counts and remaining limits:

- producer cutover beyond direct questions remains Stage 2B-2;
- refresh/restart restoration remains Stage 2C;
- historical root-level suspension files are not migrated;
- advisory/gating `pending_confirmations` remain unchanged.

- [ ] **Step 6: Commit verification docs**

```powershell
git add docs/superpowers/specs/2026-06-25-confirmation-runtime-stage-2b1-design.md docs/superpowers/plans/2026-06-25-confirmation-runtime-stage-2b1.md
git commit -m "docs: record confirmation runtime stage 2b1 verification"
```

## Stage 2B-1 Stop Condition

Do not start Stage 2B-2 or Stage 2C in this batch. Stop after direct `ask_user_question` paths are service-backed, final guard is active for direct confirmation records, and regression gates pass.
