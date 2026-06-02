# Trustworthy Analysis Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP trustworthy analysis workflow: dataset contracts, cleaning decision logs, route proposals, data-aware intent refinement, and deterministic verification reports.

**Architecture:** Add small focused modules under `src/data_agent/agent/` and `src/data_agent/tools/` that reuse existing profiling, interpretation, quality, evidence, and synthesis state. Persist new records as session-local JSON artifacts and reference compact summaries from `AnalysisSessionState` so context compression preserves IDs instead of full details.

**Tech Stack:** Python 3.11, dataclasses, pandas, pytest, existing `AnalysisSessionState`, existing tool registry, existing workspace/session artifact helpers.

---

## File Structure

- Create `src/data_agent/agent/trust_contracts.py`
  - Owns dataclasses and builders for `CleaningDecisionLog`, `DatasetUnderstandingContract`, `PreviewDigest`, and `AnalysisRouteProposal`.
  - Reuses existing data feature and data understanding outputs; does not call LLMs.

- Create `src/data_agent/agent/intent_refinement.py`
  - Refines existing `TurnIntent` using dataset contracts and route proposals.
  - Keeps intent classification deterministic after the existing rule/LLM classifier runs.

- Create `src/data_agent/agent/verification.py`
  - Owns deterministic `VerificationReport` generation and claim strength classification.
  - Reads evidence records, route proposals, and cleaning decisions.

- Modify `src/data_agent/agent/analysis_state.py`
  - Add references to dataset contracts, cleaning logs, preview digests, route proposals, and verification reports.
  - Add helper methods for storing compact references.

- Modify `src/data_agent/tools/data_io.py`
  - After `load_data` performs current cleaning/profile/interpretation work, create the new MVP records and attach compact references to analysis state.

- Modify `src/data_agent/agent/prompts.py`
  - Inject compact contract and route summaries into guidance/analysis prompts through existing session context paths.

- Modify `src/data_agent/agent/synthesis_policy.py`
  - Read verification status and suppress or downgrade risky final-answer moves.

- Test files:
  - Create `tests/test_trust_contracts.py`
  - Create `tests/test_intent_refinement.py`
  - Create `tests/test_verification_layer.py`
  - Modify `tests/test_analysis_state_v2.py`
  - Add focused integration tests in `tests/test_data_features.py` or a new `tests/test_trustworthy_load_data_integration.py`

---

### Task 1: Extend AnalysisSessionState With Trustworthy Workflow References

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Test: `tests/test_analysis_state_v2.py`

- [ ] **Step 1: Write failing tests for new reference fields**

Add these tests to `tests/test_analysis_state_v2.py`:

```python
class TestTrustworthyWorkflowRefs:
    def test_default_trust_refs_are_empty(self):
        state = AnalysisSessionState(session_id="s1")
        assert state.dataset_contracts == []
        assert state.cleaning_logs == []
        assert state.preview_digests == []
        assert state.route_proposals == []
        assert state.verification_reports == []

    def test_to_dict_roundtrip_trust_refs(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_dataset_contract_ref({"id": "duc_main_001", "dataset": "main"})
        state.add_cleaning_log_ref({"id": "clean_main_001", "dataset": "main"})
        state.add_preview_digest_ref({"id": "preview_main_001", "dataset": "main"})
        state.add_route_proposal_ref({"id": "route_main_001", "direction": "trend"})
        state.add_verification_report_ref({"id": "verify_001", "overall_status": "pass"})

        restored = AnalysisSessionState.from_dict(state.to_dict(), "s1")

        assert restored.dataset_contracts == [{"id": "duc_main_001", "dataset": "main"}]
        assert restored.cleaning_logs == [{"id": "clean_main_001", "dataset": "main"}]
        assert restored.preview_digests == [{"id": "preview_main_001", "dataset": "main"}]
        assert restored.route_proposals == [{"id": "route_main_001", "direction": "trend"}]
        assert restored.verification_reports == [{"id": "verify_001", "overall_status": "pass"}]

    def test_summary_includes_trust_refs_counts(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_dataset_contract_ref({"id": "duc_main_001", "dataset": "main"})
        state.add_route_proposal_ref({"id": "route_main_001", "direction": "trend"})
        state.add_verification_report_ref({"id": "verify_001", "overall_status": "pass"})

        summary = analysis_state_summary(state)

        assert "dataset_contracts: 1" in summary
        assert "route_proposals: 1" in summary
        assert "verification_reports: 1" in summary
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_analysis_state_v2.py::TestTrustworthyWorkflowRefs -v
```

Expected: FAIL with `AttributeError: 'AnalysisSessionState' object has no attribute 'dataset_contracts'`.

- [ ] **Step 3: Add fields and helper methods**

Modify `AnalysisSessionState` in `src/data_agent/agent/analysis_state.py`:

```python
    dataset_contracts: list[dict[str, Any]] = field(default_factory=list)
    cleaning_logs: list[dict[str, Any]] = field(default_factory=list)
    preview_digests: list[dict[str, Any]] = field(default_factory=list)
    route_proposals: list[dict[str, Any]] = field(default_factory=list)
    verification_reports: list[dict[str, Any]] = field(default_factory=list)
```

Add these fields to `from_dict`:

```python
            dataset_contracts=list(data.get("dataset_contracts") or []),
            cleaning_logs=list(data.get("cleaning_logs") or []),
            preview_digests=list(data.get("preview_digests") or []),
            route_proposals=list(data.get("route_proposals") or []),
            verification_reports=list(data.get("verification_reports") or []),
```

Add these keys to `to_dict`:

```python
            "dataset_contracts": self.dataset_contracts,
            "cleaning_logs": self.cleaning_logs,
            "preview_digests": self.preview_digests,
            "route_proposals": self.route_proposals,
            "verification_reports": self.verification_reports,
```

Add helper methods:

```python
    def _upsert_ref(self, collection: list[dict[str, Any]], ref: dict[str, Any]) -> dict[str, Any]:
        item = dict(ref)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        ref_id = item.get("id")
        for idx, existing in enumerate(collection):
            if existing.get("id") == ref_id:
                collection[idx] = item
                return item
        collection.append(item)
        return item

    def add_dataset_contract_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        self.data_state = "data_loaded"
        return self._upsert_ref(self.dataset_contracts, ref)

    def add_cleaning_log_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.cleaning_logs, ref)

    def add_preview_digest_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.preview_digests, ref)

    def add_route_proposal_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.route_proposals, ref)

    def add_verification_report_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.verification_reports, ref)
```

Update `analysis_state_summary`:

```python
        f"- dataset_contracts: {len(state.dataset_contracts)}",
        f"- cleaning_logs: {len(state.cleaning_logs)}",
        f"- preview_digests: {len(state.preview_digests)}",
        f"- route_proposals: {len(state.route_proposals)}",
        f"- verification_reports: {len(state.verification_reports)}",
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_analysis_state_v2.py::TestTrustworthyWorkflowRefs -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/analysis_state.py tests/test_analysis_state_v2.py
git commit -m "feat: track trustworthy workflow refs in analysis state"
```

---

### Task 2: Add Dataset Contracts, Cleaning Logs, Preview Digests, and Route Proposals

**Files:**
- Create: `src/data_agent/agent/trust_contracts.py`
- Test: `tests/test_trust_contracts.py`

- [ ] **Step 1: Write failing tests for contract builders**

Create `tests/test_trust_contracts.py`:

```python
import pandas as pd

from data_agent.agent.trust_contracts import (
    build_cleaning_decision_log,
    build_dataset_understanding_contract,
    build_preview_digest,
    build_route_proposals,
)


def test_build_cleaning_decision_log_classifies_decision_levels():
    applied = [
        {"column": "date", "from": "object", "to": "datetime64[ns]", "action": "datetime", "reason": "date"},
        {"column": "amount", "from": "object", "to": "float64", "action": "numeric", "reason": "numeric"},
    ]
    needs_confirm = [
        {"column": "channel_code", "current_dtype": "int64", "suggested_type": "category_maybe", "reason": "low cardinality"}
    ]

    log = build_cleaning_decision_log("main", applied, needs_confirm)

    assert log["dataset"] == "main"
    assert log["summary"]["safe_auto"] == 1
    assert log["summary"]["notify_auto"] == 1
    assert log["summary"]["needs_confirmation"] == 1
    assert log["decisions"][0]["impact"] == "Enables time-aware analysis"


def test_build_preview_digest_limits_examples_and_records_risks():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8),
        "channel": ["a", "b"] * 4,
        "gmv": [1, 2, None, 4, 5, 6, 7, 8],
    })

    digest = build_preview_digest("main", df, max_rows=3)

    assert digest["dataset"] == "main"
    assert digest["sample_rows_count"] == 3
    assert "date" in digest["column_examples"]
    assert any("missing" in risk.lower() for risk in digest["risks"])


def test_build_dataset_understanding_contract_maps_supported_and_unsupported_analyses():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=20),
        "gmv": range(20),
        "channel": ["a", "b"] * 10,
    })
    quality = {
        "quality_score": 95,
        "block_issues": [],
        "warnings": [],
        "columns": {
            "date": {"type": "date", "missing_rate": 0},
            "gmv": {"type": "numeric", "missing_rate": 0},
            "channel": {"type": "categorical", "missing_rate": 0},
        },
    }
    interpretation = {
        "grain": "daily_aggregate",
        "columns_classified": {
            "time_columns": ["date"],
            "key_metrics": [{"column": "gmv"}],
            "rate_metrics": [],
            "dimensions": [{"column": "channel"}],
            "id_columns": [],
            "other_text": [],
        },
        "time_range": {"column": "date", "min": "2026-01-01", "max": "2026-01-20", "span_days": 19},
        "analysis_signals": {"has_time": True, "has_dimensions": True, "has_ids": False, "has_rates": False},
    }

    contract = build_dataset_understanding_contract(
        dataset="main",
        df=df,
        quality=quality,
        interpretation_data=interpretation,
        cleaning_log_ids=["clean_main_001"],
        preview_digest_id="preview_main_001",
        detail_path="tool_outputs/load_main_detail.json",
    )

    assert contract["field_roles"]["date"] == ["date"]
    assert contract["field_roles"]["metrics"] == ["gmv"]
    assert contract["field_roles"]["dimensions"] == ["channel"]
    assert "trend" in contract["supported_analyses"]
    assert any(item["type"] == "user_level_retention" for item in contract["unsupported_analyses"])


def test_build_route_proposals_adds_expected_evidence():
    contract = {
        "id": "duc_main_001",
        "dataset": "main",
        "field_roles": {
            "date": ["date"],
            "metrics": ["gmv"],
            "rate_metrics": [],
            "dimensions": ["channel"],
            "ids": [],
            "text": [],
            "unknown": [],
        },
        "supported_analyses": ["trend", "period_compare", "dimension_decomposition"],
        "quality": {"status": "ready"},
    }

    proposals = build_route_proposals(contract)

    assert proposals
    first = proposals[0]
    assert first["dataset_contract_id"] == "duc_main_001"
    assert "record_evidence_record" in first["tool_chain"]
    assert "limitations" in first["expected_evidence"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_trust_contracts.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'data_agent.agent.trust_contracts'`.

- [ ] **Step 3: Implement `trust_contracts.py`**

Create `src/data_agent/agent/trust_contracts.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def _new_id(prefix: str, dataset: str = "") -> str:
    base = f"{prefix}_{dataset}_" if dataset else f"{prefix}_"
    return base + uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _decision_level(action: str) -> str:
    if action in {"datetime", "percentage_to_float", "date_int_to_datetime", "bool"}:
        return "safe_auto"
    if action in {"numeric_with_suffix", "numeric", "object_to_numeric"}:
        return "notify_auto"
    return "needs_confirmation"


def _decision_impact(action: str) -> str:
    impacts = {
        "datetime": "Enables time-aware analysis",
        "date_int_to_datetime": "Enables time-aware analysis",
        "percentage_to_float": "Enables rate analysis",
        "bool": "Enables binary segmentation",
        "numeric": "Enables numeric metric analysis",
        "numeric_with_suffix": "Enables numeric metric analysis after unit parsing",
        "object_to_numeric": "Enables numeric metric analysis after coercion",
        "category_maybe": "Requires confirmation before treating as dimension",
    }
    return impacts.get(action, "May affect downstream analysis interpretation")


def build_cleaning_decision_log(
    dataset: str,
    applied: list[dict[str, Any]] | None,
    needs_confirm: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    summary = {"safe_auto": 0, "notify_auto": 0, "needs_confirmation": 0, "blocked": 0}

    for item in applied or []:
        action = str(item.get("action") or "")
        level = _decision_level(action)
        summary[level] += 1
        decisions.append({
            "column": item.get("column", ""),
            "decision_type": level,
            "from_dtype": item.get("from", ""),
            "to_dtype": item.get("to", ""),
            "action": action,
            "reason": item.get("reason", ""),
            "impact": _decision_impact(action),
        })

    for item in needs_confirm or []:
        action = str(item.get("suggested_type") or "needs_confirmation")
        summary["needs_confirmation"] += 1
        decisions.append({
            "column": item.get("column", ""),
            "decision_type": "needs_confirmation",
            "from_dtype": item.get("current_dtype", ""),
            "suggested_type": action,
            "reason": item.get("reason", ""),
            "sample": item.get("sample", []),
            "impact": _decision_impact(action),
        })

    return {
        "id": _new_id("clean", dataset),
        "dataset": dataset,
        "created_at": _now(),
        "decisions": decisions,
        "summary": summary,
    }


def build_preview_digest(dataset: str, df: pd.DataFrame, max_rows: int = 5) -> dict[str, Any]:
    sample = df.head(max_rows)
    column_examples: dict[str, list[Any]] = {}
    risks: list[str] = []
    notable_patterns: list[str] = []

    for col in df.columns:
        values = [_json_safe(v) for v in df[col].dropna().head(3).tolist()]
        column_examples[str(col)] = values
        missing = int(df[col].isna().sum())
        if missing:
            risks.append(f"Column '{col}' has {missing} missing values")
        nunique = int(df[col].nunique(dropna=True))
        notable_patterns.append(f"{col} has {nunique} unique values")

    return {
        "id": _new_id("preview", dataset),
        "dataset": dataset,
        "created_at": _now(),
        "sample_rows_count": len(sample),
        "sample_rows": [
            {str(k): _json_safe(v) for k, v in row.items()}
            for row in sample.to_dict(orient="records")
        ],
        "column_examples": column_examples,
        "notable_patterns": notable_patterns[:10],
        "risks": risks[:10],
    }


def _quality_status(quality: dict[str, Any]) -> str:
    if quality.get("block_issues"):
        return "blocked"
    if quality.get("warnings"):
        return "ready_with_warnings"
    return "ready"


def _field_roles(classified: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "date": list(classified.get("time_columns") or []),
        "metrics": [m.get("column") for m in classified.get("key_metrics", []) if m.get("column")],
        "rate_metrics": [m.get("column") for m in classified.get("rate_metrics", []) if m.get("column")],
        "dimensions": [d.get("column") for d in classified.get("dimensions", []) if d.get("column")],
        "ids": [i.get("column") for i in classified.get("id_columns", []) if i.get("column")],
        "text": list(classified.get("other_text") or []),
        "unknown": [],
    }


def _supported_analyses(signals: dict[str, Any]) -> list[str]:
    supported: list[str] = []
    if signals.get("has_time"):
        supported.extend(["trend", "period_compare"])
    if signals.get("has_dimensions"):
        supported.append("dimension_decomposition")
    if signals.get("has_ids"):
        supported.extend(["funnel", "cohort"])
    if signals.get("metric_count", 0) >= 2:
        supported.append("correlation")
    return sorted(set(supported))


def _unsupported_analyses(signals: dict[str, Any], grain: str) -> list[dict[str, str]]:
    unsupported: list[dict[str, str]] = []
    if not signals.get("has_ids") or "aggregate" in str(grain):
        unsupported.append({
            "type": "user_level_retention",
            "reason": "Data lacks user-level event history or is aggregate-grain",
        })
    if not signals.get("has_time"):
        unsupported.append({
            "type": "trend",
            "reason": "No time column was detected",
        })
    return unsupported


def build_dataset_understanding_contract(
    dataset: str,
    df: pd.DataFrame,
    quality: dict[str, Any],
    interpretation_data: dict[str, Any],
    cleaning_log_ids: list[str],
    preview_digest_id: str,
    detail_path: str = "",
) -> dict[str, Any]:
    classified = dict(interpretation_data.get("columns_classified") or {})
    signals = dict(interpretation_data.get("analysis_signals") or {})
    grain = str(interpretation_data.get("grain") or "unknown")
    roles = _field_roles(classified)

    return {
        "id": _new_id("duc", dataset),
        "dataset": dataset,
        "created_at": _now(),
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "field_roles": roles,
        "grain": grain,
        "quality": {
            "status": _quality_status(quality),
            "score": int(quality.get("quality_score", 0)),
            "blocks": list(quality.get("block_issues") or []),
            "warnings": list(quality.get("warnings") or []),
        },
        "time_range": interpretation_data.get("time_range"),
        "supported_analyses": _supported_analyses(signals),
        "unsupported_analyses": _unsupported_analyses(signals, grain),
        "cleaning_log_ids": list(cleaning_log_ids),
        "preview_digest_id": preview_digest_id,
        "detail_path": detail_path,
    }


def build_route_proposals(contract: dict[str, Any]) -> list[dict[str, Any]]:
    roles = contract.get("field_roles") or {}
    supported = set(contract.get("supported_analyses") or [])
    proposals: list[dict[str, Any]] = []

    def add(direction: str, label: str, required: list[str], optional: list[str], tools: list[str], evidence: list[str], risk: str, budget: str) -> None:
        missing_required = [field for field in required if field not in sum(roles.values(), [])]
        proposals.append({
            "id": _new_id("route", contract.get("dataset", "")),
            "dataset": contract.get("dataset", ""),
            "dataset_contract_id": contract.get("id", ""),
            "direction": direction,
            "user_facing_label": label,
            "why_recommended": f"Supported by detected fields: {', '.join(required + optional)}",
            "required_fields": required,
            "optional_fields": optional,
            "field_coverage": "complete" if not missing_required else "missing_required",
            "tool_chain": tools,
            "expected_evidence": evidence,
            "known_risks": [risk] if risk else [],
            "budget_level": budget,
        })

    if {"trend", "period_compare"}.intersection(supported):
        add(
            "trend_or_period_compare",
            "Trend or period comparison",
            roles.get("date", [])[:1] + roles.get("metrics", [])[:1],
            roles.get("dimensions", [])[:2],
            ["compare_periods", "record_evidence_record"],
            ["metric_delta", "period_comparability", "limitations"],
            "Period comparison is descriptive unless a valid control or causal design exists",
            "standard",
        )

    if "dimension_decomposition" in supported:
        add(
            "dimension_decomposition",
            "Dimension contribution diagnosis",
            roles.get("metrics", [])[:1],
            roles.get("dimensions", [])[:2],
            ["contribute_decomposition", "record_evidence_record"],
            ["dimension_contribution", "sample_size", "limitations"],
            "Contribution does not prove causal responsibility",
            "standard",
        )

    if "correlation" in supported:
        add(
            "correlation_scan",
            "Metric relationship scan",
            roles.get("metrics", [])[:2],
            [],
            ["correlation_analysis", "record_evidence_record"],
            ["correlation", "significance", "limitations"],
            "Correlation is not causal evidence",
            "lightweight",
        )

    return proposals


def write_trust_artifact(session_dir: Path, kind: str, payload: dict[str, Any]) -> str:
    out_dir = session_dir / "trust_workflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{kind}_{payload.get('id', uuid.uuid4().hex[:8])}.json"
    path = out_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return f"trust_workflow/{filename}"
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_trust_contracts.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/trust_contracts.py tests/test_trust_contracts.py
git commit -m "feat: add trustworthy dataset contract builders"
```

---

### Task 3: Integrate Contracts Into `load_data`

**Files:**
- Modify: `src/data_agent/tools/data_io.py`
- Test: `tests/test_trustworthy_load_data_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_trustworthy_load_data_integration.py`:

```python
import json
from pathlib import Path

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.tools.data_io import load_data


def test_load_data_attaches_trust_workflow_refs(tmp_path, monkeypatch):
    csv_path = tmp_path / "sales.csv"
    pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "gmv": ["100", "120", "130"],
        "channel": ["a", "b", "a"],
    }).to_csv(csv_path, index=False)

    state = AnalysisSessionState(session_id="s_trust")
    ctx = AgentContext(session_id="s_trust", analysis_state=state)

    with use_agent_context(ctx):
        result = load_data(str(csv_path), name="sales")

    assert "trust_workflow" in result
    assert len(state.cleaning_logs) == 1
    assert len(state.preview_digests) == 1
    assert len(state.dataset_contracts) == 1
    assert len(state.route_proposals) >= 1
    assert state.dataset_contracts[0]["dataset"] == "sales"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_trustworthy_load_data_integration.py -v
```

Expected: FAIL because `load_data` does not yet create trust workflow refs.

- [ ] **Step 3: Add integration block to `load_data`**

In `src/data_agent/tools/data_io.py`, after `detail_sections` is built and before the final return, add:

```python
        try:
            from data_agent.agent.context import get_current_context
            ctx = get_current_context()
            if ctx is not None:
                from data_agent.agent.trust_contracts import (
                    build_cleaning_decision_log,
                    build_dataset_understanding_contract,
                    build_preview_digest,
                    build_route_proposals,
                    write_trust_artifact,
                )
                from data_agent.config import get_config
                from data_agent.utils.data_features import scan_data_quality

                session_dir = get_config().sessions_resolved / ctx.session_id
                trust_quality = scan_data_quality(df)

                cleaning_log = build_cleaning_decision_log(name, applied, needs_confirm)
                preview_digest = build_preview_digest(name, df)

                interpretation_data = {}
                raw_interp = detail_sections.get("interpretation_data")
                if raw_interp:
                    try:
                        interpretation_data = json.loads(raw_interp)
                    except json.JSONDecodeError:
                        interpretation_data = {}

                contract = build_dataset_understanding_contract(
                    dataset=name,
                    df=df,
                    quality=trust_quality,
                    interpretation_data=interpretation_data,
                    cleaning_log_ids=[cleaning_log["id"]],
                    preview_digest_id=preview_digest["id"],
                    detail_path=f"tool_outputs/load_{name}_detail.json",
                )
                route_proposals = build_route_proposals(contract)

                cleaning_path = write_trust_artifact(session_dir, "cleaning_log", cleaning_log)
                preview_path = write_trust_artifact(session_dir, "preview_digest", preview_digest)
                contract_path = write_trust_artifact(session_dir, "dataset_contract", contract)
                route_paths = [
                    write_trust_artifact(session_dir, "route_proposal", proposal)
                    for proposal in route_proposals
                ]

                if ctx.analysis_state is not None:
                    ctx.analysis_state.add_cleaning_log_ref({
                        "id": cleaning_log["id"],
                        "dataset": name,
                        "path": cleaning_path,
                        "summary": cleaning_log["summary"],
                    })
                    ctx.analysis_state.add_preview_digest_ref({
                        "id": preview_digest["id"],
                        "dataset": name,
                        "path": preview_path,
                    })
                    ctx.analysis_state.add_dataset_contract_ref({
                        "id": contract["id"],
                        "dataset": name,
                        "path": contract_path,
                        "quality_status": contract["quality"]["status"],
                        "supported_analyses": contract["supported_analyses"],
                    })
                    for proposal, route_path in zip(route_proposals, route_paths):
                        ctx.analysis_state.add_route_proposal_ref({
                            "id": proposal["id"],
                            "dataset": name,
                            "path": route_path,
                            "direction": proposal["direction"],
                            "budget_level": proposal["budget_level"],
                        })
                    ctx.analysis_state.save()

                summary_parts.append(
                    f"[trust_workflow] contract={contract['id']} routes={len(route_proposals)} [/trust_workflow]"
                )
        except Exception:
            pass
```

- [ ] **Step 4: Run integration test**

Run:

```bash
uv run pytest tests/test_trustworthy_load_data_integration.py -v
```

Expected: PASS.

- [ ] **Step 5: Run adjacent data tests**

Run:

```bash
uv run pytest tests/test_data_features.py tests/test_trust_contracts.py tests/test_trustworthy_load_data_integration.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data_agent/tools/data_io.py tests/test_trustworthy_load_data_integration.py
git commit -m "feat: create trust workflow records on data load"
```

---

### Task 4: Add Data-Aware Intent Refinement

**Files:**
- Create: `src/data_agent/agent/intent_refinement.py`
- Test: `tests/test_intent_refinement.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_intent_refinement.py`:

```python
from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data


def _intent(intent_type="intent_negotiation", action="guide_analysis"):
    return TurnIntent(
        intent_type=intent_type,
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action=action,
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )


def test_vague_request_uses_route_proposals():
    intent = _intent()
    contract = {
        "dataset": "sales",
        "quality": {"status": "ready"},
        "supported_analyses": ["trend"],
        "unsupported_analyses": [],
    }
    routes = [{"id": "route_1", "direction": "trend_or_period_compare", "user_facing_label": "Trend"}]

    refined = refine_intent_with_data("help me look at this data", intent, [contract], routes)

    assert refined.intent_type == "intent_negotiation"
    assert refined.recommended_action == "guide_analysis"
    assert refined.ambiguities[0]["field"] == "analysis_route"


def test_unsupported_retention_request_marks_insufficient_data():
    intent = _intent(intent_type="directed_analysis", action="run_analysis")
    contract = {
        "dataset": "daily",
        "quality": {"status": "ready"},
        "supported_analyses": ["trend"],
        "unsupported_analyses": [{"type": "user_level_retention", "reason": "aggregate grain"}],
    }

    refined = refine_intent_with_data("analyze retention", intent, [contract], [])

    assert refined.execution_readiness == "insufficient_data"
    assert refined.recommended_action == "request_data"
    assert refined.ambiguities[0]["field"] == "unsupported_analysis"


def test_blocked_quality_requests_scope_before_analysis():
    intent = _intent(intent_type="directed_analysis", action="run_analysis")
    contract = {
        "dataset": "bad",
        "quality": {"status": "blocked"},
        "supported_analyses": [],
        "unsupported_analyses": [],
    }

    refined = refine_intent_with_data("analyze why revenue dropped", intent, [contract], [])

    assert refined.analysis_stage == "scope"
    assert refined.recommended_action == "ask_question"
    assert refined.execution_readiness == "insufficient_data"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_intent_refinement.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement intent refinement**

Create `src/data_agent/agent/intent_refinement.py`:

```python
from __future__ import annotations

from dataclasses import replace
from typing import Any

from data_agent.agent.intent import TurnIntent


def _mentions_retention(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in ("retention", "留存", "cohort"))


def _blocked_contract(contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for contract in contracts:
        if (contract.get("quality") or {}).get("status") == "blocked":
            return contract
    return None


def _unsupported(contract: dict[str, Any], analysis_type: str) -> dict[str, Any] | None:
    for item in contract.get("unsupported_analyses") or []:
        if item.get("type") == analysis_type:
            return item
    return None


def refine_intent_with_data(
    user_input: str,
    intent: TurnIntent,
    dataset_contracts: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
) -> TurnIntent:
    contracts = list(dataset_contracts or [])
    routes = list(route_proposals or [])

    blocked = _blocked_contract(contracts)
    if blocked and intent.intent_type in {"directed_analysis", "comprehensive_report"}:
        return replace(
            intent,
            clarity="clarification_needed",
            analysis_stage="scope",
            recommended_action="ask_question",
            execution_readiness="insufficient_data",
            ambiguities=intent.ambiguities + [{
                "field": "data_quality",
                "issue": f"Dataset '{blocked.get('dataset')}' has blocking quality issues before formal analysis",
            }],
        )

    if _mentions_retention(user_input):
        for contract in contracts:
            unsupported = _unsupported(contract, "user_level_retention")
            if unsupported:
                return replace(
                    intent,
                    clarity="clarification_needed",
                    analysis_stage="scope",
                    recommended_action="request_data",
                    execution_readiness="insufficient_data",
                    ambiguities=intent.ambiguities + [{
                        "field": "unsupported_analysis",
                        "issue": unsupported.get("reason", "Current data does not support user-level retention"),
                    }],
                )

    if intent.intent_type == "intent_negotiation" and routes:
        labels = [route.get("user_facing_label") or route.get("direction") for route in routes[:3]]
        return replace(
            intent,
            ambiguities=intent.ambiguities + [{
                "field": "analysis_route",
                "issue": "Data supports these routes: " + ", ".join(labels),
            }],
        )

    return intent
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_intent_refinement.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/intent_refinement.py tests/test_intent_refinement.py
git commit -m "feat: refine intent using dataset contracts"
```

---

### Task 5: Add Deterministic Verification Reports

**Files:**
- Create: `src/data_agent/agent/verification.py`
- Test: `tests/test_verification_layer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_verification_layer.py`:

```python
from data_agent.agent.verification import verify_analysis_claims


def test_missing_evidence_marks_unsupported():
    report = verify_analysis_claims(
        claims=["Channel A caused the decline"],
        evidence_records=[],
        route_proposals=[],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert check["strength"] == "unsupported"
    assert check["status"] == "failed"
    assert "No evidence record" in check["issues"][0]


def test_causal_language_without_causal_evidence_is_downgraded():
    report = verify_analysis_claims(
        claims=["Channel A caused the GMV decline"],
        evidence_records=[{
            "id": "ev1",
            "claim": "Channel A contributed most of the GMV decline",
            "method": "contribute_decomposition",
            "dataset": "main",
            "sample_size": "1000",
            "time_scope": "2026-01",
            "calculation_method": "contribution decomposition",
            "method_detail": "dimension contribution",
            "limitations": ["No control group"],
            "confidence": "high",
        }],
        route_proposals=[],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert check["strength"] == "likely"
    assert check["status"] == "downgraded"
    assert any("causal" in issue.lower() for issue in check["issues"])


def test_complete_evidence_passes_likely_or_confirmed():
    report = verify_analysis_claims(
        claims=["GMV increased in the later period"],
        evidence_records=[{
            "id": "ev1",
            "claim": "GMV increased in the later period",
            "method": "compare_periods",
            "dataset": "main",
            "sample_size": "1000",
            "time_scope": "2026-01 vs 2026-02",
            "calculation_method": "period comparison",
            "method_detail": "daily average comparison",
            "limitations": ["Descriptive comparison"],
            "confidence": "medium",
        }],
        route_proposals=[{
            "id": "route1",
            "expected_evidence": ["metric_delta", "period_comparability", "limitations"],
        }],
        cleaning_logs=[],
    )

    check = report["claim_checks"][0]
    assert check["status"] in {"passed", "downgraded"}
    assert check["strength"] in {"likely", "confirmed"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_verification_layer.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement verification module**

Create `src/data_agent/agent/verification.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


_CAUSAL_TERMS = ("caused", "cause", "导致", "证明", "使得")
_STRONG_TERMS = ("significant", "显著", "main reason", "主要原因", "proved", "证明")
_REQUIRED_EVIDENCE_FIELDS = ("dataset", "method", "sample_size", "time_scope", "calculation_method", "method_detail", "limitations")


def _new_id() -> str:
    return "verify_" + uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _matches_claim(claim: str, record: dict[str, Any]) -> bool:
    claim_lower = claim.lower()
    record_claim = str(record.get("claim") or "").lower()
    if not record_claim:
        return False
    claim_words = {w for w in claim_lower.replace("_", " ").split() if len(w) >= 3}
    record_words = {w for w in record_claim.replace("_", " ").split() if len(w) >= 3}
    if not claim_words:
        return False
    return len(claim_words & record_words) / max(len(claim_words), 1) >= 0.35


def _has_causal_method(record: dict[str, Any]) -> bool:
    method = str(record.get("method") or "").lower()
    return any(term in method for term in ("causal", "ab_test", "experiment", "did", "difference_in_differences"))


def _missing_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_EVIDENCE_FIELDS if record.get(field) in (None, "", [], {})]


def _has_risky_cleaning(cleaning_logs: list[dict[str, Any]]) -> bool:
    for log in cleaning_logs:
        for decision in log.get("decisions") or []:
            if decision.get("decision_type") in {"needs_confirmation", "blocked"}:
                return True
    return False


def _check_claim(
    claim: str,
    evidence_records: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    matches = [record for record in evidence_records if _matches_claim(claim, record)]
    if not matches and evidence_records:
        matches = [evidence_records[0]]
    issues: list[str] = []

    if not matches:
        return {
            "claim": claim,
            "evidence_ids": [],
            "status": "failed",
            "strength": "unsupported",
            "issues": ["No evidence record supports this claim"],
            "required_action": "Do not present this claim as an analysis conclusion",
        }

    primary = matches[0]
    missing = _missing_fields(primary)
    if missing:
        issues.append("Evidence is missing fields: " + ", ".join(missing))

    lowered = claim.lower()
    if any(term in lowered for term in _CAUSAL_TERMS) and not _has_causal_method(primary):
        issues.append("Causal language is not supported by a causal or experimental method")

    if any(term in lowered for term in _STRONG_TERMS):
        if str(primary.get("confidence") or "").lower() not in {"high", "medium"}:
            issues.append("Strong language is not supported by evidence confidence")

    if _has_risky_cleaning(cleaning_logs):
        issues.append("Claim may depend on cleaning decisions that require confirmation")

    if not issues:
        strength = "confirmed" if str(primary.get("confidence") or "").lower() == "high" else "likely"
        return {
            "claim": claim,
            "evidence_ids": [primary.get("id", "")],
            "status": "passed",
            "strength": strength,
            "issues": [],
            "required_action": "Use normal evidence-bounded language",
        }

    strength = "exploratory" if missing else "likely"
    return {
        "claim": claim,
        "evidence_ids": [primary.get("id", "")],
        "status": "downgraded",
        "strength": strength,
        "issues": issues,
        "required_action": "Use cautious wording and include limitations",
    }


def verify_analysis_claims(
    claims: list[str],
    evidence_records: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    checks = [_check_claim(claim, list(evidence_records or []), list(cleaning_logs or [])) for claim in claims]
    statuses = {check["status"] for check in checks}
    if "failed" in statuses:
        overall = "fail"
    elif "downgraded" in statuses:
        overall = "pass_with_downgrades"
    else:
        overall = "pass"

    return {
        "id": _new_id(),
        "created_at": _now(),
        "claim_checks": checks,
        "route_proposal_ids": [r.get("id", "") for r in route_proposals or []],
        "overall_status": overall,
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_verification_layer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/verification.py tests/test_verification_layer.py
git commit -m "feat: add deterministic analysis verification"
```

---

### Task 6: Feed Verification Status Into Synthesis Policy

**Files:**
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Test: `tests/test_synthesis_policy.py`

- [ ] **Step 1: Add failing synthesis policy test**

Add to `tests/test_synthesis_policy.py`:

```python
def test_verification_downgrade_suppresses_decision_recommendation():
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.synthesis_policy import derive_synthesis_policy

    state = AnalysisSessionState(session_id="s1")
    state.add_verification_report_ref({
        "id": "verify_001",
        "overall_status": "pass_with_downgrades",
    })

    policy = derive_synthesis_policy(
        user_input="Should we keep doing this campaign?",
        turn_intent=None,
        state=state,
        profile_text="",
    )

    assert "decision_recommendation" in policy.suppressed_moves
    assert policy.business_translation == "cautious"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_synthesis_policy.py::test_verification_downgrade_suppresses_decision_recommendation -v
```

Expected: FAIL because `derive_synthesis_policy` does not yet inspect verification reports.

- [ ] **Step 3: Modify synthesis policy**

In `src/data_agent/agent/synthesis_policy.py`, add helper:

```python
def _verification_status(state) -> str:
    reports = list(_get(state, "verification_reports", []) or [])
    if not reports:
        return ""
    return str(reports[-1].get("overall_status") or "")
```

In `derive_synthesis_policy`, after existing uncertainty/evidence checks, add:

```python
    verification_status = _verification_status(state)
    if verification_status in {"fail", "pass_with_downgrades"}:
        suppressed = set(policy.suppressed_moves)
        suppressed.add("decision_recommendation")
        required = list(dict.fromkeys(list(policy.required_moves) + ["limitation"]))
        return replace(
            policy,
            business_translation="cautious",
            required_moves=required,
            suppressed_moves=sorted(suppressed),
            reason=policy.reason + f" Verification status is {verification_status}.",
        )
```

If `SynthesisPolicy` is not a dataclass or the local code uses a different construction style, implement the same mutation with the existing return object pattern. Keep the test assertion behavior unchanged.

- [ ] **Step 4: Run synthesis policy test**

Run:

```bash
uv run pytest tests/test_synthesis_policy.py::test_verification_downgrade_suppresses_decision_recommendation -v
```

Expected: PASS.

- [ ] **Step 5: Run broader workflow tests**

Run:

```bash
uv run pytest tests/test_synthesis_policy.py tests/test_analysis_state_v2.py tests/test_verification_layer.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data_agent/agent/synthesis_policy.py tests/test_synthesis_policy.py
git commit -m "feat: use verification status in synthesis policy"
```

---

### Task 7: Add Prompt Context Summary For Trust Workflow Records

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/agent/prompts.py`
- Test: `tests/test_prompt_system.py`

- [ ] **Step 1: Write failing prompt summary test**

Add to `tests/test_prompt_system.py`:

```python
def test_analysis_state_summary_includes_compact_trust_context():
    from data_agent.agent.analysis_state import AnalysisSessionState, analysis_state_summary

    state = AnalysisSessionState(session_id="s1")
    state.add_dataset_contract_ref({
        "id": "duc_main_001",
        "dataset": "main",
        "quality_status": "ready_with_warnings",
        "supported_analyses": ["trend", "period_compare"],
    })
    state.add_route_proposal_ref({
        "id": "route_main_001",
        "direction": "trend_or_period_compare",
        "budget_level": "standard",
    })
    state.add_verification_report_ref({
        "id": "verify_001",
        "overall_status": "pass_with_downgrades",
    })

    summary = analysis_state_summary(state)

    assert "duc_main_001" in summary
    assert "ready_with_warnings" in summary
    assert "route_main_001" in summary
    assert "pass_with_downgrades" in summary
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_prompt_system.py::test_analysis_state_summary_includes_compact_trust_context -v
```

Expected: FAIL until `analysis_state_summary` includes compact trust context details.

- [ ] **Step 3: Enhance `analysis_state_summary`**

Add compact detail lines:

```python
    if state.dataset_contracts:
        contracts = []
        for ref in state.dataset_contracts[-3:]:
            contracts.append(
                f"{ref.get('id')}:{ref.get('dataset')} quality={ref.get('quality_status', '-')}"
            )
        lines.append("- dataset_contract_refs: " + "; ".join(contracts))

    if state.route_proposals:
        routes = []
        for ref in state.route_proposals[-3:]:
            routes.append(
                f"{ref.get('id')}:{ref.get('direction')} budget={ref.get('budget_level', '-')}"
            )
        lines.append("- route_proposal_refs: " + "; ".join(routes))

    if state.verification_reports:
        reports = []
        for ref in state.verification_reports[-3:]:
            reports.append(
                f"{ref.get('id')} status={ref.get('overall_status', '-')}"
            )
        lines.append("- verification_report_refs: " + "; ".join(reports))
```

No direct `prompts.py` change is needed if existing system prompt construction already includes `analysis_state_summary` in session context. If it does not, add the summary to the existing session context builder rather than inventing a new prompt block.

- [ ] **Step 4: Run prompt test**

Run:

```bash
uv run pytest tests/test_prompt_system.py::test_analysis_state_summary_includes_compact_trust_context -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/analysis_state.py tests/test_prompt_system.py
git commit -m "feat: summarize trust workflow context for prompts"
```

---

### Task 8: End-to-End Regression Test For MVP Chain

**Files:**
- Create: `tests/test_trustworthy_workflow_mvp.py`

- [ ] **Step 1: Write end-to-end test**

Create `tests/test_trustworthy_workflow_mvp.py`:

```python
import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.agent.trust_contracts import (
    build_cleaning_decision_log,
    build_dataset_understanding_contract,
    build_preview_digest,
    build_route_proposals,
)
from data_agent.agent.verification import verify_analysis_claims
from data_agent.utils.data_features import scan_data_quality


def test_trustworthy_workflow_mvp_chain():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=10),
        "gmv": [100, 120, 110, 130, 140, 125, 135, 150, 155, 160],
        "channel": ["a", "b"] * 5,
    })
    state = AnalysisSessionState(session_id="s1")

    cleaning = build_cleaning_decision_log("main", [], [])
    preview = build_preview_digest("main", df)
    quality = scan_data_quality(df)
    interpretation = {
        "grain": "daily_aggregate",
        "columns_classified": {
            "time_columns": ["date"],
            "key_metrics": [{"column": "gmv"}],
            "rate_metrics": [],
            "dimensions": [{"column": "channel"}],
            "id_columns": [],
            "other_text": [],
        },
        "time_range": {"column": "date", "min": "2026-01-01", "max": "2026-01-10", "span_days": 9},
        "analysis_signals": {"has_time": True, "has_dimensions": True, "has_ids": False, "has_rates": False, "metric_count": 1},
    }
    contract = build_dataset_understanding_contract(
        "main", df, quality, interpretation, [cleaning["id"]], preview["id"], "tool_outputs/load_main_detail.json"
    )
    routes = build_route_proposals(contract)

    state.add_cleaning_log_ref({"id": cleaning["id"], "dataset": "main"})
    state.add_preview_digest_ref({"id": preview["id"], "dataset": "main"})
    state.add_dataset_contract_ref({"id": contract["id"], "dataset": "main", "quality_status": contract["quality"]["status"]})
    for route in routes:
        state.add_route_proposal_ref({"id": route["id"], "direction": route["direction"]})

    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    refined = refine_intent_with_data("help me look at this data", intent, [contract], routes)
    assert refined.recommended_action == "guide_analysis"

    report = verify_analysis_claims(
        ["GMV increased over the period"],
        [{
            "id": "ev1",
            "claim": "GMV increased over the period",
            "method": "compare_periods",
            "dataset": "main",
            "sample_size": "10",
            "time_scope": "2026-01-01 to 2026-01-10",
            "calculation_method": "period comparison",
            "method_detail": "manual comparison",
            "limitations": ["Small sample"],
            "confidence": "medium",
        }],
        routes,
        [cleaning],
    )
    state.add_verification_report_ref({"id": report["id"], "overall_status": report["overall_status"]})

    assert contract["supported_analyses"]
    assert routes
    assert report["overall_status"] in {"pass", "pass_with_downgrades"}
    assert state.verification_reports
```

- [ ] **Step 2: Run end-to-end test**

Run:

```bash
uv run pytest tests/test_trustworthy_workflow_mvp.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full focused suite**

Run:

```bash
uv run pytest tests/test_trust_contracts.py tests/test_intent_refinement.py tests/test_verification_layer.py tests/test_trustworthy_load_data_integration.py tests/test_trustworthy_workflow_mvp.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_trustworthy_workflow_mvp.py
git commit -m "test: cover trustworthy workflow mvp chain"
```

---

## Final Verification

- [ ] **Step 1: Run core focused tests**

```bash
uv run pytest tests/test_analysis_state_v2.py tests/test_data_features.py tests/test_prompt_system.py tests/test_synthesis_policy.py tests/test_trust_contracts.py tests/test_intent_refinement.py tests/test_verification_layer.py tests/test_trustworthy_load_data_integration.py tests/test_trustworthy_workflow_mvp.py -v
```

Expected: PASS.

- [ ] **Step 2: Check git status**

```bash
git status --short
```

Expected: only unrelated pre-existing files remain untracked or modified.

- [ ] **Step 3: Review artifact size**

Check that generated trust workflow JSON files are session-local runtime artifacts and are not committed:

```bash
git status --short sessions workspace project
```

Expected: runtime artifacts remain ignored or untracked outside the implementation commit set.

---

## Handoff Notes

- Keep the first implementation deterministic. Do not add an independent verifier LLM in this MVP.
- Do not replace existing prompt rules. Let the new records inform them.
- Keep route proposals internal in the first implementation. Web UI route cards can be a later plan.
- Treat cleaning decisions as analysis evidence. Final answers should become cautious when claims depend on unconfirmed cleaning.
- If Git index permissions are still blocked in the local environment, finish code and tests first, then ask the user to run the listed `git add` and `git commit` commands manually.
