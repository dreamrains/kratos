# Analysis Interaction Redesign

**Date:** 2026-06-19
**Status:** Approved design, pending implementation plan
**Scope:** Chart generation, multi-file analysis scope, confirmation lifecycle, and the current-session side panel

## 1. Problem Statement

Session `5ba97a7bb7db` exposed four symptoms with shared architectural causes:

1. Two user-level bar charts were saved successfully but rendered no visible bars because numeric user identifiers were treated as a continuous axis.
2. The analysis state contained four pending confirmations, while the conversation never received a suspended question card.
3. Four files explicitly supplied for one analysis were evaluated pairwise against the first file and generated unnecessary relationship confirmations.
4. The side panel exposed internal relationship states without explaining which files were involved, why a decision mattered, or how the user could act.

These are system-level failures rather than session-specific exceptions. The redesign must make invalid states difficult to represent and must reject unusable output before it becomes a user-visible artifact.

## 2. Design Principles

1. **User intent defines initial scope.** Files explicitly named or loaded in the same request are included by default.
2. **Participation is not relationship.** A file can participate in an analysis without being joined to every other file.
3. **Validate at the point of consequence.** Join keys, grains, and mapping assumptions are confirmed only when an operation depends on them.
4. **One confirmation lifecycle.** A blocking confirmation must be answerable, suspended, visible, resumable, and resolvable through one state machine.
5. **No unusable successful charts.** A chart that is technically serializable but visually misleading or unreadable is a validation failure.
6. **User-facing state describes decisions and impact.** Internal workflow labels remain available only as secondary diagnostic details.
7. **Backward-compatible reads, clean new writes.** Existing sessions remain inspectable, while new turns use the redesigned contracts.

## 3. Proposed Architecture

### 3.1 Analysis File Scope

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

### 3.2 Deferred Cross-File Operation Validation

Cross-file validation occurs when an operation requests a join, union, comparison mapping, or entity reconciliation.

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

The system asks a question only when the unresolved choice can materially change row counts, metric definitions, attribution, or conclusions. Questions must use dataset and file names rather than internal IDs and must describe the consequence of each option.

Safe operations do not require confirmation:

- independent summaries across included files;
- comparisons of separately aggregated metrics;
- joins with a validated unique key and compatible grain;
- unions with identical schemas and an explicit user request.

### 3.3 Confirmation State Machine

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

### 3.4 Chart Semantic Contract

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

### 3.5 Current-Session Side Panel

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

## 4. End-to-End Flows

### 4.1 Multi-File Request

1. User names four files in one request.
2. Each successful load creates an included scope entry linked to the same turn.
3. Planning may use any or all included files independently.
4. A join request triggers operation validation.
5. Only a consequential ambiguity suspends the turn.

### 4.2 Tool-Created Confirmation

1. Tool records a blocking confirmation.
2. The loop detects it immediately after the tool result.
3. State changes to suspended and SSE emits the question.
4. The side panel and conversation reference the same suspension.
5. The answer resolves the state and resumes execution.

### 4.3 Chart Request

1. Semantic roles are inferred from names, dtypes, cardinality, and values.
2. The requested chart is checked against its semantic contract.
3. Safe transformations are applied and recorded.
4. Unreadable specifications return structured recovery guidance without saving artifacts.
5. Only renderable figures are registered and displayed.

## 5. Compatibility and Migration

- Existing `analysis_state.json` files continue to deserialize.
- Legacy pending relationship confirmations without suspension IDs are treated as historical diagnostics, not actionable blockers.
- New scope entries can be derived from existing data pool and active bundle information when absent.
- Existing confirmed relationship choices remain visible under technical details.
- API responses add new fields before old fields are removed.
- No automatic mutation of historical session files is required.

## 6. Global Diagnostic Coverage

The implementation audit must cover more than the reported session:

1. Every chart type and all artifact save paths.
2. Tool-created, detector-created, method-created, and cleaning-created confirmations.
3. Structured, streaming, CLI, resume, interrupt, reload, and stale-session flows.
4. Single-file, same-turn multi-file, historical workspace file, explicit exclusion, independent summaries, joins, and unions.
5. Trust View API, conversation SSE state, sidebar rendering, and session reload parity.
6. Task confirmation metadata so task status cannot claim completion while a blocking dependency remains.

The audit should also search for state duplication, warning-only failure paths, stale pending items, raw internal IDs in user-facing strings, and code paths that register artifacts before validation finishes.

## 7. Testing Strategy

Implementation follows TDD with focused test groups:

- chart semantic and renderability contract tests;
- cross-chart regression matrix;
- same-turn file participation tests;
- deferred join validation tests;
- confirmation state-machine and post-tool suspension tests;
- final-response blocking invariant tests;
- Trust View API compatibility tests;
- side-panel content and actionability tests;
- reported session-shaped regression fixtures without hard-coding its session ID.

Each production change begins with a failing behavioral test. Targeted tests run after each slice, followed by the complete test suite.

## 8. Observability

Structured logs and metadata must identify:

- why a file was included or unused;
- why a cross-file operation required confirmation;
- confirmation lifecycle transitions;
- why a chart was rejected or transformed;
- whether a final response was blocked by an unresolved decision.

Logs must use stable IDs internally while user-facing responses use names and explanations.

## 9. Non-Goals

- Replacing Plotly.
- Rewriting all analysis tools or the task system.
- Changing output and export behavior.
- Automatically selecting a business-correct join when grain is ambiguous.
- Migrating every historical session file in place.
- Building a general BI chart editor.

## 10. Acceptance Criteria

1. Numeric identifiers cannot produce invisible bars or misleading continuous axes.
2. All supported chart types reject semantically invalid or non-renderable specifications before artifact registration.
3. Files explicitly provided in one request are available to the same analysis without relationship confirmations.
4. Cross-file confirmation occurs only at a consequential operation boundary.
5. Every blocking confirmation has one visible, answerable conversation card and one resumable suspension.
6. No final report is emitted while a blocking confirmation is unresolved.
7. The side panel names files, explains participation, and shows only actionable decisions.
8. Existing sessions remain readable.
9. Targeted and full regression suites pass.

