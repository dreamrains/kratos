# Core Contracts and Analysis Copy Implementation Plan

> **Status:** Completed by the canonical-plan and versioned-analysis-copy migration; retained as the historical implementation baseline.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate analysis planning into one canonical contract and make all file preparation and cleaning operate on versioned analysis copies while preserving immutable raw snapshots.

**Architecture:** Keep the existing workspace, loading, cleaning, and trust-workflow surfaces, but add explicit raw-snapshot and active-version storage behind the workspace facade. Normalize every planning payload through `analysis_plan_contracts.py`; treat `AnalysisSpec` as a read/adapter compatibility name only. Put pure lineage identity in one focused module, keep transformation decisions in `data_clean.py`, and make `data_io.py` orchestrate raw registration followed by analysis-copy preparation.

**Tech Stack:** Python 3.12, pandas, dataclasses, pytest, existing `AgentContext`/`WorkspaceProxy`, existing JSON artifact persistence.

## Global Constraints

- Do not use historical stage names as the new product or planning model.
- Do not build a deterministic multi-file join or aggregation planner.
- User-uploaded files and raw in-memory snapshots are immutable.
- Existing logical dataset names continue to resolve to the active analysis-ready copy.
- Safe parsing may proceed automatically only on a copy and only without introducing information loss.
- Row deletion, deduplication, imputation, outlier removal/capping, unit conversion, category remapping, denominator changes, and grain changes require confirmation unless deterministic comparison proves no material change.
- One business rule has one authoritative owner; compatibility adapters cannot become a second source of truth.
- Every production-code change follows RED → GREEN → REFACTOR and is committed independently.
- Preserve existing untracked `artifacts/` and `tmp/` content.

---

## File Structure

- Create `src/data_agent/agent/data_lineage.py`: deterministic frame identity and immutable `TransformationRecord` construction only.
- Modify `src/data_agent/agent/analysis_plan_contracts.py`: canonical plan version, normalization, executable validation, and legacy-version migration.
- Modify `src/data_agent/agent/analysis_state.py`: one stored `analysis_plan`; read-only `analysis_spec` compatibility projection.
- Modify `src/data_agent/tools/analysis_flow.py`: one plan write path plus deprecated `record_analysis_spec` adapter.
- Modify `src/data_agent/agent/trust_contracts.py`: canonical route `evidence_requirements` writer and compatibility reader.
- Modify `src/data_agent/agent/route_capabilities.py`, `analysis_entry.py`, and `question_need_detector.py`: consume the shared evidence-requirements reader.
- Modify `src/data_agent/session/workspace.py`: hidden raw snapshots, dataset-version history, active analysis-copy alias, and scope-safe facade operations.
- Modify `src/data_agent/tools/data_clean.py`: safe copy preparation, materiality classification, copy-on-write cleaning and conversion.
- Modify `src/data_agent/tools/data_io.py`: register raw first, prepare/promote a copy second, and persist lineage metadata.
- Modify `src/data_agent/agent/loop.py`: restore raw and active copies without reintroducing in-place auto-cleaning.
- Modify runtime callers that write `analysis_spec`: migrate them to `analysis_plan`/`set_analysis_plan`.
- Create focused tests listed under each task; avoid expanding legacy comprehensive test files unless a compatibility assertion belongs there.

---

### Task 1: Canonical AnalysisPlan Contract and State

**Files:**
- Modify: `src/data_agent/agent/analysis_plan_contracts.py:1-168`
- Modify: `src/data_agent/agent/analysis_state.py:117-205,265-292,540-610`
- Modify: `src/data_agent/tools/analysis_flow.py:185-295`
- Create: `tests/test_analysis_plan_consolidation.py`
- Modify: `tests/test_analysis_state_v2.py:115-220`

**Interfaces:**
- Produces: `ANALYSIS_PLAN_CONTRACT_VERSION = "analysis_plan.v1"`
- Produces: `normalize_analysis_plan_contract(plan, *, dataset_contracts=None, require_executable=False) -> ContractValidationResult`
- Preserves: `validate_analysis_plan_contract(...) -> ContractValidationResult` as the executable wrapper.
- Preserves: `AnalysisSessionState.analysis_spec` as a read-only compatibility property.
- Produces: only `AnalysisSessionState.set_analysis_plan(plan)` as the writable state API.

- [ ] **Step 1: Write failing contract-normalization tests**

```python
# tests/test_analysis_plan_consolidation.py
from data_agent.agent.analysis_plan_contracts import (
    ANALYSIS_PLAN_CONTRACT_VERSION,
    normalize_analysis_plan_contract,
)
from data_agent.agent.analysis_state import AnalysisSessionState


def test_legacy_contract_version_normalizes_to_product_version():
    result = normalize_analysis_plan_contract({
        "contract_version": "stage3c0b.v1",
        "goal": "analyze revenue",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "describe revenue",
            "combination_mode": "independent",
            "dataset_inputs": ["orders"],
            "expected_output": "summary",
            "evidence_requirements": ["sample_size"],
        }],
    }, require_executable=True)

    assert result.ok is True
    assert result.plan["contract_version"] == ANALYSIS_PLAN_CONTRACT_VERSION


def test_legacy_analysis_spec_loads_into_single_plan_field():
    state = AnalysisSessionState.from_dict({
        "session_id": "legacy",
        "analysis_spec": {"id": "plan_legacy", "goal": "legacy goal"},
    }, "legacy")

    assert state.analysis_plan["id"] == "plan_legacy"
    assert state.analysis_spec is state.analysis_plan
    assert "analysis_spec" not in state.to_dict()


def test_analysis_spec_property_is_not_a_second_write_path():
    state = AnalysisSessionState(session_id="single-writer")

    try:
        state.analysis_spec = {"goal": "bypass"}
    except AttributeError:
        pass
    else:
        raise AssertionError("analysis_spec must be read-only")
```

- [ ] **Step 2: Run the tests and verify the intended failures**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_analysis_plan_consolidation.py
```

Expected: collection or assertion failures because the product-version constant and normalizer do not exist, `analysis_spec` is serialized, and direct assignment is currently allowed.

- [ ] **Step 3: Add canonical normalization and keep the old validator as a wrapper**

Implement the following public shape in `analysis_plan_contracts.py`; move the current executable step validation into `_validate_executable_plan` without changing its safety behavior:

```python
ANALYSIS_PLAN_CONTRACT_VERSION = "analysis_plan.v1"
LEGACY_ANALYSIS_PLAN_CONTRACT_VERSIONS = {"stage3c0b.v1"}
SUPPORTED_ANALYSIS_PLAN_MODES = {"independent", "synthesis"}

# Read-only compatibility aliases for external imports during migration.
STAGE3C0B_CONTRACT_VERSION = "stage3c0b.v1"
SUPPORTED_STAGE3C0B_MODES = SUPPORTED_ANALYSIS_PLAN_MODES


def normalize_analysis_plan_contract(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
    require_executable: bool = False,
) -> ContractValidationResult:
    if not isinstance(plan, dict):
        return _error("invalid_plan", "AnalysisPlan must be a JSON object.")

    normalized = dict(plan)
    incoming_version = _text(normalized.get("contract_version"))
    if incoming_version in LEGACY_ANALYSIS_PLAN_CONTRACT_VERSIONS:
        normalized["migrated_from_contract_version"] = incoming_version
        incoming_version = ANALYSIS_PLAN_CONTRACT_VERSION
    if incoming_version and incoming_version != ANALYSIS_PLAN_CONTRACT_VERSION:
        return _error("unsupported_contract_version", f"Unsupported AnalysisPlan contract version: {incoming_version}")
    normalized["contract_version"] = ANALYSIS_PLAN_CONTRACT_VERSION
    normalized.setdefault("id", f"plan_{uuid.uuid4().hex[:10]}")
    normalized.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if not require_executable:
        normalized.setdefault("review_status", "display_only")
        return ContractValidationResult(True, plan=normalized)
    return _validate_executable_plan(normalized, dataset_contracts=dataset_contracts)


def validate_analysis_plan_contract(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
) -> ContractValidationResult:
    return normalize_analysis_plan_contract(
        plan,
        dataset_contracts=dataset_contracts,
        require_executable=True,
    )
```

Update validation messages to say `AnalysisPlan`, not a historical stage name.

- [ ] **Step 4: Make AnalysisSessionState persist one planning field**

Remove the dataclass field `analysis_spec`. Normalize the legacy input in `from_dict`, write only `analysis_plan` in `to_dict`, retain a read-only property, and make the adapter method delegate to the canonical setter:

```python
@property
def analysis_spec(self) -> dict[str, Any] | None:
    """Deprecated read-only projection of the canonical analysis plan."""
    return self.analysis_plan


def set_analysis_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
    """Deprecated callable adapter; new code must call set_analysis_plan."""
    return self.set_analysis_plan(spec)
```

In `from_dict`, normalize `data.get("analysis_plan") or data.get("analysis_spec")` through `normalize_analysis_plan_contract(..., require_executable=False)`. If normalization fails, preserve `None` and let the caller re-plan rather than loading malformed state.

- [ ] **Step 5: Route both plan tools through normalization and one setter**

In `analysis_flow.py`, make `record_analysis_spec` call `normalize_analysis_plan_contract(..., require_executable=False)` and return both `analysis_plan_id` and `deprecated_adapter="record_analysis_spec"`. Make `record_analysis_plan` call the same function with `require_executable=True`. Both paths call only `state.set_analysis_plan`.

- [ ] **Step 6: Run focused tests and fix compatibility callers exposed by them**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_analysis_plan_consolidation.py tests/test_analysis_state_v2.py tests/test_analysis_plan_contracts.py tests/test_analysis_flow_tools.py
```

Expected: all tests pass. Update existing assertions that expected two serialized fields; do not weaken the new read-only assertion.

- [ ] **Step 7: Commit Task 1**

```powershell
git add -- src/data_agent/agent/analysis_plan_contracts.py src/data_agent/agent/analysis_state.py src/data_agent/tools/analysis_flow.py tests/test_analysis_plan_consolidation.py tests/test_analysis_state_v2.py tests/test_analysis_plan_contracts.py tests/test_analysis_flow_tools.py
git commit -m "refactor: consolidate analysis plan contract"
```

---

### Task 2: One Evidence-Requirements Contract From Load to Route

**Files:**
- Modify: `src/data_agent/agent/trust_contracts.py:299-372`
- Modify: `src/data_agent/agent/route_capabilities.py:147-190,304-438`
- Modify: `src/data_agent/agent/analysis_entry.py:22-180,288-328`
- Modify: `src/data_agent/agent/question_need_detector.py:332-422`
- Create: `tests/test_load_to_route_requirements.py`

**Interfaces:**
- Produces: `route_evidence_requirements(route: Mapping[str, Any]) -> list[str]` in `trust_contracts.py`.
- Writes: route proposals use `evidence_requirements` only.
- Reads: legacy stored proposals may fall back to `expected_evidence` only inside the shared reader.

- [ ] **Step 1: Write a failing real integration test**

```python
# tests/test_load_to_route_requirements.py
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.route_capabilities import build_route_capabilities
from data_agent.agent.trust_contracts import build_dataset_understanding_contract, build_route_proposals
import pandas as pd


def test_real_route_proposal_preserves_requirements_in_runtime_capabilities():
    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8),
        "revenue": [10, 12, 9, 14, 15, 16, 13, 18],
    })
    contract = build_dataset_understanding_contract(
        dataset="orders",
        df=frame,
        quality={"status": "usable"},
        interpretation_data={"time_columns": ["date"], "key_metrics": [{"column": "revenue"}]},
        cleaning_log_ids=[],
        preview_digest_id="preview_orders",
        detail_path="",
    )
    routes = build_route_proposals(contract)
    trend = next(route for route in routes if route["direction"] == "trend")
    state = AnalysisSessionState(session_id="route-contract")
    state.dataset_contracts = [contract]
    state.route_proposals = [trend]

    runtime = build_route_capabilities(state)
    item = next(route for route in runtime["executable"] if route["direction"] == "trend")

    assert trend["evidence_requirements"]
    assert "expected_evidence" not in trend
    assert item["evidence_requirements"] == trend["evidence_requirements"]
```

- [ ] **Step 2: Run the integration test and verify RED**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_load_to_route_requirements.py
```

Expected: failure because proposals currently write `expected_evidence` while consumers read `evidence_requirements`.

- [ ] **Step 3: Add the shared compatibility reader and canonical writer**

```python
def route_evidence_requirements(route: Mapping[str, Any]) -> list[str]:
    value = route.get("evidence_requirements")
    if not isinstance(value, list):
        value = route.get("expected_evidence")
    return [str(item).strip() for item in (value or []) if str(item).strip()]
```

Change `build_route_proposals` to emit only `evidence_requirements`. Replace direct reads in `route_capabilities.py`, `analysis_entry.py`, and `question_need_detector.py` with this function. Do not create another fallback helper.

- [ ] **Step 4: Run route and entry suites**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_load_to_route_requirements.py tests/test_trust_contracts.py tests/test_route_capabilities.py tests/test_analysis_entry.py tests/test_question_need_detector.py
```

Expected: all pass; update fixture payloads to the canonical field where the fixture represents newly produced data. Keep one explicit legacy fallback test.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- src/data_agent/agent/trust_contracts.py src/data_agent/agent/route_capabilities.py src/data_agent/agent/analysis_entry.py src/data_agent/agent/question_need_detector.py tests/test_load_to_route_requirements.py tests/test_trust_contracts.py tests/test_route_capabilities.py tests/test_analysis_entry.py tests/test_question_need_detector.py
git commit -m "fix: preserve route evidence requirements"
```

---

### Task 3: Deterministic Dataset Lineage and Safe Copy Preparation

**Files:**
- Create: `src/data_agent/agent/data_lineage.py`
- Modify: `src/data_agent/tools/data_clean.py:268-375`
- Create: `tests/test_data_preparation.py`

**Interfaces:**
- Produces: `frame_fingerprint(frame: pd.DataFrame) -> str`.
- Produces: immutable `TransformationRecord` with `to_dict()` and `finalize_transformation_record(record, *, derived_dataset_id, version) -> dict`.
- Produces: `prepare_analysis_copy(frame, *, logical_name, raw_dataset_id, source_fingerprint) -> tuple[pd.DataFrame, dict, list[dict], list[dict]]` in `data_clean.py`.
- Returns: `(copy, transformation_record, applied_operations, proposals)`.

- [ ] **Step 1: Write failing lineage and safe-copy tests**

```python
# tests/test_data_preparation.py
import pandas as pd
from pandas.testing import assert_frame_equal

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.tools.data_clean import prepare_analysis_copy


def test_prepare_analysis_copy_never_mutates_raw_frame():
    raw = pd.DataFrame({"rate": ["10%", "20%"], "label": ["A", "B"]})
    before = raw.copy(deep=True)

    prepared, record, applied, proposals = prepare_analysis_copy(
        raw,
        logical_name="orders",
        raw_dataset_id="raw_orders",
        source_fingerprint=frame_fingerprint(raw),
    )

    assert_frame_equal(raw, before)
    assert prepared is not raw
    assert prepared["rate"].tolist() == [0.1, 0.2]
    assert record["parent_dataset_id"] == "raw_orders"
    assert record["information_loss"] is False
    assert applied[0]["decision_policy"] == "auto_safe"
    assert proposals == []


def test_unit_bearing_numeric_conversion_is_proposed_not_applied():
    raw = pd.DataFrame({"amount": ["10K", "20K", "30K"]})

    prepared, record, applied, proposals = prepare_analysis_copy(
        raw,
        logical_name="orders",
        raw_dataset_id="raw_orders",
        source_fingerprint=frame_fingerprint(raw),
    )

    assert prepared["amount"].tolist() == raw["amount"].tolist()
    assert applied == []
    assert proposals
    assert proposals[0]["decision_policy"] == "confirmation_required"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_data_preparation.py
```

Expected: import failures because `data_lineage.py` and `prepare_analysis_copy` do not exist.

- [ ] **Step 3: Implement deterministic lineage primitives**

Create `data_lineage.py` with no workspace or tool imports:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def frame_fingerprint(frame: pd.DataFrame) -> str:
    schema = [(str(column), str(dtype)) for column, dtype in frame.dtypes.items()]
    hashable = frame.copy(deep=True)
    for column in hashable.select_dtypes(include=["object"]).columns:
        hashable[column] = hashable[column].map(
            lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if isinstance(value, (dict, list, tuple, set)) else value
        )
    values = pd.util.hash_pandas_object(hashable, index=True, categorize=True).values.tobytes()
    digest = hashlib.sha256(json.dumps(schema, ensure_ascii=False).encode("utf-8") + values).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class TransformationRecord:
    parent_dataset_id: str
    raw_dataset_id: str
    source_fingerprint: str
    logical_name: str
    operations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    affected_columns: tuple[str, ...] = field(default_factory=tuple)
    affected_row_count: int = 0
    before_after_metrics: dict[str, Any] = field(default_factory=dict)
    information_loss: bool = False
    decision_policy: str = "auto_safe"
    confirmation_status: str = "not_required"
    derived_dataset_id: str = ""
    version: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operations"] = [dict(item) for item in self.operations]
        payload["affected_columns"] = list(self.affected_columns)
        identity = {key: value for key, value in payload.items() if key not in {"created_at", "id"}}
        payload["id"] = "transform_" + hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return payload


def finalize_transformation_record(
    record: dict[str, Any],
    *,
    derived_dataset_id: str,
    version: int,
) -> dict[str, Any]:
    payload = dict(record)
    payload["derived_dataset_id"] = derived_dataset_id
    payload["version"] = version
    identity = {key: value for key, value in payload.items() if key not in {"created_at", "id"}}
    payload["id"] = "transform_" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return payload
```

- [ ] **Step 4: Implement safe preparation in data_clean.py**

Add `prepare_analysis_copy` using existing `infer_column_type` and `apply_conversion`. It must copy before inspection, apply only high-confidence `_AUTO_CONVERT_TYPES`, and reject any conversion that introduces new nulls:

```python
def prepare_analysis_copy(
    frame: pd.DataFrame,
    *,
    logical_name: str,
    raw_dataset_id: str,
    source_fingerprint: str,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    from data_agent.agent.data_lineage import TransformationRecord

    prepared = frame.copy(deep=True)
    applied: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    for column in prepared.columns:
        info = infer_column_type(prepared[column])
        suggested = info["suggested_type"]
        if suggested == "keep":
            continue
        if suggested in _AUTO_CONVERT_TYPES and info["confidence"] == "high":
            candidate = apply_conversion(prepared[column].copy(), suggested)
            new_nulls = int(candidate.isna().sum() - prepared[column].isna().sum())
            if new_nulls <= 0:
                prepared[column] = candidate
                applied.append({
                    "column": column,
                    "action": suggested,
                    "reason": info["reason"],
                    "decision_policy": "auto_safe",
                })
                continue
        proposals.append({
            "column": column,
            "suggested_type": suggested,
            "reason": info["reason"],
            "decision_policy": "confirmation_required",
        })

    record = TransformationRecord(
        parent_dataset_id=raw_dataset_id,
        raw_dataset_id=raw_dataset_id,
        source_fingerprint=source_fingerprint,
        logical_name=logical_name,
        operations=tuple(applied),
        affected_columns=tuple(item["column"] for item in applied),
        information_loss=False,
        decision_policy="auto_safe" if applied else "none",
    ).to_dict()
    return prepared, record, applied, proposals
```

Do not call `_try_coerce_object_to_numeric`; numeric and unit-bearing conversions remain proposals in this slice.

- [ ] **Step 5: Run preparation and existing type-inference tests**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_data_preparation.py tests/test_tools_comprehensive.py -k "auto_clean or type_conversion or data_preparation"
```

Expected: all selected tests pass. Existing direct `auto_clean` tests remain compatibility tests; production loading will stop calling it in Task 5.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- src/data_agent/agent/data_lineage.py src/data_agent/tools/data_clean.py tests/test_data_preparation.py
git commit -m "feat: add deterministic analysis copy preparation"
```

---

### Task 4: Workspace Raw Snapshots and Versioned Analysis Copies

**Files:**
- Modify: `src/data_agent/session/workspace.py:41-217,220-418,437-580`
- Create: `tests/test_workspace_dataset_versions.py`
- Modify: `tests/test_scoped_workspace.py`

**Interfaces:**
- Produces: `Workspace.register_raw_snapshot(name, frame, source_fingerprint) -> dict`.
- Produces: `Workspace.promote_analysis_copy(name, frame, raw_dataset_id, transformation_record) -> dict`.
- Produces: `get_raw_snapshot(raw_dataset_id)`, `get_dataset_version(dataset_id)`, `get_active_version_info(name)`, and `list_dataset_versions(name)`; all return copies/deep copies.
- Exposes the same methods through `WorkspaceProxy` with existing scope enforcement.

- [ ] **Step 1: Write failing workspace-version tests**

```python
# tests/test_workspace_dataset_versions.py
import pandas as pd
from pandas.testing import assert_frame_equal

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.session.workspace import Workspace


def test_raw_snapshot_is_hidden_immutable_and_distinct_from_active_copy():
    store = Workspace()
    raw = pd.DataFrame({"rate": ["10%", "20%"]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    prepared = pd.DataFrame({"rate": [0.1, 0.2]})
    active_info = store.promote_analysis_copy("orders", prepared, raw_info["dataset_id"], {
        "id": "transform_prepare",
        "parent_dataset_id": raw_info["dataset_id"],
        "information_loss": False,
    })

    raw.iloc[0, 0] = "99%"
    prepared.iloc[0, 0] = 9.9

    assert store.list_datasets()["orders"]["dataset_id"] == active_info["dataset_id"]
    assert_frame_equal(store.get_raw_snapshot(raw_info["dataset_id"]), pd.DataFrame({"rate": ["10%", "20%"]}))
    assert_frame_equal(store.get("orders"), pd.DataFrame({"rate": [0.1, 0.2]}))


def test_promoting_second_copy_preserves_first_version():
    store = Workspace()
    raw = pd.DataFrame({"x": [1, 2, None]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    first = store.promote_analysis_copy("orders", raw.copy(), raw_info["dataset_id"], {"id": "prepare"})
    second_frame = raw.fillna({"x": 0})
    second = store.promote_analysis_copy("orders", second_frame, raw_info["dataset_id"], {"id": "fill"})

    assert first["dataset_id"] != second["dataset_id"]
    assert store.get_dataset_version(first["dataset_id"])["x"].isna().sum() == 1
    assert store.get("orders")["x"].isna().sum() == 0
    assert [item["version"] for item in store.list_dataset_versions("orders")] == [1, 2]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_workspace_dataset_versions.py
```

Expected: attribute failures because version APIs do not exist.

- [ ] **Step 3: Add hidden stores and direct Workspace methods**

Initialize:

```python
self._raw_snapshots: dict[str, pd.DataFrame] = {}
self._dataset_versions: dict[str, pd.DataFrame] = {}
self._version_info: dict[str, dict[str, Any]] = {}
self._active_version_by_name: dict[str, str] = {}
```

Use identifiers based on logical name, monotonically increasing version, and the first 12 hex characters of `frame_fingerprint(frame)`. `register_raw_snapshot` stores a deep copy and returns metadata with `role="raw"`. `promote_analysis_copy` stores a deep copy in version history, updates `_datasets[name]` and `_active_version_by_name[name]`, and calls `finalize_transformation_record` so the final record identity includes its derived dataset ID and version.

Extend `list_datasets()` with `dataset_id`, `raw_dataset_id`, `version`, and `role="analysis_copy"`; raw snapshots remain hidden from this list.

- [ ] **Step 4: Expose scope-safe registry and proxy operations**

Add `register_raw`, `promote_copy`, `raw_snapshot`, `dataset_version`, `active_version`, and `dataset_versions` operations. Mark only the first two as mutating. Raw/version reads are allowed only in legacy scope or when the version metadata's `logical_name` is in `scope.allowed_datasets`. Every returned frame is a deep copy.

Add matching `WorkspaceProxy` methods:

```python
def register_raw_snapshot(self, name, frame, source_fingerprint): ...
def promote_analysis_copy(self, name, frame, raw_dataset_id, transformation_record): ...
def get_raw_snapshot(self, raw_dataset_id): ...
def get_dataset_version(self, dataset_id): ...
def get_active_version_info(self, name): ...
def list_dataset_versions(self, name): ...
```

- [ ] **Step 5: Extend removal and metadata persistence**

`remove(name)` deletes active aliases, version frames, version metadata, raw snapshots, and raw metadata associated with the logical name. `save_meta` includes active version identity, version summaries, raw dataset identity, and transformation records but never serializes frame values into JSON. Extend `persist_dataset` to persist both the active copy and its raw snapshot (`<name>.parquet|pkl` and `<name>__raw.parquet|pkl`) so restore does not fabricate a raw snapshot from cleaned values.

- [ ] **Step 6: Run workspace and scope tests**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_workspace_dataset_versions.py tests/test_scoped_workspace.py tests/test_tools_comprehensive.py -k "workspace or dataset_version or raw_snapshot"
```

Expected: all selected tests pass, including cross-context denial tests added for raw/version reads.

- [ ] **Step 7: Commit Task 4**

```powershell
git add -- src/data_agent/session/workspace.py tests/test_workspace_dataset_versions.py tests/test_scoped_workspace.py
git commit -m "feat: version workspace analysis datasets"
```

---

### Task 5: Load Raw First and Promote a Prepared Analysis Copy

**Files:**
- Modify: `src/data_agent/tools/data_io.py:350-620`
- Modify: `src/data_agent/agent/loop.py:503-580`
- Modify: `tests/test_trustworthy_load_data_integration.py`
- Create: `tests/test_load_data_analysis_copy.py`

**Interfaces:**
- Consumes: `frame_fingerprint`, `prepare_analysis_copy`, `WorkspaceProxy.register_raw_snapshot`, and `promote_analysis_copy`.
- Produces: source metadata keys `_raw_dataset_id`, `_active_dataset_id`, `_source_fingerprint`, and `_transformation_record` on the logical dataset.
- Preserves: `workspace.get(name)` and ordinary tools resolve the prepared active copy.

- [ ] **Step 1: Write a failing end-to-end load test**

```python
# tests/test_load_data_analysis_copy.py
import pandas as pd
from pandas.testing import assert_frame_equal

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.data_io import load_data


def test_load_data_keeps_raw_and_analyzes_prepared_copy(tmp_path):
    source = tmp_path / "rates.csv"
    pd.DataFrame({"rate": ["10%", "20%"], "label": ["A", "B"]}).to_csv(source, index=False)
    store = Workspace()
    state = AnalysisSessionState(session_id="copy-load")
    ctx = AgentContext(session_id="copy-load", workspace=store, analysis_state=state)

    with use_agent_context(ctx):
        result = load_data(str(source), name="rates")
        active = ctx.workspace.get("rates")
        info = ctx.workspace.get_active_version_info("rates")
        raw = ctx.workspace.get_raw_snapshot(info["raw_dataset_id"])

    assert "[analysis_copy]" in result
    assert raw["rate"].tolist() == ["10%", "20%"]
    assert active["rate"].tolist() == [0.1, 0.2]
    assert_frame_equal(raw, pd.DataFrame({"rate": ["10%", "20%"], "label": ["A", "B"]}))
    assert info["role"] == "analysis_copy"
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_load_data_analysis_copy.py
```

Expected: failure because load currently auto-cleans before workspace registration and version APIs are not used.

- [ ] **Step 3: Reorder load orchestration**

Replace the `auto_clean` call with:

```python
from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.tools.data_clean import prepare_analysis_copy

raw_df = df.copy(deep=True)
source_fingerprint = frame_fingerprint(raw_df)
raw_info = workspace.register_raw_snapshot(name, raw_df, source_fingerprint)
df, transformation_record, applied, needs_confirm = prepare_analysis_copy(
    raw_df,
    logical_name=name,
    raw_dataset_id=raw_info["dataset_id"],
    source_fingerprint=source_fingerprint,
)
active_info = workspace.promote_analysis_copy(
    name,
    df,
    raw_info["dataset_id"],
    transformation_record,
)
load_msg = f"数据集 '{name}' 已加载: {df.shape[0]} 行 x {df.shape[1]} 列"
```

Run the quality scan that reports user-uploaded data issues against `raw_df`; run interpretation and downstream analysis features against the active copy. Include both raw quality and applied-copy transformations in the persisted cleaning decision log.

- [ ] **Step 4: Store lineage metadata and concise user output**

Set `_raw_dataset_id`, `_active_dataset_id`, `_source_fingerprint`, and `_transformation_record`. Add a compact output block:

```text
[analysis_copy] raw=<raw id>; active=<active id>; version=<n>; safe_changes=<count>; proposals=<count> [/analysis_copy]
```

Do not expose raw snapshots as normal datasets or add all lineage payloads to the LLM context.

- [ ] **Step 5: Run loading, restore, and trust-workflow tests**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_load_data_analysis_copy.py tests/test_trustworthy_load_data_integration.py tests/test_comprehensive_analysis_flow.py -k "load_data or restore or workspace_meta"
```

Expected: all selected tests pass. Preserve source-path restore behavior and ensure restored active data is registered as an analysis copy.

When the original source exists, `_restore_workspace` reads it as the raw frame, registers it, prepares the copy, and restores the saved active backup only when its saved fingerprint matches the metadata. When the original source is unavailable, restore `<name>__raw.parquet|pkl` as raw and `<name>.parquet|pkl` as active. A legacy session with only the active backup treats that backup as raw once and records `migrated_from_legacy_backup=True`; it must not call `auto_clean` in place.

- [ ] **Step 6: Commit Task 5**

```powershell
git add -- src/data_agent/tools/data_io.py src/data_agent/agent/loop.py tests/test_load_data_analysis_copy.py tests/test_trustworthy_load_data_integration.py tests/test_comprehensive_analysis_flow.py
git commit -m "refactor: prepare analysis copies on load"
```

---

### Task 6: Copy-on-Write Cleaning With Material-Change Confirmation

**Files:**
- Modify: `src/data_agent/tools/data_clean.py:403-598`
- Create: `tests/test_clean_data_copy_on_write.py`
- Modify: `tests/test_tools_comprehensive.py:169-270`

**Interfaces:**
- Adds: `confirmed: bool = False` to `apply_type_conversion` and `clean_data`.
- Produces: candidate response with `status="confirmation_required"` and a deterministic transformation record when a material operation is unconfirmed.
- Promotes: confirmed changes as the next hidden version while retaining the existing logical dataset name.

- [ ] **Step 1: Write failing copy-on-write and confirmation tests**

```python
# tests/test_clean_data_copy_on_write.py
import json
import pandas as pd

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.session.workspace import Workspace


def _versioned_store():
    store = Workspace()
    raw = pd.DataFrame({"x": [1.0, None, 100.0], "id": [1, 2, 3]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active_info = store.promote_analysis_copy("orders", raw.copy(), raw_info["dataset_id"], {"id": "prepare"})
    return store, raw_info, active_info


def test_unconfirmed_imputation_does_not_promote_candidate(monkeypatch):
    from data_agent.tools import data_clean
    store, raw_info, active_info = _versioned_store()
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))

    assert result["status"] == "confirmation_required"
    assert store.get_active_version_info("orders")["dataset_id"] == active_info["dataset_id"]
    assert store.get("orders")["x"].isna().sum() == 1
    assert store.get_raw_snapshot(raw_info["dataset_id"])["x"].isna().sum() == 1


def test_confirmed_imputation_promotes_new_version_and_preserves_parent(monkeypatch):
    from data_agent.tools import data_clean
    store, _, first = _versioned_store()
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median", confirmed=True))
    second = store.get_active_version_info("orders")

    assert result["status"] == "applied"
    assert second["dataset_id"] != first["dataset_id"]
    assert store.get_dataset_version(first["dataset_id"])["x"].isna().sum() == 1
    assert store.get("orders")["x"].isna().sum() == 0
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_clean_data_copy_on_write.py
```

Expected: `confirmed` is not accepted and cleaning currently overwrites the logical dataset immediately.

- [ ] **Step 3: Build candidate first and classify materiality**

Refactor `clean_data` so all transformations occur on a local deep copy. Construct an operations list before promotion. Treat `outlier_strategy="mark"` with no frame mutation as non-material; treat deduplication, missing-value handling, capping, and row dropping as material.

Create a `TransformationRecord` with before/after row counts, missing counts, affected columns, and `information_loss=True` for deletion/capping/imputation. If material and `confirmed` is false, return the record plus summary without calling `workspace.promote_analysis_copy`.

- [ ] **Step 4: Promote only confirmed or non-material results**

On approval, obtain `active_info = workspace.get_active_version_info(name)`, call `promote_analysis_copy(name, candidate, active_info["raw_dataset_id"], record)`, and return:

```python
{
    "status": "applied",
    "dataset": name,
    "dataset_id": promoted["dataset_id"],
    "parent_dataset_id": active_info["dataset_id"],
    "transformation_record": promoted["transformation_record"],
    "original_rows": len(before),
    "final_rows": len(candidate),
}
```

If a legacy dataset has no version metadata, register its current frame as raw and prepare version 1 before applying the requested cleaning. This compatibility path must still preserve the original frame.

- [ ] **Step 5: Apply the same rule to type conversion**

`apply_type_conversion` builds a candidate and checks for newly introduced nulls or cardinality collapse. A fully successful, high-confidence conversion may promote without confirmation; `auto=True`, partial conversion, unit-bearing conversion, or information loss returns `confirmation_required` until `confirmed=True`.

- [ ] **Step 6: Run cleaning, workspace, and loading regression suites**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_clean_data_copy_on_write.py tests/test_data_preparation.py tests/test_workspace_dataset_versions.py tests/test_tools_comprehensive.py -k "clean or conversion or workspace or version"
```

Expected: all selected tests pass. Update old tests that expected in-place mutation to assert active-version promotion and parent preservation.

- [ ] **Step 7: Commit Task 6**

```powershell
git add -- src/data_agent/tools/data_clean.py tests/test_clean_data_copy_on_write.py tests/test_data_preparation.py tests/test_workspace_dataset_versions.py tests/test_tools_comprehensive.py
git commit -m "feat: make cleaning copy on write"
```

---

### Task 7: Migrate Runtime Callers and Close the Slice

**Files:**
- Modify: `src/data_agent/agent/analysis_flow_controller.py`
- Modify: `src/data_agent/agent/method_playbooks.py`
- Modify: `src/data_agent/agent/question_need_detector.py`
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Modify: `src/data_agent/agent/trust_workflow_runtime.py`
- Modify: `tests/test_analysis_state_v2.py`
- Modify: `tests/test_analysis_flow_tools.py`
- Modify: `tests/test_execution_control.py`
- Modify: `tests/test_method_playbooks.py`
- Modify: `tests/test_question_need_detector.py`
- Modify: `tests/test_stage3c0b_evidence_replenishment_flow.py`
- Modify: `tests/test_synthesis_policy.py`
- Modify: `tests/test_utf8_roundtrip.py`
- Modify: `tests/test_trust_workflow_runtime.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: canonical `state.analysis_plan`, route requirements, versioned datasets, and transformation records.
- Removes: production assignments to `state.analysis_spec` and new plan payloads using the legacy contract version.
- Documents: raw/copy dataset behavior and canonical plan ownership.

- [ ] **Step 1: Add an architecture regression test for the single writer**

```python
# append to tests/test_analysis_plan_consolidation.py
from pathlib import Path


def test_runtime_does_not_assign_analysis_spec_directly():
    root = Path(__file__).resolve().parents[1] / "src" / "data_agent"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if ".analysis_spec =" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_analysis_plan_consolidation.py::test_runtime_does_not_assign_analysis_spec_directly
```

Expected: failure listing remaining direct assignments.

- [ ] **Step 3: Migrate runtime reads and writes**

Replace `state.analysis_spec or {}` reads with `state.analysis_plan or {}` in runtime modules. Replace `set_analysis_spec` calls with `set_analysis_plan`. Remove direct assignments and update confirmation identifiers to use `analysis_plan_id`; keep inbound legacy JSON keys accepted only in the normalization adapter.

- [ ] **Step 4: Document current behavior without historical-stage framing**

Update `CLAUDE.md` to state:

```markdown
- Analysis planning has one canonical `AnalysisPlan` contract; legacy `AnalysisSpec` payloads are normalized at the tool/session boundary.
- `load_data` retains an immutable raw snapshot and exposes a versioned analysis-ready copy under the user's logical dataset name.
- Material cleaning operations create candidates and require confirmation before promotion; prior versions remain available for audit.
```

- [ ] **Step 5: Run focused slice verification**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_analysis_plan_consolidation.py tests/test_load_to_route_requirements.py tests/test_data_preparation.py tests/test_workspace_dataset_versions.py tests/test_load_data_analysis_copy.py tests/test_clean_data_copy_on_write.py tests/test_trustworthy_load_data_integration.py
```

Expected: all pass with no deselected tests.

- [ ] **Step 6: Run broad regression suites**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q tests/test_analysis_state_v2.py tests/test_analysis_plan_contracts.py tests/test_analysis_flow_tools.py tests/test_route_capabilities.py tests/test_analysis_entry.py tests/test_question_need_detector.py tests/test_scoped_workspace.py tests/test_tools_comprehensive.py tests/test_comprehensive_analysis_flow.py
```

Expected: all pass. Pytest cache permission warnings are environmental; test failures are not.

- [ ] **Step 7: Run repository checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only files in this implementation slice are modified, while pre-existing `artifacts/` and `tmp/` remain untracked and untouched.

- [ ] **Step 8: Commit Task 7**

```powershell
git add -- src/data_agent/agent/analysis_flow_controller.py src/data_agent/agent/method_playbooks.py src/data_agent/agent/question_need_detector.py src/data_agent/agent/synthesis_policy.py src/data_agent/agent/trust_workflow_runtime.py tests/test_analysis_state_v2.py tests/test_analysis_flow_tools.py tests/test_execution_control.py tests/test_method_playbooks.py tests/test_question_need_detector.py tests/test_stage3c0b_evidence_replenishment_flow.py tests/test_synthesis_policy.py tests/test_utf8_roundtrip.py tests/test_trust_workflow_runtime.py CLAUDE.md
git commit -m "refactor: complete analysis contract migration"
```

---

## Completion Gate

Before claiming this slice complete:

1. Read and apply `superpowers:verification-before-completion`.
2. Re-run the focused slice command from Task 7 Step 5.
3. Re-run the broad regression command from Task 7 Step 6.
4. Run `git diff --check` and inspect `git status --short`.
5. Confirm the raw snapshot remains byte-for-byte equivalent at the DataFrame value/dtype level in the loading and cleaning tests.
6. Confirm no production module assigns `analysis_spec` and no newly generated plan writes the legacy version.
7. Confirm ordinary tools still resolve the logical dataset name to the active analysis copy.
8. Report any compatibility adapters that remain and the exact removal condition; do not call the migration complete while two writable paths remain.
