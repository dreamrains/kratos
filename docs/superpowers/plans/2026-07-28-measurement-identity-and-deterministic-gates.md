# Measurement Identity and Deterministic Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unsafe number-first evidence attachment with server-owned measurement identity, independently verify metric and claim identity, preserve complete tiered answers, and make deterministic release status truthful.

**Architecture:** Extend `evidence_record.v2` measurements with an optional validated `measurement_identity.v1` owned by the real structured-computation projector. Synthesis refers to one measurement through `[[evidence:<id>#<measurement_key>]]`; canonical verification resolves and independently checks that reference before claim-tier publication. The existing requirement, evidence, audit, and publication authorities remain the only authorities.

**Tech Stack:** Python 3.11+, Pydantic 2, pytest, deterministic `AgentLoop` replay, JSON/Markdown synthesis contracts, Windows PowerShell.

## Global Constraints

- Planning baseline is commit `84b3e087afa01b9fc1c39678bdc5da09992989f7`; execution begins from the commit containing this plan, with no intervening production changes.
- Work only in `D:\Project\Daily\data-agent\.worktrees\analysis-reliability` on `codex/analysis-reliability`.
- Run Python with `PYTHONPATH=D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests`.
- Use `D:\Project\Daily\data-agent\.venv\Scripts\python.exe`; the shared editable install otherwise points at the main checkout.
- Remove or replace the unsafe number-first authorization introduced by `776a866`; do not retain it as a fallback or rollout mode.
- Preserve `analysis_requirement.v1`, `evidence_record.v2`, and `final_answer_audit.v1` as the sole readiness, evidence, and publication authorities.
- Preserve free-form Markdown. Internal markers are removed from the published and persisted user-visible assistant message.
- Equal value, unit, direction, scope, and plan do not establish metric identity.
- A marker is a reference only; canonical verification independently checks it.
- Missing or ambiguous measurement identity never restarts an analysis tool.
- Missing identity may be exploratory only when a real current computation is an exact non-authorizing candidate; contradiction or no computation remains unsupported.
- Do not mutate historical sessions, evidence, uploaded files, raw snapshots, `artifacts/`, or `tmp/`.
- New structured measurements may receive `measurement_identity.v1`; old records continue to load without backfill.
- Production retains deterministic blockers and has no assurance-off mode.
- Use test-driven development for every production change and request a fresh review after every task.

---

## File and ownership map

| File | Responsibility after this plan |
|---|---|
| `src/data_agent/agent/evidence_contracts.py` | Build, validate, and catalog server-owned measurement identities during real evidence projection. |
| `src/data_agent/agent/synthesis_policy.py` | Tell synthesis to use measurement-grain markers while retaining free Markdown. |
| `src/data_agent/agent/answer_quality.py` | Extract and strip measurement markers; build the final audit without number-first attachment. |
| `src/data_agent/agent/verification.py` | Resolve referenced measurements and independently verify metric, claim, plan, version, value, unit, direction, and scope. |
| `src/data_agent/agent/trust_workflow_runtime.py` | Pass the configured measurement-binding mode into the existing final audit. |
| `src/data_agent/agent/loop.py` | Orchestrate synthesis-only repair and publication; measurement bookkeeping failures never schedule tools. |
| `src/data_agent/config.py` | Validate `shadow`, `soft`, and `enforced` measurement-binding rollout modes. |
| `tests/fixtures/measurement_identity.py` | Shared real computation/projection builders; tests import fixtures without importing another test module. |
| `tests/test_automatic_evidence_projection.py` | Real computation artifact to measurement-identity projection tests. |
| `tests/test_final_answer_claim_audit.py` | Marker parsing, metric substitution, legacy compatibility, and canonical audit tests. |
| `tests/test_measurement_identity_pipeline.py` | Real projection-to-publication end-to-end and mutation-style tests. |
| `tests/replay_assertions.py` | Requirement-semantic replay assertions; tool count and answer length remain diagnostics. |
| `tests/test_final_answer_publish_gate.py` | No-recomputation and complete tiered-publication behavior. |
| `tests/test_workspace_config.py` | Rollout configuration validation. |
| `scripts/replay_analysis_reliability.py` | Truthful deterministic-versus-live replay status and streamed-text naming. |
| `scripts/run_analysis_release_gates.py` | Machine-readable A-F gate matrix with no implicit success for unrun gates. |
| `tests/test_analysis_release_gate_runner.py` | Gate aggregation and process-status truthfulness. |

---

## Release-gate ownership and execution order

| Gate | Owning work |
|---|---|
| Gate A — harness integrity | Task 7 plus Plan B Tasks 1-3; release-critical Web files cannot remain ignored. |
| Gate B — contract and mutation | Tasks 1-5, including re-keyed adversarial identity mutations. |
| Gate C — real internal E2E | Task 6 real computation-to-publication pipeline. |
| Gate D — analysis-quality replay | Task 6 semantic requirement coverage, shallow-path rejection, aggregate boundary, sandbox, and Unicode replays. |
| Gate E — actual browser/SSE | Plan B Task 4 after the combined Phase B A-D gate. |
| Gate F — live provider quality | Plan B Task 5 after the combined Phase B A-D gate. |

Execute Plan A Tasks 1-6, then Plan B Tasks 1-3, then Plan A Task 7. This is
the combined Phase B boundary. Measurement bookkeeping never schedules tool
execution. Only after Gates A-D pass may Plan B Tasks 4-6 execute Phase C.

---

### Task 1: Remove unsafe number-first authorization

**Files:**
- Modify: `tests/test_final_answer_claim_audit.py:104-317`
- Modify: `tests/test_automatic_evidence_projection.py:442-511`
- Modify: `src/data_agent/agent/answer_quality.py:268-315`
- Modify: `src/data_agent/agent/answer_quality.py:368-579`

**Interfaces:**
- Consumes: `extract_material_claims(...)` and existing explicit evidence markers.
- Produces: `build_final_answer_audit(...)` with no automatic ID attachment based only on numeric and scope fields.

- [ ] **Step 1: Add the semantic-collision regression**

Add to `tests/test_final_answer_claim_audit.py`:

```python
def test_same_value_revenue_evidence_cannot_verify_profit_claim():
    audit = _audit(
        "Profit increased 12% in 2026-05 for new users.\n"
        "Limitation: this is a descriptive comparison only.",
        evidence=[_auto_bind_evidence()],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] == "blocked"
    assert audit["claims"][0]["evidence_ids"] == []
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]
```

Replace the old positive test that expected a markerless revenue claim to
become verified with:

```python
def test_markerless_same_value_claim_is_not_automatically_verified():
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence()],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] != "pass"
    assert audit["claims"][0]["evidence_ids"] == []
```

- [ ] **Step 2: Run the focused tests and verify the counterexample is RED**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_final_answer_claim_audit.py::test_same_value_revenue_evidence_cannot_verify_profit_claim tests/test_final_answer_claim_audit.py::test_markerless_same_value_claim_is_not_automatically_verified -q
```

Expected: both tests fail because the current matcher attaches `ev_revenue`
without checking the metric.

- [ ] **Step 3: Remove production number-first attachment**

In `build_final_answer_audit`, remove:

```python
claims = attach_unique_exact_evidence_ids(
    claims,
    evidence_records or [],
    current_plan_id=current_plan_id,
    current_dataset_versions=current_dataset_versions,
)
```

Delete `_claim_measurement_identity`, `_evidence_measurement_identity`, and
`attach_unique_exact_evidence_ids`. Retain generic quantity/unit helpers only
if another current caller uses them; confirm with:

```powershell
rg -n "attach_unique_exact_evidence_ids|_claim_measurement_identity|_evidence_measurement_identity" src tests
```

Delete the direct unit tests whose only subject was
`attach_unique_exact_evidence_ids`. The two public
`build_final_answer_audit` regressions from Step 1 own this behavior; do not
replace the deleted tests with a vacuous assertion over a hand-built list.

- [ ] **Step 4: Run the complete audit/projection slice**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_final_answer_claim_audit.py tests/test_automatic_evidence_projection.py -q
```

Expected: PASS; no markerless claim is upgraded to verified.

- [ ] **Step 5: Commit the fail-closed correction**

```powershell
git add src/data_agent/agent/answer_quality.py tests/test_final_answer_claim_audit.py tests/test_automatic_evidence_projection.py
git commit -m "fix: remove number-only evidence authorization"
```

---

### Task 2: Build and validate server-owned measurement identity

**Files:**
- Modify: `src/data_agent/agent/evidence_contracts.py:9-65`
- Modify: `src/data_agent/agent/evidence_contracts.py:1935-2057`
- Modify: `src/data_agent/agent/evidence_contracts.py:2259-2430`
- Create: `tests/fixtures/measurement_identity.py`
- Modify: `tests/test_automatic_evidence_projection.py:1-540`
- Modify: `tests/test_computation_evidence_binding.py:386-430`

**Interfaces:**
- Consumes: real `computation_ref.v1`, `StepBindingResult`, canonical plan, structured capability fields, hydrated tool output, and current dataset contracts.
- Produces:
  - `MEASUREMENT_IDENTITY_CONTRACT_VERSION = "measurement_identity.v1"`
  - `measurement_key_for(identity: Mapping[str, Any]) -> str`
  - `computation_ref_key(ref: Mapping[str, Any]) -> str`
  - `validate_measurement_identity(identity: Any) -> EvidenceValidationResult`
  - identity-bearing measurements under `measurement["identity"]`.

- [ ] **Step 1: Write real-projector identity tests**

Extend `test_bound_structured_computation_auto_projects_v2_evidence`:

```python
    measurement = result.record["measurements"][0]
    identity = measurement["identity"]
    assert identity["contract_version"] == "measurement_identity.v1"
    assert identity["measurement_key"].startswith("m_")
    assert identity["metric_key"] == "pairs.correlation::revenue|cost"
    assert identity["metric_label"] == "revenue cost correlation"
    assert identity["metric_aliases"] == [
        "revenue cost correlation",
        "cost revenue correlation",
    ]
    assert identity["claim_key"] == "revenue_cost_correlation"
    assert identity["plan_id"] == PLAN_ID
    assert identity["plan_version"] == PLAN_DIGEST
    assert identity["step_id"] == STEP_ID
    assert identity["requirement_ids"] == ["req_corr_effect"]
    assert identity["dataset_versions"] == [DATASET_VERSION]
    assert identity["computation_ref_id"].startswith("cr_")
```

Add deterministic and tampering tests:

```python
def test_measurement_key_is_stable_and_changes_with_metric_or_version(context):
    first = project_real_correlation(context)
    second = project_real_correlation(context)
    first_identity = first.record["measurements"][0]["identity"]
    second_identity = second.record["measurements"][0]["identity"]
    assert first_identity["measurement_key"] == second_identity["measurement_key"]

    from data_agent.agent.evidence_contracts import measurement_key_for
    changed = dict(first_identity)
    changed.pop("measurement_key")
    changed["metric_key"] = "pairs.correlation::profit|cost"
    assert measurement_key_for(changed) != first_identity["measurement_key"]

    changed["metric_key"] = first_identity["metric_key"]
    changed["dataset_versions"] = ["ds_main_v2"]
    assert measurement_key_for(changed) != first_identity["measurement_key"]


def test_measurement_identity_validator_rejects_tampered_key(context):
    result = project_real_correlation(context)
    identity = dict(result.record["measurements"][0]["identity"])
    identity["metric_key"] = "pairs.correlation::profit|cost"

    from data_agent.agent.evidence_contracts import validate_measurement_identity
    validation = validate_measurement_identity(identity)
    assert validation.ok is False
    assert validation.error_type == "measurement_key_mismatch"
```

Move the repeated real artifact, plan, and projection builders into
`tests/fixtures/measurement_identity.py`. Export
`build_projection_context(tmp_path)` and
`project_real_correlation(context)`. Both
`test_automatic_evidence_projection.py` and the later pipeline test import
these builders from `tests.fixtures.measurement_identity`; no test imports
another test module.

- [ ] **Step 2: Run the tests and verify missing identity is RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_automatic_evidence_projection.py::test_bound_structured_computation_auto_projects_v2_evidence tests/test_automatic_evidence_projection.py::test_measurement_key_is_stable_and_changes_with_metric_or_version tests/test_automatic_evidence_projection.py::test_measurement_identity_validator_rejects_tampered_key -q
```

Expected: FAIL because projected measurements have no `identity` and the new
helpers do not exist.

- [ ] **Step 3: Add canonical key builders and validation**

Add imports and constants in `evidence_contracts.py`:

```python
from collections.abc import Mapping
import math

MEASUREMENT_IDENTITY_CONTRACT_VERSION = "measurement_identity.v1"
MEASUREMENT_IDENTITY_REQUIRED_FIELDS = (
    "contract_version",
    "measurement_key",
    "metric_key",
    "metric_label",
    "metric_aliases",
    "claim_key",
    "computation_ref_id",
    "plan_id",
    "plan_version",
    "step_id",
    "requirement_ids",
    "dataset_versions",
    "time_scope",
    "population_scope",
    "value",
    "unit",
    "direction",
    "allowed_claim_class",
)
```

Implement:

```python
def _canonical_identity_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_value(value[key])
        for key in sorted(value)
        if key != "measurement_key"
    }


def measurement_key_for(identity: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_identity_payload(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "m_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def computation_ref_key(ref: Mapping[str, Any]) -> str:
    payload = {
        key: ref.get(key)
        for key in (
            "session_id",
            "turn_id",
            "tool_call_id",
            "tool_name",
            "output_digest",
            "plan_digest",
            "step_digest",
            "dataset_versions",
        )
    }
    encoded = json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "cr_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def validate_measurement_identity(identity: Any) -> EvidenceValidationResult:
    if not isinstance(identity, dict):
        return _error(
            "invalid_measurement_identity",
            "Measurement identity must be an object.",
        )
    missing = [
        field for field in MEASUREMENT_IDENTITY_REQUIRED_FIELDS
        if field not in identity
    ]
    if missing:
        return _error(
            "missing_measurement_identity_fields",
            "Measurement identity is incomplete.",
            missing=missing,
        )
    if identity.get("contract_version") != MEASUREMENT_IDENTITY_CONTRACT_VERSION:
        return _error(
            "invalid_measurement_identity_version",
            "Measurement identity contract version is invalid.",
        )
    aliases = identity.get("metric_aliases")
    if not isinstance(aliases, list) or any(
        not isinstance(item, str) or not item.strip() for item in aliases
    ):
        return _error(
            "invalid_metric_aliases",
            "Metric aliases must be a list of non-empty trusted labels.",
        )
    for field in (
        "metric_key",
        "metric_label",
        "claim_key",
        "computation_ref_id",
        "plan_id",
        "plan_version",
        "step_id",
        "time_scope",
        "population_scope",
        "allowed_claim_class",
    ):
        if not isinstance(identity.get(field), str) or not identity[field].strip():
            return _error(
                "invalid_measurement_identity_field",
                f"Measurement identity {field} must be a non-empty string.",
                field=field,
            )
    for field in ("requirement_ids", "dataset_versions"):
        values = identity.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or values != sorted(set(values))
        ):
            return _error(
                "invalid_measurement_identity_field",
                f"Measurement identity {field} must be sorted unique strings.",
                field=field,
            )
    value = identity.get("value")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return _error(
            "invalid_measurement_identity_field",
            "Measurement identity value must be a finite number.",
            field="value",
        )
    for field in ("unit", "direction"):
        if not isinstance(identity.get(field), str):
            return _error(
                "invalid_measurement_identity_field",
                f"Measurement identity {field} must be a string.",
                field=field,
            )
    expected = measurement_key_for(identity)
    if identity.get("measurement_key") != expected:
        return _error(
            "measurement_key_mismatch",
            "Measurement key does not match its canonical identity.",
            expected=expected,
        )
    return EvidenceValidationResult(True, record=dict(identity))
```

Use the existing `_json_value` function already defined in
`evidence_contracts.py`; do not add a second JSON normalizer.

- [ ] **Step 4: Derive trusted metric identity from structured output**

Implement a closed, deterministic metric-name builder:

```python
_METRIC_CONTEXT_FIELDS = (
    "metric",
    "target",
    "feature",
    "dimension",
    "column",
    "label",
    "name",
)


def _structured_metric_identity(
    *,
    declared_field: str,
    item: dict[str, Any] | None,
) -> tuple[str, str, list[str]] | None:
    tail = declared_field.rsplit(".", 1)[-1].replace("_", " ").strip()
    context: list[str] = []
    if isinstance(item, dict):
        variables = item.get("variables")
        if isinstance(variables, list):
            context = [_text(value) for value in variables if _text(value)]
        if not context:
            for key in _METRIC_CONTEXT_FIELDS:
                value = _text(item.get(key))
                if value:
                    context = [value]
                    break
    if "." in declared_field and not context:
        return None
    metric_key = declared_field
    if context:
        metric_key += "::" + "|".join(context)
    label = " ".join([*context, tail]).strip()
    aliases = [label]
    if len(context) == 2:
        aliases.append(" ".join([context[1], context[0], tail]).strip())
    return metric_key, label, list(dict.fromkeys(aliases))
```

Change `_projected_measurements_from_output` so list-item measurements pass the
item into `_structured_metric_identity`. For a declared list field without
enough structured context, retain the claim-neutral measurement but omit its
identity and set:

```python
measurement["identity_status"] = "metric_identity_missing"
```

Do not create a fake verified identity for the existing
`structured_computation=0.0` sentinel.

- [ ] **Step 5: Attach identity in the real projector and validate it**

Pass `computation_ref`, `binding`, `plan`, dataset versions, and allowed claim
class into the measurement builder. For each eligible measurement, build:

```python
identity = {
    "contract_version": MEASUREMENT_IDENTITY_CONTRACT_VERSION,
    "metric_key": metric_key,
    "metric_label": metric_label,
    "metric_aliases": metric_aliases,
    "claim_key": binding.claim_key,
    "computation_ref_id": computation_ref_key(computation_ref),
    "plan_id": plan_id,
    "plan_version": _text(computation_ref.get("plan_digest"))
        or analysis_plan_semantic_digest(plan),
    "step_id": binding.step_id,
    "requirement_ids": sorted(str(item) for item in binding.requirement_ids),
    "dataset_versions": sorted(
        str(item) for item in computation_ref.get("dataset_versions") or []
    ),
    "time_scope": _text(measurement.get("time_scope")),
    "population_scope": _text(measurement.get("population_scope")),
    "value": measurement.get("value"),
    "unit": _text(measurement.get("unit")),
    "direction": _text(measurement.get("direction")),
    "allowed_claim_class": _text(allowed_claim_class),
}
identity["measurement_key"] = measurement_key_for(identity)
measurement["identity"] = identity
```

In `validate_measurement`, validate `measurement["identity"]` when present and
replace it with the normalized validated record. Historical measurements
without identity remain valid.

- [ ] **Step 6: Run focused and compatibility suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_automatic_evidence_projection.py tests/test_computation_evidence_binding.py tests/test_stage3c0b_evidence_contracts.py -q
```

Expected: PASS; old evidence records still validate, and new real projected
correlation measurements contain deterministic identity.

- [ ] **Step 7: Commit measurement identity projection**

```powershell
git add src/data_agent/agent/evidence_contracts.py tests/fixtures/measurement_identity.py tests/test_automatic_evidence_projection.py tests/test_computation_evidence_binding.py
git commit -m "feat: project server-owned measurement identity"
```

---

### Task 3: Add measurement-grain synthesis markers

**Files:**
- Modify: `src/data_agent/agent/evidence_contracts.py:2625-2710`
- Modify: `src/data_agent/agent/synthesis_policy.py:218-258`
- Modify: `src/data_agent/agent/answer_quality.py:122-205`
- Modify: `tests/test_automatic_evidence_projection.py:442-540`
- Modify: `tests/test_final_answer_claim_audit.py:70-105`
- Modify: `tests/test_synthesis_policy.py`

**Interfaces:**
- Consumes: identity-bearing `evidence_record.v2` measurements.
- Produces:
  - markers `[[evidence:<evidence_id>#<measurement_key>]]`
  - claim field `evidence_refs: list[{"evidence_id": str, "measurement_key": str}]`
  - compatibility `evidence_ids` for existing verification/report callers.

- [ ] **Step 1: Write marker extraction, stripping, and catalog tests**

Add:

```python
def test_extractor_retains_measurement_grain_reference():
    claims = extract_material_claims(
        "Revenue increased 12% "
        "[[evidence:ev_revenue#m_revenue_change]]."
    )
    assert claims[0]["evidence_refs"] == [{
        "evidence_id": "ev_revenue",
        "measurement_key": "m_revenue_change",
    }]
    assert claims[0]["evidence_ids"] == ["ev_revenue"]
    assert "[[evidence:" not in claims[0]["text"]


def test_marker_stripping_preserves_markdown_structure():
    draft = (
        "# 结论\n\n"
        "| 指标 | 变化 |\n|---|---|\n"
        "| 收入 | 12% [[evidence:ev_1#m_1]] |\n"
    )
    public = strip_internal_evidence_markers(draft)
    assert public.startswith("# 结论")
    assert "| 收入 | 12% |" in public
    assert "[[evidence:" not in public
```

Extend the real projection catalog test:

```python
    identity = result.record["measurements"][0]["identity"]
    assert f"measurement_key={identity['measurement_key']}" in catalog
    assert "metric_key=pairs.correlation::revenue|cost" in catalog
    assert "metric_label=revenue cost correlation" in catalog
```

Add a synthesis-policy assertion:

```python
assert "[[evidence:<EvidenceRecord ID>#<measurement_key>]]" in instruction
assert "[[evidence:<EvidenceRecord ID>]] markers" not in instruction
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_final_answer_claim_audit.py::test_extractor_retains_measurement_grain_reference tests/test_final_answer_claim_audit.py::test_marker_stripping_preserves_markdown_structure tests/test_automatic_evidence_projection.py::test_bound_structured_computation_auto_projects_v2_evidence tests/test_synthesis_policy.py -q
```

Expected: marker parsing and catalog assertions fail under record-level syntax.

- [ ] **Step 3: Extend marker parsing without breaking legacy reads**

Replace `_EVIDENCE_MARKER` with:

```python
_EVIDENCE_MARKER = re.compile(
    r"\[\[evidence:([A-Za-z0-9_.:-]+)"
    r"(?:#([A-Za-z0-9_.:-]+))?\]\]",
    re.IGNORECASE,
)
```

In `extract_material_claims`:

```python
marker_pairs = list(dict.fromkeys(_EVIDENCE_MARKER.findall(raw_text)))
evidence_refs = [
    {"evidence_id": evidence_id, "measurement_key": measurement_key}
    for evidence_id, measurement_key in marker_pairs
]
evidence_ids = list(dict.fromkeys(
    ref["evidence_id"] for ref in evidence_refs
))
```

Add `evidence_refs` to each claim and update
`strip_internal_evidence_markers` to remove the optional `#measurement_key`
suffix.

- [ ] **Step 4: Render one catalog entry per identity-bearing measurement**

Change the catalog formatter so every identity-bearing measurement exposes:

```text
id=<evidence_id> | measurement_key=<key> | metric_key=<key> |
metric_label=<label> | claim_key=<claim_key> | value=<value> <unit> |
dataset_versions=<versions> | claim_class=<class>
```

Measurements without validated identity remain visible only as
`unbound_measurement`; they do not expose an authorizable marker.

Update the synthesis instruction to say:

```python
"Every material claim that uses a catalog measurement must end with the exact "
"[[evidence:<EvidenceRecord ID>#<measurement_key>]] marker shown for that measurement. "
"Do not combine an EvidenceRecord ID with a different measurement key."
```

- [ ] **Step 5: Run catalog, synthesis, and audit extraction suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_automatic_evidence_projection.py tests/test_synthesis_policy.py tests/test_final_answer_claim_audit.py -q
```

Expected: PASS; legacy record-only markers still parse with an empty
`measurement_key`, but new catalogs instruct only measurement-grain syntax.

- [ ] **Step 6: Commit the synthesis reference contract**

```powershell
git add src/data_agent/agent/evidence_contracts.py src/data_agent/agent/synthesis_policy.py src/data_agent/agent/answer_quality.py tests/test_automatic_evidence_projection.py tests/test_final_answer_claim_audit.py tests/test_synthesis_policy.py
git commit -m "feat: reference exact measurements in synthesis"
```

---

### Task 4: Independently verify metric and claim identity

**Files:**
- Modify: `src/data_agent/agent/verification.py:80-115`
- Modify: `src/data_agent/agent/verification.py:620-705`
- Modify: `src/data_agent/agent/verification.py:760-925`
- Modify: `tests/test_final_answer_claim_audit.py`
- Modify: `tests/test_verification_layer.py`
- Modify: `tests/test_stage3c0b_verification_compatibility.py`

**Interfaces:**
- Consumes: claim `evidence_refs`, current evidence, current plan/version
  context, and strict semantic verification.
- Produces:
  - exact measurement resolution;
  - `measurement_key` in claim checks;
  - stable reason codes from the approved design;
  - legacy single-measurement compatibility.

- [ ] **Step 1: Add positive and adversarial canonical-verifier tests**

Add helpers that use a real validated identity-bearing evidence record, then:

```python
def test_exact_measurement_marker_verifies_revenue_claim(identity_evidence):
    marker = (
        f"[[evidence:{identity_evidence['id']}#"
        f"{identity_evidence['measurements'][0]['identity']['measurement_key']}]]"
    )
    audit = _audit(
        f"Revenue increased 12% in 2026-05 for new users {marker}.\n"
        "Limitation: descriptive comparison only.",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
    )
    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["status"] == "passed"


def test_revenue_measurement_marker_cannot_verify_profit_claim(identity_evidence):
    marker = (
        f"[[evidence:{identity_evidence['id']}#"
        f"{identity_evidence['measurements'][0]['identity']['measurement_key']}]]"
    )
    audit = _audit(
        f"Profit increased 12% in 2026-05 for new users {marker}.",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
    )
    assert audit["status"] == "blocked"
    assert "measurement_metric_mismatch" in audit["claim_checks"][0]["reason_codes"]


def test_wrong_measurement_key_is_not_resolved(identity_evidence):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{identity_evidence['id']}#m_wrong]].",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
    )
    assert audit["status"] == "blocked"
    assert "measurement_not_found" in audit["claim_checks"][0]["reason_codes"]
```

Add a direct `verify_analysis_claims` test with a hand-built claim containing
`evidence_refs`, proving the canonical verifier rejects the profit claim even
when extraction is bypassed.

- [ ] **Step 2: Run the adversarial tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_final_answer_claim_audit.py -k "measurement_marker or revenue_measurement or wrong_measurement" -q
```

Expected: FAIL because verification resolves only record IDs and searches all
measurements without metric identity.

- [ ] **Step 3: Resolve exact measurement references**

Add:

```python
def _claim_evidence_refs(claim: Any) -> list[dict[str, str]]:
    if not isinstance(claim, dict):
        return []
    refs = []
    for item in _normalize_items(claim.get("evidence_refs")):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        measurement_key = str(item.get("measurement_key") or "").strip()
        if evidence_id:
            refs.append({
                "evidence_id": evidence_id,
                "measurement_key": measurement_key,
            })
    return refs


def _identity_measurements(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in _normalize_items(record.get("measurements"))
        if isinstance(item, dict)
        and isinstance(item.get("identity"), dict)
    ]
```

Resolution rules:

1. New reference: evidence ID and measurement key must both resolve exactly.
2. Legacy reference with no key: it may resolve only when the evidence has
   exactly one identity-bearing measurement.
3. Multiple, missing, or duplicate keys return stable failure codes.
4. The selected measurement, not every measurement in the record, is passed to
   strict semantic checks.

- [ ] **Step 4: Add independent identity checks**

Implement:

```python
def _measurement_identity_issues(
    claim: dict[str, Any],
    evidence: dict[str, Any],
    measurement: dict[str, Any],
    *,
    current_plan_id: str,
    current_plan_digest: str,
    current_step_digests: dict[str, str],
    current_dataset_versions: set[str] | None,
    active_requirement_ids: set[str],
) -> list[tuple[str, str]]:
    identity = measurement.get("identity")
    if not isinstance(identity, dict):
        return [(
            "measurement_identity_missing",
            "Referenced measurement has no server-owned identity.",
        )]
    validation = validate_measurement_identity(identity)
    if not validation.ok:
        return [(
            "measurement_marker_invalid",
            "Referenced measurement identity is invalid.",
        )]
    checks = [
        (
            identity.get("plan_id") == current_plan_id,
            "measurement_marker_invalid",
            "Measurement plan identity does not match the current plan.",
        ),
        (
            not current_plan_digest
            or identity.get("plan_version") == current_plan_digest,
            "measurement_marker_invalid",
            "Measurement plan version does not match the current plan.",
        ),
        (
            not current_plan_digest
            or all(
                str(ref.get("plan_digest") or "")
                == identity.get("plan_version")
                for ref in evidence.get("computation_refs") or []
                if isinstance(ref, dict)
            ),
            "measurement_marker_invalid",
            "Measurement plan version does not match its computation.",
        ),
        (
            identity.get("claim_key") == evidence.get("claim_key"),
            "measurement_claim_key_mismatch",
            "Measurement claim key does not match its EvidenceRecord.",
        ),
        (
            identity.get("step_id") == evidence.get("step_id"),
            "measurement_marker_invalid",
            "Measurement step does not match its EvidenceRecord.",
        ),
        (
            not current_step_digests
            or identity.get("step_id") in current_step_digests,
            "measurement_marker_invalid",
            "Measurement step is absent from the current plan revision.",
        ),
    ]
    issues = [(code, message) for ok, code, message in checks if not ok]
    computation_ref_ids = {
        computation_ref_key(ref)
        for ref in evidence.get("computation_refs") or []
        if isinstance(ref, dict)
    }
    if identity.get("computation_ref_id") not in computation_ref_ids:
        issues.append((
            "measurement_marker_invalid",
            "Measurement computation identity does not match its EvidenceRecord.",
        ))
    identity_requirement_ids = {
        str(item) for item in identity.get("requirement_ids") or []
    }
    evidence_requirement_ids = {
        str(item) for item in evidence.get("requirement_ids") or []
    }
    if (
        identity_requirement_ids != evidence_requirement_ids
        or not identity_requirement_ids
        or not identity_requirement_ids.issubset(active_requirement_ids)
    ):
        issues.append((
            "measurement_claim_key_mismatch",
            "Measurement requirements are not eligible in the current plan.",
        ))
    identity_versions = {
        str(item) for item in identity.get("dataset_versions") or []
    }
    evidence_versions = {
        str(item) for item in evidence.get("dataset_versions") or []
    }
    if (
        current_dataset_versions is None
        or identity_versions != evidence_versions
        or identity_versions != current_dataset_versions
    ):
        issues.append((
            "measurement_dataset_version_mismatch",
            "Measurement dataset versions do not exactly match the current scope.",
        ))
    if not _claim_mentions_trusted_metric(
        _claim_text(claim),
        identity.get("metric_label"),
        identity.get("metric_aliases"),
    ):
        issues.append((
            "measurement_metric_mismatch",
            "Claim metric wording does not match the referenced measurement.",
        ))
    for field, code in (
        ("value", "numeric_mismatch"),
        ("unit", "unit_mismatch"),
        ("direction", "direction_mismatch"),
        ("time_scope", "measurement_scope_mismatch"),
        ("population_scope", "measurement_scope_mismatch"),
    ):
        if identity.get(field) != measurement.get(field):
            issues.append((
                code,
                f"Measurement identity {field} does not match the selected measurement.",
            ))
    return issues
```

`_claim_mentions_trusted_metric` normalizes punctuation and whitespace but uses
only the complete server-trusted label/aliases. It does not use embeddings,
LLM judgment, token-overlap thresholds, or isolated generic words such as
`correlation`.

Pass `current_plan_digest`, `current_step_digests`, and the IDs from
`analysis_requirements` into this function. After these identity checks,
compare the selected measurement's `allowed_claim_class` against the existing
server-classified claim semantics; a causal or inferential overclaim returns
the existing bounded semantic failure and can never be verified. The existing
computation-ref hydration still independently checks plan and step digests;
the identity check does not replace it.

Import `validate_measurement_identity` and `computation_ref_key` locally in the
verifier to avoid a module cycle.

- [ ] **Step 5: Restrict strict semantic checks to the selected measurement**

Change:

```python
def _strict_semantic_issues(
    claim: Any,
    evidence: dict[str, Any],
    *,
    selected_measurements: list[dict[str, Any]] | None = None,
) -> list[tuple[str, str]]:
    measurements = (
        selected_measurements
        if selected_measurements is not None
        else _measurement_items(evidence)
    )
```

Pass the resolved measurement to this call. Add `measurement_key` to the
finalized claim check for observability.

- [ ] **Step 6: Run verifier, audit, and compatibility suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_final_answer_claim_audit.py tests/test_verification_layer.py tests/test_stage3c0b_verification_compatibility.py tests/test_computation_evidence_binding.py -q
```

Expected: PASS; direct legacy verification callers remain compatible, while
final-answer measurement references receive the new checks.

- [ ] **Step 7: Commit independent measurement verification**

```powershell
git add src/data_agent/agent/verification.py tests/test_final_answer_claim_audit.py tests/test_verification_layer.py tests/test_stage3c0b_verification_compatibility.py
git commit -m "feat: verify metric and claim measurement identity"
```

---

### Task 5: Add rollout modes and non-disruptive publication

**Files:**
- Modify: `src/data_agent/config.py:38-57`
- Modify: `src/data_agent/agent/answer_quality.py:268-340`
- Modify: `src/data_agent/agent/verification.py:760-925`
- Modify: `src/data_agent/agent/trust_workflow_runtime.py:21-53`
- Modify: `src/data_agent/agent/loop.py:110-120`
- Modify: `src/data_agent/agent/loop.py:2305-2580`
- Modify: `tests/test_workspace_config.py`
- Modify: `tests/test_final_answer_claim_audit.py`
- Modify: `tests/test_final_answer_publish_gate.py`
- Modify: `tests/test_tiered_analysis_publication.py`

**Interfaces:**
- Consumes: configured `measurement_evidence_binding_mode`.
- Produces:
  - `Literal["shadow", "soft", "enforced"]`, default `soft`;
  - exploratory treatment for an exact non-authorizing candidate in `soft`;
  - unsupported treatment for contradictions or missing computation;
  - no analysis-tool retry for marker/identity bookkeeping.

- [ ] **Step 1: Write configuration and mode behavior tests**

Add:

```python
def test_measurement_binding_mode_defaults_to_soft():
    cfg = AgentConfig(_env_file=None)
    assert cfg.measurement_evidence_binding_mode == "soft"


@pytest.mark.parametrize("mode", ["shadow", "soft", "enforced"])
def test_measurement_binding_modes_are_valid(mode):
    cfg = AgentConfig(
        MEASUREMENT_EVIDENCE_BINDING_MODE=mode,
        _env_file=None,
    )
    assert cfg.measurement_evidence_binding_mode == mode


def test_measurement_binding_mode_has_no_off_value():
    with pytest.raises(ValidationError):
        AgentConfig(
            MEASUREMENT_EVIDENCE_BINDING_MODE="off",
            _env_file=None,
        )
```

Add audit behavior:

```python
def test_soft_mode_downgrades_exact_markerless_candidate(identity_evidence):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
        measurement_binding_mode="soft",
    )
    assert audit["status"] == "revise"
    assert audit["claim_checks"][0]["status"] == "downgraded"
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


def test_soft_mode_downgrades_current_auto_projected_unbound_measurement(
    unbound_projected_evidence,
):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[unbound_projected_evidence],
        current_dataset_versions=["dataset_sales_v1"],
        measurement_binding_mode="soft",
    )
    check = audit["claim_checks"][0]
    assert audit["status"] == "revise"
    assert check["status"] == "downgraded"
    assert check["evidence_ids"] == []
    assert "measurement_identity_missing" in check["reason_codes"]


def test_soft_mode_does_not_publish_uncomputed_number_as_exploratory():
    audit = _audit(
        "Profit increased 99% in 2026-05 for new users.",
        evidence=[],
        current_dataset_versions=["dataset_sales_v1"],
        measurement_binding_mode="soft",
    )
    assert audit["status"] == "blocked"


def test_shadow_mode_records_exact_v2_match_without_authorizing_it(
    identity_evidence,
):
    audit = _audit_with_exact_marker(
        identity_evidence,
        measurement_binding_mode="shadow",
    )
    assert audit["status"] == "revise"
    assert audit["claim_checks"][0]["status"] == "downgraded"
    assert audit["measurement_binding_diagnostics"] == {
        "mode": "shadow",
        "v2_exact_match_count": 1,
        "v2_authorized_count": 0,
    }


def test_soft_mode_authorizes_exact_v2_marker(identity_evidence):
    audit = _audit_with_exact_marker(
        identity_evidence,
        measurement_binding_mode="soft",
    )
    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["status"] == "passed"
```

Add a loop test showing `measurement_identity_missing` may trigger at most one
synthesis revision and never `mode="analysis"`.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_workspace_config.py tests/test_final_answer_claim_audit.py -k "measurement_binding or markerless or uncomputed" tests/test_final_answer_publish_gate.py -k "measurement" -q
```

Expected: FAIL because the setting and soft behavior do not exist.

- [ ] **Step 3: Add validated configuration and runtime propagation**

In `AgentConfig`:

```python
measurement_evidence_binding_mode: Literal[
    "shadow", "soft", "enforced"
] = Field(
    alias="MEASUREMENT_EVIDENCE_BINDING_MODE",
    default="soft",
)
```

Add keyword-only `measurement_binding_mode: str = "enforced"` to
`build_final_answer_audit` and `verify_analysis_claims`. In
`audit_final_answer_draft`, read the validated setting and pass it into the
audit. Direct non-final verifier callers retain `enforced` by default.

- [ ] **Step 4: Implement exact non-authorizing candidate discovery**

In `verification.py`, implement a helper used only for exploratory downgrade:

```python
def _exact_exploratory_measurement_candidates(
    claim: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    *,
    current_plan_id: str,
    current_plan_digest: str,
    current_step_digests: dict[str, str],
    current_dataset_versions: set[str] | None,
    active_requirement_ids: set[str],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    candidates = []
    for evidence in _current_plan_evidence(evidence_records, current_plan_id):
        if not _has_current_bound_computation(
            evidence,
            current_plan_digest=current_plan_digest,
            current_step_digests=current_step_digests,
            current_dataset_versions=current_dataset_versions,
        ):
            continue
        for measurement in _measurement_items(evidence):
            identity = measurement.get("identity")
            if isinstance(identity, dict):
                identity_issues = _measurement_identity_issues(
                    claim,
                    evidence,
                    measurement,
                    current_plan_id=current_plan_id,
                    current_plan_digest=current_plan_digest,
                    current_step_digests=current_step_digests,
                    current_dataset_versions=current_dataset_versions,
                    active_requirement_ids=active_requirement_ids,
                )
            elif (
                measurement.get("identity_status")
                == "metric_identity_missing"
                and _claim_matches_projected_metric_fields(claim, measurement)
            ):
                identity_issues = []
            else:
                continue
            semantic_issues = _strict_semantic_issues(
                claim,
                evidence,
                selected_measurements=[measurement],
            )
            if not identity_issues and not semantic_issues:
                candidates.append((evidence, measurement))
    return candidates
```

When an explicit measurement reference is missing:

- `soft` or `shadow` plus exactly one candidate: return `downgraded`,
  `strength="exploratory"`, code `measurement_identity_missing`;
- no candidate: return failed `missing_evidence_identity`;
- multiple candidates: return failed `measurement_ambiguous`;
- `enforced`: return failed `measurement_identity_missing`.

Candidate discovery never sets `evidence_ids`, never sets
`measurement_key`, and never returns `passed`.

`_has_current_bound_computation` requires hydrated `computation_ref.v1`,
current plan/step digests, and exact dataset versions. The unbound branch is
available only for measurements produced by the current server projector with
`identity_status="metric_identity_missing"`; it matches the claim against the
projected measurement's declared `metric`/`definition` fields and exact
value/unit/direction/scope. Arbitrary historical or model-authored
measurements do not become candidates.

A legacy record-only marker that resolves to one current unbound projected
measurement follows this same exploratory path. It never becomes verified.

For an explicit exact v2 reference, `soft` and `enforced` may authorize only
after every canonical check passes. `shadow` runs and counts the same checks
but does not change the pre-v2 publication result and never returns `passed`
solely because v2 matched. Persist bounded
`measurement_binding_diagnostics` with the selected mode, exact-match count,
authorized count, downgrade count, and contradiction count; do not persist
claim text or measurement values in this diagnostic.

- [ ] **Step 5: Prevent measurement bookkeeping from scheduling tools**

Define:

```python
_MEASUREMENT_BOOKKEEPING_CODES = {
    "measurement_identity_missing",
    "measurement_marker_invalid",
    "measurement_not_found",
    "measurement_metric_mismatch",
    "measurement_claim_key_mismatch",
    "measurement_scope_mismatch",
    "measurement_dataset_version_mismatch",
    "measurement_ambiguous",
}
```

Keep these codes out of `_COMPUTATION_REPAIR_REASON_CODES`. Treat
`measurement_identity_missing` and `measurement_marker_invalid` as eligible
for the existing one synthesis-only revision when evidence exists. All other
measurement contradictions proceed directly to tiered claim publication.

Update the synthesis repair instruction to use measurement-grain markers and
explicitly say `Do not call tools`.

- [ ] **Step 6: Run publication and no-recomputation suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_workspace_config.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_tiered_analysis_publication.py tests/test_execution_control.py -q
```

Expected: PASS; missing identity preserves a complete exploratory answer when
an exact computation candidate exists, and no measurement code causes an
analysis retry.

- [ ] **Step 7: Commit rollout and publication behavior**

```powershell
git add src/data_agent/config.py src/data_agent/agent/answer_quality.py src/data_agent/agent/verification.py src/data_agent/agent/trust_workflow_runtime.py src/data_agent/agent/loop.py tests/test_workspace_config.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py tests/test_tiered_analysis_publication.py
git commit -m "feat: roll out measurement binding without blocking analysis"
```

---

### Task 6: Prove the real projection-to-publication pipeline

**Files:**
- Create: `tests/test_measurement_identity_pipeline.py`
- Modify: `tests/fixtures/measurement_identity.py`
- Modify: `tests/replay_assertions.py`
- Modify: `tests/test_analysis_reliability_replays.py`
- Modify: `scripts/replay_analysis_reliability.py`

**Interfaces:**
- Consumes: real persisted tool artifact, real projection, real catalog,
  real final audit, and real tiered renderer.
- Produces: one deterministic end-to-end proof and mutation-style
  counterexamples that fail when a load-bearing check is removed.

- [ ] **Step 1: Write the real end-to-end success test**

Import `build_projection_context` and `project_real_correlation` from
`tests.fixtures.measurement_identity`, then:

```python
def test_real_computation_projects_and_publishes_exact_measurement(
    projection_context,
):
    projection = project_real_correlation(projection_context)
    evidence = projection.record
    identity = evidence["measurements"][0]["identity"]
    catalog = build_bounded_evidence_catalog([evidence])

    assert identity["measurement_key"] in catalog
    draft = (
        "# 结论\n\n"
        "Revenue cost correlation is 0.4 "
        f"[[evidence:{evidence['id']}#{identity['measurement_key']}]].\n\n"
        "## 局限\n\n"
        "This is an association, not a causal estimate."
    )
    audit = build_final_answer_audit(
        draft,
        evidence_records=[evidence],
        current_plan_id=PLAN_ID,
        current_dataset_versions=[DATASET_VERSION],
        sessions_root=projection_context.sessions_root,
        current_session_id=SESSION_ID,
        current_plan_digest=PLAN_DIGEST,
        current_step_digests={STEP_ID: STEP_DIGEST},
        analysis_requirements=projection_context.analysis_requirements,
        measurement_binding_mode="soft",
    )
    assert audit["status"] == "pass"

    publication = render_audited_analysis_answer(
        draft=draft,
        audit=audit,
        completion=_complete_with_limits(),
        mode="tiered",
    )
    assert "# 结论" in publication.text
    assert "Revenue cost correlation is 0.4" in publication.text
    assert "[[evidence:" not in publication.text
```

Use a real `CompletionDecision` fixture; do not replace the renderer or audit
with mocks.

- [ ] **Step 2: Add mutation-style counterexamples**

Add parameterized mutations:

```python
@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("metric_key", "measurement_metric_mismatch"),
        ("claim_key", "measurement_claim_key_mismatch"),
        ("plan_id", "measurement_marker_invalid"),
        ("plan_version", "measurement_marker_invalid"),
        ("step_id", "measurement_marker_invalid"),
        ("requirement_ids", "measurement_claim_key_mismatch"),
        ("dataset_versions", "measurement_dataset_version_mismatch"),
        ("computation_ref_id", "measurement_marker_invalid"),
        ("value", "numeric_mismatch"),
        ("unit", "unit_mismatch"),
        ("direction", "direction_mismatch"),
        ("time_scope", "measurement_scope_mismatch"),
        ("population_scope", "measurement_scope_mismatch"),
    ],
)
def test_tampered_measurement_identity_never_publishes_verified(
    projection_context,
    mutation,
    reason,
):
    evidence = copy.deepcopy(project_real_correlation(projection_context).record)
    identity = evidence["measurements"][0]["identity"]
    changed_values = {
        "dataset_versions": ["stale_v0"],
        "requirement_ids": ["req_wrong"],
        "value": 999,
    }
    identity[mutation] = changed_values.get(mutation, "wrong")
    if mutation == "metric_key":
        identity["metric_label"] = "profit cost correlation"
        identity["metric_aliases"] = [
            "profit cost correlation",
            "cost profit correlation",
        ]
    identity["measurement_key"] = measurement_key_for(identity)
    audit = _audit_with_marker(
        evidence,
        measurement_key=identity["measurement_key"],
    )
    assert audit["status"] == "blocked"
    assert reason in audit["claim_checks"][0]["reason_codes"]
```

Add the same-value revenue/profit counterexample using a valid untampered
identity; it must fail with `measurement_metric_mismatch`, not merely a bad-key
error. Recomputing the key after each mutation is essential: these tests prove
that the verifier independently checks current plan, claim, metric, and
dataset context instead of relying only on key self-consistency.

- [ ] **Step 3: Run the new pipeline tests and fix only test-fixture wiring**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_measurement_identity_pipeline.py -q
```

Expected: PASS using production functions from computation persistence through
publication.

- [ ] **Step 4: Update deterministic replay markers**

Change scripted final answers in `scripts/replay_analysis_reliability.py` to
use the actual projected evidence ID and measurement key obtained from state,
not hard-coded record-only markers. Add replay assertions:

```python
assert all(
    isinstance(measurement.get("identity"), dict)
    for record in result.evidence_records
    for measurement in record.get("measurements") or []
    if measurement.get("identity_status") != "metric_identity_missing"
)
```

The deterministic replay may publish `complete_with_limits`; it must not
fabricate a verified marker when the scripted tool output lacks trusted metric
context.

Remove the factor scenario's scripted `record_evidence_record` call. Its
successful path must use evidence automatically projected from the real
`quick_profile`, `correlation_analysis`, and
`factor_relationship_analysis` outputs. Assert every evidence record used by
the final marker has `provenance_status="bound"`, at least one
`computation_ref`, and a validated measurement identity.

Extend `ReplayResult` with:

```python
successful_capability_ids: list[str] = field(default_factory=list)
requirement_statuses: dict[str, str] = field(default_factory=dict)
published_limitations: list[str] = field(default_factory=list)
```

Derive `requirement_statuses` by calling the production
`evaluate_requirement_satisfaction` over the current canonical
`analysis_requirements` and real projected evidence. Do not infer coverage
from final-answer keywords.

Add semantic quality assertions:

```python
def test_factor_replay_satisfies_semantic_depth_not_tool_count(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        root=tmp_path,
    )
    assert {
        "data.profile",
        "analysis.correlation",
        "analysis.factor_relationship",
    }.issubset(result.successful_capability_ids)
    for name in (
        "grain_definition",
        "target_definition",
        "missingness_assessment",
        "univariate_association",
        "multivariable_adjustment",
        "multiplicity_control",
        "collinearity_assessment",
        "effect_size_or_predictive_contribution",
        "limitations_and_alternatives",
    ):
        assert result.requirement_statuses[name] == "satisfied"
    for name in ("stability_or_validation", "time_dependence_assessment"):
        assert result.requirement_statuses[name] in {"satisfied", "limited"}


def test_repeated_superficial_tools_cannot_complete_factor_request(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        responses=_superficial_profile_only_responses(repetitions=6),
        fallback_text="活跃度显著影响目标值。",
        root=tmp_path,
        session_id="superficial_replay",
    )
    assert result.requirement_statuses["multivariable_adjustment"] != "satisfied"
    assert result.requirement_statuses["collinearity_assessment"] != "satisfied"
    assert result.completion_state != "complete"
    assert "显著影响" not in result.final_answer
```

`limited` is assigned only when the requirement evaluator reports unmet with
an allowed downgrade/disclosure action and the audited publication contains
the matching bounded limitation. Six tool calls are not themselves evidence
of depth.

- [ ] **Step 5: Run deterministic replay and focused release suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_measurement_identity_pipeline.py tests/test_analysis_reliability_replays.py tests/test_automatic_evidence_projection.py tests/test_final_answer_claim_audit.py tests/test_final_answer_publish_gate.py -q
$phaseBReplayRoot = Join-Path $env:TEMP ("data-agent-phase-b-" + [guid]::NewGuid().ToString("N"))
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/replay_analysis_reliability.py --mode deterministic --output-dir $phaseBReplayRoot
```

Expected: pytest PASS; replay JSON has `accepted: true`, all four deterministic
scenarios true, and no generic English publication warning.

- [ ] **Step 6: Commit the end-to-end proof**

```powershell
git add tests/fixtures/measurement_identity.py tests/test_measurement_identity_pipeline.py tests/test_analysis_reliability_replays.py scripts/replay_analysis_reliability.py
git commit -m "test: prove measurement identity end to end"
```

---

### Task 7: Make deterministic release status truthful

**Files:**
- Modify: `scripts/replay_analysis_reliability.py:70-95`
- Modify: `scripts/replay_analysis_reliability.py:790-951`
- Create: `scripts/run_analysis_release_gates.py`
- Create: `tests/test_analysis_release_gate_runner.py`
- Modify: `tests/test_analysis_reliability_replays.py`

**Interfaces:**
- Consumes: subprocess command results and optional browser/live receipt JSON.
- Produces:
  - gate status `PASS | FAIL | NOT_RUN | BLOCKED`;
  - deterministic profile A-D;
  - product profile A-F;
  - non-zero exit unless every required gate in the selected profile is PASS.

- [ ] **Step 1: Write false-green regression tests**

Add:

```python
def test_live_replay_without_provider_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(
        replay_analysis_reliability,
        "get_config",
        lambda: SimpleNamespace(api_key=None, model_id="gpt-4o"),
        raising=False,
    )
    summary = run_release_replay(tmp_path, mode="live")
    assert summary["accepted"] is False
    assert summary["overall_status"] == "BLOCKED"
    assert summary["live_provider_status"] == "BLOCKED"


def test_deterministic_profile_does_not_claim_browser_pass():
    report = build_gate_report(
        profile="deterministic",
        gate_results={
            "A": "PASS", "B": "PASS", "C": "PASS", "D": "PASS",
        },
    )
    assert report["overall_status"] == "PASS"
    assert report["gates"]["E"]["status"] == "NOT_RUN"
    assert report["gates"]["F"]["status"] == "NOT_RUN"
    assert report["product_release_passed"] is False


def test_product_profile_fails_when_browser_or_live_gate_is_not_run():
    report = build_gate_report(
        profile="product",
        gate_results={
            "A": "PASS", "B": "PASS", "C": "PASS", "D": "PASS",
            "E": "NOT_RUN", "F": "NOT_RUN",
        },
    )
    assert report["overall_status"] == "FAIL"
    assert report["product_release_passed"] is False


def test_harness_inspection_rejects_release_critical_collect_ignore(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        'collect_ignore = ["test_web_gui.py"]\n',
        encoding="utf-8",
    )
    result = inspect_test_harness(conftest)
    assert result["status"] == "FAIL"
    assert result["release_critical_ignored"] == ["test_web_gui.py"]


def test_harness_inspection_classifies_the_direct_tool_runner(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        'collect_ignore = ["test_tools_comprehensive.py"]\n',
        encoding="utf-8",
    )
    result = inspect_test_harness(conftest)
    assert result["status"] == "PASS"
    assert result["required_direct_runners"] == [
        "tests/test_tools_comprehensive.py"
    ]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_analysis_release_gate_runner.py tests/test_analysis_reliability_replays.py -q
```

Expected: FAIL because live replay currently reports `accepted: true` when no
provider and no gate aggregator exists.

- [ ] **Step 3: Correct misleading streamed-text naming**

Rename `ReplayResult.browser_text` to `streamed_text`. Update all deterministic
helpers and tests. Do not call deterministic SSE aggregation a browser result.

If a compatibility property is required by another current caller, define:

```python
@property
def browser_text(self) -> str:
    """Deprecated name; this is SSE text aggregation, not browser evidence."""
    return self.streamed_text
```

No release report may use the compatibility name.

- [ ] **Step 4: Implement the gate report**

Create:

```python
VALID_GATE_STATUSES = {"PASS", "FAIL", "NOT_RUN", "BLOCKED"}
DETERMINISTIC_REQUIRED = ("A", "B", "C", "D")
PRODUCT_REQUIRED = ("A", "B", "C", "D", "E", "F")


def build_gate_report(
    *,
    profile: str,
    gate_results: dict[str, str],
) -> dict[str, Any]:
    if profile not in {"deterministic", "product"}:
        raise ValueError("profile must be deterministic or product")
    required = (
        DETERMINISTIC_REQUIRED
        if profile == "deterministic"
        else PRODUCT_REQUIRED
    )
    gates = {}
    for gate in ("A", "B", "C", "D", "E", "F"):
        status = gate_results.get(gate, "NOT_RUN")
        if status not in VALID_GATE_STATUSES:
            raise ValueError(f"invalid gate status for {gate}: {status}")
        gates[gate] = {"status": status}
    passed = all(gates[gate]["status"] == "PASS" for gate in required)
    return {
        "contract_version": "analysis_reliability_release.v1",
        "profile": profile,
        "overall_status": "PASS" if passed else "FAIL",
        "product_release_passed": (
            profile == "product"
            and all(gates[gate]["status"] == "PASS" for gate in PRODUCT_REQUIRED)
        ),
        "gates": gates,
    }
```

The CLI runs the declared deterministic commands, records their exact exit
codes, and emits JSON to stdout. Product mode additionally requires explicit
browser and live-provider receipt files whose contract version and PASS status
are validated.

Gate A calls `inspect_test_harness(tests/conftest.py)`, fails for ignored
`test_sse_reactivity.py` or `test_web_gui.py`, and reports
`test_tools_comprehensive.py` as an explicit direct runner. Its pytest command
uses `-W error::pytest.PytestReturnNotNoneWarning`; its direct-runner command
must exit non-zero when its internal `FAIL` count is non-zero. Plan B Tasks
1-3 remove the current Web collection violation before this deterministic
profile may report Gate A PASS.

- [ ] **Step 5: Make live replay fail truthfully when not exercised**

In `run_release_replay(..., mode="live")`, return:

```python
{
    "accepted": False,
    "overall_status": "BLOCKED",
    "mode": "live",
    "live_provider_status": "BLOCKED",
    "reason": "provider_credentials_unavailable",
}
```

when credentials are unavailable. When credentials exist but live execution is
not yet implemented, use reason `live_provider_runner_not_implemented` and the
same blocked status. Phase C replaces this branch with real three-run
execution.

- [ ] **Step 6: Run gate-runner and deterministic replay tests**

Complete Plan B Tasks 1-3 before running the deterministic CLI; otherwise its
Gate A result must truthfully remain FAIL because release-critical Web scripts
are still ignored.

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_analysis_release_gate_runner.py tests/test_analysis_reliability_replays.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/run_analysis_release_gates.py --profile deterministic
```

Expected: tests PASS; deterministic report may be PASS for A-D but explicitly
shows E/F `NOT_RUN` and `product_release_passed: false`.

- [ ] **Step 7: Run the Phase B deterministic release gate**

First complete Tasks 1-3 of
`2026-07-28-web-sse-and-live-release-validation.md`; they are Phase B test
harness and implementation work, not Gate E browser acceptance.

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -W error::pytest.PytestReturnNotNoneWarning tests/test_measurement_identity_pipeline.py tests/test_automatic_evidence_projection.py tests/test_final_answer_claim_audit.py tests/test_verification_layer.py tests/test_final_answer_publish_gate.py tests/test_tiered_analysis_publication.py tests/test_analysis_reliability_replays.py tests/test_analysis_release_gate_runner.py tests/test_web_sse_contract.py tests/test_web_sse_reactivity_contract.py -q
$phaseBGateReplayRoot = Join-Path $env:TEMP ("data-agent-phase-b-gate-" + [guid]::NewGuid().ToString("N"))
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/replay_analysis_reliability.py --mode deterministic --output-dir $phaseBGateReplayRoot
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' tests/test_tools_comprehensive.py
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m compileall -q src/data_agent
node --check src/data_agent/web/static/js/app.js
git diff --check
```

Expected:

- all focused pytest tests pass;
- deterministic replay exits 0;
- direct comprehensive runner reports zero FAIL and exits 0;
- compile, Node syntax, and diff checks exit 0;
- no browser or live-provider PASS is claimed.

- [ ] **Step 8: Commit truthful deterministic gate reporting**

```powershell
git add scripts/replay_analysis_reliability.py scripts/run_analysis_release_gates.py tests/test_analysis_release_gate_runner.py tests/test_analysis_reliability_replays.py
git commit -m "test: report analysis release gates truthfully"
```

---

## Plan-level review and stop gate

Before Phase C:

1. Complete Plan B Tasks 1-3, then run every Task 7 Step 7 command from the
   worktree source.
2. Request a fresh specification-compliance review against
   `docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md`.
3. Request a separate code-quality review.
4. Reproduce the revenue-versus-profit counterexample through the public
   `build_final_answer_audit` path.
5. Confirm the real projector, not a hand-built evidence record, supplies the
   successful identity used by the end-to-end test.
6. Confirm every measurement bookkeeping reason code is absent from the
   analysis retry set.
7. Report the result as "deterministic backend gate" only.
8. Do not merge, push, or mark Task 12 complete.

Phase C is governed by
`docs/superpowers/plans/2026-07-28-web-sse-and-live-release-validation.md`.
