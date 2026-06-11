# Multi-File Session Data Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a quality-protective multi-file workflow where session files accumulate in a data pool, current analysis runs against an active bundle, uncertain file relationships pause through structured confirmation, and recommendations stay scoped to the active bundle.

**Architecture:** Extend `AnalysisSessionState` with compact data-pool and bundle references, add a deterministic relationship detector, then route existing recommendation, trust-view, and question-need logic through the active bundle. Keep raw previews out of prompt context by storing only compact summaries in state and artifact refs.

**Tech Stack:** Python dataclasses/JSON state, pytest, Flask blueprints, existing analysis/trust workflow modules, existing Alpine.js trust inspector view.

---

## File Structure

- Create `src/data_agent/agent/data_bundle.py`
  - Builds file records, bundle records, relationship records, compact bundle summaries, and deterministic relationship classifications.
- Modify `src/data_agent/agent/analysis_state.py`
  - Add `data_pool`, `dataset_bundles`, `file_relationships`, `active_bundle_id`, and bundle helper methods.
- Modify `src/data_agent/agent/question_need_detector.py`
  - Add hard-question detection for file scope, file relationship, join logic, and file exclusion confirmations.
- Modify `src/data_agent/agent/analysis_entry.py`
  - Make entry decisions respect pending file relationship confirmations and active bundle scope.
- Modify `src/data_agent/agent/route_capabilities.py`
  - Filter executable/exploratory recommendations by active bundle datasets instead of only `active_dataset`.
- Modify `src/data_agent/agent/trust_view.py`
  - Surface active bundle, session data pool, relationship status, and confirmation gate in the trust inspector model.
- Modify `src/data_agent/agent/loop.py`
  - Replace broad dataset profile injection with compact active-bundle/data-pool summaries.
- Modify `src/data_agent/tools/data_io.py`
  - Register loaded files/datasets into the data pool and update bundle state after `load_data`.
- Modify `src/data_agent/web/static/js/app.js`
  - Keep uploaded file metadata in the message payload where possible and refresh trust view after upload.
- Modify `src/data_agent/web/templates/index.html`
  - Display current analysis bundle separately from available session files.
- Add `tests/test_data_bundle.py`
  - Deterministic relationship and bundle-state tests.
- Extend `tests/test_analysis_state_v2.py`
  - Serialization and helper method tests.
- Extend `tests/test_question_need_detector.py`
  - File-scope and file-relationship confirmation tests.
- Extend `tests/test_route_capabilities.py`
  - Active-bundle scoping tests.
- Extend `tests/test_trust_view.py`
  - Trust inspector bundle/data-pool view model tests.
- Extend `tests/test_trust_inspector_ui.py`
  - Static UI assertions for bundle and data-pool sections.

---

### Task 1: Add Bundle State Model

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Test: `tests/test_analysis_state_v2.py`

- [ ] **Step 1: Write failing serialization test**

Add this test to `tests/test_analysis_state_v2.py`:

```python
def test_data_pool_and_bundle_round_trip():
    state = AnalysisSessionState(session_id="bundle_state")
    file_ref = state.add_data_pool_file({
        "file_id": "file_orders",
        "filename": "orders.xlsx",
        "dataset": "orders",
        "row_count": 10,
        "column_count": 3,
        "key_fields": ["user_id"],
        "time_range": {"start": "2026-04-01", "end": "2026-04-30"},
    })
    bundle = state.set_active_bundle({
        "bundle_id": "bundle_orders_v1",
        "label": "orders",
        "file_ids": [file_ref["file_id"]],
        "dataset_names": ["orders"],
        "version": 1,
        "relationship_status": "linked",
    })
    state.add_file_relationship({
        "relationship_id": "rel_orders",
        "file_ids": ["file_orders"],
        "status": "linked",
        "confidence": "high",
        "evidence": ["single file active bundle"],
    })

    restored = AnalysisSessionState.from_dict(state.to_dict(), "bundle_state")

    assert restored.data_pool[0]["file_id"] == "file_orders"
    assert restored.dataset_bundles[0]["bundle_id"] == "bundle_orders_v1"
    assert restored.active_bundle_id == bundle["bundle_id"]
    assert restored.file_relationships[0]["status"] == "linked"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_analysis_state_v2.py::test_data_pool_and_bundle_round_trip -q`

Expected: FAIL because `AnalysisSessionState` has no bundle fields or helper methods.

- [ ] **Step 3: Add minimal state fields and helpers**

In `AnalysisSessionState`, add fields:

```python
    data_pool: list[dict[str, Any]] = field(default_factory=list)
    dataset_bundles: list[dict[str, Any]] = field(default_factory=list)
    file_relationships: list[dict[str, Any]] = field(default_factory=list)
    active_bundle_id: str = ""
```

Update `from_dict`:

```python
            data_pool=list(data.get("data_pool") or []),
            dataset_bundles=list(data.get("dataset_bundles") or []),
            file_relationships=list(data.get("file_relationships") or []),
            active_bundle_id=data.get("active_bundle_id") or "",
```

Update `to_dict`:

```python
            "data_pool": self.data_pool,
            "dataset_bundles": self.dataset_bundles,
            "file_relationships": self.file_relationships,
            "active_bundle_id": self.active_bundle_id,
```

Add helper methods:

```python
    def add_data_pool_file(self, ref: dict[str, Any]) -> dict[str, Any]:
        item = self._upsert_ref(self.data_pool, ref)
        item.setdefault("file_id", item.get("id"))
        item.setdefault("status", "available")
        return item

    def set_active_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        item = self._upsert_ref(self.dataset_bundles, bundle)
        bundle_id = str(item.get("bundle_id") or item.get("id") or "")
        item["bundle_id"] = bundle_id
        self.active_bundle_id = bundle_id
        datasets = item.get("dataset_names") if isinstance(item.get("dataset_names"), list) else []
        if datasets:
            self.set_active_dataset(str(datasets[0]), related_ref_id=bundle_id)
        else:
            self.active_scope = _normalize_active_scope(self.active_scope)
            self.active_scope["active_mode"] = "data_loaded"
            self.active_scope["updated_at"] = _now()
        return item

    def active_bundle(self) -> dict[str, Any] | None:
        for bundle in self.dataset_bundles:
            if bundle.get("bundle_id") == self.active_bundle_id or bundle.get("id") == self.active_bundle_id:
                return bundle
        return None

    def add_file_relationship(self, relationship: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.file_relationships, relationship)
```

- [ ] **Step 4: Run focused state tests**

Run: `pytest tests/test_analysis_state_v2.py::test_data_pool_and_bundle_round_trip -q`

Expected: PASS.

- [ ] **Step 5: Run full state tests**

Run: `pytest tests/test_analysis_state_v2.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/agent/analysis_state.py tests/test_analysis_state_v2.py
git commit -m "Add multi-file bundle state"
```

---

### Task 2: Add Deterministic File Relationship Detector

**Files:**
- Create: `src/data_agent/agent/data_bundle.py`
- Test: `tests/test_data_bundle.py`

- [ ] **Step 1: Write failing detector tests**

Create `tests/test_data_bundle.py`:

```python
from data_agent.agent.data_bundle import classify_file_relationship, compact_bundle_summary


def test_related_files_link_on_shared_id_and_theme():
    existing = [{
        "file_id": "orders",
        "filename": "省钱卡订单.xlsx",
        "dataset": "orders",
        "key_fields": ["user_id"],
        "time_fields": ["支付时间"],
        "time_range": {"start": "2026-04-01", "end": "2026-05-01"},
    }]
    new_files = [{
        "file_id": "flow",
        "filename": "省钱卡用户流水.xlsx",
        "dataset": "flow",
        "key_fields": ["user_id"],
        "time_fields": ["支付时间"],
        "time_range": {"start": "2026-04-10", "end": "2026-05-10"},
    }]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "linked"
    assert result["confidence"] in {"medium", "high"}
    assert "user_id" in " ".join(result["evidence"])


def test_possible_relationship_requires_confirmation_for_ambiguous_ids():
    existing = [{"file_id": "orders", "filename": "订单.xlsx", "key_fields": ["id"]}]
    new_files = [{"file_id": "coupon", "filename": "代金券明细.xlsx", "key_fields": ["id"]}]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True
    assert result["confirmation_type"] == "file_relationship_confirmation"


def test_user_latest_only_creates_single_file_summary():
    bundle = {
        "bundle_id": "bundle_latest",
        "label": "latest upload only",
        "file_ids": ["latest"],
        "dataset_names": ["latest_dataset"],
        "relationship_status": "user_scoped",
        "version": 1,
    }

    summary = compact_bundle_summary(bundle, data_pool=[{
        "file_id": "latest",
        "filename": "latest.xlsx",
        "row_count": 20,
        "column_count": 5,
    }])

    assert "latest.xlsx" in summary
    assert "20 rows x 5 cols" in summary
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_data_bundle.py -q`

Expected: FAIL because `data_bundle.py` does not exist.

- [ ] **Step 3: Implement detector**

Create `src/data_agent/agent/data_bundle.py`:

```python
"""Session data-pool and active-bundle helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any


STRONG_ID_FIELDS = {"user_id", "userid", "uid", "order_id", "device_id", "account_id"}
WEAK_ID_FIELDS = {"id", "编号", "序号"}


def stable_file_id(filename: str, dataset: str = "") -> str:
    payload = f"{filename}|{dataset}".encode("utf-8")
    return "file_" + hashlib.sha1(payload).hexdigest()[:10]


def classify_file_relationship(
    new_files: list[dict[str, Any]],
    existing_files: list[dict[str, Any]],
    user_input: str = "",
) -> dict[str, Any]:
    if not new_files:
        return _relationship("insufficient_preview", "low", [], ["No new file profile is available."])
    if _latest_only_requested(user_input):
        return _relationship(
            "linked",
            "high",
            ["User explicitly scoped analysis to the latest uploaded file."],
            [],
            relationship_mode="user_scoped_latest_only",
        )
    if not existing_files:
        return _relationship("linked", "high", ["First available file set in the session."], [])

    shared_strong_ids = _shared_fields(new_files, existing_files, STRONG_ID_FIELDS)
    shared_weak_ids = _shared_fields(new_files, existing_files, WEAK_ID_FIELDS)
    theme_overlap = _theme_overlap(new_files, existing_files)
    time_overlap = _has_time_overlap(new_files, existing_files)

    evidence: list[str] = []
    uncertainty: list[str] = []
    if shared_strong_ids:
        evidence.append("Shared strong key fields: " + ", ".join(shared_strong_ids))
    if theme_overlap:
        evidence.append("Filenames share business theme keywords.")
    if time_overlap:
        evidence.append("Time ranges overlap or are compatible.")
    if shared_weak_ids:
        uncertainty.append("Only weak generic id fields overlap: " + ", ".join(shared_weak_ids))

    if shared_strong_ids and (theme_overlap or time_overlap):
        return _relationship("linked", "high", evidence, uncertainty)
    if shared_strong_ids:
        return _relationship("possibly_linked", "medium", evidence, ["Shared IDs exist but business role is unclear."], True)
    if shared_weak_ids or theme_overlap:
        return _relationship("possibly_linked", "low", evidence, uncertainty or ["Relationship may affect analysis scope."], True)
    return _relationship(
        "independent",
        "medium",
        ["No strong shared keys or business theme overlap detected."],
        ["User may know an external relationship not visible in the file profiles."],
        True,
        confirmation_type="file_exclusion_confirmation",
    )


def compact_bundle_summary(bundle: dict[str, Any], data_pool: list[dict[str, Any]], limit: int = 5) -> str:
    file_ids = {str(item) for item in bundle.get("file_ids", []) if item}
    lines = [
        f"- active_bundle: {bundle.get('bundle_id') or bundle.get('id') or '-'}",
        f"- label: {bundle.get('label') or '-'}",
        f"- version: {bundle.get('version') or 1}",
        f"- relationship_status: {bundle.get('relationship_status') or '-'}",
    ]
    matched = [item for item in data_pool if str(item.get("file_id") or item.get("id")) in file_ids]
    for item in matched[:limit]:
        rows = item.get("row_count", "?")
        cols = item.get("column_count", "?")
        fields = item.get("key_fields") if isinstance(item.get("key_fields"), list) else []
        lines.append(f"  - {item.get('filename') or item.get('dataset')}: {rows} rows x {cols} cols; keys={', '.join(map(str, fields[:4])) or '-'}")
    return "\n".join(lines)


def _relationship(
    status: str,
    confidence: str,
    evidence: list[str],
    uncertainties: list[str],
    requires_confirmation: bool = False,
    confirmation_type: str = "file_relationship_confirmation",
    relationship_mode: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "uncertainties": uncertainties,
        "requires_confirmation": requires_confirmation,
        "confirmation_type": confirmation_type if requires_confirmation else "",
        "relationship_mode": relationship_mode,
    }


def _latest_only_requested(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in ("only analyze the latest", "only use the latest", "只分析刚上传", "只分析最新"))


def _shared_fields(left: list[dict[str, Any]], right: list[dict[str, Any]], allowed: set[str]) -> list[str]:
    left_fields = _field_set(left)
    right_fields = _field_set(right)
    return sorted((left_fields & right_fields) & {field.lower() for field in allowed})


def _field_set(items: list[dict[str, Any]]) -> set[str]:
    fields: set[str] = set()
    for item in items:
        for key in ("key_fields", "time_fields", "columns"):
            value = item.get(key)
            if isinstance(value, list):
                fields.update(str(field).strip().lower() for field in value if str(field).strip())
    return fields


def _theme_overlap(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    return bool(_theme_tokens(left) & _theme_tokens(right))


def _theme_tokens(items: list[dict[str, Any]]) -> set[str]:
    tokens: set[str] = set()
    for item in items:
        text = f"{item.get('filename') or ''} {item.get('dataset') or ''}".lower()
        tokens.update(token for token in re.split(r"[\W_]+", text) if len(token) >= 2)
        for keyword in ("省钱卡", "订单", "用户", "流水", "代金券", "游戏", "留存", "互推"):
            if keyword in text:
                tokens.add(keyword)
    return tokens


def _has_time_overlap(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    for a in left:
        a_range = a.get("time_range") if isinstance(a.get("time_range"), dict) else {}
        for b in right:
            b_range = b.get("time_range") if isinstance(b.get("time_range"), dict) else {}
            if a_range.get("start") and a_range.get("end") and b_range.get("start") and b_range.get("end"):
                return str(a_range["start"]) <= str(b_range["end"]) and str(b_range["start"]) <= str(a_range["end"])
    return False
```

- [ ] **Step 4: Run detector tests**

Run: `pytest tests/test_data_bundle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/agent/data_bundle.py tests/test_data_bundle.py
git commit -m "Add file relationship detector"
```

---

### Task 3: Register Loaded Data Into Pool And Bundle

**Files:**
- Modify: `src/data_agent/tools/data_io.py`
- Test: `tests/test_data_bundle.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_data_bundle.py`:

```python
import pandas as pd


def test_loaded_dataset_registers_data_pool_and_active_bundle(tmp_path, clean_workspace):
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.tools.data_io import load_data

    csv_path = tmp_path / "orders.csv"
    pd.DataFrame({
        "user_id": [1, 2],
        "paid_at": ["2026-04-01", "2026-04-02"],
        "amount": [12, 45],
    }).to_csv(csv_path, index=False)

    state = AnalysisSessionState(session_id="load_bundle")
    ctx = AgentContext(session_id="load_bundle")
    ctx.analysis_state = state

    with use_agent_context(ctx):
        result = load_data(str(csv_path), name="orders")

    assert result.success
    assert state.data_pool
    assert state.active_bundle_id
    assert state.active_bundle()["dataset_names"] == ["orders"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_data_bundle.py::test_loaded_dataset_registers_data_pool_and_active_bundle -q`

Expected: FAIL because `load_data` does not register data-pool/bundle records.

- [ ] **Step 3: Update `load_data` after successful contract creation**

In `src/data_agent/tools/data_io.py`, after dataset contract and preview refs are added to state, call helper logic like:

```python
from data_agent.agent.data_bundle import stable_file_id, classify_file_relationship

file_id = stable_file_id(str(path.name), name)
file_ref = state.add_data_pool_file({
    "file_id": file_id,
    "filename": path.name,
    "dataset": name,
    "row_count": int(len(df)),
    "column_count": int(len(df.columns)),
    "columns": [str(column) for column in df.columns[:30]],
    "key_fields": contract.get("field_roles", {}).get("ids", []),
    "time_fields": contract.get("field_roles", {}).get("date", []),
    "status": "loaded",
})
existing = [item for item in state.data_pool if item.get("file_id") != file_id]
relationship = classify_file_relationship([file_ref], existing)
relationship["relationship_id"] = f"rel_{file_id}"
relationship["file_ids"] = [file_id]
state.add_file_relationship(relationship)
if not relationship.get("requires_confirmation"):
    existing_bundle = state.active_bundle()
    if existing_bundle and relationship.get("status") == "linked":
        file_ids = list(dict.fromkeys(list(existing_bundle.get("file_ids") or []) + [file_id]))
        dataset_names = list(dict.fromkeys(list(existing_bundle.get("dataset_names") or []) + [name]))
        state.set_active_bundle({
            **existing_bundle,
            "file_ids": file_ids,
            "dataset_names": dataset_names,
            "version": int(existing_bundle.get("version") or 1) + 1,
            "relationship_status": relationship.get("status"),
        })
    else:
        state.set_active_bundle({
            "bundle_id": f"bundle_{file_id}_v1",
            "label": name,
            "file_ids": [file_id],
            "dataset_names": [name],
            "version": 1,
            "relationship_status": relationship.get("status"),
        })
```

If `relationship.requires_confirmation` is true, do not add the new file to the active bundle yet.

- [ ] **Step 4: Run focused integration test**

Run: `pytest tests/test_data_bundle.py::test_loaded_dataset_registers_data_pool_and_active_bundle -q`

Expected: PASS.

- [ ] **Step 5: Run existing data IO tests**

Run: `pytest tests/test_comprehensive_analysis_flow.py::TestDataLoading tests/test_real_data_integration.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/tools/data_io.py tests/test_data_bundle.py
git commit -m "Register loaded data in active bundle"
```

---

### Task 4: Add File Relationship Confirmation Gates

**Files:**
- Modify: `src/data_agent/agent/question_need_detector.py`
- Modify: `src/data_agent/agent/analysis_entry.py`
- Test: `tests/test_question_need_detector.py`
- Test: `tests/test_analysis_entry.py`

- [ ] **Step 1: Write failing question detector tests**

Add to `tests/test_question_need_detector.py`:

```python
def test_possible_file_relationship_requires_question():
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.question_need_detector import detect_question_need

    state = AnalysisSessionState(session_id="file_question", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "orders", "filename": "订单.xlsx", "dataset": "orders"},
        {"file_id": "coupon", "filename": "代金券.xlsx", "dataset": "coupon"},
    ]
    state.file_relationships = [{
        "relationship_id": "rel_coupon",
        "file_ids": ["orders", "coupon"],
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
        "uncertainties": ["Shared generic id fields need business confirmation."],
    }]
    intent = TurnIntent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")

    need = detect_question_need("analyze the uploaded data", intent, state)

    assert need["status"] == "hard_question"
    assert need["question_type"] == "file_relationship_confirmation"
    assert "uploaded" in need["reason"].lower() or need["reason"]


def test_latest_only_request_does_not_require_file_relationship_question():
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.question_need_detector import detect_question_need

    state = AnalysisSessionState(session_id="latest_only", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_coupon",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
    }]
    intent = TurnIntent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")

    need = detect_question_need("only analyze the latest uploaded file", intent, state)

    assert need["question_type"] != "file_relationship_confirmation"
```

- [ ] **Step 2: Run detector tests to verify failure**

Run: `pytest tests/test_question_need_detector.py::test_possible_file_relationship_requires_question tests/test_question_need_detector.py::test_latest_only_request_does_not_require_file_relationship_question -q`

Expected: first test FAIL because file relationships are ignored.

- [ ] **Step 3: Implement detector branch**

In `detect_question_need`, after consulting-intent guard and before route checks:

```python
    file_gate = _file_relationship_gate(user_input, state)
    if file_gate:
        return file_gate
```

Add helpers:

```python
def _file_relationship_gate(user_input: str, state: Any) -> dict[str, Any] | None:
    text = (user_input or "").lower()
    if any(phrase in text for phrase in ("only analyze the latest", "only use the latest", "只分析刚上传", "只分析最新")):
        return None
    for relationship in _list_attr(state, "file_relationships"):
        if not relationship.get("requires_confirmation"):
            continue
        status = _text(relationship.get("status"))
        confirmation_type = _text(relationship.get("confirmation_type")) or "file_relationship_confirmation"
        uncertainties = _text_list(relationship.get("uncertainties"))
        reason = "; ".join(uncertainties) or "The relationship between uploaded files can change analysis scope."
        if status in {"possibly_linked", "independent", "insufficient_preview"}:
            return _hard_gate(
                confirmation_type,
                reason,
                _file_question_text(confirmation_type),
                options=_file_question_options(confirmation_type),
                blocking_surfaces=BLOCKED_SURFACES_ALL,
                affected_routes=[],
            )
    return None


def _file_question_text(confirmation_type: str) -> str:
    if confirmation_type == "file_exclusion_confirmation":
        return "新上传的数据文件看起来可能不属于当前分析目标。请确认是否要纳入本轮分析。"
    if confirmation_type == "join_logic_confirmation":
        return "多文件综合分析需要确认关联字段、时间窗口或连接方式。请先确认后再继续。"
    return "新上传的数据文件可能与当前分析目标有关，但关系尚不确定。请确认这些文件是否应一起分析。"


def _file_question_options(confirmation_type: str) -> list[dict[str, str]]:
    if confirmation_type == "file_exclusion_confirmation":
        return [
            {"label": "纳入当前分析", "value": "include_in_active_bundle", "description": "把该文件作为当前目标的补充数据。"},
            {"label": "暂不纳入", "value": "exclude_from_active_bundle", "description": "保留在会话数据池，但不影响本轮分析。"},
        ]
    return [
        {"label": "一起分析", "value": "include_in_active_bundle", "description": "这些文件属于同一目标，可以综合分析。"},
        {"label": "分开分析", "value": "separate_bundle", "description": "这些文件保留在会话中，但本轮不混合使用。"},
        {"label": "只分析最新文件", "value": "latest_only", "description": "旧文件保留在会话数据池。"},
    ]
```

- [ ] **Step 4: Run detector tests**

Run: `pytest tests/test_question_need_detector.py -q`

Expected: PASS.

- [ ] **Step 5: Add entry-decision regression test**

Add to `tests/test_analysis_entry.py`:

```python
def test_analysis_entry_blocks_on_file_relationship_question():
    from data_agent.agent.analysis_entry import decide_analysis_entry
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.intent import TurnIntent

    state = AnalysisSessionState(session_id="entry_file_gate", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_1",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
        "uncertainties": ["File relationship is unclear."],
    }]
    intent = TurnIntent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")

    decision = decide_analysis_entry("analyze uploaded data", intent, state)

    assert decision["required_user_action"] == "ask_user_question"
    assert decision["confirmation_gate"]["confirmation_type"] == "file_relationship_confirmation"
```

- [ ] **Step 6: Run analysis entry test**

Run: `pytest tests/test_analysis_entry.py::test_analysis_entry_blocks_on_file_relationship_question -q`

Expected: PASS after detector integration.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/data_agent/agent/question_need_detector.py src/data_agent/agent/analysis_entry.py tests/test_question_need_detector.py tests/test_analysis_entry.py
git commit -m "Gate uncertain file relationships"
```

---

### Task 5: Scope Recommendations To Active Bundle

**Files:**
- Modify: `src/data_agent/agent/route_capabilities.py`
- Test: `tests/test_route_capabilities.py`

- [ ] **Step 1: Write failing route scoping test**

Add to `tests/test_route_capabilities.py`:

```python
def test_route_capabilities_use_active_bundle_datasets():
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.route_capabilities import build_route_capabilities

    state = AnalysisSessionState(session_id="bundle_routes", data_state="data_loaded")
    state.dataset_bundles = [{
        "bundle_id": "bundle_orders",
        "file_ids": ["orders_file"],
        "dataset_names": ["orders"],
        "version": 1,
    }]
    state.active_bundle_id = "bundle_orders"
    state.active_scope = {"active_mode": "data_loaded", "active_dataset": "", "active_route": "", "active_goal": ""}
    state.route_proposals = [
        {"id": "route_orders", "dataset": "orders", "direction": "trend", "label": "Order Trend"},
        {"id": "route_game", "dataset": "game", "direction": "cohort", "label": "Game Retention"},
    ]

    model = build_route_capabilities(state)

    assert [item["id"] for item in model["executable"]] == ["route_orders"]
```

- [ ] **Step 2: Run route test to verify failure**

Run: `pytest tests/test_route_capabilities.py::test_route_capabilities_use_active_bundle_datasets -q`

Expected: FAIL because route filtering only uses `active_dataset`.

- [ ] **Step 3: Add active bundle dataset filtering**

In `route_capabilities.py`, add:

```python
def _active_bundle_datasets(state: Any) -> set[str]:
    if state is None:
        return set()
    bundle = state.active_bundle() if hasattr(state, "active_bundle") else None
    if not isinstance(bundle, dict):
        return set()
    return {_text(item) for item in bundle.get("dataset_names", []) if _text(item)}
```

In `build_route_capabilities`, compute:

```python
    active_bundle_datasets = _active_bundle_datasets(state)
```

Pass it to `_executable_routes` and `_unsupported_exploratory`. Update filtering:

```python
        if active_bundle_datasets and dataset not in active_bundle_datasets:
            continue
        if not active_bundle_datasets and active_dataset and dataset != active_dataset:
            continue
```

Return metadata:

```python
        "active_bundle_id": _text(getattr(state, "active_bundle_id", "")),
        "active_bundle_datasets": sorted(active_bundle_datasets),
```

- [ ] **Step 4: Run route tests**

Run: `pytest tests/test_route_capabilities.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/agent/route_capabilities.py tests/test_route_capabilities.py
git commit -m "Scope recommendations to active bundle"
```

---

### Task 6: Surface Bundle State In Trust View And UI

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Test: `tests/test_trust_view.py`
- Test: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Write failing trust-view test**

Add to `tests/test_trust_view.py`:

```python
def test_trust_view_exposes_active_bundle_and_data_pool():
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.trust_view import build_trust_view

    state = AnalysisSessionState(session_id="trust_bundle", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "orders_file", "filename": "orders.xlsx", "dataset": "orders", "row_count": 2, "column_count": 3},
        {"file_id": "game_file", "filename": "game.xlsx", "dataset": "game", "row_count": 5, "column_count": 4},
    ]
    state.dataset_bundles = [{
        "bundle_id": "bundle_orders",
        "label": "orders",
        "file_ids": ["orders_file"],
        "dataset_names": ["orders"],
        "version": 1,
        "relationship_status": "linked",
    }]
    state.active_bundle_id = "bundle_orders"

    view = build_trust_view(state, session_id="trust_bundle")

    assert view["active_bundle"]["bundle_id"] == "bundle_orders"
    assert view["active_bundle"]["files"][0]["filename"] == "orders.xlsx"
    assert len(view["data_pool"]) == 2
```

- [ ] **Step 2: Run trust-view test to verify failure**

Run: `pytest tests/test_trust_view.py::test_trust_view_exposes_active_bundle_and_data_pool -q`

Expected: FAIL because view has no `active_bundle` or `data_pool`.

- [ ] **Step 3: Add view-model helpers**

In `trust_view.py`, add functions:

```python
def _data_pool_items(state: Any) -> list[dict[str, Any]]:
    items = _list_attr(state, "data_pool")
    return [{
        "file_id": _text(item.get("file_id") or item.get("id")),
        "filename": _text(item.get("filename")),
        "dataset": _text(item.get("dataset")),
        "rows": _number_or_zero(item.get("row_count")),
        "columns": _number_or_zero(item.get("column_count")),
        "status": _text(item.get("status") or "available"),
    } for item in items]


def _active_bundle_view(state: Any, data_pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    bundle = state.active_bundle() if hasattr(state, "active_bundle") else None
    if not isinstance(bundle, dict):
        return None
    file_ids = {_text(item) for item in bundle.get("file_ids", [])}
    files = [item for item in data_pool if item["file_id"] in file_ids]
    return {
        "bundle_id": _text(bundle.get("bundle_id") or bundle.get("id")),
        "label": _text(bundle.get("label")),
        "version": _number_or_zero(bundle.get("version")),
        "relationship_status": _text(bundle.get("relationship_status")),
        "dataset_names": _text_list(bundle.get("dataset_names")),
        "files": files,
    }
```

In `build_trust_view`, compute and return:

```python
    data_pool = _data_pool_items(state)
    active_bundle = _active_bundle_view(state, data_pool)
```

Return keys:

```python
        "data_pool": data_pool,
        "active_bundle": active_bundle,
```

Also add empty values in `_empty_view`:

```python
        "data_pool": [],
        "active_bundle": None,
```

- [ ] **Step 4: Run trust-view tests**

Run: `pytest tests/test_trust_view.py -q`

Expected: PASS.

- [ ] **Step 5: Add static UI assertions**

Add to `tests/test_trust_inspector_ui.py`:

```python
def test_trust_panel_has_active_bundle_and_data_pool_sections():
    html = Path("src/data_agent/web/templates/index.html").read_text(encoding="utf-8")

    assert "active_bundle" in html or "activeBundle" in html
    assert "当前分析集合" in html
    assert "会话数据池" in html
```

- [ ] **Step 6: Update template and JS labels**

In the current-data section of `index.html`, add display blocks for:

```html
<div x-show="trustView && trustView.active_bundle" class="trust-data-item">
  <div class="flex items-center justify-between gap-2">
    <span class="font-medium text-stone-700 dark:text-stone-200">当前分析集合</span>
    <span class="trust-pill" x-text="'v' + ((trustView.active_bundle && trustView.active_bundle.version) || 1)"></span>
  </div>
  <p class="text-xs text-stone-500 dark:text-stone-400 mt-1" x-text="activeBundleLabel()"></p>
</div>
<div x-show="trustView && trustView.data_pool && trustView.data_pool.length" class="trust-data-item">
  <div class="flex items-center justify-between gap-2">
    <span class="font-medium text-stone-700 dark:text-stone-200">会话数据池</span>
    <span class="trust-pill" x-text="trustView.data_pool.length"></span>
  </div>
</div>
```

In `app.js`, add:

```javascript
activeBundleLabel() {
    const bundle = this.trustView && this.trustView.active_bundle;
    if (!bundle) return '暂无当前分析集合';
    const files = (bundle.files || []).map((file) => file.filename || file.dataset).filter(Boolean);
    return files.length ? files.join(' + ') : (bundle.label || bundle.bundle_id || '当前分析集合');
},
```

- [ ] **Step 7: Run UI static tests**

Run: `pytest tests/test_trust_inspector_ui.py -q`

Expected: PASS.

- [ ] **Step 8: Validate JS syntax**

Run: `node --check src\data_agent\web\static\js\app.js`

Expected: no syntax errors.

- [ ] **Step 9: Commit**

Run:

```bash
git add src/data_agent/agent/trust_view.py src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js tests/test_trust_view.py tests/test_trust_inspector_ui.py
git commit -m "Show active bundle in trust panel"
```

---

### Task 7: Keep Prompt Context Compact

**Files:**
- Modify: `src/data_agent/agent/loop.py`
- Test: `tests/test_execution_control.py`

- [ ] **Step 1: Write failing compact-context test**

Add to `tests/test_execution_control.py`:

```python
def test_prepare_analysis_turn_uses_compact_bundle_summary(monkeypatch):
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.loop import StructuredAgentLoop

    loop = StructuredAgentLoop(session_id="compact_bundle")
    state = AnalysisSessionState(session_id="compact_bundle", data_state="data_loaded")
    state.data_pool = [
        {"file_id": f"file_{i}", "filename": f"file_{i}.xlsx", "dataset": f"ds_{i}", "row_count": 10, "column_count": 5, "columns": [f"col_{j}" for j in range(50)]}
        for i in range(12)
    ]
    state.dataset_bundles = [{
        "bundle_id": "bundle_1",
        "file_ids": ["file_0", "file_1"],
        "dataset_names": ["ds_0", "ds_1"],
        "version": 1,
        "relationship_status": "linked",
    }]
    state.active_bundle_id = "bundle_1"
    loop.context.analysis_state = state

    captured = {}

    def fake_plan_turn_intent(user_input, session_ctx):
        captured["session_ctx"] = session_ctx
        from data_agent.agent.intent import TurnIntent
        return TurnIntent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")

    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", fake_plan_turn_intent)
    monkeypatch.setattr("data_agent.agent.analysis_flow_controller.AnalysisFlowController.prepare_turn", lambda *args, **kwargs: None)
    monkeypatch.setattr("data_agent.agent.analysis_flow_controller.AnalysisFlowController.activate_tool_groups", lambda *args, **kwargs: [])

    loop._prepare_analysis_turn("analyze current data")

    assert "active_bundle" in captured["session_ctx"]
    assert "file_11.xlsx" not in captured["session_ctx"]
    assert len(captured["session_ctx"]) < 2000
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_execution_control.py::test_prepare_analysis_turn_uses_compact_bundle_summary -q`

Expected: FAIL because `_prepare_analysis_turn` builds context from all workspace datasets.

- [ ] **Step 3: Add compact state summary helper**

In `loop.py`, replace the raw dataset context block in `_prepare_analysis_turn` with:

```python
        session_ctx = self._analysis_scope_context()
```

Add method:

```python
    def _analysis_scope_context(self) -> str:
        state = getattr(self.context, "analysis_state", None)
        if state is not None and getattr(state, "active_bundle_id", ""):
            try:
                from data_agent.agent.data_bundle import compact_bundle_summary

                return compact_bundle_summary(state.active_bundle() or {}, getattr(state, "data_pool", []) or [])
            except Exception:
                pass
        workspace_obj = getattr(self.context, "workspace", None)
        if workspace_obj is None:
            from data_agent.session.workspace import workspace as workspace_obj
        try:
            datasets = workspace_obj.list_datasets()
        except Exception:
            return ""
        context_parts = []
        for name, info in list((datasets or {}).items())[:4]:
            columns = info.get("column_names") if isinstance(info, dict) else []
            context_parts.append(
                f"- {name}: {info.get('rows', '?')} rows x {info.get('columns', '?')} cols, "
                f"columns: {', '.join(str(c) for c in columns[:8])}"
            )
        return "\n".join(context_parts)
```

- [ ] **Step 4: Run compact-context test**

Run: `pytest tests/test_execution_control.py::test_prepare_analysis_turn_uses_compact_bundle_summary -q`

Expected: PASS.

- [ ] **Step 5: Run execution-control tests**

Run: `pytest tests/test_execution_control.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/agent/loop.py tests/test_execution_control.py
git commit -m "Compact multi-file analysis context"
```

---

### Task 8: Full Regression And Real Data Smoke Test

**Files:**
- No required source modifications unless tests reveal a defect.

- [ ] **Step 1: Run targeted regression suite**

Run:

```bash
pytest tests/test_data_bundle.py tests/test_analysis_state_v2.py tests/test_question_need_detector.py tests/test_analysis_entry.py tests/test_route_capabilities.py tests/test_trust_view.py tests/test_trust_inspector_ui.py tests/test_execution_control.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run real-data integration suite**

Run:

```bash
pytest tests/test_real_data_integration.py tests/test_mvp_real_data_fixtures.py tests/test_trustworthy_load_data_integration.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Validate frontend JS**

Run:

```bash
node --check src\data_agent\web\static\js\app.js
```

Expected: no syntax errors.

- [ ] **Step 4: Manual API smoke test with real files**

With the Flask service running at `http://127.0.0.1:5001/`, upload:

- `D:\Project\Daily\data-agent\reference\test_doc\省钱卡订单_20260507.xlsx`
- `D:\Project\Daily\data-agent\reference\test_doc\省钱卡用户最近流水_20260511.xlsx`
- `D:\Project\Daily\data-agent\reference\test_doc\游戏互推.xlsx`

Expected behavior:

- first file creates an active bundle,
- second file is linked or asks for relationship confirmation depending on detected keys,
- third file triggers file exclusion or relationship confirmation before being mixed,
- final recommendations are hidden while confirmation is pending,
- trust view shows active bundle and session data pool separately.

- [ ] **Step 5: Fix defects only if discovered**

If a defect appears, write a focused regression test first, then apply the smallest source change needed.

- [ ] **Step 6: Final commit if fixes were needed**

Run:

```bash
git status --short
git add <changed files>
git commit -m "Fix multi-file bundle regressions"
```

Only commit if Step 5 changed files.

---

## Self-Review

Spec coverage:

- Data pool default append: Task 1 and Task 3.
- Active bundle current scope: Task 1, Task 3, Task 5, Task 6.
- Relationship detection: Task 2.
- Structured confirmation for uncertainty: Task 4.
- Recommendation scoping: Task 5.
- Web/CLI-facing state: Task 6 and existing CLI summaries through Task 7 context.
- Context budget protection: Task 7.
- Real data verification: Task 8.

Quality safeguards:

- Uncertain relationships block recommendations and execution through existing confirmation gates.
- Active bundle filtering prevents stale historical routes from contaminating current recommendations.
- Raw multi-file previews are not injected into prompts; compact summaries are used instead.
- User override for latest-only analysis is supported without deleting older files.

No placeholders remain in task steps. Function names introduced in earlier tasks are reused consistently in later tasks.
