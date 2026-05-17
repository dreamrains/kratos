# Analysis Flow and Task System Design

## Background

Session `0673c00f8ab9` exposed a workflow-level failure, not just a single bad reply. The user provided multiple data files and detailed analysis requirements in the first message. The agent loaded and profiled the data, but then stopped at a data overview and recommended analysis directions instead of executing the requested analysis.

The root symptom has two layers. First, initial intent classification mixes user intent with execution readiness: when no dataset is already loaded, a clear analysis request with attached file paths can be downgraded to `data_requirement / scope / request_data`. Second, after `load_data` finished in the same turn, the agent did not rebuild intent, analysis state, tool routing, or task workflow from the now-loaded workspace. The model therefore continued under a request-data frame even though the user had already provided data and analysis requirements.

The task polling issue exposed a separate but related design problem: the task system is used as durable workflow state, but the API and frontend treat it partly like runtime execution state. `/api/tasks?session_id=...` currently returns scoped tasks plus unrelated tasks, and the frontend compensates by filtering locally. This hides backend scope bugs and causes confusing polling behavior.

## Goals

1. Make the data analysis flow robust when data appears during the same user turn.
2. Improve analysis quality by adding explicit quality gates around planning, execution, evidence, and final answers.
3. Clarify task semantics as durable workflow items, not background jobs or worker runtime state.
4. Fix task scoping and polling so the frontend reflects real session tasks.
5. Leave a clean boundary for future runtime jobs, events, and worker lifecycle without forcing a large multi-worker rewrite now.
6. Separate user intent, intent clarity, data state, and execution readiness so clear analysis requests are not misclassified as data requirements.

## Non-Goals

1. Do not implement a full worker lifecycle system in this phase.
2. Do not replace the existing `AnalysisFlowController`, playbook, or `AnalysisSessionState` modules.
3. Do not require every simple question to create tasks or analysis specs.
4. Do not make frontend task polling the primary source of truth for execution progress.

## Design Approach

### Recommended Approach: Phase 1 Flow Governance

This phase treats `0673c00f8ab9` as a regression case and broadens the fix into a small analysis workflow state machine.

The key change is to separate classification from execution readiness, then introduce explicit checkpoints:

1. **Pre-turn intent classification**: classify what the user wants from the message content. A clear analysis goal with metrics and requirements is `directed_analysis` or `comprehensive_report`, even if data is not loaded yet.
2. **Execution readiness classification**: separately decide whether the turn is `ready`, `pending_load`, `missing_data`, or `insufficient_data`.
3. **Load-then-analyze routing**: when intent is clear and readiness is `pending_load`, first load the referenced files, then continue to analysis.
4. **Post-load replanning safety net**: if `load_data` succeeds during the turn, rebuild readiness, analysis state, prompt cache, tool routing, and task workflow from the updated workspace.
5. **Analysis spec gate**: directed analysis with usable data must either create an `AnalysisSpec` or clearly ask a blocking clarification.
6. **Execution evidence gate**: before final expert-facing output, the system checks whether evidence records or concrete tool results support the answer.
7. **Final-answer guard**: if the user asked for analysis but the agent only produced overview/recommendations, inject a corrective prompt instead of ending the turn.

This approach is intentionally narrower than a full runtime/job architecture. It fixes the current quality failures while creating boundaries that future runtime jobs can use.

### Alternative 1: Minimal Bug Fix Only

Only re-run `_prepare_analysis_turn()` after `load_data`.

This is fast, but it leaves the root classification bug in place. The system would still begin the turn as `data_requirement` even when the user supplied clear analysis requirements and file paths. It would also leave other quality leaks untouched: overview-only final answers, missing evidence records, task scoping, and unclear task/runtime semantics. It would likely improve `0673c00f8ab9` but not the broader class of user-experience failures.

### Alternative 2: Full Worker Runtime Rewrite

Introduce `RuntimeJobManager`, SSE event sourcing, ready handshakes, and worker lifecycle immediately.

This matches the design documents conceptually, but it is too large for the current failure. It risks changing many surfaces at once before the analysis state machine is reliable. The project should first make durable workflow state correct, then add runtime jobs.

## Analysis Flow Risks Found

### Intent and Readiness Are Coupled

The current intent classifier uses `data_state` to decide intent type. For analysis keywords it effectively does this:

```text
data_loaded -> directed_analysis
no_data -> data_requirement
```

This is wrong for messages that include both clear analysis requirements and data references. Intent should answer "what does the user want?" while readiness should answer "can the system execute now?" A clear analysis request with files attached or file paths provided should remain `directed_analysis`; its readiness should be `pending_load`.

Phase 1 should introduce an execution-readiness layer:

1. `ready`: usable datasets are already loaded.
2. `pending_load`: the message references loadable files, uploads, or attachments.
3. `missing_data`: the user requests analysis but provides no data source.
4. `insufficient_data`: data exists but cannot support the requested method or metrics.

This avoids treating "please analyze these files" as "please tell me what data to provide".

### Same-Turn Data State Drift

The current loop prepares analysis state before tool execution. When tools mutate the workspace, the turn-level intent and prompt cache may become stale. This affects not only `load_data`, but any tool that changes data availability, column structure, or analysis readiness.

Phase 1 should handle `load_data` first, then leave a generic hook for other data-mutating tools. This is a safety net after the root classifier is fixed, not the only repair.

### Overview-Only Completion

The agent can satisfy itself after `describe_dataset`, `preview_data`, `detect_data_quality`, or `interpret_dataset` even when the user requested deeper analysis. This creates a polished but incomplete answer.

The guard should detect turns where the user requested analysis, loaded data exists, but no real analysis/evidence/report tool was used. In that case the loop should continue with a corrective instruction.

### Weak AnalysisSpec Contract

`AnalysisFlowController.prepare_turn()` can select playbooks and create workflow tasks, but only when intent and state align. If the intent was classified before data was loaded, no spec or tasks are created.

Directed analysis should have a stronger contract:

1. If intent is clear and readiness is `ready`, create or apply an `AnalysisSpec`.
2. If intent is clear and readiness is `pending_load`, load data first, then create or apply an `AnalysisSpec`.
3. If intent is clear and readiness is `missing_data`, record a data requirement or ask for the missing data.
4. If the question is ambiguous, ask a clarification.
5. Do not silently downgrade to generic recommendations.

### Evidence Gate Is Advisory

`analysis_quality_summary()` exists, but final response generation is not strongly gated by it. This allows final answers that lack evidence records, method detail, sample size, time scope, or calculation method.

Phase 1 should add a lightweight final-answer guard. It should not block casual chat or exploratory data inspection. It should apply when the user requested directed analysis or a comprehensive report.

### Quality Requirement Extraction Is Fragile

The project extracts user quality requirements from long user input, but the extracted requirements are only reminded near budget convergence. In `0673c00f8ab9`, the important requirements were present at the start and should have influenced planning immediately.

Phase 1 should persist user requirements earlier and include them in post-load replanning and final-answer guards.

### Tool Budget Can Stop the Wrong Work

The execution budget distinguishes meta tools from analysis tools, which is good. However, if the workflow spends many calls on profiling and interpretation, it may converge before performing the requested analysis.

Phase 1 should define "profiling tools" separately from "analysis tools" for final-answer validation. Profiling alone is not enough for a directed analysis answer.

## Task System Design

### Task Semantics

`TaskRecord` should mean durable work item:

1. What analysis step needs to be done.
2. What it depends on.
3. Which session, project, workflow, and analysis spec it belongs to.
4. What evidence or confirmation resolves it.

It should not mean:

1. A running LLM turn.
2. A background worker process.
3. A frontend polling heartbeat.
4. A generic notification.

### Scope Rules

`TaskManager.list_for_scope(session_id, project_name)` should return only matching scoped tasks by default.

If global/unscoped tasks are needed, callers must request them explicitly, for example with `include_global=true`. API behavior should match frontend expectations; the frontend should not need to filter out unrelated tasks from a scoped endpoint.

### Ready Tasks

Add a ready concept:

```text
ready = status == "pending" and blockedBy is empty
```

The manager should expose `is_ready(task)` and `list_ready(session_id, project_name)`. This borrows the useful part of the reference `task.py` design without importing worker-runtime semantics.

### Workflow Tasks

Workflow tasks should be created from `AnalysisSpec.method_plan` once the spec exists. Each task should carry:

1. `session_id`
2. `project_name`
3. `workflow_id`
4. `analysis_spec_id`
5. `stage`
6. `node_type`
7. `required_capability`
8. `expected_output`
9. `evidence_requirements`

Task creation should be system-assisted and deterministic; it should not rely solely on the LLM remembering to call `task_create`.

### Runtime Jobs Boundary

This phase should not implement runtime jobs, but it should reserve the boundary:

```text
TaskRecord: durable workflow graph
RuntimeJob: currently running turn/tool/report execution
Event: notification that state changed
```

Future work can add `RuntimeJobManager` and event-driven updates without changing task semantics again.

## Frontend Polling Design

The frontend should continue to fetch tasks on:

1. session switch
2. `task_update` SSE event
3. explicit refresh
4. report/artifact generation completion

Periodic polling should be conservative:

1. no current session: no session-scoped polling
2. no active tasks: slow polling or disabled
3. pending/ready tasks: slow polling
4. in-progress tasks: faster polling

The API should return only scoped tasks for `?session_id=...`, so `activeTasks` no longer hides backend scope errors.

## Proposed Phase 1 Changes

### Backend Analysis Flow

1. Refactor intent planning so `intent_type` is based on user goal and clarity, not downgraded by `data_state`.
2. Add execution readiness inference for `ready`, `pending_load`, `missing_data`, and `insufficient_data`.
3. Detect data references conservatively:
   - local paths or filenames with supported extensions such as `.csv`, `.xlsx`, `.xls`, `.json`, `.parquet`
   - uploaded-file references already available to the session
   - attachment/file identifiers from the web UI
   - avoid classifying hypothetical wording such as "what csv files should I prepare?" as `pending_load`
4. Add a `load_then_analyze` action for clear analysis intent with `pending_load` readiness.
5. Detect successful `load_data` calls during the same turn.
6. After the load batch completes, rebuild data context, readiness, analysis state, prompt cache, tool groups, and execution budget.
7. Add a final-answer guard for directed analysis/comprehensive report requests:
   - loaded data exists
   - user asked for analysis/report
   - only data-loading/profiling tools were used
   - no evidence/spec/report was produced
   - then continue the loop with a corrective instruction
8. Add tests using a fake LLM client that reproduces `0673c00f8ab9`: clear analysis request plus files, load data, profile data, then attempt overview-only completion. The expected behavior is that the initial classification is analysis-like and the loop continues into analysis planning/execution instead of ending.

### Backend Task System

1. Change `list_for_scope()` to strict scoped filtering by default.
2. Add explicit include-global behavior for callers that need it.
3. Add `is_ready()` and `list_ready()`.
4. Update `/api/tasks` to support `include_global`, `ready_only`, and `active_only`.
5. Ensure workflow task creation remains idempotent for an `analysis_spec_id` or `workflow_id`.
6. Add regression tests for session isolation and ready filtering.

### Frontend Task Behavior

1. Keep event-driven refresh through `task_update`.
2. Reduce or stop interval polling when the current session has no non-completed tasks.
3. Use backend-scoped task responses directly.
4. Add frontend tests or static checks for task polling interval behavior.

## Quality Gates

### Intent Gate

The intent gate should classify these dimensions separately:

```text
intent_type: what the user wants
clarity: whether the goal and requested output are clear
data_state: what is already loaded in the workspace
execution_readiness: whether execution can start, must load first, or needs more data
recommended_action: the next system action
```

Example for `0673c00f8ab9` at the start of the first turn:

```text
intent_type = directed_analysis
clarity = clear
data_state = no_data
execution_readiness = pending_load
recommended_action = load_then_analyze
```

This gate is the root fix. Post-load replanning remains a safety net for load failures, unexpected schemas, unsupported files, and edge cases.

### Final Answer Guard

The final answer guard should be careful, not overbearing. It should apply only when all of these are true:

1. The latest user turn is analysis-like, not chat or simple QA.
2. Data is loaded.
3. The user's request was not just "look at the data structure".
4. The assistant is about to finish.
5. The turn used no substantive analysis/report/evidence tools.

When triggered, the loop should inject a short internal instruction such as:

```text
The user requested analysis, but the turn has only loaded/profiled data so far. Continue by creating or applying an AnalysisSpec, running the relevant analysis steps, and recording evidence before giving the final answer.
```

This should be an internal continuation, not a user-visible apology.

## Test Strategy

1. Unit tests for intent classification where no data is loaded but the message contains clear analysis requirements and loadable file references. Expected: `directed_analysis` or `comprehensive_report`, not `data_requirement`.
2. Unit tests for execution readiness inference: `ready`, `pending_load`, `missing_data`, and `insufficient_data`.
3. Unit tests that hypothetical data-preparation questions do not become `pending_load`.
4. Unit tests for post-load replanning after data load.
5. Unit tests for analysis final-answer guard classification.
6. Integration-style loop tests with a fake client reproducing the failing pattern.
7. Task manager tests for strict scope, global inclusion, ready tasks, and dependency clearing.
8. API tests for `/api/tasks?session_id=...`.
9. Frontend/static tests for polling behavior.
10. Existing golden scenario tests should remain valid; if they change, the new expected behavior must be stricter analysis completion, not weaker routing.

## Success Criteria

1. A first turn with files plus detailed analysis requirements is initially classified as analysis intent with `pending_load` readiness, not as `data_requirement`.
2. The first turn does not stop at dataset overview.
3. After `load_data`, the same turn can transition from load/profiling to analysis execution when data is available.
4. Directed analysis produces an `AnalysisSpec`, workflow tasks, evidence, or a clear blocking clarification.
5. `/api/tasks?session_id=0673c00f8ab9` returns only that session's tasks unless global inclusion is explicitly requested.
6. The frontend does not show empty task panels while continuously polling unrelated tasks.
7. Tests cover both the root classification failure and the post-load replanning safety net, and fail against the current implementation before code changes.

## Deferred Phase 2

1. Add `RuntimeJobManager` for active LLM/tool/report runs.
2. Replace most task polling with event-driven job/task updates.
3. Add worker lifecycle states such as spawning, ready, running, finished, failed.
4. Add a ready handshake for any future long-running worker.
5. Add admin views for global tasks and runtime jobs.
