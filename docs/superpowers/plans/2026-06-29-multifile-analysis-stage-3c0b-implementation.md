# Multi-File Analysis Stage 3C0B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Stage 3C0B independent multi-dataset execution with canonical plan validation, task projection, evidence lineage, sufficiency gating, user-value workbench projection, and real-data verification.

**Architecture:** Keep `AnalysisPlan.method_plan` as the source of truth. Add small deterministic services for plan validation, task projection, evidence compatibility, execution scope, sufficiency, and workbench projection; wire existing controller/tools/loop/trust-view paths through those services. New Stage 3C0B contracts are executable; legacy plans and evidence are display-only.

**Tech Stack:** Python 3, pytest, dataclasses/plain dictionaries, existing `AnalysisSessionState`, `TaskManager`, tool registry, Flask web API, Alpine-style frontend state in `src/data_agent/web/static/js/app.js`, Excel test data in `reference/test_doc`.

---

## Scope Boundary

This plan implements Stage 3C0B only:

- executable modes: `independent`, `synthesis`;
- no join, union, fuzzy matching, entity mapping, derived dataset creation, or Stage 3C1 operation records;
- no second planner, task runtime, evidence store, confirmation runtime, or workbench state model;
- no preservation of old executable dual paths for new Stage 3C0B contracts.

Historical records remain readable by existing history/workbench views, but they are not executable 3C0B input.

## File Structure

Create focused deterministic modules:

- Create `src/data_agent/agent/analysis_plan_contracts.py`
  - Owns Stage 3C0B contract constants, budget policy, plan normalization, validation, review status, and compact contract helpers.
- Create `src/data_agent/agent/workflow_projection.py`
  - Owns the single Plan-to-Task projection path.
- Create `src/data_agent/agent/evidence_contracts.py`
  - Owns canonical `measurements`, evidence IDs, evidence validation, and evidence upsert helpers.
- Create `src/data_agent/agent/evidence_compatibility.py`
  - Owns deterministic measurement compatibility checks and user-facing compatibility explanations.
- Create `src/data_agent/agent/execution_scope.py`
  - Owns current active-task selection and dataset read-scope checks.
- Create `src/data_agent/agent/analysis_sufficiency.py`
  - Owns batch sufficiency decisions and synthesis finding validation.
- Create `src/data_agent/agent/workbench_projection.py`
  - Owns user-value workbench sections built from existing state, tasks, evidence, verification, and scope plan.
- Create `tests/test_stage3c0b_plan_contracts.py`
- Create `tests/test_stage3c0b_workflow_projection.py`
- Create `tests/test_stage3c0b_evidence_contracts.py`
- Create `tests/test_stage3c0b_verification_compatibility.py`
- Create `tests/test_stage3c0b_execution_scope.py`
- Create `tests/test_stage3c0b_sufficiency.py`
- Create `tests/test_stage3c0b_workbench_projection.py`
- Create `tests/test_stage3c0b_real_data_replay.py`
- Create `docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md`

Modify existing owners only where they currently own the integration point:

- Modify `src/data_agent/agent/analysis_state.py`
  - Add evidence upsert, compact Stage 3C0B refs, and summary budget enforcement.
- Modify `src/data_agent/session/task_manager.py`
  - Add projected task fields, `failed` status, and evidence-driven completion rules.
- Modify `src/data_agent/agent/analysis_flow_controller.py`
  - Replace local task creation with the shared projector.
- Modify `src/data_agent/tools/task_tools.py`
  - Replace duplicate task projection with the shared projector and carry 3C0B fields through public task APIs.
- Modify `src/data_agent/tools/analysis_flow.py`
  - Validate Stage 3C0B plans and canonical EvidenceRecords at recording time.
- Modify `src/data_agent/agent/verification.py`
  - Filter evidence by current plan and enforce measurement compatibility for numeric comparison claims.
- Modify `src/data_agent/agent/synthesis_policy.py`
  - Read sufficiency and compatibility status so final policy cannot overstate claims.
- Modify `src/data_agent/agent/loop.py`
  - Inject current-task execution scope, stop auto-completing tasks after generic tool success, and call the sufficiency gate before final answer.
- Modify `src/data_agent/agent/multi_file_scope.py`
  - Continue deriving `used` from `dataset_inputs`, and include contract IDs when available.
- Modify `src/data_agent/agent/trust_view.py`
  - Delegate workbench payload construction to `workbench_projection.py`.
- Modify `src/data_agent/web/blueprints/tasks.py`
  - Expose new workflow task fields and `failed` status.
- Modify `src/data_agent/web/static/js/app.js`
  - Render user-value workbench sections before technical task details.

## Required Commands

Use PowerShell from `D:\Project\Daily\data-agent`.

Set test path before pytest:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
```

Focused regression command after every major task:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_stage3c0b_sufficiency.py `
  tests/test_stage3c0b_workbench_projection.py -q
```

Final focused regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_flow_tools.py `
  tests/test_analysis_entry.py `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py `
  tests/test_task_manager_scope.py `
  tests/test_task_plan_versioning.py `
  tests/test_synthesis_policy.py `
  tests/test_verification_layer.py `
  tests/test_web_workbench_parity.py `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_stage3c0b_sufficiency.py `
  tests/test_stage3c0b_workbench_projection.py `
  tests/test_stage3c0b_real_data_replay.py -q
```

Frontend syntax check:

```powershell
node -c src\data_agent\web\static\js\app.js
```

Whitespace check:

```powershell
git diff --check
```

---

### Task 1: Canonical Stage 3C0B Plan Contract

**Files:**
- Create: `src/data_agent/agent/analysis_plan_contracts.py`
- Create: `tests/test_stage3c0b_plan_contracts.py`
- Modify: `src/data_agent/agent/analysis_state.py`

- [ ] **Step 1: Write failing tests for valid plan normalization**

Create `tests/test_stage3c0b_plan_contracts.py` with:

```python
from data_agent.agent.analysis_plan_contracts import (
    STAGE3C0B_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)


def _contract(dataset: str, contract_id: str) -> dict:
    return {"dataset": dataset, "id": contract_id, "quality_status": "ready"}


def test_valid_stage3c0b_plan_is_reviewed_and_executable():
    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Compare the independent performance evidence for uploaded game files.",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner exposure and click performance.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "evidence_requirements": ["impressions", "click_rate"],
            },
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified evidence across game files.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "expected_output": "Cross-file synthesis",
                "evidence_requirements": ["comparative_summary"],
                "required_evidence_step_ids": ["step_banner"],
            },
        ],
    }

    result = validate_analysis_plan_contract(
        plan,
        dataset_contracts=[_contract("banner", "contract_banner")],
    )

    assert result.ok is True
    assert result.plan["review_status"] == "executable"
    assert result.plan["method_plan"][0]["plan_id"] == result.plan["id"]
    assert result.plan["method_plan"][0]["dataset_contract_ids"] == ["contract_banner"]
    assert result.plan["method_plan"][0]["combination_mode"] == "independent"
```

- [ ] **Step 2: Write failing tests for unsupported modes and legacy plans**

Append:

```python
def test_rejects_legacy_or_missing_contract_version_for_execution():
    result = validate_analysis_plan_contract(
        {"goal": "legacy", "method_plan": [{"step_id": "s1"}]},
        dataset_contracts=[],
    )

    assert result.ok is False
    assert result.error_type == "legacy_plan_display_only"
    assert "contract_version" in result.message


def test_rejects_join_hidden_as_executable_stage3c0b_mode():
    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Join orders and users.",
        "method_plan": [
            {
                "step_id": "step_join",
                "goal": "Join the datasets.",
                "dataset_inputs": ["orders", "users"],
                "combination_mode": "join",
                "expected_output": "Joined table",
                "evidence_requirements": ["joined_rows"],
            }
        ],
    }

    result = validate_analysis_plan_contract(plan, dataset_contracts=[
        _contract("orders", "contract_orders"),
        _contract("users", "contract_users"),
    ])

    assert result.ok is False
    assert result.error_type == "unsupported_combination_mode"
    assert "join" in result.message
```

- [ ] **Step 3: Write failing tests for batch budget and synthesis dependency budget**

Append:

```python
def test_rejects_oversize_execution_batch_instead_of_truncating():
    steps = [
        {
            "step_id": f"step_{i}",
            "goal": f"Analyze dataset {i}.",
            "dataset_inputs": [f"ds_{i}"],
            "combination_mode": "independent",
            "expected_output": "Evidence",
            "evidence_requirements": ["metric"],
        }
        for i in range(13)
    ]
    contracts = [_contract(f"ds_{i}", f"contract_{i}") for i in range(13)]

    result = validate_analysis_plan_contract(
        {
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze all datasets.",
            "method_plan": steps,
        },
        dataset_contracts=contracts,
    )

    assert result.ok is False
    assert result.error_type == "execution_batch_too_large"
    assert result.details["max_executable_steps_per_batch"] == 12


def test_rejects_synthesis_with_too_many_hard_dependencies():
    result = validate_analysis_plan_contract(
        {
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Synthesize a large batch.",
            "method_plan": [
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "evidence_requirements": ["summary"],
                    "required_evidence_step_ids": [f"step_{i}" for i in range(9)],
                }
            ],
        },
        dataset_contracts=[],
    )

    assert result.ok is False
    assert result.error_type == "too_many_required_evidence_dependencies"
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_plan_contracts.py -q
```

Expected: FAIL because `data_agent.agent.analysis_plan_contracts` does not exist.

- [ ] **Step 5: Implement plan contract validator**

Create `src/data_agent/agent/analysis_plan_contracts.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


STAGE3C0B_CONTRACT_VERSION = "stage3c0b.v1"
SUPPORTED_STAGE3C0B_MODES = {"independent", "synthesis"}
MAX_EXECUTABLE_STEPS_PER_BATCH = 12
MAX_SYNTHESIS_REQUIRED_EVIDENCE = 8


@dataclass
class ContractValidationResult:
    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _contract_indexes(dataset_contracts: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_dataset: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for contract in dataset_contracts:
        dataset = _text(contract.get("dataset"))
        contract_id = _text(contract.get("id") or contract.get("contract_id"))
        if dataset and contract_id:
            by_dataset[dataset] = contract_id
        if contract_id:
            by_id[contract_id] = contract_id
    return by_dataset, by_id


def _error(error_type: str, message: str, **details: Any) -> ContractValidationResult:
    return ContractValidationResult(False, error_type=error_type, message=message, details=details)


def _resolve_contract_ids(dataset_inputs: list[str], by_dataset: dict[str, str], by_id: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for dataset in dataset_inputs:
        contract_id = by_dataset.get(dataset) or by_id.get(dataset)
        if contract_id:
            resolved.append(contract_id)
    return resolved


def validate_analysis_plan_contract(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
) -> ContractValidationResult:
    if not isinstance(plan, dict):
        return _error("invalid_plan", "AnalysisPlan must be a JSON object.")
    if plan.get("contract_version") != STAGE3C0B_CONTRACT_VERSION:
        return _error(
            "legacy_plan_display_only",
            f"AnalysisPlan missing executable contract_version={STAGE3C0B_CONTRACT_VERSION}; legacy plans are display-only.",
        )
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list) or not method_plan:
        return _error("missing_method_plan", "Stage 3C0B AnalysisPlan requires a non-empty method_plan.")
    if len(method_plan) > MAX_EXECUTABLE_STEPS_PER_BATCH:
        return _error(
            "execution_batch_too_large",
            "Stage 3C0B execution batch exceeds the maximum executable step budget.",
            max_executable_steps_per_batch=MAX_EXECUTABLE_STEPS_PER_BATCH,
            actual=len(method_plan),
        )

    normalized = dict(plan)
    normalized.setdefault("id", f"plan_{uuid.uuid4().hex[:10]}")
    normalized.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    normalized["review_status"] = "reviewed"

    by_dataset, by_id = _contract_indexes(dataset_contracts or [])
    normalized_steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, raw_step in enumerate(method_plan, 1):
        if not isinstance(raw_step, dict):
            return _error("invalid_step", f"method_plan step {index} must be an object.")
        step = dict(raw_step)
        step_id = _text(step.get("step_id")) or f"step_{index}"
        if step_id in seen_step_ids:
            return _error("duplicate_step_id", f"Duplicate step_id: {step_id}", step_id=step_id)
        seen_step_ids.add(step_id)
        mode = _text(step.get("combination_mode")) or "independent"
        if mode not in SUPPORTED_STAGE3C0B_MODES:
            return _error(
                "unsupported_combination_mode",
                f"Stage 3C0B supports only independent and synthesis, not {mode}.",
                step_id=step_id,
                combination_mode=mode,
            )
        dataset_inputs = _text_list(step.get("dataset_inputs"))
        if mode == "independent" and len(dataset_inputs) != 1:
            return _error(
                "invalid_independent_binding",
                "Stage 3C0B independent steps must bind exactly one dataset.",
                step_id=step_id,
                dataset_inputs=dataset_inputs,
            )
        if mode == "synthesis" and dataset_inputs:
            return _error(
                "invalid_synthesis_binding",
                "Stage 3C0B synthesis steps consume evidence, not raw datasets.",
                step_id=step_id,
            )
        required_evidence = _text_list(step.get("required_evidence_step_ids"))
        if len(required_evidence) > MAX_SYNTHESIS_REQUIRED_EVIDENCE:
            return _error(
                "too_many_required_evidence_dependencies",
                "Synthesis declares too many hard required evidence dependencies.",
                step_id=step_id,
                max_required_evidence_step_ids=MAX_SYNTHESIS_REQUIRED_EVIDENCE,
                actual=len(required_evidence),
            )
        if not _text(step.get("goal")):
            return _error("missing_step_goal", "Every Stage 3C0B step needs a goal.", step_id=step_id)
        if not _text(step.get("expected_output")):
            return _error("missing_expected_output", "Every Stage 3C0B step needs expected_output.", step_id=step_id)
        if not _text_list(step.get("evidence_requirements")):
            return _error("missing_evidence_requirements", "Every Stage 3C0B step needs evidence_requirements.", step_id=step_id)

        step["plan_id"] = normalized["id"]
        step["step_id"] = step_id
        step["combination_mode"] = mode
        step["dataset_inputs"] = dataset_inputs
        step["dataset_contract_ids"] = _resolve_contract_ids(dataset_inputs, by_dataset, by_id)
        step["required_evidence_step_ids"] = required_evidence
        normalized_steps.append(step)

    normalized["method_plan"] = normalized_steps
    normalized["review_status"] = "executable"
    return ContractValidationResult(True, plan=normalized)
```

- [ ] **Step 6: Wire `AnalysisSessionState.set_analysis_plan` to keep validated plan fields**

Modify `src/data_agent/agent/analysis_state.py` so `set_analysis_plan` does not strip Stage 3C0B fields:

```python
    def set_analysis_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        item = dict(plan)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.analysis_plan = item
        self.analysis_spec = item
        self.goal = item.get("goal") or self.goal
        self.stage = "plan"
        return item
```

This method already has this shape; keep it and do not add compatibility mapping that rewrites `method_plan`.

- [ ] **Step 7: Run plan contract tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_plan_contracts.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/data_agent/agent/analysis_plan_contracts.py tests/test_stage3c0b_plan_contracts.py src/data_agent/agent/analysis_state.py
git commit -m "feat: validate stage 3c0b analysis plans"
```

---

### Task 2: Shared Plan-to-Task Projection

**Files:**
- Create: `src/data_agent/agent/workflow_projection.py`
- Create: `tests/test_stage3c0b_workflow_projection.py`
- Modify: `src/data_agent/session/task_manager.py`
- Modify: `src/data_agent/agent/analysis_flow_controller.py`
- Modify: `src/data_agent/tools/task_tools.py`
- Modify: `src/data_agent/web/blueprints/tasks.py`

- [ ] **Step 1: Write failing tests for projected task fields**

Create `tests/test_stage3c0b_workflow_projection.py`:

```python
from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION, validate_analysis_plan_contract
from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks
from data_agent.session.task_manager import TaskManager


def _validated_plan():
    result = validate_analysis_plan_contract(
        {
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze independent game files.",
            "method_plan": [
                {
                    "step_id": "step_banner",
                    "goal": "Analyze banner metrics.",
                    "dataset_inputs": ["banner"],
                    "combination_mode": "independent",
                    "expected_output": "Banner evidence",
                    "evidence_requirements": ["click_rate"],
                },
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize verified evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "evidence_requirements": ["summary"],
                    "required_evidence_step_ids": ["step_banner"],
                },
            ],
        },
        dataset_contracts=[{"dataset": "banner", "id": "contract_banner"}],
    )
    assert result.ok
    return result.plan


def test_projector_carries_stage3c0b_bindings(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    result = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
        source="analysis_plan",
    )

    assert result["created"] == 2
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    assert banner["analysis_plan_id"] == plan["id"]
    assert banner["dataset_inputs"] == ["banner"]
    assert banner["dataset_contract_ids"] == ["contract_banner"]
    assert banner["combination_mode"] == "independent"
    assert banner["evidence_requirements"] == ["click_rate"]
```

- [ ] **Step 2: Write failing tests for synthesis dependencies and `failed` status**

Append:

```python
def test_projector_translates_required_evidence_to_task_dependencies(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    project_plan_to_workflow_tasks(manager, plan, session_id="s1", project_name="p1")
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    synthesis = next(task for task in tasks if task["step_id"] == "step_synthesis")

    assert synthesis["blockedBy"] == [banner["id"]]
    assert banner["blocks"] == [synthesis["id"]]


def test_task_manager_accepts_failed_terminal_status(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    task = manager.create("analysis", session_id="s1", step_id="step_a")

    updated = manager.update(task["id"], status="failed", result_summary="Dataset contract is stale")

    assert updated["status"] == "failed"
    assert updated["completed_at"] == ""
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_workflow_projection.py -q
```

Expected: FAIL because `workflow_projection.py` does not exist and `TaskManager` does not accept `failed`.

- [ ] **Step 4: Extend `TaskManager` workflow fields and statuses**

Modify `src/data_agent/session/task_manager.py`:

```python
WORKFLOW_FIELDS = {
    "workflow_id": "",
    "project_name": "",
    "stage": "",
    "node_type": "",
    "analysis_spec_id": "",
    "analysis_plan_id": "",
    "step_id": "",
    "dataset_inputs": [],
    "dataset_contract_ids": [],
    "combination_mode": "",
    "required_evidence_step_ids": [],
    "required_data": [],
    "expected_output": "",
    "evidence_ids": [],
    "confirmation_ids": [],
    "result_summary": "",
    "limitations": "",
    "confidence": "",
    "required_capability": "",
    "evidence_requirements": [],
    "confirmation_policy": {},
}
```

In `TaskManager.update`, change allowed statuses to:

```python
allowed = ("pending", "blocked", "in_progress", "completed", "failed", "superseded", "archived", "deleted")
```

When `status == "failed"`, set:

```python
task["failed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

Do not call `_clear_dependency()` for failed tasks.

- [ ] **Step 5: Create shared projector**

Create `src/data_agent/agent/workflow_projection.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION
from data_agent.session.task_manager import TaskManager


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _step_subject(step: dict[str, Any], index: int) -> str:
    return (
        _text(step.get("task"))
        or _text(step.get("subject"))
        or _text(step.get("title"))
        or _text(step.get("goal"))
        or f"Analysis step {index}"
    )


def project_plan_to_workflow_tasks(
    manager: TaskManager,
    plan: dict[str, Any],
    *,
    session_id: str,
    project_name: str = "",
    source: str = "analysis_plan",
) -> dict[str, Any]:
    if plan.get("contract_version") != STAGE3C0B_CONTRACT_VERSION:
        return {
            "created": 0,
            "reused": 0,
            "task_ids": [],
            "error": "legacy_plan_display_only",
        }

    method_plan = plan.get("method_plan") if isinstance(plan.get("method_plan"), list) else []
    plan_id = _text(plan.get("id")) or f"plan_{uuid.uuid4().hex[:10]}"
    workflow_id = _text(plan.get("workflow_id")) or f"wf_{uuid.uuid4().hex[:8]}"
    plan_record = manager.create_plan(
        session_id=session_id,
        project_name=project_name,
        goal=_text(plan.get("goal")),
        source=source,
        analysis_spec_id=_text(plan.get("id")),
        workflow_id=workflow_id,
    )

    created: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    by_step_id: dict[str, dict[str, Any]] = {}

    for index, step in enumerate(method_plan, 1):
        if not isinstance(step, dict):
            continue
        step_id = _text(step.get("step_id")) or f"step_{index}"
        duplicate = manager.find_duplicate_task(
            session_id=session_id,
            plan_id=plan_record["id"],
            subject=_step_subject(step, index),
            analysis_spec_id=_text(plan.get("id")),
        )
        if duplicate:
            reused.append(duplicate)
            by_step_id[step_id] = duplicate
            continue
        task = manager.create(
            subject=_step_subject(step, index)[:120],
            description=_text(step.get("expected_output")),
            session_id=session_id,
            workflow_id=workflow_id,
            project_name=project_name,
            stage="execute",
            node_type=_text(step.get("combination_mode")) or "analysis",
            analysis_spec_id=_text(plan.get("id")),
            analysis_plan_id=plan_id,
            step_id=step_id,
            dataset_inputs=list(step.get("dataset_inputs") or []),
            dataset_contract_ids=list(step.get("dataset_contract_ids") or []),
            combination_mode=_text(step.get("combination_mode")),
            required_evidence_step_ids=list(step.get("required_evidence_step_ids") or []),
            required_data=list(step.get("dataset_inputs") or []),
            expected_output=_text(step.get("expected_output")),
            required_capability=_text(step.get("required_capability")),
            evidence_requirements=list(step.get("evidence_requirements") or []),
            confirmation_policy=step.get("confirmation_policy") or {},
            plan_id=plan_record["id"],
            plan_version=plan_record.get("version", 1),
            plan_status="active",
            task_kind="plan_task",
            source=source,
        )
        created.append(task)
        by_step_id[step_id] = task

    for task in created + reused:
        required_steps = list(task.get("required_evidence_step_ids") or [])
        dependency_ids = [
            by_step_id[step_id]["id"]
            for step_id in required_steps
            if step_id in by_step_id
        ]
        if dependency_ids:
            manager.update(task["id"], addBlockedBy=dependency_ids)
            for dependency_id in dependency_ids:
                manager.update(dependency_id, addBlocks=[task["id"]])

    return {
        "workflow_id": workflow_id,
        "plan_id": plan_record["id"],
        "analysis_plan_id": plan_id,
        "created": len(created),
        "reused": len(reused),
        "task_ids": [task["id"] for task in created + reused],
    }
```

- [ ] **Step 6: Route controller task creation through the projector**

Modify `AnalysisFlowController.ensure_workflow_tasks` in `src/data_agent/agent/analysis_flow_controller.py`:

```python
    def ensure_workflow_tasks(self, state: AnalysisSessionState) -> dict:
        plan = state.analysis_plan or state.analysis_spec or {}
        if not isinstance(plan, dict):
            return {"created": 0, "task_ids": []}
        from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks

        project_name = self.project_name or state.project_name or ""
        return project_plan_to_workflow_tasks(
            task_manager,
            plan,
            session_id=self.session_id,
            project_name=project_name,
            source="analysis_plan",
        )
```

Keep `ensure_confirmation_task` unchanged except for new fields inherited from `TaskManager`.

- [ ] **Step 7: Route task tools through the projector**

Modify `create_workflow_tasks_from_spec` in `src/data_agent/tools/task_tools.py`:

```python
def create_workflow_tasks_from_spec(spec: dict) -> dict:
    from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks

    return project_plan_to_workflow_tasks(
        task_manager,
        spec,
        session_id=_session_id(),
        project_name=_project_name(),
        source="analysis_plan",
    )
```

Modify `_workflow_fields_from_dict` to include:

```python
"analysis_plan_id",
"step_id",
"dataset_inputs",
"dataset_contract_ids",
"combination_mode",
"required_evidence_step_ids",
```

Modify `task_update` description and status schema text so `failed` is documented as valid.

- [ ] **Step 8: Expose task fields in web API**

Modify `src/data_agent/web/blueprints/tasks.py` create and patch handlers to pass:

```python
analysis_plan_id=data.get("analysis_plan_id", ""),
step_id=data.get("step_id", ""),
dataset_inputs=data.get("dataset_inputs", []),
dataset_contract_ids=data.get("dataset_contract_ids", []),
combination_mode=data.get("combination_mode", ""),
required_evidence_step_ids=data.get("required_evidence_step_ids", []),
```

No frontend work is done in this task.

- [ ] **Step 9: Run projection tests and existing task regressions**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_workflow_projection.py tests/test_task_manager_scope.py tests/test_task_plan_versioning.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add src/data_agent/agent/workflow_projection.py src/data_agent/session/task_manager.py src/data_agent/agent/analysis_flow_controller.py src/data_agent/tools/task_tools.py src/data_agent/web/blueprints/tasks.py tests/test_stage3c0b_workflow_projection.py
git commit -m "feat: project stage 3c0b plans to workflow tasks"
```

---

### Task 3: Stage 3C0B Plan Recording And Legacy Cutover

**Files:**
- Modify: `src/data_agent/tools/analysis_flow.py`
- Modify: `src/data_agent/agent/analysis_flow_controller.py`
- Modify: `tests/test_stage3c0b_plan_contracts.py`
- Modify: `tests/test_analysis_flow_tools.py`

- [ ] **Step 1: Write failing tests for `record_analysis_plan` validation**

Append to `tests/test_stage3c0b_plan_contracts.py`:

```python
import json

from data_agent.tools.analysis_flow import record_analysis_plan


def test_record_analysis_plan_rejects_legacy_stage3c0b_execution(monkeypatch):
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr(
        "data_agent.tools.analysis_flow._write_analysis_artifact",
        lambda kind, payload: {"saved": "artifact.json", "type": kind, "payload": payload},
    )

    result = json.loads(record_analysis_plan(json.dumps({
        "goal": "Analyze files",
        "method_plan": [{"step_id": "s1"}],
        "visualization_strategy": "none",
    })))

    assert result["error_type"] == "legacy_plan_display_only"
```

- [ ] **Step 2: Write failing tests for valid plan recording**

Append:

```python
def test_record_analysis_plan_persists_valid_stage3c0b_plan(monkeypatch):
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr(
        "data_agent.tools.analysis_flow._write_analysis_artifact",
        lambda kind, payload: {"saved": "artifact.json", "type": kind, "payload": payload},
    )

    payload = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze banner independently.",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "evidence_requirements": ["click_rate"],
            }
        ],
        "visualization_strategy": "none",
    }

    result = json.loads(record_analysis_plan(json.dumps(payload)))

    assert result["analysis_plan_id"]
    assert result["state_stage"] if "state_stage" in result else True
    assert "error" not in result
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_plan_contracts.py -q
```

Expected: FAIL because `record_analysis_plan` accepts legacy plans.

- [ ] **Step 4: Validate Stage 3C0B plans in `record_analysis_plan`**

Modify `src/data_agent/tools/analysis_flow.py` inside `record_analysis_plan` after top-level required field validation:

```python
    if payload.get("contract_version"):
        from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract

        state = _current_state()
        dataset_contracts = list(getattr(state, "dataset_contracts", []) or []) if state is not None else []
        validation = validate_analysis_plan_contract(payload, dataset_contracts=dataset_contracts)
        if not validation.ok:
            return json.dumps({
                "error": validation.message,
                "error_type": validation.error_type,
                "details": validation.details,
            }, ensure_ascii=False)
        payload = validation.plan
    else:
        from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION

        return json.dumps({
            "error": f"AnalysisPlan missing executable contract_version={STAGE3C0B_CONTRACT_VERSION}; legacy plans are display-only.",
            "error_type": "legacy_plan_display_only",
        }, ensure_ascii=False)
```

Then remove the later duplicate `state = _current_state()` line or reuse the existing `state` variable so the function still saves state and artifact once.

- [ ] **Step 5: Keep `record_analysis_spec` display-only for legacy specs**

Modify `record_analysis_spec` so it still saves old specs for history, but does not call `create_workflow_tasks_from_spec` unless `payload.get("contract_version") == STAGE3C0B_CONTRACT_VERSION`.

Use:

```python
    if payload.get("contract_version") == STAGE3C0B_CONTRACT_VERSION:
        try:
            from data_agent.tools.task_tools import create_workflow_tasks_from_spec
            result["workflow"] = create_workflow_tasks_from_spec(payload)
        except Exception as e:
            result["workflow_error"] = str(e)
    else:
        result["workflow"] = {
            "created": 0,
            "task_ids": [],
            "display_only": True,
            "reason": "legacy_analysis_spec_display_only",
        }
```

- [ ] **Step 6: Run plan recording regressions**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_plan_contracts.py tests/test_analysis_flow_tools.py -q
```

Expected: PASS. If existing tests expect legacy `record_analysis_plan` to create workflow tasks, update those tests to assert `legacy_plan_display_only` only when they are exercising executable 3C0B behavior.

- [ ] **Step 7: Commit**

```powershell
git add src/data_agent/tools/analysis_flow.py src/data_agent/agent/analysis_flow_controller.py tests/test_stage3c0b_plan_contracts.py tests/test_analysis_flow_tools.py
git commit -m "feat: require executable stage 3c0b plan contracts"
```

---

### Task 4: Canonical Evidence Records And Evidence-Driven Task Completion

**Files:**
- Create: `src/data_agent/agent/evidence_contracts.py`
- Create: `tests/test_stage3c0b_evidence_contracts.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/tools/analysis_flow.py`
- Modify: `src/data_agent/session/task_manager.py`

- [ ] **Step 1: Write failing tests for canonical evidence validation and ID stability**

Create `tests/test_stage3c0b_evidence_contracts.py`:

```python
import json

from data_agent.agent.evidence_contracts import evidence_id_for, validate_stage3c0b_evidence


def _evidence() -> dict:
    return {
        "plan_id": "plan_abc",
        "step_id": "step_banner",
        "claim_key": "banner_click_rate",
        "claim": "Banner click rate is measurable.",
        "dataset": "banner",
        "dataset_contract_id": "contract_banner",
        "method": "descriptive_aggregation",
        "tool_calls": ["quick_profile", "run_python"],
        "result_summary": "Click rate is 3.2%.",
        "sample_size": 1000,
        "limitations": ["Descriptive only."],
        "confidence": "medium",
        "evidence_requirement": "click_rate",
        "measurements": [
            {
                "metric": "click_rate",
                "definition": "clicks / impressions",
                "value": 0.032,
                "unit": "ratio",
                "grain": "banner_day",
                "population_scope": "all banner rows",
                "time_scope": "full_file",
                "method": "sum(clicks) / sum(impressions)",
                "denominator": 1000,
                "limitations": ["No causal interpretation."],
            }
        ],
    }


def test_evidence_id_is_stable_business_key():
    assert evidence_id_for("plan_abc", "step_banner", "banner_click_rate") == "ev_plan_abc_step_banner_banner_click_rate"


def test_valid_canonical_evidence_passes():
    result = validate_stage3c0b_evidence(_evidence(), current_plan_id="plan_abc")

    assert result.ok is True
    assert result.record["id"] == "ev_plan_abc_step_banner_banner_click_rate"
    assert result.record["measurements"][0]["unit"] == "ratio"
```

- [ ] **Step 2: Write failing tests for old metrics rejection and current-plan isolation**

Append:

```python
def test_rejects_old_metrics_without_measurements():
    evidence = _evidence()
    evidence.pop("measurements")
    evidence["metrics"] = {"click_rate": 0.032}

    result = validate_stage3c0b_evidence(evidence, current_plan_id="plan_abc")

    assert result.ok is False
    assert result.error_type == "missing_measurements"


def test_rejects_evidence_from_other_plan():
    evidence = _evidence()
    evidence["plan_id"] = "plan_other"

    result = validate_stage3c0b_evidence(evidence, current_plan_id="plan_abc")

    assert result.ok is False
    assert result.error_type == "evidence_outside_current_plan"
```

- [ ] **Step 3: Write failing tests for task completion only after required evidence**

Append:

```python
from data_agent.session.task_manager import TaskManager


def test_task_completion_requires_all_evidence_requirements(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    task = manager.create(
        "Analyze banner",
        session_id="s1",
        source="analysis_plan",
        step_id="step_banner",
        evidence_requirements=["click_rate", "impressions"],
    )
    evidence = _evidence()

    completed = manager.complete_matching_tasks_from_evidence("s1", evidence)

    assert completed == []
    assert manager.get(task["id"])["status"] == "pending"


def test_task_completes_when_all_requirements_have_evidence(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    task = manager.create(
        "Analyze banner",
        session_id="s1",
        source="analysis_plan",
        step_id="step_banner",
        evidence_requirements=["click_rate"],
    )
    evidence = _evidence()

    completed = manager.complete_matching_tasks_from_evidence("s1", evidence)

    assert completed == [task["id"]]
    updated = manager.get(task["id"])
    assert updated["status"] == "completed"
    assert updated["evidence_ids"] == ["ev_plan_abc_step_banner_banner_click_rate"]
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_evidence_contracts.py -q
```

Expected: FAIL because `evidence_contracts.py` does not exist and task completion is too broad.

- [ ] **Step 5: Implement evidence contract module**

Create `src/data_agent/agent/evidence_contracts.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceValidationResult:
    ok: bool
    record: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


REQUIRED_EVIDENCE_FIELDS = (
    "plan_id",
    "step_id",
    "claim_key",
    "claim",
    "dataset",
    "dataset_contract_id",
    "method",
    "tool_calls",
    "result_summary",
    "sample_size",
    "limitations",
    "confidence",
    "evidence_requirement",
    "measurements",
)

REQUIRED_MEASUREMENT_FIELDS = (
    "metric",
    "definition",
    "value",
    "unit",
    "grain",
    "population_scope",
    "time_scope",
    "method",
    "denominator",
    "limitations",
)


def _slug(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "missing"


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def evidence_id_for(plan_id: str, step_id: str, claim_key: str) -> str:
    return f"ev_{_slug(plan_id)}_{_slug(step_id)}_{_slug(claim_key)}"


def _error(error_type: str, message: str, **details: Any) -> EvidenceValidationResult:
    return EvidenceValidationResult(False, error_type=error_type, message=message, details=details)


def validate_stage3c0b_evidence(
    record: dict[str, Any],
    *,
    current_plan_id: str,
) -> EvidenceValidationResult:
    if not isinstance(record, dict):
        return _error("invalid_evidence", "EvidenceRecord must be a JSON object.")
    if record.get("plan_id") != current_plan_id:
        return _error("evidence_outside_current_plan", "EvidenceRecord does not belong to the current plan.")
    if "measurements" not in record:
        return _error("missing_measurements", "Stage 3C0B EvidenceRecord requires canonical measurements.")
    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if _missing(record.get(field))]
    if missing:
        return _error("missing_evidence_fields", "EvidenceRecord is missing required fields.", missing=missing)
    measurements = record.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return _error("invalid_measurements", "measurements must be a non-empty list.")
    for index, measurement in enumerate(measurements):
        if not isinstance(measurement, dict):
            return _error("invalid_measurement", "Each measurement must be an object.", index=index)
        missing_measurement = [
            field for field in REQUIRED_MEASUREMENT_FIELDS
            if _missing(measurement.get(field))
        ]
        if missing_measurement:
            return _error(
                "missing_measurement_fields",
                "Measurement is missing required compatibility fields.",
                index=index,
                missing=missing_measurement,
            )

    normalized = dict(record)
    normalized["id"] = evidence_id_for(
        str(normalized["plan_id"]),
        str(normalized["step_id"]),
        str(normalized["claim_key"]),
    )
    return EvidenceValidationResult(True, record=normalized)
```

- [ ] **Step 6: Add idempotent evidence upsert to analysis state**

Modify `src/data_agent/agent/analysis_state.py`:

```python
    def upsert_evidence_record(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        for index, existing in enumerate(self.evidence_records):
            if existing.get("id") == item.get("id"):
                merged = dict(existing)
                merged.update(item)
                self.evidence_records[index] = merged
                self.stage = "execute"
                return merged
        self.evidence_records.append(item)
        self.stage = "execute"
        return item
```

Keep `add_evidence_record` for non-3C0B display/history callers.

- [ ] **Step 7: Validate canonical evidence in `record_evidence_record`**

Modify `src/data_agent/tools/analysis_flow.py` inside `record_evidence_record` after JSON parsing:

```python
    state = _current_state()
    current_plan = getattr(state, "analysis_plan", None) if state is not None else {}
    current_plan_id = current_plan.get("id", "") if isinstance(current_plan, dict) else ""
    if payload.get("plan_id") or payload.get("step_id") or payload.get("measurements") is not None:
        from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

        validation = validate_stage3c0b_evidence(payload, current_plan_id=current_plan_id)
        if not validation.ok:
            return json.dumps({
                "error": validation.message,
                "error_type": validation.error_type,
                "details": validation.details,
            }, ensure_ascii=False)
        payload = validation.record
```

When saving to state, use:

```python
    if state is not None:
        if payload.get("plan_id") and payload.get("measurements") is not None:
            payload = state.upsert_evidence_record(payload)
        else:
            payload = state.add_evidence_record(payload)
        state.save()
```

Do not call `_mark_statistical_detail_status` for canonical 3C0B records; `measurements` replaces old `metrics` detail status.

- [ ] **Step 8: Make task completion evidence-driven for Stage 3C0B**

Modify `TaskManager._evidence_text`, `_evidence_has_substantive_work`, and `complete_matching_tasks_from_evidence`.

Add helper:

```python
    def _stage3c0b_evidence_matches_task(self, task: dict, evidence: dict) -> bool:
        if task.get("step_id") and evidence.get("step_id") != task.get("step_id"):
            return False
        if task.get("analysis_plan_id") and evidence.get("plan_id") != task.get("analysis_plan_id"):
            return False
        task_contracts = set(task.get("dataset_contract_ids") or [])
        if task_contracts and evidence.get("dataset_contract_id") not in task_contracts:
            return False
        requirement = str(evidence.get("evidence_requirement") or "")
        requirements = {str(item) for item in task.get("evidence_requirements") or []}
        return bool(requirement and requirement in requirements)

    def _stage3c0b_requirements_satisfied(self, task: dict, evidence_ids: list[str], evidence: dict) -> bool:
        requirements = {str(item) for item in task.get("evidence_requirements") or [] if str(item)}
        if not requirements:
            return False
        satisfied = set(task.get("satisfied_evidence_requirements") or [])
        requirement = str(evidence.get("evidence_requirement") or "")
        if requirement:
            satisfied.add(requirement)
        return requirements.issubset(satisfied)
```

In `complete_matching_tasks_from_evidence`, before free-text matching, add a Stage 3C0B branch:

```python
            if task.get("step_id") or task.get("analysis_plan_id"):
                if not self._stage3c0b_evidence_matches_task(task, evidence):
                    continue
                evidence_ids = list(task.get("evidence_ids") or [])
                if evidence_id and evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
                satisfied = list(task.get("satisfied_evidence_requirements") or [])
                requirement = str(evidence.get("evidence_requirement") or "")
                if requirement and requirement not in satisfied:
                    satisfied.append(requirement)
                should_complete = self._stage3c0b_requirements_satisfied(task, evidence_ids, evidence)
                self.update(
                    task["id"],
                    status="completed" if should_complete else task.get("status"),
                    evidence_ids=evidence_ids,
                    result_summary=evidence.get("result_summary", "") or evidence.get("claim", ""),
                    confidence=evidence.get("confidence", ""),
                    completed_by="evidence" if should_complete else task.get("completed_by", ""),
                    satisfied_evidence_requirements=satisfied,
                )
                if should_complete:
                    completed.append(task["id"])
                continue
```

Add `"satisfied_evidence_requirements": []` to `WORKFLOW_FIELDS`.

Ensure `_complete_analysis_spec_plan_from_evidence` returns `[]` when any active task has `analysis_plan_id` or `step_id`.

- [ ] **Step 9: Run evidence tests and related regressions**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_evidence_contracts.py tests/test_analysis_flow_tools.py tests/test_task_manager_scope.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add src/data_agent/agent/evidence_contracts.py src/data_agent/agent/analysis_state.py src/data_agent/tools/analysis_flow.py src/data_agent/session/task_manager.py tests/test_stage3c0b_evidence_contracts.py
git commit -m "feat: record canonical stage 3c0b evidence"
```

---

### Task 5: Measurement Compatibility And Verification Integration

**Files:**
- Create: `src/data_agent/agent/evidence_compatibility.py`
- Create: `tests/test_stage3c0b_verification_compatibility.py`
- Modify: `src/data_agent/agent/verification.py`
- Modify: `tests/test_verification_layer.py`

- [ ] **Step 1: Write failing tests for compatible and incompatible measurements**

Create `tests/test_stage3c0b_verification_compatibility.py`:

```python
from data_agent.agent.evidence_compatibility import compare_measurements


def _measurement(metric="revenue", unit="CNY", grain="day", time_scope="2026-05", population_scope="paid users"):
    return {
        "metric": metric,
        "definition": "sum paid amount",
        "value": 100,
        "unit": unit,
        "grain": grain,
        "population_scope": population_scope,
        "time_scope": time_scope,
        "method": "sum(amount)",
        "denominator": 10,
        "limitations": [],
    }


def test_measurements_are_compatible_only_when_all_scopes_match():
    result = compare_measurements(_measurement(), _measurement())

    assert result.compatible is True
    assert result.reason_code == "compatible"


def test_measurements_with_different_population_scope_are_not_comparable():
    result = compare_measurements(_measurement(), _measurement(population_scope="all users"))

    assert result.compatible is False
    assert result.reason_code == "population_scope_mismatch"
    assert "统计对象不同" in result.user_message
```

- [ ] **Step 2: Write failing tests for current-plan evidence verification**

Append:

```python
from data_agent.agent.verification import verify_analysis_claims


def test_verification_rejects_claim_evidence_from_other_plan():
    report = verify_analysis_claims(
        claims=[{"id": "claim_1", "claim": "Banner click rate is 3.2%", "evidence_id": "ev_1"}],
        evidence_records=[
            {
                "id": "ev_1",
                "plan_id": "plan_old",
                "step_id": "step_banner",
                "claim": "Banner click rate is 3.2%",
                "dataset": "banner",
                "dataset_contract_id": "contract_banner",
                "method": "descriptive",
                "sample_size": 100,
                "time_scope": "full_file",
                "calculation_method": "clicks / impressions",
                "method_detail": "ratio",
                "limitations": ["descriptive"],
                "confidence": "medium",
                "measurements": [_measurement(metric="click_rate", unit="ratio")],
            }
        ],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
    )

    assert report["overall_status"] == "fail"
    assert report["claim_checks"][0]["status"] == "failed"
    assert "current plan" in report["claim_checks"][0]["issues"][0]
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_verification_compatibility.py -q
```

Expected: FAIL because `evidence_compatibility.py` does not exist and `verify_analysis_claims` lacks `current_plan_id`.

- [ ] **Step 4: Implement measurement compatibility module**

Create `src/data_agent/agent/evidence_compatibility.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MeasurementCompatibility:
    compatible: bool
    reason_code: str
    user_message: str
    fields: list[str]


_FIELD_MESSAGES = {
    "metric": "指标不同，不能直接比较。",
    "definition": "指标定义不同，不能直接比较。",
    "unit": "单位不同，Stage 3C0B 不做自动单位换算。",
    "grain": "统计粒度不同，不能直接比较。",
    "time_scope": "时间范围不同，不能直接比较。",
    "population_scope": "统计对象不同，不能直接比较。",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, (int, float, bool)):
        return str(value).casefold()
    return ""


def compare_measurements(left: dict[str, Any], right: dict[str, Any]) -> MeasurementCompatibility:
    for field in ("metric", "definition", "unit", "grain", "time_scope", "population_scope"):
        if _text(left.get(field)) != _text(right.get(field)):
            return MeasurementCompatibility(
                compatible=False,
                reason_code=f"{field}_mismatch",
                user_message=_FIELD_MESSAGES[field],
                fields=[field],
            )
    return MeasurementCompatibility(
        compatible=True,
        reason_code="compatible",
        user_message="统计口径兼容，可以比较。",
        fields=[],
    )
```

- [ ] **Step 5: Extend verification for current-plan isolation**

Modify `verify_analysis_claims` signature in `src/data_agent/agent/verification.py`:

```python
def verify_analysis_claims(
    claims: list[Any],
    evidence_records: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
    current_plan_id: str = "",
) -> dict[str, Any]:
```

Filter evidence:

```python
    if current_plan_id:
        safe_evidence = [
            record for record in safe_evidence
            if str(record.get("plan_id") or "") == current_plan_id
        ]
```

If a claim has explicit `evidence_id` but the matching ID exists only outside the current plan, return a failed check with issue:

```python
"Evidence record exists outside the current plan and cannot support this claim"
```

Add optional parameter `current_plan_id` through `_check_claim` if needed.

- [ ] **Step 6: Add compatibility issue detection for comparison claims**

In `_check_claim`, if `claim` is a dict and has `compare_evidence_ids`, load the referenced evidence records. For every pair of first measurements, call `compare_measurements`. If incompatible, set:

```python
check["status"] = "failed"
check["strength"] = "unsupported"
check["issues"].append(f"Measurement compatibility failed: {compatibility.user_message}")
```

Do not infer conversion or alignment.

- [ ] **Step 7: Run verification tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_verification_compatibility.py tests/test_verification_layer.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/data_agent/agent/evidence_compatibility.py src/data_agent/agent/verification.py tests/test_stage3c0b_verification_compatibility.py tests/test_verification_layer.py
git commit -m "feat: enforce stage 3c0b evidence compatibility"
```

---

### Task 6: Current-Task Execution Scope Guard

**Files:**
- Create: `src/data_agent/agent/execution_scope.py`
- Create: `tests/test_stage3c0b_execution_scope.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/agent/multi_file_scope.py`

- [ ] **Step 1: Write failing tests for active task selection and dataset access**

Create `tests/test_stage3c0b_execution_scope.py`:

```python
from data_agent.agent.execution_scope import (
    current_execution_scope,
    ensure_dataset_allowed_for_current_task,
)
from data_agent.session.task_manager import TaskManager


def test_current_execution_scope_uses_unique_in_progress_task(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    manager.create(
        "Analyze banner",
        session_id="s1",
        status="in_progress",
        step_id="step_banner",
        dataset_inputs=["banner"],
        dataset_contract_ids=["contract_banner"],
        combination_mode="independent",
    )

    scope = current_execution_scope(manager, session_id="s1")

    assert scope.active is True
    assert scope.step_id == "step_banner"
    assert scope.allowed_datasets == {"banner"}


def test_scope_guard_blocks_unbound_dataset(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    manager.create(
        "Analyze banner",
        session_id="s1",
        status="in_progress",
        step_id="step_banner",
        dataset_inputs=["banner"],
    )

    result = ensure_dataset_allowed_for_current_task(manager, session_id="s1", dataset="iap")

    assert result.allowed is False
    assert result.error_type == "dataset_outside_current_task_scope"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_execution_scope.py -q
```

Expected: FAIL because `execution_scope.py` does not exist.

- [ ] **Step 3: Implement execution scope module**

Create `src/data_agent/agent/execution_scope.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_agent.session.task_manager import TaskManager


@dataclass(frozen=True)
class ExecutionScope:
    active: bool
    task_id: int = 0
    step_id: str = ""
    combination_mode: str = ""
    allowed_datasets: set[str] = field(default_factory=set)
    dataset_contract_ids: set[str] = field(default_factory=set)
    error_type: str = ""
    message: str = ""


@dataclass(frozen=True)
class ScopeGuardResult:
    allowed: bool
    error_type: str = ""
    message: str = ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def current_execution_scope(
    manager: TaskManager,
    *,
    session_id: str,
    project_name: str = "",
) -> ExecutionScope:
    tasks = manager.list_active_for_scope(session_id=session_id, project_name=project_name)
    in_progress = [task for task in tasks if task.get("status") == "in_progress"]
    if not in_progress:
        return ExecutionScope(active=False)
    if len(in_progress) > 1:
        return ExecutionScope(
            active=False,
            error_type="multiple_in_progress_tasks",
            message="Stage 3C0B allows only one in-progress task.",
        )
    task = in_progress[0]
    return ExecutionScope(
        active=True,
        task_id=int(task.get("id") or 0),
        step_id=_text(task.get("step_id")),
        combination_mode=_text(task.get("combination_mode")),
        allowed_datasets={_text(item) for item in task.get("dataset_inputs") or [] if _text(item)},
        dataset_contract_ids={_text(item) for item in task.get("dataset_contract_ids") or [] if _text(item)},
    )


def ensure_dataset_allowed_for_current_task(
    manager: TaskManager,
    *,
    session_id: str,
    dataset: str,
    project_name: str = "",
) -> ScopeGuardResult:
    scope = current_execution_scope(manager, session_id=session_id, project_name=project_name)
    if not scope.active:
        if scope.error_type:
            return ScopeGuardResult(False, scope.error_type, scope.message)
        return ScopeGuardResult(True)
    if scope.combination_mode == "synthesis":
        return ScopeGuardResult(
            False,
            "synthesis_cannot_read_raw_dataset",
            "Synthesis consumes verified evidence, not raw datasets.",
        )
    if dataset not in scope.allowed_datasets:
        return ScopeGuardResult(
            False,
            "dataset_outside_current_task_scope",
            f"Dataset '{dataset}' is not bound to the current task.",
        )
    return ScopeGuardResult(True)
```

- [ ] **Step 4: Inject compact current-task scope into analysis summary**

Modify `analysis_state_summary` in `src/data_agent/agent/analysis_state.py`. Add a safe import and append:

```python
    try:
        from data_agent.agent.execution_scope import current_execution_scope
        from data_agent.session.task_manager import task_manager
        scope = current_execution_scope(task_manager, session_id=state.session_id, project_name=state.project_name or "")
    except Exception:
        scope = None
    if scope is not None and scope.active:
        lines.append(
            "- current_task_scope: "
            f"task_id={scope.task_id}, step_id={scope.step_id}, "
            f"mode={scope.combination_mode}, datasets={sorted(scope.allowed_datasets)}"
        )
```

- [ ] **Step 5: Stop generic auto-completion in loop**

Modify `AgentLoop._auto_track_task_progress` in `src/data_agent/agent/loop.py`:

```python
    def _auto_track_task_progress(self, tool_name: str, success: bool) -> None:
        """Do not complete Stage 3C0B tasks after generic tool success."""
        try:
            from data_agent.session.task_manager import task_manager
            tasks = task_manager.list_for_scope(session_id=self.session_id)
            in_progress = [task for task in tasks if task.get("status") == "in_progress"]
            if not in_progress:
                return
            task = in_progress[0]
            if task.get("step_id") or task.get("analysis_plan_id"):
                return
            if success:
                task_manager.update(task["id"], status="completed")
        except Exception:
            return
```

- [ ] **Step 6: Add guard hook for dataset-read tools**

In `AgentLoop._execute_single_tool`, before `registry.execute`, add:

```python
            guard_error = self._guard_dataset_tool_scope(tc.name, tc.arguments)
            if guard_error:
                tool_result = json.dumps(guard_error, ensure_ascii=False)
            else:
                tool_result = registry.execute(tc.name, tc.arguments)
```

Add method:

```python
    def _guard_dataset_tool_scope(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        dataset_arg_names = ("name", "dataset", "data", "left", "right")
        dataset = ""
        for arg_name in dataset_arg_names:
            value = arguments.get(arg_name) if isinstance(arguments, dict) else ""
            if isinstance(value, str) and value:
                dataset = value
                break
        if not dataset:
            return None
        from data_agent.agent.execution_scope import ensure_dataset_allowed_for_current_task
        from data_agent.session.task_manager import task_manager
        result = ensure_dataset_allowed_for_current_task(
            task_manager,
            session_id=self.session_id,
            project_name=self.context.project_name or "",
            dataset=dataset,
        )
        if result.allowed:
            return None
        return {"error": result.message, "error_type": result.error_type}
```

Apply the same guard in `_execute_tools_parallel` before each read-only execution by calling the helper and returning the error JSON for blocked calls.

- [ ] **Step 7: Run execution-scope tests and loop regressions**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_execution_scope.py tests/test_comprehensive_analysis_flow.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/data_agent/agent/execution_scope.py src/data_agent/agent/loop.py src/data_agent/agent/analysis_state.py src/data_agent/agent/multi_file_scope.py tests/test_stage3c0b_execution_scope.py
git commit -m "feat: enforce stage 3c0b task execution scope"
```

---

### Task 7: Analysis Sufficiency Gate And Synthesis Claim Validation

**Files:**
- Create: `src/data_agent/agent/analysis_sufficiency.py`
- Create: `tests/test_stage3c0b_sufficiency.py`
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/agent/analysis_state.py`

- [ ] **Step 1: Write failing tests for sufficiency outcomes**

Create `tests/test_stage3c0b_sufficiency.py`:

```python
from data_agent.agent.analysis_sufficiency import evaluate_analysis_sufficiency, validate_synthesis_findings


def _task(step_id: str, status: str, requirements=None):
    return {
        "id": 1,
        "step_id": step_id,
        "status": status,
        "evidence_requirements": requirements or ["metric"],
        "required_evidence_step_ids": [],
    }


def _evidence(step_id="step_banner", evidence_requirement="metric"):
    return {
        "id": "ev_1",
        "plan_id": "plan_1",
        "step_id": step_id,
        "evidence_requirement": evidence_requirement,
        "confidence": "medium",
    }


def test_sufficiency_ready_when_required_evidence_passed():
    result = evaluate_analysis_sufficiency(
        plan_id="plan_1",
        tasks=[_task("step_banner", "completed")],
        evidence_records=[_evidence()],
        verification_reports=[{"overall_status": "pass"}],
        user_questions=["How did banner perform?"],
    )

    assert result.status == "ready_for_synthesis"


def test_sufficiency_needs_more_analysis_when_question_uncovered():
    result = evaluate_analysis_sufficiency(
        plan_id="plan_1",
        tasks=[_task("step_banner", "completed")],
        evidence_records=[_evidence()],
        verification_reports=[{"overall_status": "pass"}],
        user_questions=["How did banner perform?", "How did IAP perform?"],
    )

    assert result.status == "needs_more_analysis"
    assert "IAP" in " ".join(result.uncovered_questions)


def test_sufficiency_blocks_when_required_task_failed():
    result = evaluate_analysis_sufficiency(
        plan_id="plan_1",
        tasks=[_task("step_banner", "failed")],
        evidence_records=[],
        verification_reports=[],
        user_questions=["How did banner perform?"],
    )

    assert result.status == "blocked_by_missing_data"
```

- [ ] **Step 2: Write failing tests for synthesis finding evidence citations**

Append:

```python
def test_synthesis_findings_require_current_plan_evidence_ids():
    result = validate_synthesis_findings(
        findings=[{"claim": "Banner is better.", "evidence_ids": ["ev_missing"], "strength": "confirmed"}],
        current_plan_id="plan_1",
        evidence_records=[_evidence()],
    )

    assert result.ok is False
    assert result.error_type == "unsupported_finding"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_sufficiency.py -q
```

Expected: FAIL because `analysis_sufficiency.py` does not exist.

- [ ] **Step 4: Implement sufficiency module**

Create `src/data_agent/agent/analysis_sufficiency.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SufficiencyResult:
    status: str
    reasons: list[str] = field(default_factory=list)
    uncovered_questions: list[str] = field(default_factory=list)
    missing_evidence_step_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FindingValidationResult:
    ok: bool
    error_type: str = ""
    message: str = ""
    finding_index: int = -1


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def evaluate_analysis_sufficiency(
    *,
    plan_id: str,
    tasks: list[dict[str, Any]],
    evidence_records: list[dict[str, Any]],
    verification_reports: list[dict[str, Any]],
    user_questions: list[str],
) -> SufficiencyResult:
    current_evidence = [
        record for record in evidence_records
        if not record.get("plan_id") or record.get("plan_id") == plan_id
    ]
    evidence_step_ids = {_text(record.get("step_id")) for record in current_evidence if _text(record.get("step_id"))}
    failed_required = [
        _text(task.get("step_id"))
        for task in tasks
        if task.get("status") == "failed" and task.get("evidence_requirements")
    ]
    if failed_required and not current_evidence:
        return SufficiencyResult(
            "blocked_by_missing_data",
            reasons=["Required task failed without valid evidence."],
            missing_evidence_step_ids=failed_required,
        )
    missing = [
        _text(task.get("step_id"))
        for task in tasks
        if task.get("status") == "completed"
        and task.get("evidence_requirements")
        and _text(task.get("step_id")) not in evidence_step_ids
    ]
    if missing:
        return SufficiencyResult(
            "needs_more_analysis",
            reasons=["Completed tasks are missing required EvidenceRecords."],
            missing_evidence_step_ids=missing,
        )
    evidence_text = " ".join(
        _text(record.get("claim")) + " " + _text(record.get("result_summary"))
        for record in current_evidence
    ).casefold()
    uncovered = [
        question for question in user_questions
        if question and not any(token in evidence_text for token in _question_tokens(question))
    ]
    if uncovered and current_evidence:
        return SufficiencyResult(
            "needs_more_analysis",
            reasons=["Some user questions are not covered by current evidence."],
            uncovered_questions=uncovered,
        )
    latest = verification_reports[-1] if verification_reports else {}
    if latest.get("overall_status") == "fail":
        return SufficiencyResult("needs_more_analysis", reasons=["Verification failed."])
    if current_evidence:
        return SufficiencyResult("ready_for_synthesis")
    return SufficiencyResult("blocked_by_missing_data", reasons=["No valid evidence exists."])


def _question_tokens(question: str) -> set[str]:
    return {
        token.casefold()
        for token in question.replace("?", " ").replace("？", " ").split()
        if len(token) >= 3
    }


def validate_synthesis_findings(
    *,
    findings: list[dict[str, Any]],
    current_plan_id: str,
    evidence_records: list[dict[str, Any]],
) -> FindingValidationResult:
    evidence_by_id = {
        _text(record.get("id")): record
        for record in evidence_records
        if _text(record.get("id")) and (not record.get("plan_id") or record.get("plan_id") == current_plan_id)
    }
    for index, finding in enumerate(findings):
        ids = [_text(item) for item in finding.get("evidence_ids") or [] if _text(item)]
        if not ids or any(evidence_id not in evidence_by_id for evidence_id in ids):
            return FindingValidationResult(
                False,
                error_type="unsupported_finding",
                message="Every synthesis finding must cite current-plan evidence.",
                finding_index=index,
            )
    return FindingValidationResult(True)
```

- [ ] **Step 5: Add sufficiency summary to analysis state**

Modify `AnalysisSessionState` in `src/data_agent/agent/analysis_state.py`:

```python
    sufficiency_reports: list[dict[str, Any]] = field(default_factory=list)
```

Add to `from_dict`, `to_dict`, and `analysis_state_summary` count lines.

Add:

```python
    def add_sufficiency_report_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.sufficiency_reports, ref)
```

- [ ] **Step 6: Wire synthesis policy to sufficiency reports**

Modify `src/data_agent/agent/synthesis_policy.py`. Add helper:

```python
def _latest_sufficiency_status(state: Any) -> str:
    reports = _get(state, "sufficiency_reports", None)
    if not isinstance(reports, list) or not reports:
        return ""
    latest = reports[-1]
    if not isinstance(latest, dict):
        return ""
    return str(latest.get("status") or "").strip()
```

In `derive_synthesis_policy`, after verification status:

```python
    sufficiency_status = _latest_sufficiency_status(state)
```

If status is `blocked_by_missing_data`, return a policy with:

```python
SynthesisPolicy(
    answer_mode="partial",
    insight_depth="none",
    business_translation="cautious",
    risk_boundary="insufficient_evidence",
    required_moves=["core_answer", "limitation", "next_step"],
    suppressed_moves=["decision_recommendation", "unsupported_comparison"],
    wording_style=wording_style,
    reason="Sufficiency gate found missing required data or evidence.",
)
```

If status is `needs_more_analysis`, require `next_step` and suppress `decision_recommendation`.

- [ ] **Step 7: Call sufficiency gate before final answer in loop**

Modify `AgentLoop._should_continue_for_analysis_quality` or the no-tool-call branch in `src/data_agent/agent/loop.py` so, when current state has a Stage 3C0B plan, it calls:

```python
from data_agent.agent.analysis_sufficiency import evaluate_analysis_sufficiency
from data_agent.session.task_manager import task_manager

plan = self.context.analysis_state.analysis_plan or {}
tasks = task_manager.list_active_for_scope(
    session_id=self.session_id,
    project_name=self.context.project_name or "",
)
result = evaluate_analysis_sufficiency(
    plan_id=plan.get("id", ""),
    tasks=tasks,
    evidence_records=self.context.analysis_state.evidence_records,
    verification_reports=self.context.analysis_state.verification_reports,
    user_questions=[self.context.analysis_state.goal or user_input],
)
self.context.analysis_state.add_sufficiency_report_ref({
    "id": f"suff_{plan.get('id', 'plan')}",
    "status": result.status,
    "reasons": result.reasons,
    "uncovered_questions": result.uncovered_questions,
    "missing_evidence_step_ids": result.missing_evidence_step_ids,
})
self.context.analysis_state.save()
```

If status is `needs_more_analysis`, inject a system message asking for another bounded execution batch instead of returning final text. If status is `blocked_by_missing_data`, allow final text only if it states insufficient evidence or next steps.

- [ ] **Step 8: Run sufficiency and synthesis policy tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_sufficiency.py tests/test_synthesis_policy.py tests/test_analysis_quality.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add src/data_agent/agent/analysis_sufficiency.py src/data_agent/agent/synthesis_policy.py src/data_agent/agent/loop.py src/data_agent/agent/analysis_state.py tests/test_stage3c0b_sufficiency.py tests/test_synthesis_policy.py
git commit -m "feat: gate stage 3c0b synthesis on sufficiency"
```

---

### Task 8: User-Value Workbench Projection

**Files:**
- Create: `src/data_agent/agent/workbench_projection.py`
- Create: `tests/test_stage3c0b_workbench_projection.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `tests/test_web_workbench_parity.py`

- [ ] **Step 1: Write failing tests for action board and question map**

Create `tests/test_stage3c0b_workbench_projection.py`:

```python
from types import SimpleNamespace

from data_agent.agent.workbench_projection import build_stage3c0b_workbench


def test_workbench_leads_with_user_value_not_scheduler_state():
    state = SimpleNamespace(
        goal="Which game file shows stronger monetization evidence?",
        evidence_records=[
            {
                "id": "ev_banner",
                "plan_id": "plan_1",
                "step_id": "step_banner",
                "claim": "Banner click rate is measurable.",
                "dataset": "banner",
                "confidence": "medium",
                "measurements": [],
            }
        ],
        sufficiency_reports=[{"status": "ready_for_synthesis"}],
        verification_reports=[{"overall_status": "pass"}],
    )
    tasks = [
        {"id": 1, "step_id": "step_banner", "status": "completed", "dataset_inputs": ["banner"]},
        {"id": 2, "step_id": "step_iap", "status": "failed", "dataset_inputs": ["iap"], "result_summary": "Missing metric"},
    ]

    workbench = build_stage3c0b_workbench(state, tasks=tasks)

    assert "core_conclusion" in workbench
    assert "action_board" in workbench
    assert "question_map" in workbench
    assert workbench["action_board"]["still_uncertain"][0]["user_meaning"]
    assert "technical_tasks" in workbench["trust_details"]
```

- [ ] **Step 2: Write failing tests for bounded first screen**

Append:

```python
def test_workbench_first_screen_is_bounded():
    state = SimpleNamespace(
        goal="Analyze many files",
        evidence_records=[],
        sufficiency_reports=[{"status": "needs_more_analysis"}],
        verification_reports=[],
    )
    tasks = [
        {"id": i, "step_id": f"step_{i}", "status": "pending", "dataset_inputs": [f"ds_{i}"]}
        for i in range(25)
    ]

    workbench = build_stage3c0b_workbench(state, tasks=tasks)

    assert len(workbench["trust_details"]["technical_tasks"]) == 20
    assert workbench["trust_details"]["omitted_task_count"] == 5
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_workbench_projection.py -q
```

Expected: FAIL because `workbench_projection.py` does not exist.

- [ ] **Step 4: Implement workbench projection module**

Create `src/data_agent/agent/workbench_projection.py`:

```python
from __future__ import annotations

from typing import Any


MAX_FIRST_SCREEN_TASKS = 20


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _list_attr(obj: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(obj, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _latest_status(items: list[dict[str, Any]], key: str, default: str = "") -> str:
    if not items:
        return default
    return _text(items[-1].get(key)) or default


def _failure_user_meaning(task: dict[str, Any]) -> str:
    datasets = ", ".join(_text(item) for item in task.get("dataset_inputs") or [] if _text(item))
    if task.get("status") == "failed":
        return f"{datasets or '相关数据'} 的问题暂时无法判断；需要补充证据或修复数据后再判断。"
    if task.get("status") == "blocked":
        return f"{datasets or '相关数据'} 需要先解决结构性阻塞，当前不能安全分析。"
    return ""


def build_stage3c0b_workbench(
    state: Any,
    *,
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = _list_attr(state, "evidence_records")
    sufficiency = _latest_status(_list_attr(state, "sufficiency_reports"), "status", "not_run")
    verification = _latest_status(_list_attr(state, "verification_reports"), "overall_status", "not_run")
    confirmed = [
        {
            "claim": _text(record.get("claim")),
            "evidence_id": _text(record.get("id")),
            "dataset": _text(record.get("dataset")),
            "confidence": _text(record.get("confidence")),
        }
        for record in evidence[:8]
        if _text(record.get("claim"))
    ]
    uncertain = [
        {
            "step_id": _text(task.get("step_id")),
            "dataset_inputs": list(task.get("dataset_inputs") or []),
            "user_meaning": _failure_user_meaning(task),
        }
        for task in tasks
        if task.get("status") in {"failed", "blocked"}
    ]
    next_steps = []
    if sufficiency == "needs_more_analysis":
        next_steps.append({"action": "继续执行下一批分析", "reason": "当前证据还没有覆盖所有关键问题。"})
    if sufficiency == "blocked_by_missing_data":
        next_steps.append({"action": "补充缺失数据或修复阻塞", "reason": "缺少必要证据，不能安全得出结论。"})
    if not next_steps and uncertain:
        next_steps.append({"action": "只重跑受影响部分", "reason": "失败被隔离到相关问题，不需要重跑全部分析。"})

    bounded_tasks = tasks[:MAX_FIRST_SCREEN_TASKS]
    return {
        "core_conclusion": {
            "status": sufficiency,
            "summary": "已有证据可综合。" if sufficiency == "ready_for_synthesis" else "当前结论仍受证据限制。",
            "verification_status": verification,
        },
        "action_board": {
            "confirmed": confirmed,
            "still_uncertain": uncertain,
            "recommended_next_steps": next_steps,
        },
        "question_map": [
            {
                "question": _text(getattr(state, "goal", "")),
                "answer_status": "answered" if confirmed and sufficiency == "ready_for_synthesis" else "partial",
                "evidence_ids": [item["evidence_id"] for item in confirmed if item["evidence_id"]],
            }
        ],
        "trust_details": {
            "technical_tasks": bounded_tasks,
            "omitted_task_count": max(len(tasks) - len(bounded_tasks), 0),
            "verification_status": verification,
            "sufficiency_status": sufficiency,
        },
    }
```

- [ ] **Step 5: Delegate `trust_view` workbench payload to new projection**

Modify `_workbench_summary` in `src/data_agent/agent/trust_view.py`:

```python
    try:
        from data_agent.agent.workbench_projection import build_stage3c0b_workbench
        from data_agent.session.task_manager import task_manager
        tasks = task_manager.list_active_for_scope(
            session_id=_text(getattr(state, "session_id", "")),
            project_name=_text(getattr(state, "project_name", "")),
        )
        stage3c0b = build_stage3c0b_workbench(state, tasks=tasks)
    except Exception:
        stage3c0b = {}
```

Add `"stage3c0b": stage3c0b` to the returned workbench dictionary while preserving existing `current_context`, `confirmations`, `trust_evidence`, and `relationship_diagnostics` keys.

- [ ] **Step 6: Render value-first workbench in frontend**

Modify `src/data_agent/web/static/js/app.js` computed helpers:

```javascript
        stage3c0bWorkbench() {
            return this.trustView?.workbench?.stage3c0b || {};
        },
        stage3c0bActionBoard() {
            return this.stage3c0bWorkbench?.action_board || { confirmed: [], still_uncertain: [], recommended_next_steps: [] };
        },
```

In the Trust/workbench template area, render sections in this order:

```html
<section x-show="stage3c0bWorkbench.core_conclusion" class="trust-section">
  <h4>核心结论</h4>
  <p x-text="stage3c0bWorkbench.core_conclusion.summary"></p>
</section>
<section x-show="stage3c0bWorkbench.action_board" class="trust-section">
  <h4>行动看板</h4>
  <div>
    <strong>已确认</strong>
    <template x-for="item in stage3c0bActionBoard.confirmed" :key="item.evidence_id">
      <p x-text="item.claim"></p>
    </template>
  </div>
  <div>
    <strong>尚不确定</strong>
    <template x-for="item in stage3c0bActionBoard.still_uncertain" :key="item.step_id">
      <p x-text="item.user_meaning"></p>
    </template>
  </div>
  <div>
    <strong>建议下一步</strong>
    <template x-for="item in stage3c0bActionBoard.recommended_next_steps" :key="item.action">
      <p><span x-text="item.action"></span>：<span x-text="item.reason"></span></p>
    </template>
  </div>
</section>
```

Place existing technical details below these sections.

- [ ] **Step 7: Run workbench tests and JS syntax check**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_workbench_projection.py tests/test_web_workbench_parity.py -q
node -c src\data_agent\web\static\js\app.js
```

Expected: pytest PASS and `node -c` exits 0.

- [ ] **Step 8: Commit**

```powershell
git add src/data_agent/agent/workbench_projection.py src/data_agent/agent/trust_view.py src/data_agent/web/static/js/app.js tests/test_stage3c0b_workbench_projection.py tests/test_web_workbench_parity.py
git commit -m "feat: show stage 3c0b user-value workbench"
```

---

### Task 9: Real-Data Replay And Verification Note

**Files:**
- Create: `tests/test_stage3c0b_real_data_replay.py`
- Create: `docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md`
- Modify: code only if real-data replay reveals a Stage 3C0B bug in the implemented units.

- [ ] **Step 1: Write real-data smoke tests using `reference/test_doc`**

Create `tests/test_stage3c0b_real_data_replay.py`:

```python
from pathlib import Path

import pandas as pd

from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION, validate_analysis_plan_contract
from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence
from data_agent.agent.evidence_compatibility import compare_measurements


TEST_DOC = Path("reference/test_doc")


def test_reference_test_doc_files_exist():
    expected = [
        "游戏Abanner汇总数据.xlsx",
        "游戏A内购数据.xlsx",
        "游戏A激励视频汇总数据报表.xlsx",
        "游戏B留存.xlsx",
        "游戏互推.xlsx",
        "省钱卡用户最近流水_20260511.xlsx",
        "省钱卡订单_20260507.xlsx",
    ]

    missing = [name for name in expected if not (TEST_DOC / name).exists()]

    assert missing == []


def test_real_game_files_can_form_independent_stage3c0b_plan():
    files = [
        ("game_a_banner", "游戏Abanner汇总数据.xlsx"),
        ("game_a_iap", "游戏A内购数据.xlsx"),
        ("game_a_reward_video", "游戏A激励视频汇总数据报表.xlsx"),
    ]
    contracts = [{"dataset": dataset, "id": f"contract_{dataset}", "quality_status": "ready"} for dataset, _ in files]
    for dataset, filename in files:
        df = pd.read_excel(TEST_DOC / filename)
        assert len(df) > 0
        assert len(df.columns) > 0

    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze Game A monetization and ad evidence independently.",
        "method_plan": [
            {
                "step_id": f"step_{dataset}",
                "goal": f"Analyze {dataset} independently.",
                "dataset_inputs": [dataset],
                "combination_mode": "independent",
                "expected_output": f"{dataset} evidence",
                "evidence_requirements": ["row_count"],
            }
            for dataset, _ in files
        ] + [
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified game evidence without joining raw datasets.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "expected_output": "Game A synthesis",
                "evidence_requirements": ["summary"],
                "required_evidence_step_ids": [f"step_{dataset}" for dataset, _ in files],
            }
        ],
    }

    result = validate_analysis_plan_contract(plan, dataset_contracts=contracts)

    assert result.ok is True
    assert all(step["combination_mode"] != "join" for step in result.plan["method_plan"])


def test_mixed_domain_measurements_are_not_forced_into_comparison():
    game_measurement = {
        "metric": "revenue",
        "definition": "sum game purchase amount",
        "value": 100,
        "unit": "CNY",
        "grain": "game_day",
        "population_scope": "game users",
        "time_scope": "full_file",
        "method": "sum(amount)",
        "denominator": 10,
        "limitations": [],
    }
    savings_card_measurement = {
        "metric": "revenue",
        "definition": "sum order amount",
        "value": 100,
        "unit": "CNY",
        "grain": "order",
        "population_scope": "savings card users",
        "time_scope": "full_file",
        "method": "sum(amount)",
        "denominator": 10,
        "limitations": [],
    }

    result = compare_measurements(game_measurement, savings_card_measurement)

    assert result.compatible is False
    assert result.reason_code in {"definition_mismatch", "grain_mismatch", "population_scope_mismatch"}
```

- [ ] **Step 2: Run real-data tests and verify failure or pass**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/test_stage3c0b_real_data_replay.py -q
```

Expected after implementation: PASS. If pandas lacks the Excel engine in the environment, record the exact import error in the verification note and run the same file-existence and contract tests without reading Excel contents.

- [ ] **Step 3: Create verification note**

Create `docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md` with:

```markdown
# Stage 3C0B Verification

Date: 2026-06-29

## Scope

This note records Stage 3C0B implementation verification. It does not approve Stage 3C1A.

## Real Files Used

- `reference/test_doc/游戏Abanner汇总数据.xlsx`
- `reference/test_doc/游戏A内购数据.xlsx`
- `reference/test_doc/游戏A激励视频汇总数据报表.xlsx`
- `reference/test_doc/游戏B留存.xlsx`
- `reference/test_doc/游戏互推.xlsx`
- `reference/test_doc/省钱卡用户最近流水_20260511.xlsx`
- `reference/test_doc/省钱卡订单_20260507.xlsx`

## Commands

This section is filled during Task 10 with the exact command blocks below and
the observed output copied from the terminal.

### Focused Stage 3C0B Suite

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_stage3c0b_sufficiency.py `
  tests/test_stage3c0b_workbench_projection.py `
  tests/test_stage3c0b_real_data_replay.py -q
```

Observed output:

```text
Not run yet. Task 10 records the terminal output after implementation.
```

### Cross-System Regression Suite

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_flow_tools.py `
  tests/test_analysis_entry.py `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py `
  tests/test_task_manager_scope.py `
  tests/test_task_plan_versioning.py `
  tests/test_synthesis_policy.py `
  tests/test_verification_layer.py `
  tests/test_web_workbench_parity.py `
  tests/test_trust_workflow_runtime.py `
  tests/test_trustworthy_workflow_mvp.py -q
```

Observed output:

```text
Not run yet. Task 10 records the terminal output after implementation.
```

### Frontend And Whitespace

Command:

```powershell
node -c src\data_agent\web\static\js\app.js
git diff --check
```

Observed output:

```text
Not run yet. Task 10 records the terminal output after implementation.
```

## Stop Gate

- [ ] every used dataset has at least one task binding
- [ ] independent tasks run without relationship confirmation
- [ ] single-file intent, cleaning, routing, evidence, verification, and output quality show no material regression
- [ ] insufficient evidence triggers more analysis, partial output, or a missing-data explanation rather than forced synthesis
- [ ] optional failure is isolated to related questions
- [ ] all numeric comparisons pass measurement compatibility
- [ ] current task cannot read an unbound dataset
- [ ] historical evidence cannot enter current-plan synthesis
- [ ] prompt and workbench projections stay within budgets
- [ ] real-data case produces independent evidence, partial failure behavior where applicable, and bounded synthesis
- [ ] every workbench suggestion is traceable to evidence or explicitly marked as a next-data/action recommendation
- [ ] no executable compatibility dual path remains for new Stage 3C0B plans

## Result

Record pass, partial, or fail with deviations.
```

- [ ] **Step 4: Commit**

```powershell
git add tests/test_stage3c0b_real_data_replay.py docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md
git commit -m "test: add stage 3c0b real-data replay gate"
```

---

### Task 10: Final Regression, Stop Gate Review, And Handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md`
- Modify: code only for failures discovered by the final verification commands.

- [ ] **Step 1: Run focused Stage 3C0B suite**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_stage3c0b_sufficiency.py `
  tests/test_stage3c0b_workbench_projection.py `
  tests/test_stage3c0b_real_data_replay.py -q
```

Expected: PASS.

- [ ] **Step 2: Run cross-system regression suite**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_flow_tools.py `
  tests/test_analysis_entry.py `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py `
  tests/test_task_manager_scope.py `
  tests/test_task_plan_versioning.py `
  tests/test_synthesis_policy.py `
  tests/test_verification_layer.py `
  tests/test_web_workbench_parity.py `
  tests/test_trust_workflow_runtime.py `
  tests/test_trustworthy_workflow_mvp.py -q
```

Expected: PASS or documented failures unrelated to Stage 3C0B. If a failure touches task projection, evidence, verification, loop quality, or workbench output, fix it before continuing.

- [ ] **Step 3: Run frontend and whitespace checks**

Run:

```powershell
node -c src\data_agent\web\static\js\app.js
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 4: Update verification note with actual evidence**

Edit `docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md`.

For the focused Stage 3C0B suite, replace:

```text
Not run yet. Task 10 records the terminal output after implementation.
```

with the exact pytest output from Step 1.

For the cross-system regression suite, replace the same `Not run yet` sentence
with the exact pytest output from Step 2.

For frontend and whitespace checks, replace the same `Not run yet` sentence with
the exact output from Step 3. If a command emits no text and exits 0, write:

```text
Exit code 0 with no output.
```

If any command times out, record the timeout duration, observed pass/fail
progress, and whether any failure was observed before timeout.

- [ ] **Step 5: Verify no Stage 3C1A implementation slipped in**

Run:

```powershell
rg -n "DataOperationRecord|safe_to_execute|join preflight|many_to_many|operation_id" src tests
```

Expected: no new executable Stage 3C1A implementation. References in historical docs or tests that assert out-of-scope behavior are allowed.

- [ ] **Step 6: Final git status**

Run:

```powershell
git status --short
git log -8 --oneline
```

Expected: only intentional verification-note edits before final commit; recent commits show the Stage 3C0B task sequence.

- [ ] **Step 7: Commit verification note and any final fixes**

```powershell
git add docs/superpowers/plans/2026-06-29-multifile-analysis-stage-3c0b-verification.md
git commit -m "docs: record stage 3c0b verification"
```

- [ ] **Step 8: Handoff summary**

Prepare a final implementation summary containing:

- commits made;
- focused and regression test results;
- real files used from `reference/test_doc`;
- any deviations or environment warnings;
- confirmation that Stage 3C1A is still blocked until the stop gate is reviewed.

Do not claim Stage 3C0B is complete unless the verification note has concrete pass evidence for every stop-gate item.

---

## Plan Self-Review

Spec coverage:

- clean cutover and no executable dual path: Tasks 1, 2, 3, 10;
- canonical plan contract: Tasks 1, 2, 3;
- workflow projection and failed terminal status: Task 2;
- evidence and measurement compatibility: Tasks 4, 5;
- current-task isolation: Task 6;
- sufficiency and synthesis claim strength: Task 7;
- user-value workbench: Task 8;
- real-data verification: Tasks 9, 10.

Implementation risk controls:

- Every behavior change starts with a failing test.
- Every major unit ends with a focused pytest run and commit.
- Final verification uses real data and cross-system regressions.
- Stage 3C1A remains out of scope until the Stage 3C0B stop gate passes.
