# Analysis Execution and Publication Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable uploaded-file analysis by fixing execution contracts, method depth, canonical evidence projection, bounded completion, claim-level publication, and safe live progress as one end-to-end workflow.

**Architecture:** Extend the existing registry, canonical `AnalysisPlan`, `analysis_requirement.v1`, `computation_ref.v1`, `evidence_record.v2`, `final_answer_audit.v1`, and turn budget owners; do not introduce parallel trust authorities. Work proceeds in dependency order so later evidence and publication behavior cannot conceal an earlier calculation, routing, binding, or data-source failure.

**Tech Stack:** Python 3.11+, Pydantic 2, pandas, NumPy, SciPy, statsmodels, scikit-learn, pytest, Flask/SSE, vanilla JavaScript, Windows PowerShell.

## Global Constraints

- Do not modify user-uploaded source files, raw snapshots, historical sessions, or legacy evidence in place.
- `analysis_requirement.v1`, `evidence_record.v2`, and `final_answer_audit.v1` remain the sole readiness, evidence, and publication authorities.
- Every directed or comprehensive analysis turn must receive a server-owned canonical executable plan before its first substantive analytical tool call.
- Automatic evidence projection is allowed only for successful, structured, current-plan computations with exact session, turn, step, dataset-version, claim-key, and requirement identity.
- Free-form Python, failed tools, ambiguous step bindings, and legacy-unbound evidence are never automatically upgraded into trusted evidence.
- A critical requirement receives at most one corrected retry and one declared fallback; the whole turn receives at most one quality-guard continuation.
- Missing evidence projection, citation syntax, or limitation wording must never restart tool execution.
- Completion must end in exactly one of `complete`, `complete_with_limits`, `blocked_by_data`, `blocked_by_tool`, or `budget_limited`.
- Tool-call count is diagnostic only; analysis depth is judged from question-specific coverage and supported claim class.
- Final analytical findings remain buffered until audit; only server-generated method and state narration may stream before publication.
- Progress payloads must not contain raw reasoning, unaudited values, rankings, p-values, significance findings, or causal findings.
- Production assurance mode may be `tiered` or `strict`; there is no production `off` mode and minimum deterministic blockers always run.
- An explicitly named chart dataset must exist; it may never fall back to a different workspace dataset.
- Supported CLI, web, REPL, background, and logging paths must survive Chinese text, emoji, and variation selectors on a simulated CP936/GBK sink.
- Existing confirmation, immutable data-version, causal-claim, context-budget, and chart semantic safeguards must remain authoritative.
- Preserve unrelated untracked `artifacts/` and `tmp/`; tests must use `tmp_path` or another isolated temporary directory.
- Baseline for execution is commit `6af3633` (`docs: refine analysis reliability design`).

---

## File and Ownership Map

| File | Responsibility after this plan |
|---|---|
| `tests/fixtures/analysis_reliability.py` | Canonical privacy-safe 32x21 factor fixture, aggregate-only fixture, and safe replay prompts. |
| `tests/replay_assertions.py` | Deterministic trace assertions for depth, bounded retries, terminal state, evidence, publication, and progress. |
| `src/data_agent/tools/registry.py` | LLM-visible schemas, compatibility aliases, lossless argument normalization, and structured argument failures. |
| `src/data_agent/tools/analysis_flow.py`, `src/data_agent/agent/analysis_plan_contracts.py` | Object-shaped plan input and the existing canonical plan normalization/writer contract. |
| `src/data_agent/tools/task_tools.py` | The one documented task-title compatibility alias. |
| `src/data_agent/tools/_utils.py` | AST validation and normalization rules for preloaded sandbox imports. |
| `src/data_agent/tools/sandbox.py` | Preloaded analytical namespace, exact dataset lookup, structured sandbox outcomes. |
| `src/data_agent/utils/unicode_io.py` | Shared UTF-8 setup and replacement-safe console boundary. |
| `src/data_agent/utils/logging.py`, `src/data_agent/main.py`, `src/data_agent/web/entry.py`, `src/data_agent/agent/repl.py`, `src/data_agent/agent/runner.py` | Shared Unicode-safe console integration across supported launch, background, and logging paths. |
| `src/data_agent/tools/visualization.py` | Exact chart dataset selection and structured ambiguity/not-found errors. |
| `src/data_agent/agent/execution_scope.py` | Eligible dataset scope for exact chart resolution and scoped analysis calls. |
| `src/data_agent/agent/analysis_execution.py` | Orchestration of canonical plan materialization and deterministic tool-to-step binding; it defines no new trust schema. |
| `src/data_agent/agent/analysis_flow_controller.py`, `src/data_agent/agent/analysis_state.py` | Pre-tool envelope scheduling and bounded persisted diagnostics. |
| `src/data_agent/agent/intent.py` | Recognition of factor, association, significance, predictive, and causal wording. |
| `src/data_agent/agent/method_playbooks.py` | Dedicated factor-relationship plan and maximum requested claim class. |
| `src/data_agent/agent/analysis_requirements.py` | Existing canonical requirement compilation and satisfaction semantics used by routing and completion. |
| `src/data_agent/tools/eda.py` | Pairwise association output with effective N and validated p-values. |
| `src/data_agent/tools/statistics.py` | Multivariable inferential association tool with diagnostics and bounded claim class. |
| `src/data_agent/tools/ml.py` | Truthful predictive validation, feature-importance, and limitation output. |
| `src/data_agent/agent/execution_control.py` | Per-requirement recovery accounting, one-turn continuation budget, and five-state completion decision. |
| `src/data_agent/agent/evidence_contracts.py` | Automatic projection of eligible computation refs into validated evidence v2. |
| `src/data_agent/agent/synthesis_policy.py` | Bounded evidence catalog and synthesis policy without analysis-tool restart instructions. |
| `src/data_agent/agent/answer_quality.py` | Exact unique evidence attachment and structure-preserving claim publication. |
| `src/data_agent/agent/loop.py` | Runtime orchestration only: envelope, binding, projection, completion, synthesis, audit, and progress events. |
| `src/data_agent/agent/progress.py` | Allowlisted, server-authored, non-conclusion progress events. |
| `src/data_agent/config.py` | Validated `tiered`/`strict` rollout configuration and feature flags. |
| `src/data_agent/web/blueprints/chat.py` | SSE projection of safe analysis progress. |
| `src/data_agent/web/static/js/app.js` | Visible per-turn progress rendering without exposing buffered findings. |
| `scripts/replay_analysis_reliability.py` | Deterministic replay and optional three-run live-provider acceptance runner. |

---

### Task 1: Canonical Reliability Fixtures and Trace Assertions

**Files:**
- Create: `tests/fixtures/analysis_reliability.py`
- Create: `tests/replay_assertions.py`
- Create: `tests/test_analysis_reliability_fixtures.py`

**Interfaces:**
- Consumes: pandas and ordinary Python dictionaries only.
- Produces: `build_factor_relationship_frame(rows: int = 32) -> pd.DataFrame`, `build_aggregate_payment_frame() -> pd.DataFrame`, `factor_relationship_prompt() -> str`, and `assert_reliable_analysis_trace(trace: list[dict[str, Any]], *, require_inferential_attempt: bool) -> None`.

- [ ] **Step 1: Write the fixture-shape and privacy tests**

```python
from tests.fixtures.analysis_reliability import (
    build_aggregate_payment_frame,
    build_factor_relationship_frame,
    factor_relationship_prompt,
)


def test_factor_fixture_is_deterministic_32_by_21():
    left = build_factor_relationship_frame()
    right = build_factor_relationship_frame()
    assert left.shape == (32, 21)
    assert left.equals(right)
    assert {"目标值", "活跃度", "价格", "渠道", "日期"} <= set(left.columns)


def test_aggregate_fixture_cannot_support_user_profile_claims():
    frame = build_aggregate_payment_frame()
    assert {"日期", "订单数", "收入"} <= set(frame.columns)
    assert not {"user_id", "年龄", "用户消费金额"} & set(frame.columns)


def test_replay_prompt_asks_for_significance_without_claiming_causality():
    prompt = factor_relationship_prompt()
    assert "显著" in prompt
    assert "影响因素" in prompt
    assert "因果" not in prompt
```

- [ ] **Step 2: Run the fixture tests and verify the module is absent**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_reliability_fixtures.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'tests.fixtures.analysis_reliability'`.

- [ ] **Step 3: Implement deterministic fixtures with no copied real-user values**

```python
from __future__ import annotations

import numpy as np
import pandas as pd


def build_factor_relationship_frame(rows: int = 32) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    frame = pd.DataFrame({
        "日期": pd.date_range("2026-01-01", periods=rows, freq="D"),
        "目标值": 80 + 2.4 * index + np.sin(index) * 3,
        "活跃度": 10 + index * 0.8,
        "价格": 30 + (index % 5),
        "渠道": np.where(index % 2 == 0, "自然", "投放"),
        "缺失特征": np.where(index % 7 == 0, np.nan, index / 10),
    })
    for number in range(15):
        frame[f"辅助特征_{number:02d}"] = ((index + number) % (number + 3)).astype(float)
    return frame


def build_aggregate_payment_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "日期": pd.date_range("2026-02-01", periods=14, freq="D"),
        "订单数": [20 + i for i in range(14)],
        "收入": [600 + i * 25 for i in range(14)],
    })


def factor_relationship_prompt() -> str:
    return "请分析哪些因素与目标值存在显著关系，并说明方法、稳定性和局限。"
```

- [ ] **Step 4: Add a reusable trace contract that rejects shallow success**

```python
TERMINAL_STATES = {
    "complete",
    "complete_with_limits",
    "blocked_by_data",
    "blocked_by_tool",
    "budget_limited",
}


def assert_reliable_analysis_trace(
    trace: list[dict[str, object]],
    *,
    require_inferential_attempt: bool,
) -> None:
    codes = [str(event.get("code") or "") for event in trace]
    terminal = [event for event in trace if event.get("completion_state") in TERMINAL_STATES]
    assert len(terminal) == 1
    assert "grain_and_missingness_checked" in codes
    assert "univariate_relationship_checked" in codes
    if require_inferential_attempt:
        assert "multivariable_method_attempted" in codes
    assert "limitations_prepared" in codes
    repeated = [
        event for event in trace
        if int(event.get("same_failure_attempt", 0) or 0) > 2
    ]
    assert repeated == []
```

- [ ] **Step 5: Run and commit the fixture foundation**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_reliability_fixtures.py -q
git diff --check
```

Expected: all fixture tests pass and `git diff --check` exits 0.

Commit:

```powershell
git add tests/fixtures/analysis_reliability.py tests/replay_assertions.py tests/test_analysis_reliability_fixtures.py
git commit -m "test: add analysis reliability replay fixtures"
```

---

### Task 2: Typed Tool Schemas and Lossless Runtime Arguments

**Files:**
- Modify: `src/data_agent/tools/registry.py`
- Modify: `src/data_agent/tools/analysis_flow.py`
- Modify: `src/data_agent/agent/analysis_plan_contracts.py`
- Modify: `src/data_agent/tools/task_tools.py`
- Create: `tests/test_tool_registry_contracts.py`
- Modify: `tests/test_tool_recovery.py`
- Modify: `tests/test_tools_comprehensive.py`

**Interfaces:**
- Consumes: Python call signatures and annotations, including postponed annotations.
- Produces: `normalize_tool_arguments(definition: ToolDefinition, params: Mapping[str, Any]) -> dict[str, Any]`, `validate_tool_definition_contract(definition: ToolDefinition) -> list[dict[str, Any]]`, `ToolArgumentValidationError.to_payload() -> dict[str, Any]`, `ToolDefinition.argument_aliases: dict[str, str]`, `ToolDefinition.compatibility_json_object_parameters: set[str]`, and LLM-visible object input for `record_analysis_plan`.

- [ ] **Step 1: Write schema, normalization, alias, and plan-object tests**

```python
def test_registry_resolves_postponed_integer_annotation():
    definition = registry.get("regression_analysis")
    cv = definition.parameters["properties"]["cv_folds"]
    assert cv["type"] == "integer"
    assert cv["default"] == 0


def test_registry_losslessly_normalizes_integer_and_boolean_strings():
    def sample(count: int, flag: bool = False) -> dict[str, object]:
        return {"count": count, "flag": flag}

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )
    assert normalize_tool_arguments(definition, {"count": "0", "flag": "false"}) == {
        "count": 0,
        "flag": False,
    }


def test_registry_rejects_ambiguous_number_and_unknown_argument():
    def sample(count: int) -> int:
        return count

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )
    with pytest.raises(ToolArgumentValidationError) as exc:
        normalize_tool_arguments(definition, {"count": "1.5", "extra": 1})
    assert exc.value.to_payload()["error_type"] == "invalid_tool_arguments"


def test_task_create_title_alias_is_compatible_but_conflicts_fail():
    assert registry.execute("task_create", {"title": "检查缺失值"}).data is not None
    result = registry.execute(
        "task_create",
        {"subject": "A", "title": "B"},
    )
    assert json.loads(result.summary)["error_type"] == "invalid_tool_arguments"


def test_record_analysis_plan_exposes_object_not_opaque_json_string():
    schema = registry.get("record_analysis_plan").parameters
    assert schema["properties"]["plan"]["type"] == "object"
    assert "plan" in schema["required"]
    assert "plan_json" not in schema["properties"]
```

- [ ] **Step 2: Run the focused tests and capture current failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry_contracts.py tests/test_tool_recovery.py tests/test_tools_comprehensive.py -q
```

Expected: `cv_folds` is reported as `string`; raw string arguments reach tools; the alias and object-plan tests fail.

- [ ] **Step 3: Resolve annotations and generate truthful JSON Schema**

Implement in `registry.py`:

```python
from enum import Enum
from types import UnionType
from typing import Any, Literal, Mapping, Union, get_args, get_origin, get_type_hints


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, UnionType):
        non_none = [arg for arg in args if arg is not type(None)]
        schema = _annotation_schema(non_none[0]) if len(non_none) == 1 else {
            "anyOf": [_annotation_schema(arg) for arg in non_none]
        }
        if len(non_none) != len(args):
            schema["nullable"] = True
        return schema
    if origin is Literal:
        values = list(args)
        return {"type": _python_type_to_json(type(values[0])), "enum": values}
    if origin in (list, tuple, set):
        item = args[0] if args else Any
        return {"type": "array", "items": _annotation_schema(item)}
    if origin is dict:
        value = args[1] if len(args) == 2 else Any
        return {"type": "object", "additionalProperties": _annotation_schema(value)}
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        values = [member.value for member in annotation]
        return {"type": _python_type_to_json(type(values[0])), "enum": values}
    return {"type": _python_type_to_json(annotation)}


def _build_schema(func: Callable) -> dict[str, Any]:
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        properties[name] = _annotation_schema(hints.get(name, str))
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        else:
            properties[name]["default"] = parameter.default
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
```

- [ ] **Step 4: Normalize arguments before hooks and tool execution**

Add `argument_aliases` and `compatibility_json_object_parameters` to `ToolDefinition`, `ToolRegistry.register`, and `ToolRegistry.add`. Implement exact Boolean vocabulary `true/false/1/0/yes/no/on/off`, integer strings matching `^[+-]?\d+$`, finite floats, enum membership, and recursive lists/dictionaries. Reject lossful conversion, unknown keys, missing required keys, and conflicting aliases through:

```python
class ToolArgumentValidationError(ValueError):
    def __init__(self, *, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__("invalid tool arguments")

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "工具参数不符合已声明契约。",
            "error_type": "invalid_tool_arguments",
            "issues": self.issues,
        }
```

Call `normalize_tool_arguments(tool, params)` before before-hooks and return its payload as:

```python
payload = exc.to_payload()
return ToolResult(
    summary=json.dumps(payload, ensure_ascii=False),
    data=payload,
)
```

Do not invoke the tool when validation fails. Register `task_create` with `argument_aliases={"title": "subject"}`.

- [ ] **Step 5: Expose the canonical plan as an object while retaining a hidden compatibility reader**

Change the tool signature and registration to:

```python
@registry.register(
    name="record_analysis_plan",
    description="Save a canonical executable AnalysisPlan.",
    argument_aliases={"plan_json": "plan"},
    compatibility_json_object_parameters={"plan"},
    parameters={
        "type": "object",
        "properties": {
            "plan": analysis_plan_tool_object_schema(),
        },
        "required": ["plan"],
        "additionalProperties": False,
    },
)
def record_analysis_plan(plan: dict[str, Any]) -> str:
    payload = plan
    if not isinstance(payload, dict):
        return json.dumps({
            "error": "plan must be an object",
            "error_type": "invalid_analysis_plan",
        }, ensure_ascii=False)
    return _persist_analysis_plan_payload(payload)
```

Extract the existing normalization, state persistence, artifact write, and workflow projection body into `_persist_analysis_plan_payload(payload: dict[str, Any]) -> str`; object and compatibility paths call this single writer. `analysis_plan_tool_object_schema()` must be defined beside `normalize_analysis_plan_contract` in `analysis_plan_contracts.py` and require `goal`, `method_plan`, and `visualization_strategy`. At the registry boundary, legacy `plan_json="<object JSON>"` is alias-mapped to `plan` and decoded only because `plan` is explicitly listed in `compatibility_json_object_parameters`; ordinary `plan="<string>"`, non-object JSON, conflicts between `plan` and `plan_json`, and every other implicit string-to-object conversion are rejected.

- [ ] **Step 6: Add a registry-wide signature/schema invariant**

```python
def test_every_native_tool_schema_matches_signature():
    registry._ensure_discovered()
    failures = {
        definition.name: validate_tool_definition_contract(definition)
        for definition in registry._tools.values()
        if definition.origin == "native"
        and validate_tool_definition_contract(definition)
    }
    assert failures == {}
```

`normalize_tool_arguments` applies JSON-object decoding only after a compatibility alias mapped the legacy key to an explicitly declared target. `validate_tool_definition_contract` compares visible names, required/default status, normalized annotation schemas, aliases, and compatibility decoders. Allow only `record_analysis_plan.plan_json -> plan`; no other opaque JSON compatibility path is accepted.

- [ ] **Step 7: Run focused suites and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry_contracts.py tests/test_tool_recovery.py tests/test_tools_comprehensive.py tests/test_knowledge_tools_phase2.py -q
.\.venv\Scripts\python.exe -m compileall -q src/data_agent
git diff --check
```

Expected: all tests pass; `regression_analysis.cv_folds` is integer; string `"0"` reaches the function as integer `0`.

Commit:

```powershell
git add src/data_agent/tools/registry.py src/data_agent/tools/analysis_flow.py src/data_agent/agent/analysis_plan_contracts.py src/data_agent/tools/task_tools.py tests/test_tool_registry_contracts.py tests/test_tool_recovery.py tests/test_tools_comprehensive.py
git commit -m "fix: enforce typed tool argument contracts"
```

---

### Task 3: Bounded Sandbox Imports, Dataset Lookup, and Failure Recovery

**Files:**
- Modify: `src/data_agent/tools/_utils.py`
- Modify: `src/data_agent/tools/sandbox.py`
- Modify: `src/data_agent/agent/execution_control.py`
- Create: `tests/test_sandbox_contract.py`
- Modify: `tests/test_tool_recovery.py`
- Modify: `tests/test_stage3c0b_execution_scope.py`

**Interfaces:**
- Consumes: sandbox code string and execution-scope dataset allowlist.
- Produces: `normalize_preloaded_imports(code: str, preloaded: Mapping[str, Any]) -> tuple[str, dict[str, Any]]`, `SandboxContractError.to_payload()`, and a failure fingerprint recorded by `TurnExecutionState`.

- [ ] **Step 1: Write allowlisted import and rejection tests**

```python
@pytest.mark.parametrize("code", [
    "import pandas\nresult = pandas.DataFrame({'x': [1]}).shape",
    "import pandas as frame_lib\nresult = frame_lib.DataFrame({'x': [1]}).shape",
    "from pandas import DataFrame\nresult = DataFrame({'x': [1]}).shape",
    "import numpy\nresult = numpy.mean([1, 2, 3])",
    "from scipy import stats\nresult = stats.pearsonr([1, 2, 3], [1, 2, 4]).statistic",
])
def test_preloaded_import_forms_do_not_call_runtime_import(code):
    payload = json.loads(run_python(code))
    assert payload["success"] is True
    assert "__import__ not found" not in json.dumps(payload)


@pytest.mark.parametrize("code", [
    "import requests",
    "import scipy.optimize",
    "from pandas import *",
    "from pandas import __dict__",
])
def test_unapproved_imports_fail_before_execution(code):
    payload = json.loads(run_python(code))
    assert payload["error_type"] == "sandbox_import_not_allowed"
```

- [ ] **Step 2: Write exact missing-dataset and repeated-failure tests**

```python
def test_get_dataset_missing_name_is_structured_and_never_none(workspace):
    payload = json.loads(run_python("df = get_dataset('missing')\nresult = df['x'].sum()"))
    assert payload["error_type"] == "dataset_not_found"
    assert payload["dataset_reads"] == ["missing"]
    assert payload["allowed_datasets"] == ["orders"]
    assert "NoneType" not in json.dumps(payload)


def test_identical_sandbox_failure_is_blocked_after_first_corrected_retry(turn_state):
    fingerprint = turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    assert turn_state.can_retry_failure(fingerprint) is False
```

- [ ] **Step 3: Run tests and verify current sandbox behavior fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_sandbox_contract.py tests/test_tool_recovery.py tests/test_stage3c0b_execution_scope.py -q
```

Expected: approved imports fail with `__import__ not found`; unknown datasets can cascade through `None`; new structured fields are absent.

- [ ] **Step 4: Normalize imports with AST bindings and no runtime importer**

Implement these exact allowlists:

```python
PRELOADED_IMPORT_ROOTS = {"pandas", "numpy", "math", "statistics", "json"}
PRELOADED_DOTTED_IMPORTS = {"scipy.stats"}


def normalize_preloaded_imports(
    code: str,
    preloaded: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    tree = ast.parse(code, mode="exec")
    bindings: dict[str, Any] = {}
    kept: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _bind_allowlisted_import(node, preloaded, bindings)
        else:
            kept.append(node)
    tree.body = kept
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), bindings
```

`_bind_allowlisted_import` must bind ordinary aliases and public attributes from already loaded module objects. It must reject multi-module import statements containing any unapproved member, relative imports, unapproved dotted modules, `*`, and names beginning `_` with `SandboxContractError(error_type="sandbox_import_not_allowed")`.

- [ ] **Step 5: Make dataset and execution failures structured**

Preload `pd`, `np`, `math`, `statistics`, `json`, and `stats`. Merge normalized alias bindings into safe locals. Replace `_get_dataset` behavior with:

```python
def _get_dataset(name: str) -> pd.DataFrame:
    dataset_reads.append(name)
    frame = workspace.get(name)
    if frame is None:
        raise SandboxContractError(
            error_type="dataset_not_found",
            message=f"数据集 {name!r} 不存在。",
            details={"allowed_datasets": sorted(allowed_dataset_names)},
        )
    return frame
```

Every failure payload must include `success=False`, `error_type`, `message`, `dataset_reads`, `failed_operation`, `allowed_datasets`, and `safe_alternatives`. Remove the unreachable duplicate `return` in `run_python`.

- [ ] **Step 6: Persist the failure fingerprint and enforce bounded recovery**

Extend `TurnExecutionState` with:

```python
requirement_failures: dict[str, dict[str, Any]] = field(default_factory=dict)

def record_requirement_failure(
    self,
    *,
    requirement_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    error_type: str,
) -> str:
    canonical = json.dumps(
        {
            "requirement_id": requirement_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "error_type": error_type,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    entry = self.requirement_failures.setdefault(
        fingerprint,
        {"attempts": 0, "requirement_id": requirement_id, "error_type": error_type},
    )
    entry["attempts"] = int(entry["attempts"]) + 1
    return fingerprint

def can_retry_failure(self, fingerprint: str) -> bool:
    return int(self.requirement_failures.get(fingerprint, {}).get("attempts", 0)) < 2
```

The fingerprint is a stable digest of requirement ID, tool name, normalized arguments, and error type. `can_retry_failure` permits only the initial failure plus one corrected retry; an identical third call is blocked before registry execution. The later completion task will add the one declared fallback budget.

- [ ] **Step 7: Run sandbox and execution-scope suites, then commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_sandbox_contract.py tests/test_tool_recovery.py tests/test_stage3c0b_execution_scope.py tests/test_execution_control.py -q
git diff --check
```

Expected: approved imports execute, prohibited imports remain blocked, missing data never becomes `NoneType`, and repeated identical failures converge.

Commit:

```powershell
git add src/data_agent/tools/_utils.py src/data_agent/tools/sandbox.py src/data_agent/agent/execution_control.py tests/test_sandbox_contract.py tests/test_tool_recovery.py tests/test_stage3c0b_execution_scope.py
git commit -m "fix: make sandbox execution bounded and recoverable"
```

---

### Task 4: Shared Unicode-Safe Process Boundary

**Files:**
- Create: `src/data_agent/utils/unicode_io.py`
- Modify: `src/data_agent/utils/logging.py`
- Modify: `src/data_agent/main.py`
- Modify: `src/data_agent/web/entry.py`
- Modify: `src/data_agent/agent/repl.py`
- Modify: `src/data_agent/agent/runner.py`
- Create: `tests/test_unicode_io.py`
- Modify: `tests/test_suspension_encoding.py`

**Interfaces:**
- Consumes: text streams that may be UTF-8, CP936, or non-reconfigurable.
- Produces: `configure_utf8_stdio(stdout: TextIO | None = None, stderr: TextIO | None = None) -> tuple[TextIO, TextIO]` and `ReplacementSafeTextStream`.

- [ ] **Step 1: Write CP936, early-captured logger, and launcher tests**

```python
def test_replacement_safe_stream_survives_emoji_and_variation_selector():
    raw = io.BytesIO()
    cp936 = io.TextIOWrapper(raw, encoding="cp936", errors="strict")
    safe = ReplacementSafeTextStream(cp936)
    safe.write("分析中 ⚠️ 中文标点：完成")
    safe.flush()
    assert raw.getvalue()


def test_logger_captured_before_reconfigure_cannot_abort_turn():
    raw = io.BytesIO()
    captured = io.TextIOWrapper(raw, encoding="cp936", errors="strict")
    handler = build_console_handler(stream=captured)
    handler.emit(_record("进度 ⚠️"))
    assert raw.getvalue()


@pytest.mark.parametrize("module_name", [
    "data_agent.main",
    "data_agent.web.entry",
    "data_agent.agent.repl",
])
def test_supported_launcher_uses_shared_utf8_helper(module_name):
    source = inspect.getsource(importlib.import_module(module_name))
    assert "configure_utf8_stdio" in source
```

- [ ] **Step 2: Run tests and observe current duplicated boundary**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_unicode_io.py tests/test_suspension_encoding.py -q
```

Expected: the simulated CP936 write raises `UnicodeEncodeError`; shared helper assertions fail.

- [ ] **Step 3: Implement reconfigure-first and replacement-safe fallback**

```python
class ReplacementSafeTextStream:
    def __init__(self, stream: TextIO):
        self._stream = stream

    def write(self, text: str) -> int:
        try:
            return self._stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self._stream, "encoding", None) or "utf-8"
            safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            return self._stream.write(safe)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def configure_utf8_stdio(
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> tuple[TextIO, TextIO]:
    configured = []
    for stream in (stdout or sys.stdout, stderr or sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
            configured.append(stream)
        except (AttributeError, OSError, ValueError):
            configured.append(ReplacementSafeTextStream(stream))
    return configured[0], configured[1]
```

- [ ] **Step 4: Route launchers, logging, and background runner through the helper**

Replace the three duplicated `reconfigure` blocks with one call. Make `build_console_handler(stream: TextIO | None = None)` wrap its resolved stream with `ReplacementSafeTextStream` so a logger captured before launcher setup is still safe. In `runner.py`, ensure status/error writes use the safe logger and do not catch-and-rethrow `UnicodeEncodeError` originating only from console emission.

- [ ] **Step 5: Verify Unicode preservation and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_unicode_io.py tests/test_suspension_encoding.py tests/test_utf8_roundtrip.py -q
.\.venv\Scripts\python.exe -m compileall -q src/data_agent
git diff --check
```

Expected: browser/persistence-facing strings remain unchanged Unicode; only an unrepresentable console sink replaces glyphs.

Commit:

```powershell
git add src/data_agent/utils/unicode_io.py src/data_agent/utils/logging.py src/data_agent/main.py src/data_agent/web/entry.py src/data_agent/agent/repl.py src/data_agent/agent/runner.py tests/test_unicode_io.py tests/test_suspension_encoding.py
git commit -m "fix: harden unicode output boundaries"
```

---

### Task 5: Exact Chart Dataset Identity

**Files:**
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `src/data_agent/agent/execution_scope.py`
- Modify: `tests/test_chart_contract.py`
- Modify: `tests/test_stage3c0b_execution_scope.py`

**Interfaces:**
- Consumes: explicit `data`, optional `data_json`, active execution scope, and workspace datasets.
- Produces: `resolve_chart_dataset(data: str, data_json: str, eligible_names: Sequence[str]) -> ChartDatasetResolution` with error types `chart_dataset_not_found` and `chart_dataset_ambiguous`.

- [ ] **Step 1: Write explicit-missing and omitted-ambiguous tests**

```python
def test_explicit_unknown_chart_dataset_never_falls_back(tmp_path):
    workspace.add("orders", pd.DataFrame({"x": [1], "y": [2]}))
    payload = json.loads(create_chart(data="missing", chart_type="bar", x="x", y="y"))
    assert payload["error_type"] == "chart_dataset_not_found"
    assert payload["requested_dataset"] == "missing"


def test_omitted_chart_dataset_requires_one_eligible_dataset(tmp_path):
    workspace.add("orders", pd.DataFrame({"x": [1], "y": [2]}))
    workspace.add("users", pd.DataFrame({"x": [1], "y": [3]}))
    payload = json.loads(create_chart(chart_type="bar", x="x", y="y"))
    assert payload["error_type"] == "chart_dataset_ambiguous"
    assert payload["eligible_datasets"] == ["orders", "users"]
```

- [ ] **Step 2: Run focused tests and confirm the fallback bug**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_stage3c0b_execution_scope.py -q
```

Expected: an explicit unknown name can select the main/largest dataset; omitted multi-dataset behavior is not a structured ambiguity.

- [ ] **Step 3: Implement one resolver with exact branching**

```python
@dataclass(frozen=True)
class ChartDatasetResolution:
    ok: bool
    dataset_name: str = ""
    error_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def resolve_chart_dataset(
    *,
    data: str,
    data_json: str,
    eligible_names: Sequence[str],
) -> ChartDatasetResolution:
    names = sorted(set(eligible_names))
    if data_json:
        return ChartDatasetResolution(ok=True, dataset_name="__inline__")
    if data:
        if data not in names:
            return ChartDatasetResolution(
                ok=False,
                error_type="chart_dataset_not_found",
                details={"requested_dataset": data, "eligible_datasets": names},
            )
        return ChartDatasetResolution(ok=True, dataset_name=data)
    if len(names) == 1:
        return ChartDatasetResolution(ok=True, dataset_name=names[0])
    return ChartDatasetResolution(
        ok=False,
        error_type="chart_dataset_ambiguous",
        details={"eligible_datasets": names},
    )
```

Call this resolver before reading any frame. Execution scope supplies `eligible_names`; inactive scope supplies all current workspace names. Remove the main/largest fallback for explicit or ambiguous inputs.

- [ ] **Step 4: Run chart suites and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_stage3c0b_execution_scope.py -q
git diff --check
```

Expected: exact and single-default paths pass; unknown and ambiguous paths return structured errors without opening another frame.

Commit:

```powershell
git add src/data_agent/tools/visualization.py src/data_agent/agent/execution_scope.py tests/test_chart_contract.py tests/test_stage3c0b_execution_scope.py
git commit -m "fix: preserve exact chart dataset identity"
```

---

### Task 6: Server-Owned Canonical Execution Envelope

**Files:**
- Create: `src/data_agent/agent/analysis_execution.py`
- Modify: `src/data_agent/agent/analysis_plan_contracts.py`
- Modify: `src/data_agent/agent/analysis_flow_controller.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/agent/loop.py`
- Create: `tests/test_analysis_execution_envelope.py`
- Modify: `tests/test_method_playbooks.py`
- Modify: `tests/test_stage3c0b_execution_scope.py`
- Modify: `tests/test_execution_control.py`

**Interfaces:**
- Consumes: current `AnalysisSessionState`, `TurnIntent`, selected playbook plan, active dataset contracts, and tool capability metadata.
- Produces: `EnvelopeResult`, `StepBindingResult`, `ensure_canonical_execution_envelope(state: AnalysisSessionState, intent: TurnIntent, user_input: str, active_dataset_contracts: list[dict[str, Any]]) -> EnvelopeResult`, and `bind_tool_call_to_plan_step(plan: dict[str, Any], tool_name: str, capability: dict[str, Any] | None, dataset_names: Sequence[str], preferred_step_id: str = "") -> StepBindingResult`; all persisted plans still pass through `normalize_analysis_plan_contract`.

- [ ] **Step 1: Write an ad-hoc plan and exact-binding test**

```python
def test_directed_turn_gets_executable_envelope_without_model_plan(state, intent):
    result = ensure_canonical_execution_envelope(
        state=state,
        intent=intent,
        user_input="分析哪些因素与目标值显著相关",
        active_dataset_contracts=[dataset_contract("factors", version="v1")],
    )
    assert result.ok is True
    assert result.plan["review_status"] == "executable"
    assert result.plan["id"].startswith("plan_")
    assert all(step["dataset_inputs"] == ["factors"] for step in result.plan["method_plan"])
    assert all(step["requirement_ids"] for step in result.plan["method_plan"])


def test_single_compatible_pending_step_binds_deterministically(envelope):
    binding = bind_tool_call_to_plan_step(
        plan=envelope.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is True
    assert binding.claim_key
    assert binding.requirement_ids
```

- [ ] **Step 2: Write ambiguity and envelope-failure tests**

```python
def test_ambiguous_step_binding_remains_computation_only(envelope_with_two_matches):
    binding = bind_tool_call_to_plan_step(
        plan=envelope_with_two_matches.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is False
    assert binding.error_type == "ambiguous_analysis_step"
    assert sorted(binding.candidate_step_ids) == ["step_association_a", "step_association_b"]


def test_envelope_failure_cannot_report_complete(state):
    result = ensure_canonical_execution_envelope(
        state=state,
        intent=directed_intent(),
        user_input="分析显著影响因素",
        active_dataset_contracts=[],
    )
    assert result.ok is False
    assert result.error_type == "analysis_dataset_identity_missing"
    assert state.analysis_plan == {}
```

- [ ] **Step 3: Run tests and verify display-only/ad-hoc gaps**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_execution_envelope.py tests/test_method_playbooks.py tests/test_stage3c0b_execution_scope.py -q
```

Expected: generated playbook plans remain `display_only`; ad-hoc calls lack plan/step identity; no deterministic binder exists.

- [ ] **Step 4: Implement orchestration types without defining a new plan schema**

```python
@dataclass(frozen=True)
class EnvelopeResult:
    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    current_step_id: str = ""
    error_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepBindingResult:
    ok: bool
    plan_id: str = ""
    step_id: str = ""
    claim_key: str = ""
    requirement_ids: tuple[str, ...] = ()
    error_type: str = ""
    candidate_step_ids: tuple[str, ...] = ()
```

`ensure_canonical_execution_envelope` takes the selected playbook plan, injects the one active dataset name/version into each executable analytical step, preserves route requirement inputs, and calls:

```python
validation = normalize_analysis_plan_contract(
    candidate,
    require_executable=True,
    dataset_contracts=active_dataset_contracts,
)
```

It persists only `validation.plan` through `state.set_analysis_plan`. It must not mint evidence, reinterpret a failed plan after computation, or create a second requirement evaluator.

- [ ] **Step 5: Implement current-step-or-single-compatible binding**

`bind_tool_call_to_plan_step` filters by current/pending status, dataset inputs, capability ID/problem type, and step expected output. It binds the preferred current step when compatible; otherwise it binds exactly one compatible pending step. Zero candidates returns `analysis_step_not_found`; multiple candidates returns `ambiguous_analysis_step`.

Change the persistence method signature to `def _compact_tool_output(self, tool_result: ToolResult, tc: ToolCall, step_binding: StepBindingResult | None = None) -> str`. Retain its existing artifact compaction behavior, but source `plan_id`, `step_id`, `claim_key`, and `requirement_ids` only from the supplied successful binding.

The computation ref uses binding plan/step IDs. An unsuccessful binding still persists a computation ref with empty step identity plus the structured diagnostic; it never invents identity later.

- [ ] **Step 6: Materialize the envelope before the first substantive call**

In `AnalysisFlowController.prepare_turn`, after route/playbook selection and before workflow task projection, call `ensure_canonical_execution_envelope` for `directed_analysis` and `comprehensive_report` when current dataset contracts exist. In both synchronous and streaming tool paths, bind every substantive analytical call before registry execution and pass the result into persistence. Explicit executable `record_analysis_plan` output may replace the auto envelope before the first substantive call, but not after a computation has been bound to it.

- [ ] **Step 7: Persist bounded turn diagnostics**

Add to `AnalysisSessionState`:

```python
turn_diagnostics: list[dict[str, Any]] = field(default_factory=list)

def append_turn_diagnostic(self, diagnostic: dict[str, Any], *, limit: int = 20) -> None:
    self.turn_diagnostics = (self.turn_diagnostics + [diagnostic])[-limit:]
```

Record envelope creation/failure, plan ID, step binding/failure, dataset versions, and tool-call ID; do not store raw rows or unbounded tool output.

- [ ] **Step 8: Run envelope, plan, scope, and loop suites, then commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_execution_envelope.py tests/test_method_playbooks.py tests/test_analysis_requirements.py tests/test_stage3c0b_execution_scope.py tests/test_execution_control.py -q
git diff --check
```

Expected: directed ad-hoc turns receive executable plans; exact unique matching binds; ambiguity stays untrusted and diagnostic.

Commit:

```powershell
git add src/data_agent/agent/analysis_execution.py src/data_agent/agent/analysis_plan_contracts.py src/data_agent/agent/analysis_flow_controller.py src/data_agent/agent/analysis_state.py src/data_agent/agent/loop.py tests/test_analysis_execution_envelope.py tests/test_method_playbooks.py tests/test_stage3c0b_execution_scope.py tests/test_execution_control.py
git commit -m "feat: materialize canonical analysis execution envelopes"
```

---

### Task 7: Factor-Relationship Route and Truthful Analytical Capabilities

**Files:**
- Modify: `src/data_agent/agent/intent.py`
- Modify: `src/data_agent/agent/method_playbooks.py`
- Modify: `src/data_agent/agent/analysis_requirements.py`
- Modify: `src/data_agent/tools/registry.py`
- Modify: `src/data_agent/tools/eda.py`
- Modify: `src/data_agent/tools/statistics.py`
- Modify: `src/data_agent/tools/ml.py`
- Create: `tests/test_factor_relationship_route.py`
- Create: `tests/test_tool_capability_truthfulness.py`
- Modify: `tests/test_intent_classification.py`
- Modify: `tests/test_method_playbooks.py`
- Modify: `tests/test_analysis_requirements.py`

**Interfaces:**
- Consumes: factor/significance language, data structure, and current analytical tools.
- Produces: playbook ID `factor_relationship`, claim classes `exploratory_association`, `inferential_association`, `predictive_importance`, and `causal_effect`, `validate_capability_output(capability: Mapping[str, Any], payload: Mapping[str, Any]) -> list[str]`, plus structured analytical outputs whose declared evidence fields exist.

- [ ] **Step 1: Write route-separation and claim-class tests**

```python
@pytest.mark.parametrize("text", [
    "哪些因素显著影响目标值？",
    "哪些变量与收入相关？",
    "find factors associated with conversion",
])
def test_factor_questions_select_factor_relationship_not_period_driver(text):
    intent = classify_intent(text, data_loaded=True)
    selection = select_playbooks(text, intent=intent)
    assert selection.primary_id == "factor_relationship"
    assert selection.primary_id != "driver_decomposition"


def test_significance_plan_contains_required_depth_and_no_causal_upgrade():
    plan = build_plan("哪些因素显著影响目标值", dataset="factors")
    codes = [step["analysis_code"] for step in plan["method_plan"]]
    assert codes == [
        "grain_and_missingness_checked",
        "univariate_relationship_checked",
        "multivariable_method_attempted",
        "stability_and_dependence_checked",
        "effect_or_contribution_estimated",
        "limitations_prepared",
    ]
    assert plan["maximum_claim_class"] == "inferential_association"
```

- [ ] **Step 2: Write structured-output and capability-truth tests**

```python
def test_correlation_emits_effective_n_and_validated_p_value(workspace):
    payload = json.loads(correlation_analysis("factors", "目标值,活跃度"))
    pair = payload["pairs"][0]
    assert {"var1", "var2", "correlation", "effective_sample_size", "p_value"} <= set(pair)
    assert payload["allowed_claim_class"] == "exploratory_association"


def test_factor_relationship_emits_inferential_diagnostics(workspace):
    payload = json.loads(factor_relationship_analysis(
        "factors",
        target_col="目标值",
        features="活跃度,价格",
        time_col="日期",
    ))
    coefficient = payload["coefficients"][0]
    assert {"estimate", "std_error", "confidence_interval", "p_value", "adjusted_p_value"} <= set(coefficient)
    assert {"effective_sample_size", "collinearity", "time_dependence", "limitations"} <= set(payload)
    assert payload["allowed_claim_class"] == "inferential_association"


@pytest.mark.parametrize(("tool_name", "arguments"), [
    ("correlation_analysis", {"name": "factors", "columns": "目标值,活跃度"}),
    ("factor_relationship_analysis", {
        "name": "factors",
        "target_col": "目标值",
        "features": "活跃度,价格",
        "time_col": "日期",
    }),
    ("regression_analysis", {
        "name": "factors",
        "target_col": "目标值",
        "features": "活跃度,价格",
    }),
    ("attribution_analysis", {
        "name": "factors",
        "target_col": "目标值",
        "features": "活跃度,价格",
    }),
])
def test_declared_evidence_fields_exist_in_representative_output(tool_name, arguments):
    result = registry.execute(tool_name, arguments)
    payload = json.loads(result.summary)
    capability = registry.capability_for(tool_name)
    assert validate_capability_output(capability, payload) == []
```

- [ ] **Step 3: Run route and tool tests and capture shallow/current mismatches**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_factor_relationship_route.py tests/test_tool_capability_truthfulness.py tests/test_intent_classification.py tests/test_method_playbooks.py tests/test_analysis_requirements.py -q
```

Expected: factor wording selects period decomposition or generic analysis; correlation lacks p-value/N; capability metadata advertises absent fields.

- [ ] **Step 4: Add the dedicated playbook and compile method-specific requirements**

Add `_FACTOR_RELATIONSHIP_KEYWORDS` including `影响因素`, `显著影响`, `驱动因素`, `相关因素`, `associated factors`, and `significant factors`. Preserve priority so explicit time-period change wording still selects `driver_decomposition`.

Define `PLAYBOOKS["factor_relationship"]` with six steps matching the test order. Requirement compiler inputs must include:

```python
[
    "grain_definition",
    "target_definition",
    "missingness_assessment",
    "effective_sample_size",
    "univariate_association",
    "multivariable_adjustment",
    "multiplicity_control",
    "collinearity_assessment",
    "stability_or_validation",
    "time_dependence_assessment",
    "effect_size_or_predictive_contribution",
    "limitations_and_alternatives",
]
```

The compiler marks inferential requirements required only when inferential wording is present. Predictive wording sets `maximum_claim_class="predictive_importance"`; explicit causal wording continues through the existing high-risk confirmation and causal-design requirements.

- [ ] **Step 5: Make pairwise correlation output statistically truthful**

Replace matrix-only summary logic with per-pair results calculated on pairwise-complete rows. Use `scipy.stats.pearsonr`, `spearmanr`, or `kendalltau` as selected. Emit:

```python
{
    "method": method,
    "pairs": [{
        "var1": c1,
        "var2": c2,
        "correlation": float(statistic),
        "effective_sample_size": int(len(pair)),
        "p_value": float(p_value),
    }],
    "multiplicity": {
        "strategy": "none",
        "reason": "pairwise exploratory screen; multivariable tool applies correction",
    },
    "allowed_claim_class": "exploratory_association",
    "limitations": ["相关关系不等于因果关系。"],
}
```

Return a structured insufficient-data error for fewer than three pairwise-complete observations.

- [ ] **Step 6: Add a multivariable inferential association tool**

Register in `statistics.py`:

```python
def factor_relationship_analysis(
    name: str,
    target_col: str,
    features: str = "",
    time_col: str = "",
    alpha: float = 0.05,
    correction: Literal["fdr_bh", "holm", "none"] = "fdr_bh",
) -> str:
    return json.dumps(
        _fit_factor_relationship(
            name=name,
            target_col=target_col,
            features=features,
            time_col=time_col,
            alpha=alpha,
            correction=correction,
        ),
        ensure_ascii=False,
        indent=2,
    )
```

Implement `_fit_factor_relationship(*, name: str, target_col: str, features: str, time_col: str, alpha: float, correction: str) -> dict[str, Any]` in the same module. Use statsmodels OLS for a numeric target, one-hot encode public low-cardinality categorical features, drop rows only for required columns, and report excluded features. Use heteroskedasticity-robust HC3 covariance by default; when an ordered time column is supplied, use a documented HAC lag rule and report it. Emit effective sample size, coefficient estimates, robust standard errors, confidence intervals, raw and adjusted p-values, R-squared/adjusted R-squared, VIF or exact collinearity failure, residual/time-dependence diagnostic, encoding map, correction method, limitations, and `allowed_claim_class="inferential_association"`. If design or sample structure is insufficient, return `complete_with_limits`-compatible diagnostics rather than silently switching to causal language.

- [ ] **Step 7: Correct predictive tool outputs and capability metadata**

`regression_analysis` and `attribution_analysis` must emit `effective_sample_size`, train/test or cross-validation details, `allowed_claim_class="predictive_importance"`, and explicit limitations. They must not advertise coefficient significance or causal impact. Update `DEFAULT_TOOL_CAPABILITIES` so each `evidence_fields` entry is a dotted field present in a successful payload; declare `factor_relationship_analysis` as the inferential association capability and provide only a method-appropriate fallback. Implement `validate_capability_output` in `registry.py` by resolving each dotted evidence field through nested mappings and returning the missing field names; Task 9 reuses this function before projection.

- [ ] **Step 8: Run analytical suites and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_factor_relationship_route.py tests/test_tool_capability_truthfulness.py tests/test_intent_classification.py tests/test_method_playbooks.py tests/test_analysis_requirements.py tests/test_tools_comprehensive.py tests/test_golden_scenarios.py -q
git diff --check
```

Expected: factor requests follow the six-step plan, significance has a real inferential method or exact downgrade, and all declared evidence fields are present.

Commit:

```powershell
git add src/data_agent/agent/intent.py src/data_agent/agent/method_playbooks.py src/data_agent/agent/analysis_requirements.py src/data_agent/tools/registry.py src/data_agent/tools/eda.py src/data_agent/tools/statistics.py src/data_agent/tools/ml.py tests/test_factor_relationship_route.py tests/test_tool_capability_truthfulness.py tests/test_intent_classification.py tests/test_method_playbooks.py tests/test_analysis_requirements.py
git commit -m "feat: add truthful factor relationship analysis"
```

---

### Task 8: Requirement-Based Bounded Completion

**Files:**
- Modify: `src/data_agent/agent/execution_control.py`
- Modify: `src/data_agent/agent/analysis_requirements.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/agent/loop.py`
- Create: `tests/test_analysis_completion.py`
- Modify: `tests/test_execution_control.py`
- Modify: `tests/test_comprehensive_analysis_flow.py`
- Modify: `tests/test_analysis_quality.py`

**Interfaces:**
- Consumes: canonical requirements, computation refs, evidence records, per-requirement tool outcomes, and turn budget.
- Produces: `CompletionDecision`, `evaluate_analysis_completion(plan: dict[str, Any], requirements: Sequence[dict[str, Any]], computation_refs: Sequence[dict[str, Any]], evidence_records: Sequence[dict[str, Any]], tool_outcomes: Sequence[dict[str, Any]], turn_state: TurnExecutionState, budget_exhausted: bool) -> CompletionDecision`, `TurnExecutionState.consume_quality_continuation(reason: str) -> bool`, and per-requirement corrected-retry/fallback accounting.

- [ ] **Step 1: Write five terminal-state tests**

```python
@pytest.mark.parametrize(("fixture_name", "expected"), [
    ("all_satisfied", "complete"),
    ("inferential_unattainable_but_exploratory_success", "complete_with_limits"),
    ("missing_required_columns", "blocked_by_data"),
    ("critical_tool_and_fallback_failed", "blocked_by_tool"),
    ("execution_budget_exhausted", "budget_limited"),
])
def test_completion_returns_one_terminal_state(fixture_name, expected, request):
    decision = evaluate_analysis_completion(**request.getfixturevalue(fixture_name))
    assert decision.status == expected
    assert decision.is_terminal is True
```

- [ ] **Step 2: Write convergence and execution/publication separation tests**

```python
def test_missing_projection_never_requests_another_tool(completed_computation_case):
    decision = evaluate_analysis_completion(
        **completed_computation_case,
        evidence_records=[],
    )
    assert decision.status == "complete_with_limits"
    assert decision.allow_analysis_continuation is False


def test_quality_guard_allows_only_one_recoverable_continuation(turn_state):
    assert turn_state.consume_quality_continuation(reason="missing_multivariable_method") is True
    assert turn_state.consume_quality_continuation(reason="missing_stability_check") is False


def test_one_substantive_tool_does_not_complete_six_step_factor_plan(factor_plan):
    case = factor_completion_case(
        plan=factor_plan,
        computation_refs=[successful_profile_ref()],
        evidence_records=[],
        tool_outcomes=[successful_tool_outcome("profile_data")],
        budget_exhausted=False,
    )
    decision = evaluate_analysis_completion(**case)
    assert decision.status != "complete"
    assert "req_multivariable_adjustment" in decision.unmet_requirement_ids
```

- [ ] **Step 3: Run tests and verify the one-tool shortcut**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_completion.py tests/test_execution_control.py tests/test_comprehensive_analysis_flow.py tests/test_analysis_quality.py -q
```

Expected: no completion model exists; the current guard treats one substantive tool as sufficient.

- [ ] **Step 4: Define the decision as an orchestration result over canonical requirements**

```python
CompletionStatus = Literal[
    "complete",
    "complete_with_limits",
    "blocked_by_data",
    "blocked_by_tool",
    "budget_limited",
]


@dataclass(frozen=True)
class CompletionDecision:
    status: CompletionStatus
    is_terminal: bool
    supported_claim_class: str
    satisfied_requirement_ids: tuple[str, ...]
    unmet_requirement_ids: tuple[str, ...]
    recoverable_requirement_ids: tuple[str, ...]
    allow_analysis_continuation: bool
    reason_code: str
    diagnostics: tuple[dict[str, Any], ...]
```

`evaluate_analysis_completion` must call `evaluate_requirement_satisfaction`; it may not reimplement requirement semantics. It separately derives execution obligations from tool/computation outcomes and publication obligations from projection/limitation readiness.

- [ ] **Step 5: Enforce per-requirement retry and fallback limits**

Extend `TurnExecutionState` with:

```python
requirement_recovery: dict[str, dict[str, int]] = field(default_factory=dict)
analysis_continuations_used: int = 0
```

Add these methods:

```python
def can_correct_requirement(self, requirement_id: str) -> bool:
    return int(self.requirement_recovery.get(requirement_id, {}).get("corrected_retry", 0)) < 1

def record_corrected_retry(self, requirement_id: str) -> None:
    entry = self.requirement_recovery.setdefault(requirement_id, {})
    entry["corrected_retry"] = int(entry.get("corrected_retry", 0)) + 1

def can_use_fallback(self, requirement_id: str) -> bool:
    return int(self.requirement_recovery.get(requirement_id, {}).get("fallback", 0)) < 1

def record_fallback(self, requirement_id: str) -> None:
    entry = self.requirement_recovery.setdefault(requirement_id, {})
    entry["fallback"] = int(entry.get("fallback", 0)) + 1

def consume_quality_continuation(self, *, reason: str) -> bool:
    if self.analysis_continuations_used >= 1:
        return False
    self.analysis_continuations_used += 1
    self.budget_diagnostics["quality_continuation_reason"] = reason
    return True
```

Each requirement permits counts `corrected_retry <= 1` and `fallback <= 1`; the turn permits `analysis_continuations_used <= 1`. The loop must call `consume_quality_continuation` only when a missing hard computation is still recoverable and synthesis/audit token reserves remain intact.

- [ ] **Step 6: Replace the substantive-tool guard in the loop**

Replace `_is_analysis_quality_guard_candidate` with completion evaluation before synthesis. A decision with `allow_analysis_continuation=True` injects one targeted instruction naming the missing requirement and allowed capability/fallback. All five terminal statuses proceed to synthesis. Evidence/catalog/wording failures always proceed to synthesis and never reactivate tools.

Persist the compact decision and recovery counters through `append_turn_diagnostic`; never store the full prompt or raw result.

- [ ] **Step 7: Run completion and low-budget suites, then commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_completion.py tests/test_execution_control.py tests/test_comprehensive_analysis_flow.py tests/test_analysis_quality.py tests/real_data/test_context_budget_degradation.py -q
git diff --check
```

Expected: every scenario reaches one terminal state, shallow traces do not report complete, and low budget produces `budget_limited` without stronger wording.

Commit:

```powershell
git add src/data_agent/agent/execution_control.py src/data_agent/agent/analysis_requirements.py src/data_agent/agent/analysis_state.py src/data_agent/agent/loop.py tests/test_analysis_completion.py tests/test_execution_control.py tests/test_comprehensive_analysis_flow.py tests/test_analysis_quality.py
git commit -m "feat: make analysis completion requirement based"
```

---

### Task 9: Automatic Structured Evidence Projection and Catalog

**Files:**
- Modify: `src/data_agent/agent/evidence_contracts.py`
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/agent/answer_quality.py`
- Modify: `src/data_agent/agent/loop.py`
- Create: `tests/test_automatic_evidence_projection.py`
- Modify: `tests/test_stage3c0b_evidence_contracts.py`
- Modify: `tests/test_final_answer_claim_audit.py`
- Modify: `tests/test_execution_control.py`

**Interfaces:**
- Consumes: successful computation ref, exact step binding, current plan, current dataset contracts, and truthful tool capability.
- Produces: `EvidenceProjectionResult`, the exact `project_structured_computation_evidence` signature in Step 4, `build_bounded_evidence_catalog(evidence_records: Sequence[dict[str, Any]], max_records: int = 12, max_chars: int = 6000) -> str`, and `attach_unique_exact_evidence_ids(claims: Sequence[dict[str, Any]], evidence_records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]`.

- [ ] **Step 1: Write eligible, ineligible, and ad-hoc projection tests**

```python
def test_bound_structured_computation_auto_projects_v2_evidence(context):
    result = project_structured_computation_evidence(
        computation_ref=structured_correlation_ref(),
        binding=exact_step_binding(),
        plan=current_plan(),
        capability=correlation_capability(),
        dataset_contracts=current_dataset_contracts(),
        current_session_id=context.session_id,
        current_turn_id=context.turn_id,
        sessions_root=context.sessions_root,
    )
    assert result.projected is True
    assert result.record["contract_version"] == "evidence_record.v2"
    assert result.record["plan_id"] == current_plan()["id"]
    assert result.record["requirement_ids"] == list(exact_step_binding().requirement_ids)


@pytest.mark.parametrize("ref,binding,reason", [
    (failed_ref(), exact_step_binding(), "computation_failed"),
    (free_form_python_ref(), exact_step_binding(), "unstructured_tool"),
    (structured_correlation_ref(), ambiguous_binding(), "ambiguous_analysis_step"),
    (stale_dataset_ref(), exact_step_binding(), "stale_dataset_version"),
])
def test_ineligible_computation_stays_computation_only(
    projection_context,
    ref,
    binding,
    reason,
):
    result = project_structured_computation_evidence(
        computation_ref=ref,
        binding=binding,
        plan=projection_context.plan,
        capability=projection_context.capability,
        dataset_contracts=projection_context.dataset_contracts,
        current_session_id=projection_context.session_id,
        current_turn_id=projection_context.turn_id,
        sessions_root=projection_context.sessions_root,
    )
    assert result.projected is False
    assert result.reason == reason
```

- [ ] **Step 2: Write catalog and exact-unique matcher tests**

```python
def test_empty_evidence_still_injects_catalog_header():
    catalog = build_bounded_evidence_catalog([], max_records=8, max_chars=2000)
    assert "可用证据：0 条" in catalog
    assert "不要重新运行工具来制造证据" in catalog


def test_exact_unique_match_attaches_existing_id_only():
    claims = [{"text": "收入增长 12%", "value": 12, "unit": "%", "direction": "increase"}]
    bound = attach_unique_exact_evidence_ids(claims, [matching_evidence("ev_1")])
    assert bound[0]["evidence_ids"] == ["ev_1"]


def test_zero_or_multiple_matches_never_guess():
    claims = [{"text": "收入增长 12%", "value": 12, "unit": "%", "direction": "increase"}]
    assert attach_unique_exact_evidence_ids(claims, []) == claims
    assert attach_unique_exact_evidence_ids(
        claims,
        [matching_evidence("ev_1"), matching_evidence("ev_2")],
    ) == claims
```

- [ ] **Step 3: Run tests and confirm the evidence chicken-and-egg**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_automatic_evidence_projection.py tests/test_stage3c0b_evidence_contracts.py tests/test_final_answer_claim_audit.py tests/test_execution_control.py -q
```

Expected: successful computation refs do not create evidence; empty evidence prevents useful catalog injection; final claims require model-authored IDs.

- [ ] **Step 4: Project only exact, structured, current computations**

Add the result type:

```python
@dataclass(frozen=True)
class EvidenceProjectionResult:
    projected: bool
    record: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    diagnostics: tuple[dict[str, Any], ...] = ()
```

Implement `project_structured_computation_evidence(*, computation_ref: dict[str, Any], binding: StepBindingResult, plan: dict[str, Any], capability: dict[str, Any] | None, dataset_contracts: list[dict[str, Any]], current_session_id: str, current_turn_id: str, sessions_root: Path) -> EvidenceProjectionResult` with early returns in this fixed order: computation success; binding success; non-`run_python` structured capability; current session/turn/plan/step; exact dataset-version set equality; required declared-field presence; claim key and requirement IDs; then canonical record validation. Each failed condition returns `EvidenceProjectionResult(projected=False, reason=<stable code>)`. The success branch builds a claim-neutral summary from declared structured fields, sets the maximum allowed claim class from capability output, calls the existing `validate_evidence_record`, and returns the validated record. It never parses model prose into evidence and never upgrades `run_python`.

- [ ] **Step 5: Call projection immediately after computation persistence**

After `_compact_tool_output` creates a computation ref, pass that ref and the call-specific binding to projection. On success, `state.upsert_evidence_record(result.record)` and mark synthesis-policy cache dirty. On failure, append a bounded projection diagnostic and continue; do not schedule a tool solely for evidence bookkeeping.

- [ ] **Step 6: Build and inject a bounded catalog even when empty**

Implement `build_bounded_evidence_catalog(evidence_records: Sequence[dict[str, Any]], *, max_records: int = 12, max_chars: int = 6000) -> str` by sorting current-plan records by `(step_order, evidence_id)`, serializing one compact line per record, taking at most `max_records`, and stopping before the next line would exceed `max_chars`. Include evidence ID, claim key, allowed claim class, measurements, dataset version, verification level, and limitations. For zero records, return:

```python
"可用证据：0 条。请基于现有计算诊断说明局限，不要重新运行工具来制造证据。"
```

Remove any synthesis-policy instruction that tells the model to call analysis tools or `record_evidence_record` during final answer generation.

- [ ] **Step 7: Attach an existing evidence ID only on one exact match**

`attach_unique_exact_evidence_ids` compares claim class, quantity, unit, direction, time scope, population/dataset scope, and current plan ID. Attach only when all material fields match and exactly one evidence record is eligible. Zero or multiple matches remain unbound for audit action.

- [ ] **Step 8: Run evidence, synthesis, and audit suites, then commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_automatic_evidence_projection.py tests/test_stage3c0b_evidence_contracts.py tests/test_final_answer_claim_audit.py tests/test_execution_control.py tests/test_synthesis_policy.py -q
git diff --check
```

Expected: ordinary structured results project evidence without a model bookkeeping call; ambiguous/ad-hoc paths remain untrusted; catalog injection cannot trigger an evidence ritual.

Commit:

```powershell
git add src/data_agent/agent/evidence_contracts.py src/data_agent/agent/synthesis_policy.py src/data_agent/agent/analysis_state.py src/data_agent/agent/answer_quality.py src/data_agent/agent/loop.py tests/test_automatic_evidence_projection.py tests/test_stage3c0b_evidence_contracts.py tests/test_final_answer_claim_audit.py tests/test_execution_control.py tests/test_synthesis_policy.py
git commit -m "feat: project structured computation evidence"
```

---

### Task 10: Tiered Claim Publication and Fail-Safer Configuration

**Files:**
- Modify: `src/data_agent/config.py`
- Modify: `src/data_agent/agent/answer_quality.py`
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Modify: `src/data_agent/agent/loop.py`
- Create: `tests/test_tiered_analysis_publication.py`
- Modify: `tests/test_final_answer_claim_audit.py`
- Modify: `tests/test_final_answer_publish_gate.py`
- Modify: `tests/test_workspace_config.py`

**Interfaces:**
- Consumes: synthesis draft, final-answer audit, completion decision, and validated publication mode.
- Produces: `PublicationResult`, `render_audited_analysis_answer(draft: str, audit: dict[str, Any], completion: CompletionDecision, mode: Literal["tiered", "strict"]) -> PublicationResult`, `AgentConfig.assurance_publication_mode: Literal["tiered", "strict"]`, and claim actions `verified`, `exploratory`, `unsupported`.

- [ ] **Step 1: Write structure-preserving tiered publication tests**

```python
def test_tiered_mode_preserves_headings_tables_and_supported_findings():
    draft = "# 结论\n\n- 已验证发现\n- 未验证数字 99%\n\n## 局限\n\n原有局限"
    result = render_audited_analysis_answer(
        draft=draft,
        audit=mixed_audit(),
        completion=limited_completion(),
        mode="tiered",
    )
    assert "# 结论" in result.text
    assert "已验证发现" in result.text
    assert "探索性，未经独立校验" in result.text
    assert "无法发布该数值" in result.text
    assert "Some requested analysis claims" not in result.text


def test_strict_mode_still_blocks_only_claims_not_whole_answer():
    result = render_audited_analysis_answer(
        draft="# 结论\n\n已验证描述。\n\nunsupported exact claim",
        audit=mixed_audit(),
        completion=limited_completion(),
        mode="strict",
    )
    assert result.text.startswith("# 结论")
    assert "unsupported exact claim" not in result.text
    assert result.actions["claim_unsupported"] == "unsupported"
```

- [ ] **Step 2: Write deterministic blocker and config tests**

```python
@pytest.mark.parametrize("claim_fixture", [
    "fabricated_value",
    "contradictory_direction",
    "stale_dataset",
    "cross_scope_evidence",
    "causal_upgrade",
])
def test_minimum_blockers_apply_in_both_modes(claim_fixture, request):
    for mode in ("tiered", "strict"):
        result = render_audited_analysis_answer(
            draft=request.getfixturevalue(claim_fixture),
            audit=audit_for(claim_fixture),
            completion=complete_decision(),
            mode=mode,
        )
        assert result.actions["claim_1"] == "unsupported"


def test_publication_mode_has_no_off_value():
    with pytest.raises(ValidationError):
        AgentConfig(ASSURANCE_PUBLICATION_MODE="off")
```

- [ ] **Step 3: Run tests and reproduce whole-answer fallback**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tiered_analysis_publication.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_workspace_config.py -q
```

Expected: current gate replaces the useful draft with the generic English warning or stripped fragments; no validated mode exists.

- [ ] **Step 4: Add validated rollback controls without an off switch**

```python
assurance_publication_mode: Literal["tiered", "strict"] = Field(
    alias="ASSURANCE_PUBLICATION_MODE",
    default="tiered",
)
auto_evidence_projection_enabled: bool = Field(
    alias="AUTO_EVIDENCE_PROJECTION_ENABLED",
    default=True,
)
analysis_live_progress_enabled: bool = Field(
    alias="ANALYSIS_LIVE_PROGRESS_ENABLED",
    default=True,
)
```

Projection-disabled rollout behavior must remain `complete_with_limits`/exploratory; it must not bypass deterministic blockers. Persist the selected mode and feature flags in turn diagnostics.

- [ ] **Step 5: Implement claim actions and a deterministic partial renderer**

```python
@dataclass(frozen=True)
class PublicationResult:
    text: str
    actions: dict[str, Literal["verified", "exploratory", "unsupported"]]
    diagnostics: tuple[dict[str, Any], ...]
```

Implement `render_audited_analysis_answer(*, draft: str, audit: dict[str, Any], completion: CompletionDecision, mode: Literal["tiered", "strict"]) -> PublicationResult` with these rules:

- verified claims retain their original text;
- current traceable computations that cannot support the requested class remain visible only as exploratory and receive the local suffix `（探索性，未经独立校验）`;
- fabricated, contradictory, stale, cross-scope, and causal-invalid claims are replaced in place with a Chinese diagnostic naming the missing evidence, method, or data;
- headings, tables, non-claim explanation, method, and limitations remain in their original order;
- if span replacement is unsafe, rebuild only the affected section from audit claim spans and preserve all other sections;
- mode `strict` never removes the entire answer merely because one claim fails.

Delete `_safe_final_answer_fallback` and route `_gate_final_analysis_answer` through this renderer after one bounded wording revision. Audit failure cannot trigger another analysis tool call.

- [ ] **Step 6: Run publication, assurance, and configuration suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tiered_analysis_publication.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_workspace_config.py tests/test_verification_layer.py tests/test_causal_claim_guard.py -q
git diff --check
```

Expected: complete Chinese answers survive partial evidence; deterministic false claims remain blocked in both modes; no generic English fallback remains.

- [ ] **Step 7: Commit tiered publication**

```powershell
git add src/data_agent/config.py src/data_agent/agent/answer_quality.py src/data_agent/agent/synthesis_policy.py src/data_agent/agent/loop.py tests/test_tiered_analysis_publication.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_workspace_config.py
git commit -m "feat: publish audited analysis by claim tier"
```

---

### Task 11: Safe Live Analysis Progress and Method Narration

**Files:**
- Create: `src/data_agent/agent/progress.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/web/blueprints/chat.py`
- Modify: `src/data_agent/web/static/js/app.js`
- Create: `tests/test_analysis_progress_streaming.py`
- Modify: `tests/test_sse_reactivity.py`
- Modify: `tests/test_web_overhaul.py`

**Interfaces:**
- Consumes: server-owned phase, plan step, tool name, recovery category, and completion state.
- Produces: `AnalysisProgressEvent.to_dict()`, event type `analysis_progress`, and a visible per-turn progress status in the web client.

- [ ] **Step 1: Write safe payload and pre-final ordering tests**

```python
def test_progress_payload_is_server_authored_and_contains_no_findings():
    event = build_analysis_progress(
        code="analysis_step_started",
        step_id="step_relationship",
        status="running",
    )
    payload = event.to_dict()
    assert payload["label"] == "正在评估变量关系"
    assert not {"value", "p_value", "ranking", "claim", "reasoning"} & set(payload)


def test_stream_emits_progress_before_buffered_final_answer(agent):
    events = list(agent.run_stream("分析显著影响因素"))
    progress_index = next(i for i, event in enumerate(events) if event["type"] == "analysis_progress")
    final_index = next(i for i, event in enumerate(events) if event["type"] == "text_delta")
    assert progress_index < final_index
    assert all("显著因素是" not in event.get("label", "") for event in events[:final_index])
```

- [ ] **Step 2: Write SSE and browser-state tests**

```python
def test_chat_blueprint_projects_analysis_progress():
    sse = feed_one({"type": "analysis_progress", "code": "tool_started", "label": "正在运行相关性分析"})
    assert sse.event == "analysis_progress"
    assert sse.data["label"] == "正在运行相关性分析"


def test_frontend_handles_analysis_progress_without_appending_final_text():
    source = Path("src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    assert "case 'analysis_progress':" in source
    assert "turn.analysisProgress" in source
```

- [ ] **Step 3: Run streaming tests and observe the buffered gap**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_progress_streaming.py tests/test_sse_reactivity.py tests/test_web_overhaul.py -q
```

Expected: no `analysis_progress` event exists; analysis text remains buffered with no useful server-authored narrative.

- [ ] **Step 4: Implement a closed progress vocabulary**

```python
PROGRESS_LABELS = {
    "analysis_plan_ready": "分析方案已准备",
    "analysis_step_started": "正在执行分析步骤",
    "tool_started": "正在运行分析工具",
    "tool_succeeded": "分析步骤已完成",
    "tool_recovery": "正在按约定尝试恢复",
    "completion_evaluated": "正在整理可支持的结论",
    "audit_started": "正在校验最终结论",
}


@dataclass(frozen=True)
class AnalysisProgressEvent:
    code: str
    label: str
    status: Literal["pending", "running", "completed", "limited"]
    step_id: str = ""
    phase: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "analysis_progress",
            "code": self.code,
            "label": self.label,
            "status": self.status,
            "step_id": self.step_id,
            "phase": self.phase,
        }
```

`build_analysis_progress` accepts only allowlisted codes and chooses labels from server templates. Step-specific labels may use an allowlisted `analysis_code -> Chinese label` mapping. Reject arbitrary model text and any extra numeric/claim fields.

- [ ] **Step 5: Emit progress around envelope, tools, recovery, completion, and audit**

In streaming execution, yield progress when the envelope is ready, a canonical step starts, a tool starts/finishes, bounded recovery begins, completion is evaluated, and audit starts. Keep candidate findings buffered exactly as before. In synchronous execution, append the same events to turn diagnostics so CLI and tests share state even when they do not consume SSE.

- [ ] **Step 6: Project and render progress in the web client**

In `chat.py`, map `analysis_progress` to an SSE event containing only code, label, status, step ID, and phase. In `app.js`, add:

```javascript
case 'analysis_progress':
    turn.analysisProgress = {
        code: event.data.code,
        label: event.data.label,
        status: event.data.status,
        stepId: event.data.step_id || ''
    };
    turn.thinkingText = event.data.label;
    this._renderMessages();
    break;
```

Clear the active progress indicator only after final publication or a terminal error; retain the final status in the turn timeline. Do not append progress labels to final assistant Markdown.

- [ ] **Step 7: Run streaming suites and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_progress_streaming.py tests/test_sse_reactivity.py tests/test_web_overhaul.py tests/test_execution_control.py -q
node --check src/data_agent/web/static/js/app.js
git diff --check
```

Expected: progress arrives before final text; payloads contain no conclusions; candidate answer remains buffered until audit.

Commit:

```powershell
git add src/data_agent/agent/progress.py src/data_agent/agent/loop.py src/data_agent/web/blueprints/chat.py src/data_agent/web/static/js/app.js tests/test_analysis_progress_streaming.py tests/test_sse_reactivity.py tests/test_web_overhaul.py
git commit -m "feat: stream safe analysis progress"
```

---

### Task 12: Systemic Replays, Depth Gate, Browser Verification, and Release Gate

**Files:**
- Create: `scripts/replay_analysis_reliability.py`
- Create: `tests/test_analysis_reliability_replays.py`
- Modify: `tests/test_golden_scenarios.py`
- Modify: `tests/real_data/test_context_budget_degradation.py`
- Modify: `docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md`

**Interfaces:**
- Consumes: fixture builders, deterministic fake-LLM traces, optional configured external provider, web SSE endpoint, and all production contracts from Tasks 2-11.
- Produces: deterministic replay exit status, JSON acceptance summary, optional three-run live-provider report in a new temporary/output directory, and the final implementation evidence recorded in the design document.

- [ ] **Step 1: Write deterministic target-session replay tests**

```python
def test_factor_session_replay_is_deep_bounded_and_publishable(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        root=tmp_path,
    )
    assert_reliable_analysis_trace(result.trace, require_inferential_attempt=True)
    assert result.completion_state in {"complete", "complete_with_limits"}
    assert result.evidence_records
    assert result.progress_events[0].sequence < result.final_answer_sequence
    assert result.final_answer.strip()
    assert result.final_answer_language == "zh"
    assert "Some requested analysis claims" not in result.final_answer


def test_aggregate_profile_replay_blocks_unavailable_user_claims(tmp_path):
    result = run_deterministic_replay(
        frame=build_aggregate_payment_frame(),
        prompt="请分析用户画像、复购和消费分布",
        root=tmp_path,
    )
    assert "年龄" not in result.asserted_dimensions
    assert "个人复购" not in result.asserted_dimensions
    assert result.completion_state in {"complete_with_limits", "blocked_by_data"}
    assert "需要用户级字段" in result.final_answer
```

- [ ] **Step 2: Add sandbox-heavy and Unicode replay tests**

```python
def test_sandbox_heavy_replay_has_no_import_or_none_cascade(tmp_path):
    result = run_sandbox_replay(tmp_path)
    assert "__import__ not found" not in result.serialized_trace
    assert "NoneType" not in result.serialized_trace
    assert result.max_identical_failure_attempts <= 2


def test_unicode_progress_replay_survives_cp936_and_keeps_browser_unicode(tmp_path):
    result = run_unicode_replay(tmp_path, console_encoding="cp936")
    assert result.turn_completed is True
    assert "⚠️" in result.persisted_text
    assert "⚠️" in result.browser_text
```

- [ ] **Step 3: Run replay tests and fix only contract-level integration gaps**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_reliability_replays.py tests/test_golden_scenarios.py tests/real_data/test_context_budget_degradation.py -q
```

Expected before the final integration fixes: failures identify exact missing wiring between already implemented task interfaces. Fix the owning module named by the failing contract; do not weaken trace depth, evidence eligibility, deterministic blocker, or terminal-state assertions to make the test green.

- [ ] **Step 4: Implement the replay CLI with deterministic and live modes**

```python
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deterministic", "live"], default="deterministic")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "live" and args.runs != 3:
        parser.error("live mode requires --runs 3")
    summary = replay_suite(mode=args.mode, runs=args.runs, output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1
```

The CLI creates only new session/output directories. Deterministic mode uses the fixture and fake-LLM routes. Live mode uses the configured provider, starts three fresh sessions, and accepts each run only when it terminates without repeated errors and either satisfies applicable minimum coverage or returns an exact `complete_with_limits`, `blocked_by_data`, or `blocked_by_tool` reason.

- [ ] **Step 5: Run the deterministic acceptance CLI**

Run:

```powershell
$replayRoot = Join-Path $env:TEMP "data-agent-reliability-replay"
.\.venv\Scripts\python.exe scripts/replay_analysis_reliability.py --mode deterministic --runs 1 --output-dir $replayRoot
```

Expected JSON:

```json
{
  "accepted": true,
  "factor_relationship": true,
  "sandbox_recovery": true,
  "unicode_boundary": true,
  "aggregate_profile_boundary": true
}
```

- [ ] **Step 6: Run live-provider consistency only when credentials are configured**

Check:

```powershell
.\.venv\Scripts\python.exe -c "from data_agent.config import get_config; c=get_config(); print(bool(c.api_key and c.model_id))"
```

When output is `True`, run:

```powershell
$liveReplayRoot = Join-Path $env:TEMP "data-agent-live-reliability-replay"
.\.venv\Scripts\python.exe scripts/replay_analysis_reliability.py --mode live --runs 3 --output-dir $liveReplayRoot
```

Expected: `accepted` is true and each of the three new runs records a terminal state, depth coverage or exact limitation, zero repeated-error loops, safe progress before final output, and no generic English fallback. When output is `False`, record `not_run_no_provider_credentials`; deterministic CI remains the release gate.

- [ ] **Step 7: Verify the browser SSE path**

Use the already-running local service if available; otherwise start it with the project-supported web command. In the browser, upload or inject the tracked 32x21 fixture, submit the factor prompt, and verify:

1. at least one method/progress label is visible before the final answer;
2. no draft numbers or findings appear before audit;
3. the final answer contains method, supported findings, limitations, and an exact downgrade when needed;
4. the final answer does not contain the generic English warning;
5. the network SSE stream contains `analysis_progress` before final `text_delta`;
6. the exact uploaded dataset, not another workspace dataset, backs any chart.

Capture the browser result in the replay JSON or a test-owned temporary screenshot path; do not write into untracked project `artifacts/`.

- [ ] **Step 8: Run focused assurance and execution regression suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry_contracts.py tests/test_sandbox_contract.py tests/test_unicode_io.py tests/test_chart_contract.py tests/test_analysis_execution_envelope.py tests/test_factor_relationship_route.py tests/test_tool_capability_truthfulness.py tests/test_analysis_completion.py tests/test_automatic_evidence_projection.py tests/test_tiered_analysis_publication.py tests/test_analysis_progress_streaming.py tests/test_analysis_reliability_replays.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_execution_control.py tests/test_stage3c0b_execution_scope.py tests/test_analysis_requirements.py tests/test_stage3c0b_evidence_contracts.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_golden_scenarios.py tests/real_data/test_context_budget_degradation.py -q
```

Expected: all focused and cross-layer suites pass.

- [ ] **Step 9: Run the complete release gate**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src/data_agent
node --check src/data_agent/web/static/js/app.js
git diff --check
git status --short
```

Expected: all tests pass, compile and JavaScript checks exit 0, diff check exits 0, and `git status --short` lists only intended implementation files plus the pre-existing untracked `artifacts/` and `tmp/`.

- [ ] **Step 10: Record actual verification evidence and commit**

Update the design document status to `Implemented` only after Step 9 succeeds. Add the exact test counts, deterministic replay summary, live-provider result or `not_run_no_provider_credentials`, browser verification result, and implementation commit range. Do not state that normal analysis is restored if any acceptance gate remains failing.

Commit:

```powershell
git add scripts/replay_analysis_reliability.py tests/test_analysis_reliability_replays.py tests/test_golden_scenarios.py tests/real_data/test_context_budget_degradation.py docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md
git commit -m "test: verify systemic analysis reliability"
```

---

## Dependency and Stop Gates

| After task | Required gate before continuing |
|---|---|
| 2 | Every native LLM schema matches its Python signature and runtime normalization is lossless. |
| 3 | Approved sandbox imports work; forbidden imports remain blocked; missing datasets cannot cascade through `None`. |
| 4 | CP936/GBK console failures cannot terminate a supported launcher or logging path. |
| 5 | Explicit chart dataset identity is exact and omission is deterministic. |
| 6 | Every directed/comprehensive turn has an executable canonical envelope or an explicit diagnostic before substantive analysis. |
| 7 | Factor/significance questions receive the six-part route and tool metadata matches real structured output. |
| 8 | Completion converges within retry/fallback/continuation bounds and one tool cannot satisfy a multi-step question. |
| 9 | Eligible structured computations become current-plan evidence; ineligible computations remain refs only. |
| 10 | Partial evidence preserves a useful answer while deterministic false claims remain blocked. |
| 11 | Safe progress precedes final publication without leaking findings. |
| 12 | Deterministic systemic replays, focused suites, browser verification, and the complete release gate pass. |

Stop and diagnose the owning earlier layer if a later test can pass only by weakening a prior gate. In particular:

- do not use exploratory labels to conceal a tool that never executed;
- do not auto-project evidence from ambiguous or unstructured output;
- do not count tool calls as proof of depth;
- do not restart analysis because publication metadata is missing;
- do not disable deterministic blockers to make an answer look complete.

## Spec Coverage Self-Review

| Design requirement | Implemented by |
|---|---|
| Typed schemas, aliases, runtime normalization, plan object | Task 2 |
| AST sandbox imports, dataset-not-found, bounded repeat recovery | Task 3 |
| Unicode-safe supported launch and logging paths | Task 4 |
| Exact chart data identity | Task 5 |
| Server-owned plan for explicit and ad-hoc analysis | Task 6 |
| Exact unique step binding and ambiguity diagnostics | Task 6 |
| Dedicated factor/significance method depth | Task 7 |
| Truthful evidence fields and supported claim classes | Task 7 |
| Five completion states and anti-ritual convergence | Task 8 |
| Automatic structured evidence projection | Task 9 |
| Bounded evidence catalog and unique exact ID attachment | Task 9 |
| Verified/exploratory/unsupported publication | Task 10 |
| Tiered/strict rollback with no production off mode | Task 10 |
| Safe process narration and live SSE progress | Task 11 |
| Target, sandbox-heavy, Unicode, and aggregate-profile replays | Task 12 |
| Real-provider three-run consistency and browser verification | Task 12 |
| Broad assurance, execution, chart, web, and budget regression | Task 12 |

## Completion Standard

This plan is complete only when the release evidence shows all of the following:

1. tool parameters execute with their declared types;
2. sandbox and Unicode failures cannot kill ordinary analysis;
3. the correct dataset and method are used;
4. factor/significance analysis reaches applicable univariate, multivariable, stability, and limitation coverage or reports the exact unattainable requirement;
5. successful structured computations automatically become canonical current evidence;
6. completion terminates without shallow one-tool success or evidence-bookkeeping loops;
7. partial assurance produces a complete, useful, bounded answer instead of an empty shell;
8. false, stale, contradictory, cross-scope, and causal-invalid claims remain blocked;
9. users see safe method progress before the audited final answer;
10. deterministic replays and the full test suite pass without modifying historical sessions or unrelated workspace content.
