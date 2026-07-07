# Data Agent Trustworthy Analysis Continuation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue the Data Agent project as a reusable, high-quality professional analysis agent by improving data understanding, evidence-centered analysis, trustworthy synthesis, user-facing Workbench value, real-data regression, and future data-operation readiness without accumulating compatibility debt or degrading analysis quality.

**Architecture:** Treat the existing project as a trustworthy-analysis runtime, not as a generic BI pipeline. Reuse the current safety substrate (`DataUnderstandingBundle`, relationship validation, route capabilities, multi-file scope, execution scope, EvidenceRecords, verification, synthesis policy, workflow projection, Trust/Workbench UI), remove or merge duplicate paths when they create debt, and add only the smallest abstractions that improve user value or quality gates. Multifile analysis starts with data scope and relationship understanding; executable joins and derived data operations remain future opt-in operation capabilities, not the default multifile workflow.

**Tech Stack:** Python, pytest, pandas, existing `data_agent.agent` contracts, `AnalysisSessionState`, `TaskManager`, Flask/Alpine Workbench UI, PowerShell commands with `D:\Project\Daily\data-agent\.venv\Scripts\python.exe`.

---

## 0. Why This Replaces The Earlier Plan

The previous `2026-07-06-stage3c0b-realigned-continuation-plan.md` was a Stage 3C0B continuation plan. That was too narrow for the current requirement.

This rewritten plan is the **complete continuation roadmap**. It keeps the slim Stage 3C0B user-value loop as the first execution slice, but also defines how later iterations should handle cleanup, quality regression, Workbench evolution, evidence/synthesis hardening, and future data operations.

The plan intentionally does not preserve unreasonable compatibility. The project has no formal production compatibility obligation in the current branch. If a legacy behavior conflicts with analysis quality, correctness, or a cleaner reusable design, implementation should update, merge, or remove it after tests and validation.

## 1. Non-Negotiable Principles

### 1.1 No Analysis Quality Regression

Every iteration must preserve or improve:

- professional usefulness;
- analytical rigor;
- depth of insight;
- breadth of reasonable exploration;
- metric-definition clarity;
- evidence citation;
- limitation visibility;
- valid confidence calibration;
- user-facing actionability.

Any feature that makes the agent more rigid, shallow, narrow, verbose without value, or less able to discover useful analysis must be rejected, redesigned, or guarded behind a later opt-in phase.

### 1.2 Reuse Before Rebuilding

Before creating a new module, contract, or state field, inspect and prefer existing implementations:

- `src/data_agent/agent/data_understanding.py`
- `src/data_agent/agent/relationship_validation.py`
- `src/data_agent/agent/analysis_plan_contracts.py`
- `src/data_agent/agent/evidence_contracts.py`
- `src/data_agent/agent/evidence_compatibility.py`
- `src/data_agent/agent/verification.py`
- `src/data_agent/agent/execution_scope.py`
- `src/data_agent/agent/workflow_projection.py`
- `src/data_agent/agent/route_capabilities.py`
- `src/data_agent/agent/multi_file_scope.py`
- `src/data_agent/agent/synthesis_policy.py`
- `src/data_agent/agent/trust_view.py`
- `src/data_agent/tools/data_io.py`
- `src/data_agent/tools/analysis_flow.py`

Do not add `AnalysisOpportunity`, `StrategyRecord`, a second route engine, a second synthesis store, a second Workbench model with overlapping responsibilities, or a new DAG executor unless a later phase proves the existing path cannot meet the requirement.

### 1.3 Clean Breaks Are Allowed

When existing behavior is wrong or unnecessarily duplicated:

- prefer one clean execution path over compatibility branches;
- redesign the current UI or workflow around the desired analysis behavior, not around old screens;
- remove stale tests only after replacing them with stricter tests for the new desired behavior;
- keep migration small and explicit;
- document any intentionally broken legacy behavior in the validation report.

### 1.4 Data Scope First, Join Later If Needed

Multifile or data-warehouse analysis starts by deciding:

- which data sources are relevant;
- which are usable;
- what their grain, time scope, entities, metrics, and quality are;
- what questions are answerable without new operations;
- what relationships are plausible and risky.

Executable joins, aggregate-then-join operations, derived datasets, rollback, approval, and operation resume are future data-operation capabilities. They are not the default architecture for multifile understanding.

### 1.5 LLM-Led Analysis With Deterministic Guardrails

The LLM remains responsible for professional analysis judgment, exploration, strategy, and synthesis. Deterministic code should:

- constrain unsafe operations;
- validate relationships and measurement compatibility;
- record evidence and verification status;
- prevent unsupported claims from being delivered as strong conclusions;
- provide compact context and user-facing summaries.

Deterministic code should not replace professional judgment with magic weights, hard `question_id` coverage scores, or a rigid role pipeline.

## 2. Current Baseline To Preserve And Reuse

The current branch already provides the core safety substrate:

- `SUPPORTED_STAGE3C0B_MODES = {"independent", "synthesis"}` in `analysis_plan_contracts.py`.
- `AnalysisSessionState.add_data_understanding_bundle_ref()` and `state.data_understanding_bundles` for canonical data-understanding refs.
- Legacy `state.dataset_bundles` for active file-bundle diagnostics and `data_pool` grouping.
- `load_data` trust workflow records for dataset contracts, previews, cleaning logs, route proposals, legacy file bundles, and diagnostic file relationships.
- `route_capabilities.build_route_capabilities()` for executable/exploratory route recommendations and confirmation gates.
- `multi_file_scope.build_analysis_scope_plan()` for file eligibility, active scope, ambiguity, and assignment planning.
- `execution_scope` guards that block synthesis from raw dataset reads and enforce current task bindings.
- `record_analysis_plan` and `workflow_projection.project_plan_to_workflow_tasks()` for executable Stage 3C0B independent/synthesis tasks.
- `record_evidence_record` and canonical evidence validation for Stage 3C0B measurements.
- `verify_analysis_claims` and measurement compatibility checks.
- `derive_synthesis_policy` and runtime verification injection before final answers.
- Existing Trust Inspector / Workbench API and UI backed by `build_trust_view()`.

## 3. Phase Roadmap

### Phase 0: Baseline And Architecture Debt Audit

Purpose: verify the actual code state, identify duplicate concepts, and prevent further work from building on the wrong abstraction.

Exit criteria:

- current Stage 3C0B safety tests pass or failures are understood;
- duplicate concepts are documented;
- old/new bundle responsibilities are explicit;
- future implementation starts from a known quality baseline.

### Phase 1: Stage 3C0B Slim User-Value Loop

Purpose: deliver the immediate user-value loop without new heavy contracts.

Scope:

- load-time `DataUnderstandingBundle` refs and User Data Brief;
- Workbench four sections: data understanding, relationships, analysis directions, answer coverage;
- bounded evidence replenishment before synthesis;
- real-data scenarios and soft quality rubric;
- no `joint`, no `aggregate_then_join`, no DerivedDataset, no `AnalysisOpportunity`, no `StrategyRecord`.

Exit criteria:

- single-file quality does not regress;
- multifile scope and relationship value are visible;
- synthesis remains evidence-centered;
- Workbench is useful without exposing technical state first;
- real-data tests cover the reference files.

### Phase 2: Quality Regression System And Golden Questions

Purpose: make quality measurable enough to protect future changes.

Scope:

- real-data golden scenarios for gaming, saving-card, unrelated files, quality faults;
- regression comparisons for professional usefulness, rigor, depth, breadth, actionability;
- claim-level readiness checks for unsupported conclusions and invalid relationship use;
- validation reports that separate implemented behavior from design intent.

Exit criteria:

- quality regression suite is runnable locally;
- failures identify whether the problem is evidence, metric definition, relationship validation, synthesis, or UI presentation;
- new features cannot be called complete without quality evidence.

### Phase 3: Workbench And Trust UX Simplification

Purpose: simplify the user-facing Workbench after the clean Phase 1 replacement, keeping only technical drill-down that still improves analysis trust, debugging, or validation.

Scope:

- primary view answers user questions, not scheduler questions;
- technical state becomes secondary drill-down;
- evidence, verification, limitations, and next actions are visible;
- no second route-selection surface that conflicts with chat.

Exit criteria:

- users can understand what data exists, what relationships mean, what analysis is recommended, and what conclusions are covered;
- replacement tests pass for the new desired behavior;
- no duplicate Workbench/trust surfaces remain.

### Phase 4: Evidence-Centered Analysis Hardening

Purpose: improve conclusion reliability without making analysis rigid.

Scope:

- better prompt instructions for evidence recording;
- claim extraction or claim review only if current verification misses material unsupported claims;
- bounded evidence replenishment refined from Phase 1 evidence;
- synthesis policy tuned against golden scenarios.

Exit criteria:

- unsupported claims are downgraded or blocked;
- useful exploratory insights are not suppressed merely because they were not pre-registered;
- final answers remain deep and professional.

### Phase 5: Data Operation Readiness Decision

Purpose: decide whether executable join/aggregate/derived dataset operations are actually needed, and if so, design them as operation capabilities rather than the default multifile architecture.

Entry criteria:

- Phase 1-4 are stable;
- real scenarios show repeated user value that cannot be met with independent evidence plus synthesis;
- the operation can be made safe with deterministic preflight and user confirmation.

Possible scope:

- `DataOperationRecord`;
- exact two-dataset join preflight;
- source fingerprints;
- operation approval;
- deterministic resume;
- idempotency;
- rollback or immutable derived outputs;
- derived trust artifact registration.

Exit criteria:

- no hidden join path;
- operations are opt-in and auditable;
- analysis quality improves on real scenarios enough to justify complexity.

### Phase 6: Reusable Domain And Connector Expansion

Purpose: broaden the agent's usefulness after the core trustworthy workflow is stable.

Scope:

- richer domain playbooks;
- reusable data-source descriptors for warehouses/lakes;
- metadata/catalog ingestion;
- project-specific metric dictionaries;
- data-quality playbooks.

Exit criteria:

- extensions improve analysis quality without coupling to one dataset;
- new domain logic has regression coverage;
- connector metadata feeds the same data-scope and evidence pipeline.

---

## Task 0: Baseline Audit And Plan Alignment

**Files:**
- Read: `docs/superpowers/specs/2026-07-06-stage3c0b-slim-continuation-design.md`
- Read: `docs/superpowers/specs/2026-06-29-multifile-analysis-stage-3c0b-design-delta.md`
- Read: `CLAUDE.md`
- Read: source anchors listed in Section 2
- Modify: `docs/superpowers/validation/2026-07-06-continuation-architecture-audit.md`

- [x] **Step 1: Confirm worktree and branch**

Run:

```powershell
git status --short
git branch --show-current
git rev-parse --short HEAD
```

Expected:

```text
codex/stage3c0b-implementation
```

`git status --short` may show this plan file as modified or untracked. Do not revert unrelated changes.

- [x] **Step 2: Run the Stage 3C0B safety baseline**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_data_understanding_bundle.py `
  tests/test_relationship_validation.py `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_scoped_workspace.py
```

Expected: all tests pass. If not, stop implementation work and diagnose the failing safety layer first.

- [x] **Step 3: Audit duplicate concepts**

Run:

```powershell
rg -n "dataset_bundles|data_understanding_bundles|file_relationships|route_proposals|AnalysisOpportunity|StrategyRecord|DataOperationRecord|DerivedDataset|aggregate_then_join|SUPPORTED_STAGE3C0B_MODES" src tests docs/superpowers/specs docs/superpowers/plans
```

Expected: findings are reviewed and categorized as:

- current execution path;
- legacy display/state path;
- future operation concept;
- superseded design concept.

- [x] **Step 4: Write architecture audit**

Create `docs/superpowers/validation/2026-07-06-continuation-architecture-audit.md` with:

```markdown
# Continuation Architecture Audit

## Baseline Commands

- branch command output:
- safety baseline command output:

## Reuse Anchors

- DataUnderstandingBundle:
- relationship validation:
- route capabilities:
- multi-file scope:
- evidence and verification:
- synthesis policy:
- Workbench/trust view:

## Duplicate Concepts

| Concept | Current Status | Decision |
|---|---|---|
| dataset_bundles | Legacy active file-bundle diagnostics | Keep only for file grouping/display |
| data_understanding_bundles | Canonical DataUnderstandingBundle refs | Use for user data brief |
| AnalysisOpportunity | Superseded expansion concept | Do not implement |
| StrategyRecord | Superseded expansion concept | Do not implement |
| DataOperationRecord | Future data-operation concept | Phase 5 only if justified |

## Quality Risks

- risk:
- mitigation:

## Compatibility Decisions

- old execution compatibility:
- old display-only behavior:
```

Replace each bullet with concrete findings before committing.

- [x] **Step 5: Commit audit and plan alignment**

```powershell
git add docs/superpowers/plans/2026-07-06-stage3c0b-realigned-continuation-plan.md docs/superpowers/validation/2026-07-06-continuation-architecture-audit.md
git commit -m "docs: define data agent continuation roadmap"
```

---

## Task 1: Phase 1 Load-Time Data Understanding And User Data Brief

**Files:**
- Modify: `src/data_agent/tools/data_io.py`
- Modify: `src/data_agent/agent/data_understanding.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Create: `tests/test_stage3c0b_load_data_brief.py`

Purpose: wire the canonical `DataUnderstandingBundle` into load-time state and expose a compact user-facing brief.

Required behavior:

- successful `load_data` records a valid `data_understanding.v1` bundle through `AnalysisSessionState.add_data_understanding_bundle_ref()`;
- refs are stored in `state.data_understanding_bundles`, not legacy `state.dataset_bundles`;
- legacy `dataset_bundles` remains only for active file-bundle diagnostics;
- User Data Brief hides raw rows, artifact paths, internal IDs as primary content, tool logs, and large schemas.

- [x] **Step 1: Add failing tests for bundle ref storage and brief compactness**

Create `tests/test_stage3c0b_load_data_brief.py` with tests that assert:

```python
assert state.data_understanding_bundles[-1]["contract_version"] == "data_understanding.v1"
assert state.active_scope["related_ref_ids"]["data_understanding_bundles"]
assert "artifact_path" not in json.dumps(brief, ensure_ascii=False)
assert "sample_rows" not in json.dumps(brief, ensure_ascii=False)
```

- [x] **Step 2: Run focused tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q tests/test_stage3c0b_load_data_brief.py
```

Expected: fails because the brief helper and load-time ref wiring are absent.

- [x] **Step 3: Implement `build_user_data_brief()` as a projection helper**

Add to `src/data_agent/agent/data_understanding.py`:

```python
def build_user_data_brief(bundle: dict[str, Any]) -> dict[str, Any]:
    """Project DataUnderstandingBundle into compact user-facing content."""
```

The helper must return:

- `bundle_id`;
- `fingerprint`;
- compact dataset summaries;
- relationship summaries;
- quality findings;
- answerable questions;
- unanswerable questions;
- recommended paths;
- needed confirmations;
- analysis constraints.

It must not return raw rows, artifact paths, or unbounded schema dumps.

- [x] **Step 4: Wire `load_data` to call `add_data_understanding_bundle_ref()`**

Add a helper in `src/data_agent/tools/data_io.py` that builds a bundle with `build_data_understanding_bundle()` and calls:

```python
state.add_data_understanding_bundle_ref(bundle)
```

Call it after trust workflow records are available. If trust workflow fails, still produce a minimal bundle from dataframe shape and columns.

- [x] **Step 5: Expose the latest brief through Trust view**

In `src/data_agent/agent/trust_view.py`, add the latest valid User Data Brief to `workbench` under:

```python
workbench["user_data_brief"]
```

- [x] **Step 6: Run regression tests**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_stage3c0b_load_data_brief.py `
  tests/test_data_understanding_bundle.py `
  tests/test_trustworthy_load_data_integration.py `
  tests/test_analysis_state_v2.py
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```powershell
git add src/data_agent/tools/data_io.py src/data_agent/agent/data_understanding.py src/data_agent/agent/trust_view.py tests/test_stage3c0b_load_data_brief.py
git commit -m "feat: publish user data brief on load"
```

---

## Task 2: Phase 1 Four-Section Workbench Read Model

**Files:**
- Create: `src/data_agent/agent/workbench_view.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Create: `tests/test_multifile_workbench_view.py`
- Modify: `tests/test_trust_view.py`

Purpose: create a user-value Workbench read model that answers four user questions without creating a second route engine.

Required sections:

- `data_understanding`;
- `relationships`;
- `analysis_directions`;
- `answer_coverage`.

- [x] **Step 1: Write failing read-model tests**

Create tests that assert:

```python
assert set(view) == {"data_understanding", "relationships", "analysis_directions", "answer_coverage"}
assert view["analysis_directions"][0]["source"] == "route_capabilities"
assert "artifact_path" not in json.dumps(view, ensure_ascii=False)
assert "scheduler" not in json.dumps(view, ensure_ascii=False).lower()
```

- [x] **Step 2: Run tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q tests/test_multifile_workbench_view.py
```

Expected: fails because `workbench_view.py` is absent.

- [x] **Step 3: Implement `build_multifile_workbench_view(state)`**

Create `src/data_agent/agent/workbench_view.py`.

Implementation must reuse:

- `build_user_data_brief()`;
- `build_route_capabilities()`;
- `state.file_relationships`;
- `state.evidence_records`;
- `state.verification_reports`.

It must not create `AnalysisOpportunity`, `StrategyRecord`, or new execution state.

- [x] **Step 4: Embed read model in Trust view**

Add to `build_trust_view()`:

```python
workbench["multifile_analysis"] = build_multifile_workbench_view(state)
```

The builder must be read-only and must not mutate state.

- [x] **Step 5: Run tests**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_multifile_workbench_view.py `
  tests/test_trust_view.py `
  tests/test_trust_inspector_api.py
```

Expected: all tests pass.

- [x] **Step 6: Commit**

```powershell
git add src/data_agent/agent/workbench_view.py src/data_agent/agent/trust_view.py tests/test_multifile_workbench_view.py tests/test_trust_view.py
git commit -m "feat: build multifile workbench read model"
```

---

## Task 3: Phase 1 Workbench UI Replacement

**Files:**
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/static/css/app.css`
- Modify: `tests/test_trust_inspector_ui.py`
- Create: `tests/test_web_workbench_replacement.py`
- Delete: `tests/test_web_workbench_parity.py` after moving any still-current replacement assertions into `tests/test_web_workbench_replacement.py`

Purpose: replace the old Trust Inspector front panel with the new Workbench as the primary user-facing analysis surface. This project has no production compatibility burden; do not keep old panels, helpers, or tests unless they still serve current evidence quality, analysis trust, or debugging needs.

- [x] **Step 1: Add failing UI contract tests**

Tests must assert the template includes:

```text
multifile-data-understanding
multifile-relationships
multifile-analysis-directions
multifile-answer-coverage
trustView.workbench.multifile_analysis
```

Tests must assert the old Trust Inspector front-panel sections are absent from the primary panel. Technical details may remain only under an explicit secondary debug/details region when they support verification or troubleshooting.

Tests must assert `app.js` includes helpers:

```text
multifileWorkbench()
multifileDataUnderstanding()
multifileRelationships()
multifileAnalysisDirections()
multifileAnswerCoverage()
```

- [x] **Step 2: Run focused UI tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q tests/test_trust_inspector_ui.py
```

Expected: new UI contract tests fail.

- [x] **Step 3: Replace Alpine helpers**

Add helper methods to `src/data_agent/web/static/js/app.js` that read from:

```javascript
this.trustView?.workbench?.multifile_analysis
```

Remove old primary-panel helpers when their only purpose is to render the previous Trust Inspector surface. Keep a helper only if the new Workbench or a clearly labeled debug/details region still uses it.

- [x] **Step 4: Replace the primary panel with four sections**

Replace the previous Trust Inspector primary content in `src/data_agent/web/templates/index.html` with four compact Workbench sections:

- data understanding;
- relationships;
- analysis directions;
- answer coverage.

Do not add route auto-submit controls. Direction cards are explanatory unless existing route-prefill behavior already handles them.

- [x] **Step 5: Run UI checks**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py
node -c src\data_agent\web\static\js\app.js
```

Expected: pytest passes and JavaScript syntax check exits 0.

- [x] **Step 6: Commit**

```powershell
git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py
git commit -m "feat: replace trust inspector with workbench"
```

---

## Task 4: Phase 1 Bounded Evidence Replenishment Before Synthesis

**Files:**
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Modify: `src/data_agent/agent/loop.py` only if current prompt injection drops the instruction
- Modify: `tests/test_synthesis_policy.py`
- Modify: `tests/test_execution_control.py`
- Create: `tests/test_stage3c0b_evidence_replenishment.py`
- Create: `tests/test_stage3c0b_evidence_replenishment_flow.py`

Purpose: preserve evidence-only synthesis while letting the LLM request bounded independent evidence tasks when the evidence is insufficient.

Required behavior:

- synthesis does not directly read raw datasets;
- instruction tells the LLM to check intended material claims against EvidenceRecords;
- if evidence is missing, the LLM may call `record_analysis_plan` with a bounded Stage 3C0B `independent` step;
- no hard `question_id` coverage gate;
- no magic score or threshold;
- if evidence remains insufficient, answer partially with limitations.
- deterministic integration coverage proves the substrate loop works without relying on live LLM behavior.

- [x] **Step 1: Add failing instruction tests**

Create tests asserting `build_synthesis_instruction()` contains:

```text
bounded_evidence_replenishment
record_analysis_plan
independent
do not read raw datasets during synthesis
```

and does not contain:

```text
question_id
magic threshold
score =
```

- [x] **Step 2: Run tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q tests/test_stage3c0b_evidence_replenishment.py
```

Expected: fails because the replenishment instruction is absent.

- [x] **Step 3: Add replenishment instruction block**

In `src/data_agent/agent/synthesis_policy.py`, append a compact XML-like block to `build_synthesis_instruction()`:

```xml
<bounded_evidence_replenishment>
Before final synthesis, check whether each material claim is supported by an EvidenceRecord.
Do not read raw datasets during synthesis.
If a material claim lacks evidence and a relevant dataset is available, call record_analysis_plan with contract_version stage3c0b.v1 and one bounded independent step for that dataset.
After the step runs, record the result with record_evidence_record and synthesize from EvidenceRecords.
If evidence cannot be produced within the bounded plan, return a partial answer with missing-evidence limitations.
</bounded_evidence_replenishment>
```

- [x] **Step 4: Add deterministic replenishment flow integration tests**

Create `tests/test_stage3c0b_evidence_replenishment_flow.py`.

The tests must simulate the LLM decision by directly calling current substrate functions and classes. Do not call a live model.

Cover the happy path:

```text
synthesis task has a material claim without EvidenceRecord
synthesis scope cannot read raw datasets
record_analysis_plan creates one bounded independent step
workflow projection creates the independent task
independent scope can execute the bounded data check
record_evidence_record stores the EvidenceRecord
TaskManager.complete_matching_tasks_from_evidence completes the matching task
synthesis can proceed from EvidenceRecords
```

Cover failure isolation:

```text
two material claims need different evidence
one bounded independent task produces evidence
one bounded independent task fails or produces no matching evidence
only the unsupported claim is blocked or caveated
completed evidence remains usable for the supported claim
no global replan or blanket synthesis failure is triggered
```

Use existing components only:

```text
data_agent.tools.analysis_flow.record_analysis_plan
data_agent.tools.analysis_flow.record_evidence_record
data_agent.session.task_manager.TaskManager
data_agent.agent.workflow_projection
data_agent.agent.execution_scope
```

- [x] **Step 5: Run synthesis, scope, and replenishment flow regressions**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_stage3c0b_evidence_replenishment.py `
  tests/test_stage3c0b_evidence_replenishment_flow.py `
  tests/test_synthesis_policy.py `
  tests/test_execution_control.py `
  tests/test_stage3c0b_execution_scope.py
```

Expected: all tests pass and synthesis raw dataset blocking remains intact.

- [x] **Step 6: Commit**

```powershell
git add src/data_agent/agent/synthesis_policy.py src/data_agent/agent/loop.py tests/test_synthesis_policy.py tests/test_execution_control.py tests/test_stage3c0b_evidence_replenishment.py tests/test_stage3c0b_evidence_replenishment_flow.py
git commit -m "feat: guide bounded evidence replenishment before synthesis"
```

---

## Task 5: Phase 2 Real-Data Regression And Soft Quality Rubric

**Files:**
- Create: `src/data_agent/agent/analysis_quality_rubric.py`
- Create: `tests/real_data/scenario_manifest.json`
- Create: `tests/real_data/test_multifile_real_data_scenarios.py`
- Create: `tests/real_data/test_multifile_analysis_quality.py`
- Create: `scripts/run_multifile_quality_scenarios.py`
- Create: `docs/superpowers/validation/2026-07-06-analysis-quality-rubric.md`
- Modify: `tests/test_analysis_quality.py`

Purpose: prevent quality regressions and protect professional usefulness with real data and scenario-level checks.

Scenarios:

- Game A banner / IAP / rewarded video: independent analysis and synthesis.
- Saving-card user flow + orders: relationship value/risk, candidate key, cardinality, coverage, time/grain checks, no executed join.
- Unrelated files: false join prevention.
- Fault injection: duplicate keys, missing keys, time mismatch, many-to-many risk.

- [x] **Step 1: Add scenario manifest**

Create `tests/real_data/scenario_manifest.json` with the scenarios above and explicit `forbidden_modes`:

```json
["joint", "aggregate_then_join"]
```

- [x] **Step 2: Add tests that all manifest files exist**

Tests must check `reference/test_doc` contains:

```text
游戏Abanner汇总数据.xlsx
游戏A内购数据.xlsx
游戏A激励视频汇总数据报表.xlsx
游戏B留存.xlsx
省钱卡用户最近流水_20260511.xlsx
省钱卡订单_20260507.xlsx
```

- [x] **Step 3: Add soft rubric tests**

Tests must assert:

- unsupported material claims mark `claim_delivery_ready=False`;
- invalid relationship use marks `claim_delivery_ready=False`;
- rubric returns `global_publish_gate=False`;
- no single `total` magic score controls readiness.

- [x] **Step 4: Implement `score_analysis_quality()`**

Create `src/data_agent/agent/analysis_quality_rubric.py`.

The function must return:

- `claim_delivery_ready`;
- `global_publish_gate`;
- `blockers`;
- `dimensions`;
- `notes`.

Do not make this helper part of runtime synthesis yet. It is for scenario validation and regression reporting.

- [x] **Step 5: Add scenario runner**

Create `scripts/run_multifile_quality_scenarios.py`.

The script must:

- read the manifest;
- verify files exist;
- write `artifacts/multifile-quality/<timestamp>/results.json`;
- never modify source spreadsheets;
- exit nonzero only for missing required files or malformed manifest.

- [x] **Step 6: Run regression tests and scenario script**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/real_data/test_multifile_real_data_scenarios.py `
  tests/real_data/test_multifile_analysis_quality.py `
  tests/test_analysis_quality.py `
  tests/test_system_data_analysis_quality_audit.py
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/run_multifile_quality_scenarios.py --data-dir 'D:\Project\Daily\data-agent\reference\test_doc'
```

Expected: all tests pass and script prints the results path.

- [x] **Step 7: Commit**

```powershell
git add src/data_agent/agent/analysis_quality_rubric.py tests/real_data/test_multifile_real_data_scenarios.py tests/real_data/test_multifile_analysis_quality.py tests/real_data/scenario_manifest.json scripts/run_multifile_quality_scenarios.py docs/superpowers/validation/2026-07-06-analysis-quality-rubric.md
git commit -m "test: add analysis quality regression scenarios"
```

---

## Task 6: Phase 3 Workbench And Trust UX Simplification Review

**Files:**
- Create: `src/data_agent/agent/artifact_refs.py`
- Modify: `src/data_agent/agent/analysis_entry.py`
- Modify: `src/data_agent/agent/hypotheses.py`
- Modify: `src/data_agent/agent/route_capabilities.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `src/data_agent/agent/workbench_view.py`
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/css/app.css`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/blueprints/sessions.py`
- Modify: `tests/test_trust_view.py`
- Modify: `tests/test_trust_inspector_api.py`
- Modify: `tests/test_trust_inspector_ui.py`
- Modify: `tests/test_web_workbench_replacement.py`
- Modify: `tests/test_web_overhaul.py`
- Modify: `tests/test_multifile_regressions.py`
- Modify: `tests/test_multifile_workbench_view.py`
- Modify: `tests/test_stage3c0b_load_data_brief.py`
- Create: `docs/superpowers/validation/2026-07-06-workbench-ux-review.md`

Purpose: after Phase 1 and Phase 2 pass, simplify the clean Workbench replacement and remove any old Trust Inspector residue that does not improve analysis trust, verification, or debugging.

- [x] **Step 1: Audit Workbench fields**

Run:

```powershell
rg -n "workbench|trustView|active_bundle|history|routes|risks|hypotheses|multifile_analysis" src/data_agent/agent src/data_agent/web tests/test_trust*
```

Categorize each field as:

- primary user-value section;
- technical drill-down;
- current debugging or verification support;
- removable duplicate.

- [x] **Step 2: Add tests for primary sections and drill-down**

Tests must assert:

- four primary sections are present;
- technical history is reachable only if it supports debugging or validation;
- route suggestions do not auto-submit;
- Workbench does not expose raw artifact paths as primary text.

- [x] **Step 3: Simplify UI and view model**

Remove duplicate front-panel sections and stale helper fields. Do not keep old UI just to preserve history; keep only current-value technical detail under an explicit secondary debug/details region.

- [x] **Step 4: Write UX review**

Create `docs/superpowers/validation/2026-07-06-workbench-ux-review.md` recording:

- primary sections;
- drill-down sections;
- removed duplicates;
- user tasks supported;
- remaining caveats.

- [x] **Step 5: Run UI and API tests**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q tests/test_trust_view.py tests/test_trust_inspector_api.py tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py
node -c src\data_agent\web\static\js\app.js
```

Expected: all tests pass.

- [x] **Step 6: Commit**

```powershell
git add src/data_agent/agent/trust_view.py src/data_agent/agent/workbench_view.py src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js tests/test_trust_view.py tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py docs/superpowers/validation/2026-07-06-workbench-ux-review.md
git commit -m "refactor: simplify workbench trust surface"
```

---

## Task 7: Phase 4 Evidence And Synthesis Hardening Decision

**Files:**
- Read: `src/data_agent/agent/verification.py`
- Read: `src/data_agent/agent/trust_workflow_runtime.py`
- Read: `src/data_agent/agent/synthesis_policy.py`
- Read: `src/data_agent/tools/analysis_flow.py`
- Create: `docs/superpowers/specs/2026-07-06-evidence-synthesis-hardening-decision.md`

Purpose: decide whether more claim extraction, independent audit, or synthesis verification is needed after Phase 1-3 evidence.

- [x] **Step 1: Review quality failures**

Read outputs from:

- `docs/superpowers/validation/2026-07-06-analysis-quality-rubric.md`;
- latest `artifacts/multifile-quality/*/results.json`;
- failed or downgraded verification reports in real-data scenarios.

- [x] **Step 2: Classify failure type**

Write a decision table:

| Failure | Existing layer catches it? | Needed change |
|---|---|---|
| unsupported claim | yes/no | prompt, verification, claim extraction, or no change |
| weak evidence | yes/no | evidence schema, prompt, or no change |
| shallow synthesis | yes/no | synthesis policy, golden question, or no change |
| over-rigid synthesis | yes/no | loosen prompt, remove hard gate, or no change |

- [x] **Step 3: Write hardening decision spec**

Create `docs/superpowers/specs/2026-07-06-evidence-synthesis-hardening-decision.md`.

The decision must choose one of:

- no new hardening needed;
- prompt-only improvement;
- verification improvement;
- claim extraction/readiness helper;
- independent audit phase.

If the decision is anything other than prompt-only or no-op, write a separate implementation plan before touching code.

- [x] **Step 4: Commit decision**

```powershell
git add docs/superpowers/specs/2026-07-06-evidence-synthesis-hardening-decision.md
git commit -m "docs: decide evidence synthesis hardening path"
```

---

## Task 8: Phase 5 Data Operation Readiness Decision

**Files:**
- Read: Phase 1-4 validation outputs
- Create: `docs/superpowers/specs/2026-07-06-data-operation-readiness-decision.md`

Purpose: decide whether Stage 3C1A data operations are justified. This task is a decision gate, not an implementation.

- [ ] **Step 1: Gather evidence for operation need**

Review real scenarios and user requests for repeated cases where independent evidence plus synthesis cannot answer the question.

Examples that may justify operations:

- user asks for exact user-level order impact;
- evidence requires row-level combination after validation;
- aggregate relationship value cannot answer the business question.

Examples that do not justify operations:

- files merely share a column name;
- the user wants a broad summary;
- relationship risk is high or scope is unclear;
- independent analyses plus synthesis answer the question well enough.

- [ ] **Step 2: Write the decision spec**

Create `docs/superpowers/specs/2026-07-06-data-operation-readiness-decision.md` with:

```markdown
# Data Operation Readiness Decision

## Decision

Choose one:

- Not ready: keep Stage 3C1A deferred.
- Ready for design: write a Stage 3C1A operation spec.

## Evidence

- scenario:
- user value:
- why independent evidence + synthesis is insufficient:
- operation risk:
- required safety mechanism:

## If Ready

Stage 3C1A must include:

- immutable DataOperationRecord;
- exact two-dataset preflight;
- source fingerprints;
- user approval for risky operations;
- deterministic resume;
- idempotency;
- rollback or immutable derived outputs;
- derived trust artifact registration.
```

- [ ] **Step 3: Commit decision**

```powershell
git add docs/superpowers/specs/2026-07-06-data-operation-readiness-decision.md
git commit -m "docs: decide data operation readiness"
```

---

## Task 9: Final Continuation Validation Report

**Files:**
- Create: `docs/superpowers/validation/2026-07-06-data-agent-continuation-validation-report.md`

Purpose: prove the continuation plan improved the project without quality regression or unnecessary complexity.

- [ ] **Step 1: Run final suite**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_data_understanding_bundle.py `
  tests/test_relationship_validation.py `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_scoped_workspace.py `
  tests/test_stage3c0b_load_data_brief.py `
  tests/test_multifile_workbench_view.py `
  tests/test_stage3c0b_evidence_replenishment.py `
  tests/test_stage3c0b_evidence_replenishment_flow.py `
  tests/real_data/test_multifile_real_data_scenarios.py `
  tests/real_data/test_multifile_analysis_quality.py `
  tests/test_analysis_quality.py `
  tests/test_system_data_analysis_quality_audit.py `
  tests/test_trust_view.py `
  tests/test_trust_inspector_api.py `
  tests/test_trust_inspector_ui.py `
  tests/test_web_workbench_replacement.py `
  tests/test_synthesis_policy.py `
  tests/test_execution_control.py
```

Expected: all tests pass.

- [ ] **Step 2: Run real-data scenario script**

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/run_multifile_quality_scenarios.py --data-dir 'D:\Project\Daily\data-agent\reference\test_doc'
```

Expected: script exits 0 and prints the result JSON path.

- [ ] **Step 3: Run frontend and whitespace checks**

```powershell
node -c src\data_agent\web\static\js\app.js
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 4: Run non-slippage checks**

```powershell
rg -n "AnalysisOpportunity|StrategyRecord|DataOperationRecord|safe_to_execute|join preflight|operation_id|aggregate_then_join|DerivedDataset" src tests
rg -n "SUPPORTED_STAGE3C0B_MODES\s*=\s*\{[^}]*joint|SUPPORTED_STAGE3C0B_MODES\s*=\s*\{[^}]*aggregate_then_join" src tests
```

Expected: no matches in `src tests`. Future decision docs may mention these terms, but current executable code must not.

- [ ] **Step 5: Write final report**

Create `docs/superpowers/validation/2026-07-06-data-agent-continuation-validation-report.md` with:

- exact command outputs;
- real-data files used;
- quality rubric results;
- Workbench UX evidence;
- unsupported claim and invalid relationship handling;
- cleanup and compatibility decisions;
- Stage 3C1A decision status;
- known caveats and next recommended task.

- [ ] **Step 6: Commit report**

```powershell
git add docs/superpowers/validation/2026-07-06-data-agent-continuation-validation-report.md
git commit -m "docs: validate data agent continuation roadmap"
```

---

## Execution Order

1. Task 0: baseline audit and architecture alignment.
2. Task 1-4: Phase 1, Stage 3C0B slim user-value loop.
3. Task 5: Phase 2 quality regression system.
4. Task 6: Phase 3 Workbench/Trust UX consolidation.
5. Task 7: Phase 4 evidence/synthesis hardening decision.
6. Task 8: Phase 5 data operation readiness decision.
7. Task 9: final validation report.

Do not start a later phase until the previous phase has passing tests and a validation artifact. If a later phase reveals a premise problem in an earlier phase, stop and revise the earlier phase rather than adding compatibility branches.

## Completion Criteria

The roadmap is complete when:

- no Stage 3C0B safety test regresses;
- single-file analysis quality is preserved;
- multifile scope and relationship value are user-visible without forced joins;
- synthesis remains evidence-centered and can trigger bounded evidence replenishment;
- Workbench answers user-value questions first;
- real-data scenarios run and record quality evidence;
- future data operations are either explicitly deferred or justified by evidence;
- no duplicate heavy contracts are introduced.

## Self-Review

- Scope coverage: this is a full continuation roadmap, not only a Stage 3C0B task list.
- Technical debt: clean breaks are allowed; compatibility branches are discouraged; reuse anchors are explicit.
- Quality protection: every phase has quality gates, and the final suite includes single-file, multifile, evidence, synthesis, Workbench, and real-data checks.
- Stage boundaries: joins, derived datasets, and operation lifecycles remain future opt-in decisions, not current execution defaults.
