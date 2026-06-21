# Confirmation Runtime Stage 2A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dormant, fully tested Confirmation Runtime domain kernel with strict contracts, durable event storage, validated state transitions, typed resolution actions, decision deduplication, and continuation records, without connecting it to production Agent Loop paths.

**Architecture:** Create a focused `data_agent.agent.confirmation` package. Immutable request/event contracts feed a session-scoped event store; `ConfirmationService` is the sole transition authority and materializes record snapshots. A policy validates whether a request is actionable, an action registry applies typed idempotent resolutions, and a continuation store records safe resume metadata. Stage 2A introduces no legacy reads, writes, or production-loop integration.

**Tech Stack:** Python 3.12, standard-library dataclasses/enums/JSON/pathlib/threading/fsync, pytest, existing session-directory conventions.

---

## File Map

- Create `src/data_agent/agent/confirmation/__init__.py`: public Stage 2A API only.
- Create `src/data_agent/agent/confirmation/models.py`: enums, immutable request/event/record contracts, validation, serialization.
- Create `src/data_agent/agent/confirmation/policy.py`: trigger validation, advisory downgrade, decision-key reuse rules.
- Create `src/data_agent/agent/confirmation/store.py`: session-scoped append-only event log, atomic snapshot, replay, corruption detection, per-session locking.
- Create `src/data_agent/agent/confirmation/actions.py`: typed action registry and idempotent application receipts.
- Create `src/data_agent/agent/confirmation/continuation.py`: continuation contract and atomic store.
- Create `src/data_agent/agent/confirmation/service.py`: queueing, state transitions, concurrency/version checks, response handling.
- Create `tests/test_confirmation_models.py`: model validation and serialization tests.
- Create `tests/test_confirmation_policy.py`: trigger and decision reuse tests.
- Create `tests/test_confirmation_store.py`: persistence, replay, atomic snapshot, truncation, and concurrency tests.
- Create `tests/test_confirmation_actions.py`: action validation and idempotency tests.
- Create `tests/test_confirmation_continuation.py`: continuation persistence and integrity tests.
- Create `tests/test_confirmation_service.py`: state machine, queue, version conflicts, terminal states, and failure tests.
- Modify `docs/superpowers/specs/2026-06-21-confirmation-runtime-design.md`: record Stage 2A verification only after all gates pass.

## Task 1: Domain Contracts

**Files:**
- Create: `src/data_agent/agent/confirmation/__init__.py`
- Create: `src/data_agent/agent/confirmation/models.py`
- Create: `tests/test_confirmation_models.py`

- [x] **Step 1: Write failing validation and round-trip tests**

Add tests for:

```python
def _valid_request(**overrides):
    values = {
        "confirmation_id": "cf_metric_1",
        "session_id": "session_1",
        "turn_id": "turn_1",
        "decision_key": "session_1:choose_metric:revenue:v1",
        "source": "question_detector",
        "operation": "period_compare",
        "question": "Which metric should be compared?",
        "decision_impact": "The selected metric changes every reported value.",
        "answer_mode": AnswerMode.SINGLE_SELECT,
        "options": (
            ConfirmationOption("Revenue", "revenue", "Compare collected revenue."),
            ConfirmationOption("Orders", "orders", "Compare paid order count."),
        ),
        "blocking_surfaces": ("analysis_execution", "report_generation"),
        "skippable": False,
        "resolution_action": "choose_metric",
        "resolution_params": {"analysis_spec_id": "spec_1"},
        "data_version": "data_v1",
        "spec_version": "spec_v1",
    }
    values.update(overrides)
    return ConfirmationRequest(**values)


def test_request_requires_actionable_question():
    with pytest.raises(ConfirmationContractError, match="question"):
        _valid_request(question="")


def test_single_select_requires_unique_option_values():
    duplicate = (
        ConfirmationOption("Revenue", "revenue"),
        ConfirmationOption("Revenue again", "revenue"),
    )
    with pytest.raises(ConfirmationContractError, match="unique"):
        _valid_request(options=duplicate)


def test_record_and_event_json_round_trip():
    request = _valid_request()
    record = ConfirmationRecord.from_request(request, now="2026-06-21T00:00:00Z")
    event = ConfirmationEvent.requested(record, event_id="event_1")
    assert ConfirmationRecord.from_dict(record.to_dict()) == record
    assert ConfirmationEvent.from_dict(event.to_dict()) == event
```

Also cover free-text mode, multi-select mode, missing blocking surfaces, missing resolution action, unknown fields ignored only during `from_dict`, and enum parsing failures.

- [x] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_confirmation_models.py -q
```

Expected: collection fails because `data_agent.agent.confirmation` does not exist.

- [x] **Step 3: Implement immutable contracts**

Implement:

```python
class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    SUSPENDED = "suspended"
    RESPONSE_RECEIVED = "response_received"
    APPLYING = "applying"
    RESOLVED = "resolved"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class AnswerMode(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    FREE_TEXT = "free_text"
```

Use frozen dataclasses for `ConfirmationOption`, `ConfirmationRequest`, `ConfirmationRecord`, and `ConfirmationEvent`. Validate trimmed IDs, decision key, source, operation, question, impact, blocking surfaces, action name, option uniqueness, and mode-specific option rules in `__post_init__`. Serialize tuples as lists and enums as values.

- [x] **Step 4: Run the tests and verify GREEN**

Run the Task 1 command. Expected: all model tests pass.

- [x] **Step 5: Commit domain contracts**

```powershell
git add src/data_agent/agent/confirmation tests/test_confirmation_models.py
git commit -m "feat: add confirmation domain contracts"
```

## Task 2: Trigger Policy and Decision Reuse

**Files:**
- Create: `src/data_agent/agent/confirmation/policy.py`
- Create: `tests/test_confirmation_policy.py`

Implementation refinement: producers submit a `QuestionCandidate`, which may
represent non-blocking uncertainty. Policy creates a strict
`ConfirmationRequest` only for accepted blocking decisions, preserving the
request contract while still supporting advisory downgrade.

- [x] **Step 1: Write failing policy tests**

Cover these exact outcomes:

```python
def test_policy_accepts_material_operation_decision():
    result = QuestionPolicy().evaluate(_valid_request())
    assert result.disposition == RequestDisposition.CONFIRMATION


def test_policy_downgrades_general_uncertainty_to_advisory():
    request = _valid_request(operation="", blocking_surfaces=())
    result = QuestionPolicy().evaluate(request, allow_advisory=True)
    assert result.disposition == RequestDisposition.ADVISORY


def test_policy_reuses_matching_resolved_decision():
    resolved = _resolved_record(decision_key=_valid_request().decision_key)
    result = QuestionPolicy().evaluate(_valid_request(), existing=(resolved,))
    assert result.disposition == RequestDisposition.REUSED
    assert result.reused_confirmation_id == resolved.confirmation_id


def test_policy_does_not_reuse_answer_after_spec_version_changes():
    resolved = _resolved_record(spec_version="spec_v1")
    request = _valid_request(spec_version="spec_v2")
    assert QuestionPolicy().evaluate(request, existing=(resolved,)).disposition == RequestDisposition.CONFIRMATION
```

Also reject legacy records as trigger inputs, speculative file relationships without an imminent operation, and requests with a declared safe default.

- [x] **Step 2: Run and verify RED**

Run `pytest tests/test_confirmation_policy.py -q`. Expected: import failure.

- [x] **Step 3: Implement policy results**

Add `RequestDisposition` (`confirmation`, `advisory`, `reused`, `rejected`) and immutable `PolicyResult`. `QuestionPolicy.evaluate()` must be deterministic and must not inspect chat text or call an LLM. Reuse requires equal decision key, data version, spec version, and a resolved terminal state.

- [x] **Step 4: Run and verify GREEN**

Run model and policy tests together. Expected: PASS.

- [x] **Step 5: Commit policy**

```powershell
git add src/data_agent/agent/confirmation/policy.py tests/test_confirmation_policy.py
git commit -m "feat: validate confirmation trigger policy"
```

## Task 3: Durable Event Store

**Files:**
- Create: `src/data_agent/agent/confirmation/store.py`
- Create: `tests/test_confirmation_store.py`

- [x] **Step 1: Write failing persistence tests**

Test:

```python
def test_store_appends_event_and_rebuilds_snapshot(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    record = _pending_record()
    store.append(ConfirmationEvent.requested(record, event_id="event_1"))
    assert store.load_records()[record.confirmation_id] == record
    store.snapshot_path.unlink()
    assert store.load_records()[record.confirmation_id] == record


def test_truncated_tail_preserves_valid_events_and_marks_integrity_failure(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    store.append(_requested_event("event_1"))
    with store.events_path.open("ab") as handle:
        handle.write(b'{"event_id":"broken"')
    result = store.load()
    assert result.integrity_status == "truncated_tail"
    assert "cf_metric_1" in result.records


def test_duplicate_event_id_is_idempotent(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    event = _requested_event("event_1")
    store.append(event)
    store.append(event)
    assert len(store.load().event_ids) == 1
```

Also test mid-log corruption fails closed, atomic snapshot replacement leaves no temporary file, event `fsync` is invoked through an injectable sync helper, and two threads cannot create conflicting snapshot versions.

- [x] **Step 2: Run and verify RED**

Run `pytest tests/test_confirmation_store.py -q`. Expected: import failure.

- [x] **Step 3: Implement session-scoped store**

Use paths under `<sessions_root>/<session_id>/confirmations`. Append one compact JSON event per line, flush, and call `os.fsync`. Write snapshots to `snapshot.json.tmp`, flush/fsync, then `os.replace`. Maintain a process-local `RLock` per resolved session path. Replay validates event sequence and returns `StoreLoadResult(records, event_ids, integrity_status, error)`.

- [x] **Step 4: Run and verify GREEN**

Run store plus model tests. Expected: PASS.

- [x] **Step 5: Commit event store**

```powershell
git add src/data_agent/agent/confirmation/store.py tests/test_confirmation_store.py
git commit -m "feat: persist confirmation event log"
```

## Task 4: Typed Resolution Actions

**Files:**
- Create: `src/data_agent/agent/confirmation/actions.py`
- Create: `tests/test_confirmation_actions.py`

- [ ] **Step 1: Write failing registry tests**

```python
def test_registry_rejects_unknown_action():
    with pytest.raises(UnknownResolutionAction):
        ResolutionActionRegistry().apply("missing", _context(), "yes", "resolution_1")


def test_action_receipt_makes_repeated_apply_idempotent():
    calls = []
    registry = ResolutionActionRegistry()
    registry.register("choose_metric", lambda context, answer: calls.append(answer) or {"metric": answer})
    first = registry.apply("choose_metric", _context(), "revenue", "resolution_1")
    second = registry.apply("choose_metric", _context(), "revenue", "resolution_1")
    assert first == second
    assert calls == ["revenue"]
```

Also test conflicting reuse of a resolution ID, answer validation before handler invocation, and handler exception receipts.

- [ ] **Step 2: Run and verify RED**

Run `pytest tests/test_confirmation_actions.py -q`. Expected: import failure.

- [ ] **Step 3: Implement registry and receipt store interface**

Define `ResolutionContext`, `ResolutionReceipt`, an in-memory receipt repository for Stage 2A tests, and a registry that requires unique action names. A repeated identical resolution ID returns the prior receipt. Reuse with different action, answer, or context raises `ResolutionConflict`.

- [ ] **Step 4: Run and verify GREEN**

Run action and model tests. Expected: PASS.

- [ ] **Step 5: Commit action registry**

```powershell
git add src/data_agent/agent/confirmation/actions.py tests/test_confirmation_actions.py
git commit -m "feat: add idempotent confirmation actions"
```

## Task 5: Continuation Records

**Files:**
- Create: `src/data_agent/agent/confirmation/continuation.py`
- Create: `tests/test_confirmation_continuation.py`

- [ ] **Step 1: Write failing continuation tests**

Test immutable continuation creation, atomic save/load, completed tool-call preservation, confirmation-ID matching, checksum failure, and terminal continuation states.

```python
def test_continuation_round_trip_preserves_completed_tools(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    continuation = ContinuationRecord(
        confirmation_id="cf_metric_1",
        session_id="session_1",
        turn_id="turn_1",
        message_version=12,
        completed_tool_call_ids=("tool_1", "tool_2"),
        blocked_operation="period_compare",
        request_identity="sha256:request",
        status=ContinuationStatus.SUSPENDED,
    )
    store.save(continuation)
    assert store.load("cf_metric_1") == continuation
```

- [ ] **Step 2: Run and verify RED**

Run `pytest tests/test_confirmation_continuation.py -q`. Expected: import failure.

- [ ] **Step 3: Implement atomic continuation store**

Store one JSON file per confirmation under the session confirmation directory. Include a SHA-256 checksum of the canonical payload. Use temp-file write, fsync, and atomic replace. Invalid checksum raises `ContinuationIntegrityError` rather than returning partial state.

- [ ] **Step 4: Run and verify GREEN**

Run continuation tests. Expected: PASS.

- [ ] **Step 5: Commit continuation records**

```powershell
git add src/data_agent/agent/confirmation/continuation.py tests/test_confirmation_continuation.py
git commit -m "feat: persist confirmation continuations"
```

## Task 6: Confirmation Service and State Machine

**Files:**
- Create: `src/data_agent/agent/confirmation/service.py`
- Create: `tests/test_confirmation_service.py`
- Modify: `src/data_agent/agent/confirmation/__init__.py`

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

```python
def test_service_allows_only_one_suspended_confirmation(tmp_path):
    service = _service(tmp_path)
    first = service.request(_valid_request(confirmation_id="cf_1", decision_key="key_1"))
    second = service.request(_valid_request(confirmation_id="cf_2", decision_key="key_2"))
    active = service.checkpoint("session_1")
    assert active.confirmation_id == first.record.confirmation_id
    assert service.checkpoint("session_1").confirmation_id == active.confirmation_id
    assert service.get("session_1", second.record.confirmation_id).status == ConfirmationStatus.PENDING


def test_response_uses_expected_version_and_applies_once(tmp_path):
    service, calls = _service_with_metric_action(tmp_path)
    service.request(_valid_request())
    active = service.checkpoint("session_1")
    resolved = service.respond(
        "session_1",
        active.confirmation_id,
        answer="revenue",
        expected_version=active.version,
        idempotency_key="answer_1",
    )
    repeated = service.respond(
        "session_1",
        active.confirmation_id,
        answer="revenue",
        expected_version=active.version,
        idempotency_key="answer_1",
    )
    assert resolved.status == ConfirmationStatus.RESOLVED
    assert repeated == resolved
    assert calls == ["revenue"]


def test_illegal_transition_fails_closed(tmp_path):
    service = _service(tmp_path)
    pending = service.request(_valid_request()).record
    with pytest.raises(InvalidConfirmationTransition):
        service.respond("session_1", pending.confirmation_id, "revenue", pending.version, "answer_1")
```

Also test advisory/reused policy results, skip authorization, cancel, expire, action failure to `failed`, stale version conflicts, invalid answer values, deterministic queue order, store integrity failure, and restoration after recreating the service.

- [ ] **Step 2: Run and verify RED**

Run `pytest tests/test_confirmation_service.py -q`. Expected: import failure.

- [ ] **Step 3: Implement the sole transition authority**

`ConfirmationService` receives store, policy, action registry, continuation store, clock, and ID factory dependencies. Every public transition loads authoritative state, validates expected status/version, appends an event, and returns the materialized record. `respond()` appends `response_received`, transitions to `applying`, invokes the registry with a stable resolution ID, then appends `resolved` or `failed`.

Expose only public contracts and service types from `confirmation/__init__.py`.

- [ ] **Step 4: Run and verify GREEN**

Run all `tests/test_confirmation_*.py -q`. Expected: PASS.

- [ ] **Step 5: Commit service**

```powershell
git add src/data_agent/agent/confirmation tests/test_confirmation_service.py
git commit -m "feat: add confirmation lifecycle service"
```

## Task 7: Stage 2A Integrity and Regression Gate

**Files:**
- Modify only if a failure is reproduced by a new failing test first.

- [ ] **Step 1: Run the complete Stage 2A suite**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_confirmation_models.py tests/test_confirmation_policy.py tests/test_confirmation_store.py tests/test_confirmation_actions.py tests/test_confirmation_continuation.py tests/test_confirmation_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run neighboring existing confirmation tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interaction.py tests/test_execution_control.py tests/test_question_need_detector.py tests/test_analysis_state_v2.py tests/test_analysis_entry.py tests/test_route_capabilities.py tests/test_method_playbooks.py -q
```

Expected: PASS because Stage 2A is dormant.

- [ ] **Step 3: Run static compilation and diff checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\data_agent\agent\confirmation
git diff --check
git status --short
```

Expected: compilation succeeds; only Stage 2A files and plan status are changed.

- [ ] **Step 4: Run the pytest-compatible full suite in deterministic partitions**

Exclude script-style modules already documented by Stage 1. Expected: zero failures.

- [ ] **Step 5: Record Stage 2A verification**

Add exact test counts and residual limitations to the design document. Explicitly state that no production confirmation path uses the new runtime until Stage 2B.

- [ ] **Step 6: Commit verification documentation**

```powershell
git add docs/superpowers/specs/2026-06-21-confirmation-runtime-design.md docs/superpowers/plans/2026-06-21-confirmation-runtime-stage-2a.md
git commit -m "docs: record confirmation kernel verification"
```

## Stage 2A Stop Condition

Do not start Stage 2B in this implementation batch. Stage 2A is complete only when:

- domain contracts reject incomplete or unsafe questions;
- event replay and snapshot reconstruction are deterministic;
- corruption and write failures fail explicitly;
- resolution actions are idempotent;
- the state machine rejects illegal and concurrent transitions;
- one session exposes at most one suspended record;
- the complete new and neighboring suites pass;
- existing production confirmation behavior is unchanged.
