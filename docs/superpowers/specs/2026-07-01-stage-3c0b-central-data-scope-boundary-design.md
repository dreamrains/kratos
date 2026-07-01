# Stage 3C0B Central Data Scope Boundary Design

## Context

Task 6 originally enforced the current task's dataset bindings at individual tool entry points. Review found that this cannot be the authoritative boundary: tools may read datasets implicitly, Python code can call `get_dataset()` internally, prompt construction reads workspace state before tools run, and new tools can omit classification. Continuing to extend a per-tool allowlist would leave recurring bypasses and create technical debt.

Stage 3C0B therefore adopts a clean cutover: task scope is enforced at the shared workspace/data-access boundary. Tool guards remain only as an early, user-readable preflight check.

## Goals

- A Stage 3C0B task can observe and read only datasets bound to its unique in-progress task.
- A synthesis task cannot observe or read raw datasets or raw dataset metadata.
- Session and project identity are exact; an empty project name never acts as a wildcard for Stage 3C0B execution.
- Python, prompt construction, implicit relationship discovery, charts, exports, and future tools inherit the same policy automatically.
- Allowed analytical work remains fully available within the task's bound datasets.

## Architecture

### 1. Exact execution-scope resolution

`execution_scope` resolves the unique in-progress task using exact `session_id` and `project_name` matching. It must not reuse a TaskManager query whose blank project value means “all projects.” Multiple matching in-progress tasks fail closed.

The resolved scope contains:

- task and step identity;
- combination mode;
- allowed dataset names;
- dataset contract IDs;
- an explicit error when scope cannot be determined safely.

### 2. Central scoped workspace view

The context-aware workspace is the authoritative data boundary. For an active Stage 3C0B task:

- `get`, `exists`, `list`, schema/metadata access, and helpers exposing DataFrames return only allowed datasets;
- attempts to access an unbound dataset raise a stable scope error;
- synthesis mode exposes no raw datasets and rejects all raw-data access;
- inactive non-Stage-3C0B flows retain their existing workspace behavior.

Scope is carried by the existing agent context/context-variable mechanism and propagated into worker threads. No process-global mutable “current scope” is introduced.

### 3. Prompt and implicit-read consumers

Prompt construction, analysis-state summaries, relationship discovery, `list_data`, Python sandbox helpers, charts, and exports consume the scoped workspace view. They must not reach behind it to global workspace storage.

`load_data` is additionally checked before mutation:

- analysis tasks may load only an alias bound to the current task;
- synthesis tasks cannot load raw data;
- inactive legacy flows keep existing loading behavior.

### 4. Tool preflight guard

The existing tool guard remains for fast, clear errors and deterministic argument completion such as a chart task with exactly one allowed dataset. It is defense in depth, not the source of truth. A missing tool classification must no longer create a data leak because the central workspace boundary still applies.

## Error behavior

Blocked access returns or raises stable errors that the loop serializes without invoking the underlying operation:

- `dataset_outside_current_task_scope` for unbound datasets;
- `synthesis_cannot_read_raw_dataset` for synthesis access;
- `multiple_in_progress_tasks` or an exact-scope error when task identity is ambiguous.

Errors must name the attempted operation or dataset without revealing hidden dataset contents or schemas.

## Testing

TDD coverage must prove:

- exact project isolation, including blank-project contexts;
- central `get/list/exists/schema` filtering;
- synthesis sees no raw dataset names or metadata;
- prompt construction excludes unbound datasets;
- `list_data` cannot enumerate unbound datasets and is blocked for synthesis;
- `load_data` rejects unbound aliases and synthesis loads;
- Python worker threads inherit scope;
- implicit relationship scans use only allowed datasets;
- allowed single- and multi-dataset analysis remains functional;
- inactive non-Stage-3C0B behavior remains unchanged;
- single, parallel, and streaming loop paths serialize stable scope errors.

## Non-goals

- No compatibility bridge for partially scoped Stage 3C0B tasks.
- No redesign of planning-time dataset assignment.
- No Task 7 sufficiency or synthesis-policy work.
- No restriction on computation depth within allowed datasets.

