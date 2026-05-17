# Task Plan Versioning Design

## Background

Session `38465eb4172f` exposed a task-system design problem. The final analysis was completed and a report was produced, but the task panel still showed many pending tasks. Inspection showed that the session had 17 tasks:

1. Five pending tasks from recommended playbooks and confirmation handling.
2. Six pending workflow tasks generated from an `AnalysisSpec.method_plan`.
3. Six completed human-readable tasks that matched the actual executed analysis.

The visible failure is "task status did not update", but the root cause is deeper: candidate work, active plan work, and completed execution work are all stored as the same visible task type. The frontend then shows all scoped tasks as if they belong to one current plan.

The reference `reference/reference_code/task.py` and the s12 task-system article provide a useful baseline: task records should be durable work-graph items with dependencies and ready-state calculation. The worker lifecycle and ready-handshake references are useful future architecture material, but they are too large for the immediate issue. This phase should fix current-plan semantics before adding runtime workers.

## Goals

1. Make the task panel represent the current session's active plan, not every task ever created for the session.
2. Support replanning when the LLM or user changes the goal, without leaving stale pending tasks in the active panel.
3. Preserve old tasks for auditability by archiving or superseding them instead of deleting them.
4. Reduce reliance on the LLM remembering to call `task_update`.
5. Keep a clean boundary between durable plan tasks, suggestion/backlog items, and future runtime jobs.

## Non-Goals

1. Do not build a full worker runtime in this phase.
2. Do not implement background job scheduling, worker boot, or ready handshake yet.
3. Do not turn every simple answer into a task plan.
4. Do not delete historical tasks as a way to make the UI look clean.

## Current Problems

### Multiple Task Sources Create Duplicate Plans

Tasks can currently come from several paths:

1. `AnalysisFlowController.ensure_workflow_tasks()`
2. `task_create(analysis_spec_json=...)`
3. LLM-created tasks through `task_create(tasks=...)`
4. Confirmation tasks from `ensure_confirmation_task()`
5. Report/evidence-gap tasks

These paths do not share a plan identity or a single deduplication contract. As a result, two equivalent plans can coexist as separate pending/completed groups.

### Task Records Do Not Know Whether They Are Active

`TaskRecord.status` describes task progress, but not whether the task belongs to the active plan. A pending task can mean:

1. Still waiting in the current plan.
2. Superseded by a later plan.
3. A recommendation/backlog item.
4. A confirmation that is no longer blocking the chosen analysis path.

The UI cannot distinguish these cases.

### Completion Is Not Evidence-Aware

The agent prompt asks the LLM to call `task_update`, and `AgentLoop._auto_track_task_progress()` has a basic fallback that completes the first in-progress task after a successful tool call. Neither mechanism can reliably map an evidence record, report section, or tool result back to a specific task.

### Suggestions Are Displayed As Execution Tasks

Recommended playbooks and supporting checks can be useful, but they are not always chosen execution steps. They should not appear as pending active work unless the plan explicitly adopts them.

## Recommended Design: Active Plan Versioning

Phase 1 should introduce an explicit plan layer above tasks.

```text
TaskPlan
  id
  session_id
  project_name
  goal
  version
  status: active | superseded | completed | archived
  source: llm_plan | analysis_spec | system_replan | user_replan
  previous_plan_id
  created_at
  updated_at

TaskRecord
  id
  plan_id
  plan_version
  task_kind: plan_task | confirmation | backlog | suggestion | evidence_gap
  status: pending | in_progress | completed | blocked | superseded | archived | deleted
  ...
```

The active task panel should show only:

```text
session_id == current session
plan_id == active plan id
task_kind in (plan_task, confirmation, evidence_gap)
status not in (deleted, archived, superseded)
```

Historical tasks remain available through a future "history/backlog" view, but they do not pollute current progress.

## Plan Lifecycle

### Create

When the system has a clear analysis plan, it creates a `TaskPlan` and task records for that plan. This should be system-assisted and deterministic, not solely dependent on LLM tool calls.

Preferred first-phase authority:

1. `AnalysisFlowController` owns plan creation for analysis workflows.
2. `task_create` remains available, but it should attach to the active plan unless explicitly creating backlog/suggestion tasks.
3. `record_analysis_plan` or `record_analysis_spec` should not create an independent duplicate task set if an equivalent active plan already exists.

### Replan

When the user changes requirements or the LLM discovers the original plan is unsuitable, the system creates a new plan version.

Rules:

1. Mark old active plan as `superseded`.
2. Mark old pending/in-progress tasks as `superseded` unless they were completed and still relevant.
3. Create a new active plan with `previous_plan_id`.
4. Optionally carry completed evidence-linked tasks forward as references, not as active tasks.

### Complete

A plan can be completed when:

1. All required active plan tasks are completed, or
2. A final report/answer is produced and evidence coverage satisfies the plan's required outputs, or
3. The user explicitly accepts a partial result and remaining tasks are archived/superseded.

Completion should be a plan-level transition, not just a visual count.

## Task Status Semantics

Recommended statuses:

1. `pending`: part of active plan, not started.
2. `blocked`: part of active plan, waiting on dependencies or confirmation.
3. `in_progress`: currently being worked on by the LLM/tool loop.
4. `completed`: resolved by evidence, report output, or explicit update.
5. `superseded`: no longer part of the active plan because a newer plan replaced it.
6. `archived`: intentionally hidden from active work but kept for history.
7. `deleted`: logical delete.

This keeps `pending` meaningful: if the active session is finished, visible pending tasks should usually mean either genuinely incomplete work or a bug.

## Evidence-Aware Completion

The task system should combine LLM updates with deterministic system assistance.

### LLM Responsibility

The LLM should still call `task_update` when it starts or completes a clearly named task. This gives good real-time UX.

### System Responsibility

The system should also update task state when reliable artifacts appear:

1. `record_evidence_record` can complete a task whose `evidence_requirements`, `expected_output`, or capability match the evidence.
2. `generate_analysis_brief` or `generate_formal_report` can complete remaining report tasks if evidence coverage is sufficient.
3. `ask_user_question` / confirmation resolution can unblock confirmation tasks.
4. A tool failure should not complete a task; it may add `limitations` or keep the task in progress/blocked.

The first implementation can use conservative matching:

```text
task.analysis_spec_id == evidence.related_spec_id
and task.status in (pending, in_progress)
and any keyword/capability/expected_output overlap is present
```

If confidence is low, do not auto-complete; instead leave the task pending and let the LLM update it.

## Data Model Changes

### TaskPlan Storage

Use file-based persistence consistent with the current task manager:

```text
project/tasks/plans/plan_<id>.json
```

or, if keeping the first phase smaller:

```text
project/tasks/task_*.json
```

with plan metadata embedded in each task and active-plan metadata stored in:

```text
project/tasks/active_plans.json
```

The smaller first phase can use embedded task fields plus `active_plans.json`; a dedicated `TaskPlanManager` can follow if the logic grows.

### New Task Fields

Add defaults in `TaskManager._normalize()`:

```python
plan_id = ""
plan_version = 1
plan_status = ""
task_kind = "plan_task"
source = ""
superseded_by = ""
archived_at = ""
completed_by = ""
completed_at = ""
```

Existing task files remain readable.

## Backend API

`GET /api/tasks?session_id=...` should default to active-plan tasks only once plan versioning exists.

Add optional filters:

```text
scope=active      default
scope=all         all scoped tasks
scope=history     archived/superseded/completed old plans
task_kind=...
include_suggestions=true
```

The current `include_global`, `ready_only`, and `active_only` filters can remain, but they should operate after scope selection.

## Frontend Behavior

The default task panel should show:

1. Active plan title/goal.
2. Progress for active plan tasks only.
3. Pending, blocked, in-progress, and completed states.
4. A small indication if an old plan was superseded, without showing old tasks inline.

When all active tasks complete:

1. Keep the panel briefly visible.
2. Collapse it after a short delay.
3. Do not show superseded pending tasks as active work.

Future UI can add tabs:

1. `Current`
2. `History`
3. `Backlog/Suggestions`

Phase 1 should only implement `Current` correctly.

## Relationship To Runtime Jobs

Keep these concepts separate:

```text
TaskPlan: what the agent intends to accomplish for this analysis.
TaskRecord: durable step inside that plan.
RuntimeJob: currently running LLM/tool/report execution.
Event: notification that state changed.
```

Worker lifecycle, ready handshake, and event sourcing should be deferred until the durable plan semantics are correct.

## Migration Strategy

Existing task files should not be deleted. On first load:

1. Normalize missing plan fields.
2. Treat tasks without `plan_id` as legacy.
3. For a session with completed report/evidence and multiple legacy task groups, do not show legacy pending tasks in the active panel unless an active plan is explicitly selected.
4. Optionally provide an admin cleanup command later to archive legacy pending tasks.

For session `38465eb4172f`, the six completed tasks (`588`-`593`) represent the effective completed plan. The pending playbook/spec duplicates (`577`-`587`) should be treated as legacy/superseded, not active work.

## Testing Strategy

1. Unit tests for active plan creation and lookup.
2. Unit tests for superseding old plans on replan.
3. Unit tests ensuring scoped active task queries exclude superseded legacy tasks.
4. Regression test using `38465eb4172f`-style data:
   - Create candidate tasks.
   - Create duplicate spec tasks.
   - Complete the actual execution tasks.
   - Assert active panel returns only the effective active/completed plan, not stale pending tasks.
5. Tests for evidence-aware task completion with conservative matching.
6. API tests for `scope=active`, `scope=history`, and current default behavior.
7. Frontend/static tests confirming task progress uses active-plan response directly.

## Success Criteria

1. A completed session does not show stale pending tasks from superseded candidate plans.
2. Replanning creates a new active plan and removes old pending tasks from the active panel without deleting history.
3. Task progress is explainable from persisted state.
4. LLM task updates improve UX but are not the only path to correctness.
5. The design still leaves room for future backlog and runtime job views.

## Open Decisions

1. Whether to add a dedicated `TaskPlanManager` immediately or start with embedded plan fields plus `active_plans.json`.
2. Whether suggestions/backlog should use `TaskRecord` with `task_kind=suggestion` or a separate `SuggestionRecord`.
3. How strict evidence-to-task matching should be in the first implementation.
4. Whether legacy sessions should be auto-archived on read or only through an explicit migration command.

## Recommended First Implementation Slice

Start with the smallest slice that fixes the user-visible bug:

1. Add plan metadata fields to `TaskRecord`.
2. Add active-plan registry per session.
3. Make `AnalysisFlowController` create or reuse one active plan.
4. Make duplicate workflow generation attach to or skip the active plan.
5. Add `superseded` status.
6. Update `/api/tasks` default query to return active-plan tasks.
7. Add regression tests for duplicate pending tasks not showing after plan completion.

This solves the current task-panel correctness problem without prematurely building a worker runtime.
