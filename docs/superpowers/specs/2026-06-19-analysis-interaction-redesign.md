# Analysis Interaction Redesign

**Date:** 2026-06-19
**Status:** Revised after dependency and root-cause audit; pending approval
**Scope:** Overall diagnosis and staged delivery boundaries for chart generation, confirmation lifecycle, multi-file analysis scope, and the current-session side panel

## 1. Problem Statement

Session `5ba97a7bb7db` exposed four symptoms with shared architectural causes:

1. Two user-level bar charts were saved successfully but rendered no visible bars because numeric user identifiers were treated as a continuous axis.
2. The analysis state contained four pending confirmations, while the conversation never received a suspended question card.
3. Four files explicitly supplied for one analysis were evaluated pairwise against the first file and generated unnecessary relationship confirmations.
4. The side panel exposed internal relationship states without explaining which files were involved, why a decision mattered, or how the user could act.

These are system-level failures rather than session-specific exceptions. They do not, however, form one indivisible implementation. The redesign defines shared principles while delivery is split into independently testable stages.

## 2. Root-Cause Audit

### 2.1 Chart generation

The reported charts fail because high-magnitude numeric identifiers are passed unchanged to Plotly. Plotly creates a continuous axis and derives a bar width that is effectively invisible relative to the identifier range.

The broader audit found additional independent defects:

- high-cardinality bar and line charts only emit warnings and still save unreadable artifacts;
- duplicate bar categories are silently aggregated with `mean`, regardless of metric semantics;
- pie charts ignore a supplied category/measure relationship and always count values from one column;
- box plots treat both `x_col` and `y_col` as independent measure series instead of category and measure;
- heatmaps ignore the requested fields and correlate every numeric column;
- stacked bars bypass the axis normalization helper used by ordinary bars;
- a column is considered numeric when only one value can be coerced;
- chart tests assert file creation and serialized strings but do not assert semantic correctness or renderability.

This subsystem is independent of confirmation, multi-file scope, and the side panel.

### 2.2 Confirmation lifecycle

There are two creation paths with different behavior:

- `ask_user_question` raises `UserConfirmationRequired` and suspends immediately;
- workflow components append records to `pending_confirmations` without raising.

The loop promotes pending records only once before entering the model/tool loop. A confirmation created by an ordinary tool during the loop is therefore not suspended in the same turn. Additional findings:

- synchronous and streaming loops duplicate suspension handling;
- the pending detector and the pending record can select different questions;
- a final response has no invariant that rejects unresolved blocking confirmations;
- session reconstruction restores messages but not an active confirmation card;
- suspension files are stored outside the session directory and are not exposed by the session API;
- frontend skip and cancel actions resume through the normal answer path, so cancellation can apply ordinary state updates;
- current tests cover individual helpers but not post-tool creation, reload, cancel semantics, or final-response blocking end to end.

This is a generic runtime issue. It must be fixed without depending on the multi-file redesign.

### 2.3 Multi-file analysis scope

File ingestion currently compares each new file with files in the active bundle. Relationship heuristics then decide whether the new file is admitted to the bundle and whether a confirmation is created. This conflates three questions:

1. Did the user provide the file for this analysis?
2. Can the file contribute independently?
3. Is a particular cross-file operation safe?

The tested session explicitly named four files, but only the first entered the active bundle automatically. The remaining files generated pairwise confirmations even though the later analysis used their datasets. Further findings:

- scope planning gives pending relationship records higher priority than goal relevance;
- an explicitly loaded file can be excluded by filename heuristics even when it is already in the active bundle;
- user-facing questions use internal file IDs rather than filenames;
- the relationship implementation was added across several recent commits and its tests encode relationship-first behavior, so a broad replacement would invalidate many assumptions at once;
- the project has one explicit dataset merge path in `transform_data`, but no general cross-file operation layer shared by every analysis tool.

The first multi-file delivery will therefore fix participation scope only. Join/union validation remains a separate follow-up audit and will not be abstracted until actual operation paths justify a shared layer.

### 2.4 Side panel

The current side panel is a projection of `active_bundle`, `file_relationships`, `analysis_scope_plan`, and a summarized confirmation gate. Its unclear wording is partly a presentation defect and partly a consequence of ambiguous backend state.

The panel redesign depends on stable confirmation and participation contracts. Implementing it earlier would hard-code another translation over data that is about to change. Confirmation-card restoration belongs to the confirmation stage; the broader data-scope information architecture belongs to the final UI stage.

## 3. Design Principles

1. **User intent defines initial scope.** Files explicitly named or loaded in the same request are included by default.
2. **Participation is not relationship.** A file can participate in an analysis without being joined to every other file.
3. **Validate at the point of consequence.** Join keys, grains, and mapping assumptions are confirmed only when an operation depends on them.
4. **One confirmation lifecycle.** A blocking confirmation must be answerable, suspended, visible, resumable, and resolvable through one state machine.
5. **No unusable successful charts.** A chart that is technically serializable but visually misleading or unreadable is a validation failure.
6. **User-facing state describes decisions and impact.** Internal workflow labels remain available only as secondary diagnostic details.
7. **Backward-compatible reads, clean new writes.** Existing sessions remain inspectable, while new turns use the redesigned contracts.

## 4. Target Architecture

### 4.1 Analysis File Scope

Replace relationship-first ingestion with a file participation model.

Each loaded file receives an `analysis_scope_entry`:

```json
{
  "file_id": "file_123",
  "dataset": "orders",
  "participation": "included",
  "reason_code": "explicit_request",
  "reason": "The file was explicitly supplied for this analysis.",
  "source_turn_id": "turn_123",
  "intended_uses": [],
  "status": "ready"
}
```

Supported participation states:

- `included`: available to tools and analysis planning.
- `unused`: available but not currently needed for the goal.
- `needs_scope_decision`: only for genuine ambiguity about whether the file belongs to the requested analysis.
- `unavailable`: could not be loaded or inspected.

Default rules:

- Files explicitly named in the current user request are `included`.
- Files loaded within the same user turn are `included` unless the user explicitly excludes them.
- A file that is clearly irrelevant may be `unused`; this is informative and non-blocking.
- Historical files already present in the workspace are not silently added to a new analysis.
- Pairwise key or theme similarity does not create a confirmation.

Legacy `dataset_bundles` and `file_relationships` remain readable during migration but no longer determine whether newly loaded files participate.

### 4.2 Deferred Cross-File Operation Validation

Cross-file validation is a future operation-level stage, not part of the initial scope repair. The first step is to inventory the actual merge, union, comparison mapping, and entity reconciliation paths.

An operation contract records:

```json
{
  "operation": "join",
  "left_dataset": "orders",
  "right_dataset": "coupons",
  "candidate_keys": ["user_id"],
  "left_grain": "order",
  "right_grain": "coupon_usage",
  "cardinality": "many_to_many",
  "risk": "row_multiplication",
  "decision": "needs_confirmation"
}
```

If the inventory supports a shared contract, the system will ask a question only when the unresolved choice can materially change row counts, metric definitions, attribution, or conclusions. Questions must use dataset and file names rather than internal IDs and must describe the consequence of each option.

Safe operations do not require confirmation:

- independent summaries across included files;
- comparisons of separately aggregated metrics;
- joins with a validated unique key and compatible grain;
- unions with identical schemas and an explicit user request.

### 4.3 Confirmation State Machine

All confirmation sources use one contract:

```text
draft -> pending -> suspended -> resolved
                         |-> cancelled
                         |-> expired
```

A confirmation is user-actionable only when it contains:

- stable confirmation ID;
- concrete question;
- at least one option or an explicit free-text response mode;
- state update payload;
- blocking surfaces;
- blocking reason and user-visible impact;
- suspension ID once delivered to the client.

Runtime invariants:

1. Tool execution may create a `pending` confirmation.
2. After every tool result, the loop checks for newly created blocking confirmations before asking the model to continue.
3. A blocking item transitions to `suspended`, is persisted, and emits exactly one `suspended` SSE event.
4. A final response cannot be emitted while a blocking confirmation remains pending or suspended.
5. Resolution applies state updates, records the answer, and resumes the interrupted turn.
6. Confirmations from abandoned plans, replaced specs, or completed non-dependent work become `expired`.
7. Informational uncertainty is not stored as a pending confirmation.

Method confirmation applies to the operation actually selected for execution. An optional predictive step inside a broad playbook must not block descriptive analysis that does not use that step.

### 4.4 Chart Semantic Contract

Chart validation becomes a pipeline:

```text
input fields
  -> semantic typing
  -> chart-specific validation
  -> aggregation and cardinality policy
  -> renderability checks
  -> artifact save
```

Semantic roles include:

- identifier;
- categorical dimension;
- ordered category;
- time;
- numeric measure;
- rate or proportion;
- geographic field;
- unknown.

Global rules:

- Identifier values are never plotted as continuous quantitative axes.
- Required measures must contain finite numeric values after coercion.
- Missingness and aggregation are recorded in metadata.
- Validation failures do not register HTML, PNG, JSON, or artifact entries.
- Warnings are reserved for readable charts with limitations; unreadable charts are errors.
- Rendered figures must contain non-empty traces with finite ranges.

Chart-specific rules:

| Chart | Required semantics | Rejected conditions |
|---|---|---|
| Line | ordered time/category plus measure | identifier trend axis, unordered high-cardinality axis |
| Bar | categorical/ordered dimension plus measure | continuous identifier axis, unreadable category count |
| Stacked bar | category, measure, grouping dimension | excessive groups, invalid totals, missing grouping field |
| Scatter | two measures | identifier used as a measure, non-numeric axes |
| Histogram | one measure | categorical or identifier metric |
| Box | measure, optional category | identifier as measure, excessive category count |
| Pie | category plus non-negative measure or counts | high cardinality, negative values, meaningless identifier slices |
| Heatmap | compatible matrix or two dimensions plus measure | empty/non-finite matrix, identifier correlation without explicit intent |
| Funnel | ordered stages and non-negative values | unreadable keys, mixed metric semantics, invalid stage order |

Identifier category policy:

- A low-cardinality identifier bar chart is converted to an explicit categorical axis.
- A high-cardinality identifier comparison is rejected with structured recovery alternatives such as Top N, before/after scatter, difference distribution, box plot, or summary table.
- The two reported 62-user charts therefore must not silently regenerate as 62 thin bars. The caller must choose a readable comparison form.

Artifact metadata gains `semantic_roles`, `renderability_status`, `category_count`, `transformations`, and structured `recovery_options`.

### 4.5 Current-Session Side Panel

The primary panel is redesigned around user questions.

#### Data used in this analysis

- Shows included filename, dataset name, row/column counts, and why it is included.
- Shows intended or observed use when available.
- Uses `Used`, `Available`, `Not used`, and `Unavailable` labels rather than relationship terminology.

#### Needs your decision

- Appears only for actionable `suspended` confirmations.
- Shows the concrete question, affected files or method, decision impact, and a `Go to question` action.
- Never displays a pending count that has no corresponding answerable conversation card.

#### Details

- Technical join evidence, key candidates, grain, and legacy relationship diagnostics move into a collapsed details area.
- Internal status values are translated to user-facing explanations.

The output and export sections are unchanged.

## 5. End-to-End Flows

### 5.1 Multi-File Request

1. User names four files in one request.
2. Each successful load creates an included scope entry linked to the same turn.
3. Planning may use any or all included files independently.
4. Independent analysis proceeds without relationship confirmation.
5. A later cross-file-operation stage may validate joins after the operation inventory is approved.

### 5.2 Tool-Created Confirmation

1. Tool records a blocking confirmation.
2. The loop detects it immediately after the tool result.
3. State changes to suspended and SSE emits the question.
4. The side panel and conversation reference the same suspension.
5. The answer resolves the state and resumes execution.

### 5.3 Chart Request

1. Semantic roles are inferred from names, dtypes, cardinality, and values.
2. The requested chart is checked against its semantic contract.
3. Safe transformations are applied and recorded.
4. Unreadable specifications return structured recovery guidance without saving artifacts.
5. Only renderable figures are registered and displayed.

## 6. Staged Delivery Plan

Each stage gets its own implementation plan, failing tests, production changes, verification report, and commit boundary. A later stage does not start until the previous stage passes its acceptance criteria.

### Stage 1: Chart contract and renderability

**Owns:** `tools/visualization.py`, chart artifact validation, and chart contract tests.

**Does not touch:** agent loop, analysis state, multi-file scope, Trust View, or side-panel markup.

Delivery slices:

1. Characterize the reported numeric-identifier failure and assert that no artifact is registered.
2. Add shared semantic typing and finite-value validation.
3. Correct bar/stacked-bar axis and cardinality handling.
4. Correct line, scatter, histogram, box, pie, heatmap, and funnel contracts one chart family at a time.
5. Add pre-save renderability checks and artifact atomicity.

Stop condition: if a correction requires changing an analysis tool's business aggregation, return a structured validation error instead of silently choosing an aggregation.

Stage gate:

- the two reported failure shapes are rejected or transformed into categorical axes according to the documented cardinality rule;
- every chart family has positive and negative semantic tests;
- rejected charts leave no HTML, JSON, PNG, or artifact-registry entry;
- chart, registry, report-consumer, and artifact tests pass before Stage 2 starts.

**Status (2026-06-19): complete on `codex/chart-contract-renderability`.**

- 48 focused chart contract and semantic tests pass, including the reported 62-user failure shape and artifact non-creation assertions.
- 213 chart, report, artifact, and offline Web consumer tests pass.
- 100 neighboring confirmation, multi-file, question-detection, and Trust View tests pass without production changes in those areas.
- The full pytest-compatible suite passes in four deterministic partitions: 1,554 passed and 11 skipped. Script-style modules are executed separately rather than collected by pytest.
- `test_tools_comprehensive.py` passes 108 checks with 2 documented skips after its duplicate stacked-bar fixture declares `aggregation="sum"`.
- `test_comparability.py` passes 13 checks. `test_v91.py` retains 4 baseline failures and `test_v10_new.py` retains 2 baseline failures; both reproduce unchanged on `main` and are outside Stage 1.
- Live-server scripts `test_sse_reactivity.py` and `test_web_gui.py` were not run because this stage changes the chart backend and their required server was not started; offline Web consumer tests cover the affected artifact paths.
- Stage 2 has not started.

### Stage 2: Confirmation lifecycle

**Owns:** confirmation state transitions, sync/stream loop promotion, suspension persistence, session restoration, resume/cancel behavior, and final-response invariants.

**Does not touch:** file relationship classification or side-panel data-scope layout.

Delivery slices:

1. Characterize a confirmation created after an ordinary tool result.
2. Extract one promotion path used by sync and streaming loops.
3. Separate answer, skip, cancel, expire, and resolve transitions.
4. Restore active suspensions through the session API and conversation reconstruction.
5. Enforce that blocking confirmations prevent final responses.

Stop condition: existing `ask_user_question` behavior and CLI prompting must remain green before pending-record promotion is enabled.

Stage gate:

- direct and pending-record confirmations share the same transitions;
- sync, streaming, CLI, resume, reload, skip, cancel, and stale-suspension tests pass;
- an unresolved blocking confirmation cannot coexist with a final response;
- no multi-file classification behavior changes in this stage.

### Stage 3: Multi-file participation scope

**Owns:** same-turn file participation, active analysis scope, legacy relationship compatibility, and scope-focused tests.

**Depends on:** Stage 2 confirmation semantics, but does not require a new confirmation for same-turn explicit files.

**Does not own:** generic join/union validation or final side-panel presentation.

Delivery slices:

1. Add same-turn and explicitly named file provenance.
2. Include those files in analysis scope without pairwise relationship confirmation.
3. Keep historical workspace files out unless explicitly selected.
4. Treat clearly unused files as non-blocking scope information.
5. Preserve read compatibility for legacy bundles and relationship records.

Stop condition: do not remove legacy fields or migrate historical sessions in place.

Stage gate:

- same-turn explicit files are included without pairwise confirmation;
- historical or explicitly excluded files are not silently included;
- legacy session fixtures still deserialize and render through existing API fields;
- no merge, join, union, or metric aggregation behavior changes in this stage.

### Stage 4: User-facing current-session panel

**Owns:** Trust View projection, side-panel content hierarchy, actionable decision navigation, and browser-level UI verification.

**Depends on:** Stage 2 active-confirmation API and Stage 3 participation scope.

Delivery slices:

1. Add an additive view model for used, available, unused, and unavailable files.
2. Show only suspended, answerable decisions in the primary panel.
3. Move legacy relationship diagnostics into collapsed technical details.
4. Add `Go to question` behavior and reload verification.
5. Verify that output and export UI is unchanged.

Stop condition: do not remove old API fields until all existing API and UI tests have additive replacements.

Stage gate:

- the primary panel shows filenames, participation reasons, and only actionable decisions;
- reload preserves the same active question and `Go to question` target;
- output and export sections are unchanged in static and browser verification;
- legacy diagnostic details remain available but are not presented as required user actions.

### Future Stage: Cross-file operation safety

After Stage 3, inventory `transform_data(merge)` and any tool-specific cross-file logic. Create a separate design only if repeated operation-level risks justify a shared validator. This work is explicitly excluded from the four-stage repair above.

## 7. Compatibility and Migration

- Existing `analysis_state.json` files continue to deserialize.
- Legacy pending relationship confirmations without suspension IDs are treated as historical diagnostics, not actionable blockers.
- New scope entries can be derived from existing data pool and active bundle information when absent.
- Existing confirmed relationship choices remain visible under technical details.
- API responses add new fields before old fields are removed.
- No automatic mutation of historical session files is required.

## 8. Global Diagnostic Coverage

The implementation audit must cover more than the reported session:

1. Every chart type and all artifact save paths.
2. Tool-created, detector-created, method-created, and cleaning-created confirmations.
3. Structured, streaming, CLI, resume, interrupt, reload, and stale-session flows.
4. Single-file, same-turn multi-file, historical workspace file, explicit exclusion, independent summaries, joins, and unions.
5. Trust View API, conversation SSE state, sidebar rendering, and session reload parity.
6. Task confirmation metadata so task status cannot claim completion while a blocking dependency remains.

The audit should also search for state duplication, warning-only failure paths, stale pending items, raw internal IDs in user-facing strings, and code paths that register artifacts before validation finishes.

## 9. Regression-Control Strategy

Implementation follows TDD with focused test groups:

- chart semantic and renderability contract tests;
- cross-chart regression matrix;
- same-turn file participation tests;
- confirmation state-machine and post-tool suspension tests;
- final-response blocking invariant tests;
- Trust View API compatibility tests;
- side-panel content and actionability tests;
- reported session-shaped regression fixtures without hard-coding its session ID.

Each production change begins with a failing behavioral test. Targeted tests run after each slice.

Regression controls:

1. Record the targeted baseline before each stage.
2. Test the changed module plus direct consumers after every slice.
3. Keep API changes additive until the final UI stage.
4. Commit each passing slice separately so it can be reverted without undoing other stages.
5. Use session-shaped fixtures rather than modifying session `5ba97a7bb7db`.
6. Run the full suite in deterministic test-file partitions because the single full-suite command exceeds the current 240-second execution window.
7. Run browser verification only after backend and static UI tests pass.
8. Compare artifact registry counts before and after rejected chart requests.
9. Verify existing-session read paths without rewriting historical state.

Current diagnostic baseline:

- chart contract: 21 passed;
- confirmation/interaction/entry: 109 passed;
- multi-file/Trust View: 92 passed;
- monolithic full suite: reached 46% with no failures before the 240-second command timeout; this is not a completed full-suite pass.

## 10. Observability

Structured logs and metadata must identify:

- why a file was included or unused;
- why a cross-file operation required confirmation;
- confirmation lifecycle transitions;
- why a chart was rejected or transformed;
- whether a final response was blocked by an unresolved decision.

Logs must use stable IDs internally while user-facing responses use names and explanations.

## 11. Non-Goals

- Replacing Plotly.
- Rewriting all analysis tools or the task system.
- Changing output and export behavior.
- Automatically selecting a business-correct join when grain is ambiguous.
- Migrating every historical session file in place.
- Building a general BI chart editor.
- Introducing a generic cross-file operation framework before operation paths are inventoried.
- Shipping all four stages in one undifferentiated change.

## 12. Overall Acceptance Criteria

1. Numeric identifiers cannot produce invisible bars or misleading continuous axes.
2. All supported chart types reject semantically invalid or non-renderable specifications before artifact registration.
3. Files explicitly provided in one request are available to the same analysis without relationship confirmations.
4. Scope repair does not silently introduce a new join or union policy.
5. Every blocking confirmation has one visible, answerable conversation card and one resumable suspension.
6. No final report is emitted while a blocking confirmation is unresolved.
7. The side panel names files, explains participation, and shows only actionable decisions.
8. Existing sessions remain readable.
9. Targeted and full regression suites pass.
