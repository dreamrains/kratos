# Multifile Understanding Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical data-understanding, relationship-validation, central scope, joint-analysis, and derived-data foundation required by the approved multifile design.

**Architecture:** Deterministic scanners create versioned DataUnderstandingBundles and validate relationship candidates before any join. A context-local workspace boundary enforces planning, execution, and synthesis visibility, while plan contracts explicitly support independent, joint, aggregate-then-join, and synthesis tasks.

**Tech Stack:** Python 3.11+, pandas, dataclasses, ContextVar, pytest, existing AnalysisSessionState and TaskManager persistence.

---

### Task 1: Canonical DataUnderstandingBundle Contract

**Files:**
- Create: `src/data_agent/agent/data_understanding.py`
- Create: `tests/test_data_understanding_bundle.py`
- Modify: `src/data_agent/agent/analysis_state.py`

- [ ] **Step 1: Write failing contract and versioning tests**

```python
from data_agent.agent.data_understanding import build_data_understanding_bundle, validate_data_understanding_bundle


def test_bundle_is_versioned_and_fingerprinted():
    bundle = build_data_understanding_bundle(
        datasets=[{"dataset": "orders", "rows": 10, "columns": ["user_id", "amount"]}],
        quality_findings=[],
        relationship_candidates=[],
    )
    assert bundle["contract_version"] == "data_understanding.v1"
    assert bundle["data_fingerprint"]
    assert validate_data_understanding_bundle(bundle).ok is True


def test_bundle_rejects_dataset_without_grain_or_contract():
    result = validate_data_understanding_bundle({
        "contract_version": "data_understanding.v1",
        "datasets": [{"dataset": "orders"}],
    })
    assert result.ok is False
    assert result.error_type == "invalid_dataset_understanding"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `$env:PYTHONPATH=(Resolve-Path 'src').Path; & 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_data_understanding_bundle.py -q`

Expected: collection fails because `data_understanding.py` does not exist.

- [ ] **Step 3: Implement the bundle builder and validator**

```python
DATA_UNDERSTANDING_VERSION = "data_understanding.v1"

@dataclass(frozen=True)
class BundleValidationResult:
    ok: bool
    error_type: str = ""
    message: str = ""

def build_data_understanding_bundle(*, datasets, quality_findings, relationship_candidates):
    payload = {
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "datasets": datasets,
        "quality_findings": quality_findings,
        "relationship_candidates": relationship_candidates,
        "entities": [], "metrics": [], "dimensions": [], "supported_questions": [],
        "unsupported_questions": [], "analysis_constraints": [],
    }
    payload["data_fingerprint"] = stable_json_fingerprint(payload)
    payload["id"] = f"dub_{payload['data_fingerprint'][:12]}"
    return payload
```

Add `data_understanding_bundles: list[dict[str, Any]]` to `AnalysisSessionState`, serialization, upsert, summary count, and active-ref tracking.

- [ ] **Step 4: Run contract and state tests**

Run: `$env:PYTHONPATH=(Resolve-Path 'src').Path; & 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_data_understanding_bundle.py tests/test_analysis_state_v2.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/data_understanding.py src/data_agent/agent/analysis_state.py tests/test_data_understanding_bundle.py
git commit -m "feat: add canonical data understanding bundles"
```

### Task 2: Deterministic Relationship Validation

**Files:**
- Create: `src/data_agent/agent/relationship_validation.py`
- Create: `tests/test_relationship_validation.py`
- Modify: `src/data_agent/agent/data_understanding.py`

- [ ] **Step 1: Write failing cardinality, coverage, and rejection tests**

```python
def test_many_to_many_relationship_is_rejected():
    left = pd.DataFrame({"user_id": [1, 1, 2], "value": [1, 2, 3]})
    right = pd.DataFrame({"user_id": [1, 1, 3], "amount": [5, 6, 7]})
    result = validate_relationship(left, right, left_key="user_id", right_key="user_id")
    assert result.status == "rejected"
    assert result.cardinality == "many_to_many"
    assert "join_explosion" in result.risks


def test_validated_relationship_reports_coverage():
    left = pd.DataFrame({"user_id": [1, 2, 3]})
    right = pd.DataFrame({"user_id": [1, 2, 4]})
    result = validate_relationship(left, right, left_key="user_id", right_key="user_id")
    assert result.status == "validated"
    assert result.left_coverage == pytest.approx(2 / 3)
```

- [ ] **Step 2: Run tests and verify RED**

Run the focused file; expect missing module failure.

- [ ] **Step 3: Implement validation without fuzzy-key fallback**

```python
@dataclass(frozen=True)
class RelationshipValidation:
    status: str
    cardinality: str
    left_coverage: float
    right_coverage: float
    expected_rows: int
    risks: tuple[str, ...] = ()

def validate_relationship(left, right, *, left_key, right_key):
    left_counts = left[left_key].dropna().value_counts()
    right_counts = right[right_key].dropna().value_counts()
    cardinality = classify_cardinality(left_counts, right_counts)
    shared = set(left_counts.index) & set(right_counts.index)
    risks = ("join_explosion",) if cardinality == "many_to_many" else ()
    return RelationshipValidation(
        status="rejected" if risks else "validated",
        cardinality=cardinality,
        left_coverage=covered_share(left[left_key], shared),
        right_coverage=covered_share(right[right_key], shared),
        expected_rows=expected_join_rows(left_counts, right_counts, shared),
        risks=risks,
    )
```

- [ ] **Step 4: Run focused and multi-file regressions**

Run: `python -m pytest tests/test_relationship_validation.py tests/test_multi_file_scope.py -q` with the worktree interpreter and PYTHONPATH.

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/relationship_validation.py src/data_agent/agent/data_understanding.py tests/test_relationship_validation.py
git commit -m "feat: validate multifile relationships deterministically"
```

### Task 3: Context-Local Central Workspace Boundary

**Files:**
- Modify: `src/data_agent/agent/context.py`
- Modify: `src/data_agent/agent/execution_scope.py`
- Modify: `src/data_agent/session/workspace.py`
- Modify: `src/data_agent/agent/loop.py`
- Create: `tests/test_scoped_workspace.py`

- [ ] **Step 1: Write failing planning, execution, synthesis, and cache tests**

```python
def test_execution_workspace_lists_only_bound_datasets(scoped_context, workspace):
    workspace.add("banner", pd.DataFrame({"x": [1]}))
    workspace.add("iap", pd.DataFrame({"x": [2]}))
    with scoped_context(mode="execution", allowed={"banner"}):
        assert set(workspace.list_datasets()) == {"banner"}
        assert workspace.get("iap") is None

def test_synthesis_workspace_exposes_no_raw_datasets(scoped_context, workspace):
    workspace.add("banner", pd.DataFrame({"x": [1]}))
    with scoped_context(mode="synthesis", allowed=set()):
        assert workspace.list_datasets() == {}
```

Also test exact blank-project isolation, active-plan-without-current-task fail-closed, thread context propagation, and prompt cache invalidation when the scope fingerprint changes.

- [ ] **Step 2: Run tests and verify RED**

Expected: unbound datasets remain visible and prompt cache ignores scope changes.

- [ ] **Step 3: Implement an immutable per-turn scope snapshot**

```python
@dataclass(frozen=True)
class WorkspaceScopeSnapshot:
    phase: str = "legacy"
    plan_id: str = ""
    task_id: int = 0
    allowed_datasets: frozenset[str] = frozenset()
    fingerprint: str = ""

Add this field to the existing `AgentContext` dataclass without changing its other fields:

```python
workspace_scope: "WorkspaceScopeSnapshot | None" = None
```
```

Add explicit proxy methods for `get`, `list_datasets`, `get_metadata`, `exists`, `add`, and `derive`. Execution filters names; synthesis rejects raw access; planning exposes schema/quality metadata and bounded previews through dedicated methods rather than unrestricted DataFrames.

- [ ] **Step 4: Key the prompt cache by scope fingerprint**

```python
cache_key = (
    self.context.workspace_scope.fingerprint if self.context.workspace_scope else "legacy",
    self.context.analysis_state.data_understanding_bundles[-1]["data_fingerprint"]
    if self.context.analysis_state and self.context.analysis_state.data_understanding_bundles else "",
)
if cache_key != self._prompt_cache_key:
    self._prompt_cache_dirty = True
    self._prompt_cache_key = cache_key
```

- [ ] **Step 5: Run scope and loop regressions**

Run: `$env:PYTHONPATH=(Resolve-Path 'src').Path; & 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_scoped_workspace.py tests/test_stage3c0b_execution_scope.py tests/test_comprehensive_analysis_flow.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/data_agent/agent/context.py src/data_agent/agent/execution_scope.py src/data_agent/session/workspace.py src/data_agent/agent/loop.py tests/test_scoped_workspace.py
git commit -m "feat: enforce central stage 3c0b workspace scope"
```

### Task 4: Joint Modes and Derived Dataset Lineage

**Files:**
- Create: `src/data_agent/agent/derived_datasets.py`
- Modify: `src/data_agent/agent/analysis_plan_contracts.py`
- Modify: `src/data_agent/agent/workflow_projection.py`
- Modify: `src/data_agent/session/workspace.py`
- Modify: `tests/test_stage3c0b_plan_contracts.py`
- Create: `tests/test_derived_dataset_scope.py`

- [ ] **Step 1: Write failing plan-mode and lineage tests**

```python
def test_joint_step_requires_two_datasets_and_validated_relationship():
    result = validate_analysis_plan_contract(joint_plan(relationship_ids=[]), dataset_contracts=contracts())
    assert result.ok is False
    assert result.error_type == "missing_validated_relationship"

def test_derived_dataset_inherits_all_source_scope(workspace, scoped_context):
    with scoped_context(mode="execution", allowed={"orders", "users"}):
        workspace.add_derived("joined", frame(), sources=["orders", "users"], expression="orders join users")
        assert workspace.get("joined") is not None
```

- [ ] **Step 2: Verify RED**

Expected: unsupported combination mode and missing `add_derived`.

- [ ] **Step 3: Add explicit modes and contract rules**

```python
SUPPORTED_STAGE3C0B_MODES = {"independent", "joint", "aggregate_then_join", "synthesis"}

if mode in {"joint", "aggregate_then_join"} and len(dataset_inputs) < 2:
    return _error("invalid_joint_binding", "Joint steps require at least two datasets.")
if mode in {"joint", "aggregate_then_join"} and not relationship_ids:
    return _error("missing_validated_relationship", "Joint steps require validated relationship IDs.")
```

Persist `DerivedDatasetRecord(id, sources, expression, grain, plan_id, task_id, data_fingerprint)` in workspace metadata. Visibility is inherited only when every source is visible.

- [ ] **Step 4: Run plan, projection, and derived-scope tests**

Expected: PASS with no synthesis raw-data regression.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/derived_datasets.py src/data_agent/agent/analysis_plan_contracts.py src/data_agent/agent/workflow_projection.py src/data_agent/session/workspace.py tests/test_stage3c0b_plan_contracts.py tests/test_derived_dataset_scope.py
git commit -m "feat: support validated joint analysis tasks"
```

### Task 5: Load-Time Bundle and User Brief Integration

**Files:**
- Modify: `src/data_agent/tools/data_io.py`
- Modify: `src/data_agent/agent/trust_contracts.py`
- Modify: `src/data_agent/agent/trust_view.py`
- Create: `tests/test_data_understanding_integration.py`

- [ ] **Step 1: Write failing integration tests**

```python
def test_loading_second_dataset_rebuilds_bundle_without_approving_relationship(tmp_path, agent_context):
    load_fixture(tmp_path, "orders.csv", "user_id,amount\n1,10\n2,20\n")
    load_fixture(tmp_path, "users.csv", "user_id,segment\n1,A\n2,B\n")
    load_data(str(tmp_path / "orders.csv"), name="orders")
    load_data(str(tmp_path / "users.csv"), name="users")
    state = load_analysis_state(agent_context.session_id)
    bundle = hydrate_ref(state.data_understanding_bundles[-1])
    assert len(bundle["datasets"]) == 2
    assert {item["status"] for item in bundle["relationship_candidates"]} <= {"proposed", "rejected"}
    assert build_user_data_brief(bundle)["supported_questions"]
```

- [ ] **Step 2: Verify RED**

Expected: load creates separate preview artifacts but no canonical bundle.

- [ ] **Step 3: Build and persist the bundle after trust artifacts**

```python
bundle = build_data_understanding_bundle(
    datasets=hydrate_current_dataset_understanding(state),
    quality_findings=hydrate_current_quality_findings(state),
    relationship_candidates=build_relationship_candidates(state),
)
state.add_data_understanding_bundle_ref(persist_bundle(session_id, bundle))
state.save()
```

Add `build_user_data_brief(bundle)` to the trust view; do not expose raw sample rows or hidden dataset schemas.

- [ ] **Step 4: Run load, trust, and foundation tests**

Run: `pytest tests/test_data_understanding_integration.py tests/test_trust_contracts.py tests/test_trust_view.py tests/test_trustworthy_load_data_integration.py -q` with the worktree interpreter.

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/tools/data_io.py src/data_agent/agent/trust_contracts.py src/data_agent/agent/trust_view.py tests/test_data_understanding_integration.py
git commit -m "feat: connect data loading to understanding bundles"
```

### Task 6: Foundation Regression Gate

**Files:**
- Create: `tests/test_multifile_foundation_regression.py`

- [ ] **Step 1: Add end-to-end foundation tests**

```python
def test_data_mutation_invalidates_relationship_and_bundle(workflow_fixture):
    first = workflow_fixture.build_bundle()
    workflow_fixture.workspace.add("orders", pd.DataFrame({"user_id": [1, 1], "amount": [10, 20]}))
    second = workflow_fixture.build_bundle()
    assert second["data_fingerprint"] != first["data_fingerprint"]
    assert all(item["status"] != "validated" for item in second["relationship_candidates"])

def test_synthesis_cannot_read_joint_sources(workflow_fixture):
    with workflow_fixture.scope(mode="synthesis", allowed=set()):
        assert workflow_fixture.workspace.list_datasets() == {}
        assert workflow_fixture.workspace.get("orders") is None
```

- [ ] **Step 2: Run the complete foundation suite**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_data_understanding_bundle.py tests/test_relationship_validation.py tests/test_scoped_workspace.py tests/test_derived_dataset_scope.py tests/test_data_understanding_integration.py tests/test_multifile_foundation_regression.py tests/test_stage3c0b_plan_contracts.py tests/test_stage3c0b_workflow_projection.py tests/test_stage3c0b_execution_scope.py tests/test_trust_contracts.py tests/test_trustworthy_load_data_integration.py tests/test_analysis_state_v2.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_comprehensive_analysis_flow.py -q
```

Expected: zero failures. Run known order-sensitive comprehensive files in separate pytest processes and record both outputs.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_multifile_foundation_regression.py
git commit -m "test: gate multifile understanding foundation"
```
