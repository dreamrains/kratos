# Fallback Resolution and Compact Evidence Alias Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to execute this plan task-by-task in the current session. Use `superpowers:subagent-driven-development` only if the user explicitly authorizes subagent delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate false fallback-resolution error cascades, make exact measurement evidence easy for the configured provider to cite, and rerun honest A-F release validation with three live sessions that each contain a verified analytical core.

**Architecture:** Keep `TurnExecutionState` as the sole execution-control authority and move fallback pending transitions from attempted calls to successful outcomes. Add a bounded synthesis-only alias catalog that maps short, turn-local markers to full immutable evidence identities immediately before the existing final audit. Extend the live receipt with identity-correct retry and fallback-cascade observables; do not weaken the existing tiered publisher or measurement audit.

**Tech Stack:** Python 3.11+, dataclasses, JSON/SHA hashing, pytest, existing `AgentLoop`, existing EvidenceRecord v2 and final-answer audit, Flask/Alpine browser fixture, real configured DeepSeek provider.

## Global Constraints

- Work only in `D:\Project\Daily\data-agent\.worktrees\analysis-reliability` on `codex/analysis-reliability`.
- Implementation baseline is `4cab45238af0547cc13b55908b6683913a9ee3fc`; preserve all pre-existing uncommitted work.
- Run Python with `PYTHONPATH=D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests` and `D:\Project\Daily\data-agent\.venv\Scripts\python.exe`.
- Use `apply_patch` for every source, test, plan, and documentation edit.
- Do not infer evidence from claim text, values, labels, or fuzzy similarity. Alias expansion is exact and turn-local.
- Do not weaken plan, step, requirement, dataset-version, computation, measurement, value, unit, scope, or verification checks.
- Preserve mixed-tier publication: verified claims remain normal, safe unsupported claims may be exploratory, and the whole answer is not stripped.
- A failed fallback call never creates pending work; a failed resolution call never clears pending work.
- Gate F stores bounded counts, statuses, action labels, reason codes, and hashes only. It stores no raw arguments, Python code, prompt, answer, reasoning, or uploaded rows.
- Any `src/`, `scripts/`, `tests/`, or `pyproject.toml` change invalidates all previous Gate E and Gate F receipts.
- Do not stage, commit, merge, or push until the user explicitly authorizes the exact action.
- Do not mark Task 12 complete unless A-F are PASS for one release-source digest and both final review passes have no unresolved high/medium findings.

---

## File and ownership map

| File | Responsibility after this plan |
|---|---|
| `src/data_agent/agent/execution_control.py` | Own success-based fallback pending state and proactive resolution hints. |
| `src/data_agent/agent/loop.py` | Report successful tool identity to execution control, retain the exact current-turn alias map, and pass it to final audit. |
| `src/data_agent/agent/evidence_contracts.py` | Build the bounded alias catalog and expand exact current-turn aliases to full evidence identities. |
| `src/data_agent/agent/synthesis_policy.py` | Carry alias catalog text and immutable alias mappings into synthesis prompt assembly. |
| `src/data_agent/agent/trust_workflow_runtime.py` | Expand aliases before invoking the unchanged deterministic final-answer audit. |
| `scripts/replay_analysis_reliability.py` | Reconstruct canonical call identities and bounded live fallback/verified-claim observables. |
| `scripts/acceptance/live_provider_gate_contract.py` | Validate new receipt fields and require zero fallback cascades plus a nonzero verified core. |
| `tests/test_execution_control.py` | State-transition and proactive-hint RED/GREEN coverage. |
| `tests/test_tool_recovery.py` | Sync/stream/parallel loop result-path coverage. |
| `tests/test_automatic_evidence_projection.py` | Alias catalog ordering, bounding, and exact map coverage. |
| `tests/test_synthesis_policy.py` | Ready-to-copy alias marker prompt coverage. |
| `tests/test_final_answer_claim_audit.py` | Exact expansion and unknown/stale/cross-metric rejection coverage. |
| `tests/test_final_answer_publish_gate.py` | End-to-end mixed verified/exploratory publication coverage. |
| `tests/test_live_provider_release_runner.py` | Exact retry identity, fallback cascade, verified core, and privacy coverage. |
| `tests/test_analysis_release_gate_runner.py` | Product receipt validation remains fail-closed for stale/new-schema receipts. |

---

### Task 1: Make fallback state success-owned and proactively visible

**Files:**
- Modify: `src/data_agent/agent/execution_control.py:376-500`
- Modify: `src/data_agent/agent/loop.py:3742-3751`
- Modify: `src/data_agent/agent/loop.py:4316-4325`
- Modify: `src/data_agent/agent/loop.py:4403-4412`
- Test: `tests/test_execution_control.py`
- Test: `tests/test_tool_recovery.py`

**Interfaces:**
- Consumes: `record_tool_call(tool_name, args)`, `record_tool_error(tool_name, args, error)`, and the existing fallback-resolution allowlist.
- Produces: `record_tool_success(tool_name: str = "") -> None` and a prompt hint that exposes pending fallback state without raw output.

- [ ] **Step 1: Write state-transition RED tests**

Add to `tests/test_execution_control.py`:

```python
def test_failed_run_python_does_not_create_pending_fallback():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis"))
    args = {"purpose": "custom check", "code": "raise ValueError('x')"}

    state.record_tool_call("run_python", args)
    state.record_tool_error("run_python", args, '{"error":"x"}')

    assert state.pending_fallback_resolution is False


def test_successful_run_python_sets_pending_and_prompt_names_resolution():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis"))
    args = {"purpose": "custom check", "code": "print(1)"}

    state.record_tool_call("run_python", args)
    state.record_tool_success("run_python")

    hint = state.prompt_hint()
    assert state.pending_fallback_resolution is True
    assert "pending resolution" in hint
    assert "record_evidence_record" in hint
    assert "Do not call run_python again" in hint
    budget_index = hint.find("Execution budget")
    assert budget_index == -1 or hint.index("pending resolution") < budget_index


def test_failed_resolution_does_not_clear_pending_fallback():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis"))
    state.record_tool_call("run_python", {"purpose": "check", "code": "print(1)"})
    state.record_tool_success("run_python")

    resolution = {"record_json": "{}"}
    state.record_tool_call("record_evidence_record", resolution)
    state.record_tool_error(
        "record_evidence_record",
        resolution,
        '{"error":"invalid record"}',
    )

    assert state.pending_fallback_resolution is True


def test_successful_resolution_clears_pending_fallback():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis"))
    state.record_tool_call("run_python", {"purpose": "check", "code": "print(1)"})
    state.record_tool_success("run_python")

    state.record_tool_call("record_evidence_record", {"record_json": "{}"})
    state.record_tool_success("record_evidence_record")

    assert state.pending_fallback_resolution is False
```

Update the existing `test_run_python_success_requires_resolution_before_more_exploration` to call `record_tool_success("run_python")`.

- [ ] **Step 2: Run the new state tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_execution_control.py -k "pending_fallback or run_python_success_requires_resolution" -q
```

Expected: FAIL because attempted calls currently mutate pending state and `record_tool_success` does not accept a tool name.

- [ ] **Step 3: Move fallback transitions to successful outcomes**

In `TurnExecutionState.record_tool_call`, retain call and budget counters but remove both pending-state assignments. Replace `record_tool_success` with:

```python
def record_tool_success(self, tool_name: str = "") -> None:
    self.consecutive_errors = 0
    self.consecutive_error_recovery_attempted = False
    if tool_name == "run_python":
        self.pending_fallback_resolution = True
    elif tool_name in self._fallback_resolution_tools():
        self.pending_fallback_resolution = False
```

Do not change `record_tool_error`; failure must preserve the pre-call pending state.

- [ ] **Step 4: Add the proactive prompt hint**

At the beginning of `prompt_hint()` after the empty-turn guard, append:

```python
if self.pending_fallback_resolution:
    allowed = ", ".join(sorted(self._fallback_resolution_tools()))
    hints.append(
        "The previous run_python result is pending resolution. Before any "
        "additional analysis tool, resolve it with exactly one allowed "
        f"evidence, limitation, task, or user-confirmation action: {allowed}. "
        "Do not call run_python again yet."
    )
```

Keep existing budget hints after this block. Do not return early merely because the pending hint exists.

- [ ] **Step 5: Pass the successful tool name through every loop path**

Replace all three production calls:

```python
turn_state.record_tool_success()
```

with:

```python
turn_state.record_tool_success(tc.name)
```

Add a focused test in `tests/test_tool_recovery.py` that executes a failed `run_python` followed by a normal structured tool and asserts the latter is not rejected with `Fallback Python result must be resolved`. Add a successful fallback case that asserts the next model prompt contains `pending resolution` before any subsequent tool is selected.

- [ ] **Step 6: Run execution-control and recovery suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_execution_control.py tests/test_tool_recovery.py tests/test_sandbox_contract.py -q
```

Expected: PASS; failed fallback calls leave no pending state, successful fallback calls require an explicit successful resolution, and all loop paths report the tool name.

- [ ] **Step 7: Review checkpoint without committing**

Inspect `git diff -- src/data_agent/agent/execution_control.py src/data_agent/agent/loop.py tests/test_execution_control.py tests/test_tool_recovery.py`. Do not stage or commit without explicit user authorization.

---

### Task 2: Add exact compact evidence aliases to synthesis and audit

**Files:**
- Modify: `src/data_agent/agent/evidence_contracts.py:3540-3715`
- Modify: `src/data_agent/agent/synthesis_policy.py:21-260`
- Modify: `src/data_agent/agent/loop.py:2130-2145`
- Modify: `src/data_agent/agent/loop.py:2303-2350`
- Modify: `src/data_agent/agent/loop.py:2613-2623`
- Modify: `src/data_agent/agent/trust_workflow_runtime.py:25-55`
- Test: `tests/test_automatic_evidence_projection.py`
- Test: `tests/test_synthesis_policy.py`
- Test: `tests/test_final_answer_claim_audit.py`
- Test: `tests/test_final_answer_publish_gate.py`

**Interfaces:**
- Produces: `BoundedEvidenceAliasCatalog(text: str, aliases: tuple[tuple[str, str, str, str], ...])`.
- Produces: `build_bounded_evidence_alias_catalog(records, max_records=12, max_chars=6000) -> BoundedEvidenceAliasCatalog`.
- Produces: `expand_evidence_alias_markers(answer_text, aliases) -> str`.
- Extends: `audit_final_answer_draft(..., evidence_aliases=())`.

- [ ] **Step 1: Write bounded alias catalog RED tests**

Add to `tests/test_automatic_evidence_projection.py`:

```python
def test_bounded_alias_catalog_emits_ready_marker_and_exact_map():
    record = _catalog_record_with_two_measurements()
    catalog = build_bounded_evidence_alias_catalog(
        [record], max_records=8, max_chars=2000
    )

    first_key = record["measurements"][0]["identity"]["measurement_key"]
    second_key = record["measurements"][1]["identity"]["measurement_key"]
    assert "marker=[[evidence:ae01#am01]]" in catalog.text
    assert "marker=[[evidence:ae01#am02]]" in catalog.text
    assert catalog.aliases == (
        ("ae01", "am01", record["id"], first_key),
        ("ae01", "am02", record["id"], second_key),
    )


def test_alias_map_contains_only_entries_that_fit_catalog_bound():
    record = _catalog_record_with_two_measurements()
    full = build_bounded_evidence_alias_catalog(
        [record], max_records=8, max_chars=2000
    )
    first_line_limit = len(full.text.splitlines()[0]) + 1 + len(full.text.splitlines()[1])
    bounded = build_bounded_evidence_alias_catalog(
        [record], max_records=8, max_chars=first_line_limit
    )

    assert len(bounded.aliases) == 1
    assert "ae01#am02" not in bounded.text
```

Use the existing real measurement-identity fixture rather than a hand-built unvalidated marker shape.

- [ ] **Step 2: Run alias catalog tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_automatic_evidence_projection.py -k "alias_catalog" -q
```

Expected: FAIL because the bundle type and builder do not exist.

- [ ] **Step 3: Refactor the existing catalog candidate generation once**

In `evidence_contracts.py`, extract the current sorted, validated, deduplicated candidate creation into one private helper used by both the legacy full-ID catalog and the new alias catalog. Add:

```python
@dataclass(frozen=True)
class BoundedEvidenceAliasCatalog:
    text: str
    aliases: tuple[tuple[str, str, str, str], ...] = ()
```

The new builder must:

1. use the exact existing candidate order;
2. assign one `aeNN` per emitted EvidenceRecord and one `amNN` per emitted measurement within that record;
3. render `marker=[[evidence:aeNN#amNN]]` instead of full `id=` and `measurement_key=` fields;
4. append an alias tuple only after the rendered line passes both `max_records` and `max_chars`;
5. emit no alias for unbound measurements.

Keep `build_bounded_evidence_catalog(...) -> str` backward compatible for non-synthesis callers.

- [ ] **Step 4: Write exact expansion RED tests**

Add to `tests/test_final_answer_claim_audit.py`:

```python
def test_exact_alias_expands_to_full_measurement_marker(identity_evidence):
    key = identity_evidence["measurements"][0]["identity"]["measurement_key"]
    expanded = expand_evidence_alias_markers(
        "Revenue increased 12% [[evidence:ae01#am01]].",
        (("ae01", "am01", identity_evidence["id"], key),),
    )
    assert expanded == (
        "Revenue increased 12% "
        f"[[evidence:{identity_evidence['id']}#{key}]]."
    )


def test_unknown_or_stale_alias_is_not_expanded(identity_evidence):
    source = "Revenue increased 12% [[evidence:ae99#am99]]."
    assert expand_evidence_alias_markers(source, ()) == source


def test_alias_cannot_cross_bind_equal_value_metric(identity_evidence):
    key = identity_evidence["measurements"][0]["identity"]["measurement_key"]
    audit = _identity_audit(
        expand_evidence_alias_markers(
            "Profit increased 12% [[evidence:ae01#am01]].",
            (("ae01", "am01", identity_evidence["id"], key),),
        ),
        identity_evidence,
    )
    assert audit["status"] == "blocked"
    assert "measurement_metric_mismatch" in audit["claim_checks"][0]["reason_codes"]
```

- [ ] **Step 5: Run expansion tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_final_answer_claim_audit.py -k "alias" -q
```

Expected: FAIL because alias expansion does not exist.

- [ ] **Step 6: Implement lexical exact expansion**

In `evidence_contracts.py`, compile a marker regex compatible with the existing syntax and implement:

```python
def expand_evidence_alias_markers(
    answer_text: str,
    aliases: Sequence[tuple[str, str, str, str]],
) -> str:
    alias_map = {
        (alias_evidence, alias_measurement): (evidence_id, measurement_key)
        for alias_evidence, alias_measurement, evidence_id, measurement_key in aliases
    }

    def replace(match: re.Match[str]) -> str:
        target = alias_map.get((match.group(1), match.group(2)))
        if target is None:
            return match.group(0)
        return f"[[evidence:{target[0]}#{target[1]}]]"

    return _EVIDENCE_ALIAS_MARKER.sub(replace, answer_text or "")
```

The regex must require both alias components. It must not match or rewrite full EvidenceRecord markers.

- [ ] **Step 7: Carry the exact prompt alias map into audit**

Extend `SynthesisPolicy` with:

```python
evidence_aliases: tuple[tuple[str, str, str, str], ...] = ()
```

Make `_build_catalog_for_plan` return the new bundle and pass its text and aliases into every policy constructor. Update `build_synthesis_instruction` to include `<allowed_evidence_aliases>` and the ready-to-copy markers from the alias catalog; do not ask the model to reconstruct full IDs.

In `_maybe_inject_synthesis_policy`, assign:

```python
self._turn_synthesis_evidence_aliases = tuple(policy.evidence_aliases)
```

Reset that tuple in `_reset_turn_tracking`. Extend `audit_final_answer_draft` with the optional tuple and expand before `build_final_answer_audit`. Call it from `AgentLoop` with the exact stored tuple.

- [ ] **Step 8: Write synthesis and publication integration tests**

Add assertions that:

- `build_synthesis_instruction` contains `[[evidence:ae01#am01]]` and does not require the full EvidenceRecord ID in the model-facing marker;
- an `AgentLoop` audit with the current alias map verifies the intended claim;
- the same alias with an empty next-turn map is not verified;
- one verified claim and one exploratory claim produce a complete mixed-tier answer with no internal marker leakage;
- unknown alias markers are removed from both ordinary publication and audit fallback output even though they remain unexpanded for fail-closed audit evaluation.

- [ ] **Step 9: Run alias, audit, and publication suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_automatic_evidence_projection.py tests/test_synthesis_policy.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_tiered_analysis_publication.py -q
```

Expected: PASS; exact aliases verify, unknown aliases fail at claim level, semantic collisions remain blocked, and public Markdown contains no marker.

- [ ] **Step 10: Review checkpoint without committing**

Inspect the scoped diff and confirm there is one alias authority and one full audit authority. Do not stage or commit without explicit user authorization.

---

### Task 3: Correct Gate F failure identity and prove a verified core

**Files:**
- Modify: `scripts/replay_analysis_reliability.py:1367-1588`
- Modify: `scripts/acceptance/live_provider_gate_contract.py`
- Modify: `tests/test_live_provider_release_runner.py`
- Modify: `tests/test_analysis_reliability_replays.py`
- Modify: `tests/test_analysis_release_gate_runner.py`

**Interfaces:**
- Extends each internal tool outcome with `arguments_hash: str` and `fallback_resolution_blocked: bool`.
- Extends each persisted run receipt with `unresolved_fallback_blocked_calls: int` and `verified_material_claims: int`.
- Keeps raw arguments and error text out of the receipt.

- [ ] **Step 1: Write exact retry-identity RED tests**

Add to `tests/test_live_provider_release_runner.py`:

```python
def test_different_arguments_are_not_one_repeated_failure():
    messages = _tool_failure_messages(
        ("preview_data", {"name": "a"}, "budget_exceeded"),
        ("preview_data", {"name": "b"}, "budget_exceeded"),
        ("preview_data", {"name": "c"}, "budget_exceeded"),
    )
    outcomes = replay_analysis_reliability._session_tool_outcomes(messages)
    assert replay_analysis_reliability._repeated_failure_max(outcomes) == 1


def test_identical_call_failure_three_times_is_rejected():
    messages = _tool_failure_messages(
        *[("preview_data", {"name": "a"}, "budget_exceeded")] * 3
    )
    outcomes = replay_analysis_reliability._session_tool_outcomes(messages)
    assert replay_analysis_reliability._repeated_failure_max(outcomes) == 3
```

- [ ] **Step 2: Write new live-threshold RED tests**

Extend the passing run fixture with:

```python
"unresolved_fallback_blocked_calls": 0,
"verified_material_claims": 1,
```

Add:

```python
def test_unresolved_fallback_cascade_fails_live_run():
    run = _passing_run(1)
    run["unresolved_fallback_blocked_calls"] = 1
    result = evaluate_live_provider_run(run)
    assert result["status"] == "FAIL"
    assert "unresolved_fallback_cascade" in result["reason_codes"]


def test_fixed_live_scenario_requires_verified_material_claim():
    run = _passing_run(1)
    run["verified_material_claims"] = 0
    result = evaluate_live_provider_run(run)
    assert result["status"] == "FAIL"
    assert "verified_material_claim_missing" in result["reason_codes"]
```

Add FAIL and BLOCKED privacy tests proving any raw `arguments`, `code`, `answer`, or `error_message` field remains rejected.

- [ ] **Step 3: Run Gate F tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_live_provider_release_runner.py -q
```

Expected: FAIL because arguments identity and the two new receipt fields are absent.

- [ ] **Step 4: Implement canonical bounded outcome reconstruction**

Add `import hashlib`. In `_session_tool_outcomes`, replace the name-only call map with a map from `tool_call_id` to `(tool_name, arguments_hash)`. Parse each assistant tool call's argument JSON and compute the same canonical SHA-1 prefix used by `TurnExecutionState`:

```python
raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
arguments_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
```

For invalid argument JSON, hash `{"raw": <exact argument string>}` deterministically. Add only the hash to outcomes.

Set `fallback_resolution_blocked=True` only when the bounded server-owned error text exactly contains:

```text
Fallback Python result must be resolved into evidence, limitations, task state, or user confirmation before more exploration.
```

Implement `_repeated_failure_max` using `(tool_name, error_category, arguments_hash)`.

- [ ] **Step 5: Add live receipt observables and thresholds**

In `_run_one_live_provider_analysis`, derive:

```python
unresolved_fallback_blocked_calls = sum(
    bool(outcome.get("fallback_resolution_blocked")) for outcome in outcomes
)
verified_material_claims = sum(
    action == "verified" for action in publication_actions.values()
)
```

Add both integer fields to `_RUN_FIELDS`. In `evaluate_live_provider_run`, require exactly zero unresolved fallback blocks and at least one verified material claim. Preserve the existing audit-pass-or-exploratory rule so a mixed-tier answer remains acceptable.

- [ ] **Step 6: Run live contract, replay, and product receipt tests**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_live_provider_release_runner.py tests/test_analysis_reliability_replays.py tests/test_analysis_release_gate_runner.py -q
```

Expected: PASS; differently parameterized calls are distinct, exact retry loops fail, fallback cascades fail, markerless all-exploratory runs fail the fixed scenario, and receipt privacy remains closed.

- [ ] **Step 7: Review checkpoint without committing**

Confirm `git diff` contains no raw live prompt, model answer, Python code, tool arguments, or error text in persisted receipt fields. Do not stage or commit without explicit user authorization.

---

### Task 4: Run fresh deterministic verification and freeze the release source

**Files:**
- Runtime output only under a new temporary directory.

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: fresh A-D PASS evidence and one final release-source digest used by Gates E/F.

- [ ] **Step 1: Run all affected focused suites**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_execution_control.py tests/test_tool_recovery.py tests/test_sandbox_contract.py tests/test_automatic_evidence_projection.py tests/test_synthesis_policy.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_tiered_analysis_publication.py tests/test_live_provider_release_runner.py tests/test_analysis_reliability_replays.py tests/test_analysis_release_gate_runner.py -q
```

Expected: all selected tests PASS with zero unexpected skips.

- [ ] **Step 2: Run the complete Python and direct-tool baseline**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -W error::pytest.PytestReturnNotNoneWarning -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' tests/test_tools_comprehensive.py
```

Expected: pytest exits 0; the direct runner reports zero FAIL.

- [ ] **Step 3: Run compile, JavaScript, and diff checks**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m compileall -q src/data_agent scripts tests
node --check src/data_agent/web/static/js/app.js
git diff --check
```

Also run `node --check` for every tracked `.js` file under `src/data_agent/web/static/js`.

- [ ] **Step 4: Run deterministic A-D aggregator**

Run `scripts/run_analysis_release_gates.py --profile deterministic` with a new temporary output path. Require Gates A-D PASS and process exit 0.

- [ ] **Step 5: Compute and freeze the release-source digest**

Compute `release_source_digest(ROOT)`, record the exact digest and current HEAD, and run `git status --short`. From this point, any runtime/test edit returns execution to Task 4 Step 1 and invalidates later receipts.

---

### Task 5: Regenerate actual Browser Gate E for the frozen digest

**Files:**
- Runtime output only: new `analysis_browser_gate.v1.json`.

**Interfaces:**
- Consumes: Task 4 digest and `scripts/acceptance/run_web_sse_fixture.py`.
- Produces: one actual-browser PASS receipt for the exact digest, or an honest BLOCKED/FAIL result.

- [ ] **Step 1: Read and use the current in-app browser skill**

Use `browser:control-in-app-browser`; do not install or substitute standalone Playwright, Selenium, raw CDP, or another browser surface.

- [ ] **Step 2: Start the isolated fixture from worktree source**

Bind only `127.0.0.1` on a free known port, use a fresh temporary output directory, and verify the fixture reports `web_sse_fixture_v1`. Keep the server process identity so only that process is stopped later.

- [ ] **Step 3: Capture all ten required DOM observations**

Through the normal page and upload UI, record:

1. upload starts analysis;
2. progress appears before answer text;
3. first final chunk appears before the second;
4. complete answer appears before `turn_end`;
5. Markdown table and limitation render;
6. answer persists after refresh;
7. answer survives session switching;
8. suspend/resume leaves a nonblank assistant turn;
9. interruption leaves a nonblank assistant turn;
10. forced error leaves a nonblank assistant turn.

Do not infer a missed timing observation from the server trace.

- [ ] **Step 4: Write and validate the Gate E receipt**

Use `write_browser_gate_receipt`, then run the browser receipt validator against the Task 4 root. Require exact digest match and PASS.

- [ ] **Step 5: Stop only the fixture process**

Confirm the selected port no longer listens. If browser security blocks the actual observation, stop safely, record Gate E as BLOCKED, and ask the user for the required next action. Do not circumvent browser policy.

---

### Task 6: Regenerate three-run real-provider Gate F

**Files:**
- Runtime output only: new `analysis_live_provider_gate.v1.json` and isolated synthetic run directories.

**Interfaces:**
- Consumes: the same frozen digest as Gate E and the configured real provider.
- Produces: exactly three fresh run outcomes and one validated Gate F receipt.

- [ ] **Step 1: Request explicit authorization for exactly three calls**

State the provider host, configured model, synthetic-data scope, fixed prompt, receipt privacy boundary, and that any rerun requires separate authorization. Do not start until the user approves.

- [ ] **Step 2: Verify provider configuration without exposing secrets**

Report only model ID, API base, and whether a key is present. Never print the key or environment file contents.

- [ ] **Step 3: Run exactly three live sessions**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/replay_analysis_reliability.py --mode live --runs 3 --output-dir $liveGateRoot --receipt $liveReceipt
```

Do not retry a failed run inside the same authorization.

- [ ] **Step 4: Validate Gate F independently**

Require:

- exact source digest and model identity;
- exactly runs `live_1`, `live_2`, `live_3`;
- every run PASS;
- `unresolved_fallback_blocked_calls == 0`;
- `verified_material_claims >= 1`;
- `repeated_failure_max <= 2` using exact call identity;
- complete Chinese findings, recommendations, and limitations;
- progress before final text;
- streamed/persisted equality;
- privacy whitelist compliance.

If any condition fails, keep Gate F FAIL, diagnose before proposing another call, and request new authorization for any rerun.

---

### Task 7: Run product A-F, complete reviews, and update status honestly

**Files:**
- Modify only after PASS: `docs/superpowers/specs/2026-08-08-fallback-resolution-and-compact-evidence-alias-design.md`
- Modify only after PASS: `docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md`
- Modify only after PASS: `docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md`
- Modify only after PASS: `.superpowers/sdd/2026-07-28-web-sse-and-live-release-validation/progress.md`

**Interfaces:**
- Consumes: same-digest Gate E and Gate F PASS receipts plus deterministic A-D.
- Produces: final `analysis_reliability_release.v1`, review evidence, and an explicit branch handoff.

- [ ] **Step 1: Run the product aggregator**

Run `scripts/run_analysis_release_gates.py --profile product` with both exact receipt paths. Require process exit 0, `overall_status="PASS"`, `product_release_passed=true`, and A-F all PASS.

- [ ] **Step 2: Perform specification-compliance review**

Review every requirement in the approved 2026-08-08 design and both 2026-07-28 release documents. Record any missing behavior as high/medium/low. Any confirmed high/medium finding returns to a RED test and invalidates both receipts if runtime/test source changes.

- [ ] **Step 3: Perform code-quality and trust-boundary review**

Review fallback ownership, prompt/runtime authority, alias scoping, stale alias rejection, semantic collision rejection, receipt privacy, exact retry identity, Web background-session ownership, and false-green paths. Resolve all confirmed high/medium findings with TDD.

- [ ] **Step 4: Rerun affected and product gates after review fixes**

If review changes source/tests, return to Task 4 and regenerate E/F. Documentation-only edits may reuse receipts only after recomputing and confirming an unchanged release-source digest.

- [ ] **Step 5: Update documentation only after the final PASS**

Record an implementation commit only after it actually exists; before commit, record branch, HEAD baseline, digest, report paths, Gate E observation names, Gate F model/run count, and bounded remaining limitations. Mark the 2026-08-08 design `Implemented and validated` only after all stop gates pass.

- [ ] **Step 6: Fresh final verification**

Rerun full pytest, direct tools, compileall, all Web JavaScript syntax checks, `git diff --check`, and the product aggregator. Read exit codes and failure counts before making any completion claim.

- [ ] **Step 7: Ask for explicit branch action**

Report the complete diff and verification evidence, then offer separate choices to commit, merge, push, or keep the worktree. Perform none without explicit user selection.

---

## Plan stop gates

- After Task 1: stop if fallback state still changes on failed calls or failed resolution.
- After Task 2: stop if an unknown/stale alias can bind or equal-value cross-metric evidence verifies.
- After Task 3: stop if a receipt can contain raw arguments/content or an all-exploratory live run passes the fixed scenario.
- After Task 4: stop if any deterministic check fails or the release digest changes unexpectedly.
- After Task 5: stop if any actual browser observation is missing or browser policy blocks access.
- After Task 6: stop if any of the three live runs fails; do not rerun without new authorization.
- After Task 7: Task 12 remains HOLD unless A-F and both review passes are clean for the same final source.
