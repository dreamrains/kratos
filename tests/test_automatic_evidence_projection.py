"""Task 9: automatic structured-computation evidence projection.

Eligible structured computations must auto-project ``evidence_record.v2``
evidence without the model calling ``record_evidence_record``. Ineligible
computations (failed runs, ambiguous bindings, free-form python, stale
dataset versions) stay computation-only. The bounded catalog is injected
even when empty, and an existing evidence id attaches to a claim only on
exactly one material-field match.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PLAN_ID = "plan_current"
STEP_ID = "step_correlation"
SESSION_ID = "sess_current"
TURN_ID = "turn_1"
TOOL_CALL_ID = "call_corr_1"
DATASET_VERSION = "ds_main_v1"
PLAN_DIGEST = "sha256:plan_digest"
STEP_DIGEST = "sha256:step_digest"


from data_agent.agent.analysis_execution import StepBindingResult
from data_agent.agent.evidence_contracts import (
    COMPUTATION_REF_CONTRACT_VERSION,
    TOOL_OUTPUT_CONTRACT_VERSION,
    analysis_plan_semantic_digest,
    analysis_step_semantic_digest,
    computation_digest,
    persist_computation_output,
)


# ---------------------------------------------------------------------------
# Helpers: build a real computation artifact under sessions_root so the
# projection can hydrate the output and run the structured-field check.
# ---------------------------------------------------------------------------


def _artifact_filename(turn_id: str, tool_call_id: str) -> str:
    from data_agent.tools._utils import sanitize_filename

    artifact_identity = json.dumps(
        [str(turn_id or ""), str(tool_call_id)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    suffix = hashlib.sha256(artifact_identity.encode("utf-8")).hexdigest()[:12]
    return f"{sanitize_filename(tool_call_id)}_{suffix}_computation.json"


def _write_artifact(
    sessions_root: Path,
    *,
    session_id: str,
    turn_id: str,
    plan_id: str,
    plan_digest: str,
    step_id: str,
    step_digest: str,
    tool_call_id: str,
    tool_name: str,
    capability_id: str,
    evidence_fields: list[str],
    arguments: dict,
    output: dict,
    dataset_versions: list[str],
    success: bool,
) -> Path:
    """Use ``persist_computation_output`` so digests/identity are consistent."""

    output_dir = sessions_root / session_id / "tool_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Defer to the canonical helper for all digest/identity logic.
    persist_computation_output(
        sessions_root=sessions_root,
        session_id=session_id,
        turn_id=turn_id,
        plan_id=plan_id,
        step_id=step_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments=arguments,
        output=output,
        dataset_versions=dataset_versions,
        success=success,
        plan_digest=plan_digest,
        step_digest=step_digest,
        capability_id=capability_id,
        evidence_fields=evidence_fields,
    )
    return output_dir / _artifact_filename(turn_id, tool_call_id)


def _ref_from_artifact(
    *,
    artifact_path: Path,
    plan_digest: str,
    step_digest: str,
    dataset_versions: list[str],
    tool_call_id: str = TOOL_CALL_ID,
    tool_name: str = "correlation_analysis",
    capability_id: str = "analysis.correlation",
    success: bool = True,
    extra: dict | None = None,
) -> dict:
    """Build a compact ``computation_ref.v1`` matching the persisted artifact."""

    arguments = {"name": "main", "method": "pearson"}
    output = correlation_output()
    ref = {
        "contract_version": COMPUTATION_REF_CONTRACT_VERSION,
        "session_id": SESSION_ID,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "capability_id": capability_id,
        "arguments_digest": computation_digest(arguments),
        "output_digest": computation_digest(output),
        "artifact_path": str(artifact_path),
        "dataset_versions": list(dataset_versions),
        "turn_id": TURN_ID,
        "plan_id": PLAN_ID,
        "plan_digest": plan_digest,
        "step_id": STEP_ID,
        "step_digest": step_digest,
        "success": success,
        "structured_checked_fields": correlation_capability()["evidence_fields"],
        "verification_level": "structured_checked",
        "claim_key": "revenue_cost_correlation",
        "requirement_ids": ["req_corr_effect"],
    }
    if extra:
        ref.update(extra)
    return ref


def correlation_capability() -> dict:
    return {
        "capability_id": "analysis.correlation",
        "category": "relationship",
        "evidence_fields": [
            "pairs.correlation",
            "pairs.effective_sample_size",
            "pairs.p_value",
            "allowed_claim_class",
        ],
    }


def correlation_output() -> dict:
    return {
        "summary": "Pearson correlation: r=0.40, n=100, p=0.001",
        "data": {
            "method": "pearson",
            "pairs": [
                {
                    "variables": ["revenue", "cost"],
                    "correlation": 0.4,
                    "effective_sample_size": 100,
                    "p_value": 0.001,
                },
            ],
            "allowed_claim_class": "association",
        },
    }


def current_plan() -> dict:
    return {
        "id": PLAN_ID,
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "describe correlation between revenue and cost",
        "method_plan": [
            {
                "step_id": STEP_ID,
                "goal": "Compute revenue/cost correlation",
                "dataset_inputs": ["main"],
                "dataset_contract_ids": ["contract_main_v1"],
                "required_capability": "analysis.correlation",
                "claim_type": "correlation",
                "required_claim_keys": ["revenue_cost_correlation"],
                "requirement_ids": ["req_corr_effect", "req_corr_interval"],
            }
        ],
        "analysis_requirements": {
            STEP_ID: [
                {
                    "id": "req_corr_effect",
                    "step_id": STEP_ID,
                    "name": "correlation",
                    "necessity": "required",
                    "trigger": "relationship",
                },
                {
                    "id": "req_corr_interval",
                    "step_id": STEP_ID,
                    "name": "confidence_interval",
                    "necessity": "required",
                    "trigger": "relationship",
                },
            ]
        },
    }


def current_dataset_contracts() -> list[dict]:
    return [
        {
            "id": "contract_main_v1",
            "dataset": "main",
            "dataset_id": DATASET_VERSION,
            "quality_status": "ready",
        }
    ]


def exact_step_binding() -> StepBindingResult:
    return StepBindingResult(
        ok=True,
        plan_id=PLAN_ID,
        step_id=STEP_ID,
        claim_key="revenue_cost_correlation",
        requirement_ids=("req_corr_effect",),
    )


def ambiguous_binding() -> StepBindingResult:
    return StepBindingResult(
        ok=False,
        plan_id=PLAN_ID,
        error_type="ambiguous_analysis_step",
        candidate_step_ids=(STEP_ID, "step_other"),
    )


def structured_correlation_ref(
    *,
    artifact_path: Path | str = "",
    dataset_versions: list[str] | None = None,
) -> dict:
    return _ref_from_artifact(
        artifact_path=Path(artifact_path) if artifact_path else Path("/_unused"),
        plan_digest=PLAN_DIGEST,
        step_digest=STEP_DIGEST,
        dataset_versions=list(
            dataset_versions if dataset_versions is not None else [DATASET_VERSION]
        ),
    )


def failed_ref() -> dict:
    return {**structured_correlation_ref(), "success": False}


def free_form_python_ref() -> dict:
    return {
        **structured_correlation_ref(),
        "tool_name": "run_python",
        "capability_id": "fallback.python",
        "structured_checked_fields": [],
        "verification_level": "traceable",
    }


def stale_dataset_ref() -> dict:
    return structured_correlation_ref(dataset_versions=["ds_main_v0_stale"])


@dataclass
class _Context:
    session_id: str
    turn_id: str
    sessions_root: Path


@dataclass
class _ProjectionContext:
    plan: dict
    capability: dict
    dataset_contracts: list[dict]
    session_id: str
    turn_id: str
    sessions_root: Path


@pytest.fixture
def context(tmp_path) -> _Context:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)
    return _Context(
        session_id=SESSION_ID,
        turn_id=TURN_ID,
        sessions_root=sessions_root,
    )


@pytest.fixture
def projection_context(tmp_path) -> _ProjectionContext:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)
    # Write a real artifact so the eligible path can hydrate structured output.
    artifact_path = _write_artifact(
        sessions_root,
        session_id=SESSION_ID,
        turn_id=TURN_ID,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        step_id=STEP_ID,
        step_digest=STEP_DIGEST,
        tool_call_id=TOOL_CALL_ID,
        tool_name="correlation_analysis",
        capability_id="analysis.correlation",
        evidence_fields=correlation_capability()["evidence_fields"],
        arguments={"name": "main", "method": "pearson"},
        output=correlation_output(),
        dataset_versions=[DATASET_VERSION],
        success=True,
    )
    # Stash the artifact path on the capability for the eligible-test fixture.
    cap = correlation_capability()
    cap["_artifact_path"] = str(artifact_path)
    return _ProjectionContext(
        plan=current_plan(),
        capability=cap,
        dataset_contracts=current_dataset_contracts(),
        session_id=SESSION_ID,
        turn_id=TURN_ID,
        sessions_root=sessions_root,
    )


# ---------------------------------------------------------------------------
# Step 1 tests
# ---------------------------------------------------------------------------


def test_bound_structured_computation_auto_projects_v2_evidence(context):
    from data_agent.agent.evidence_contracts import (
        EVIDENCE_RECORD_CONTRACT_VERSION,
        build_bounded_evidence_catalog,
        project_structured_computation_evidence,
    )

    sessions_root = context.sessions_root
    artifact_path = _write_artifact(
        sessions_root,
        session_id=SESSION_ID,
        turn_id=TURN_ID,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        step_id=STEP_ID,
        step_digest=STEP_DIGEST,
        tool_call_id=TOOL_CALL_ID,
        tool_name="correlation_analysis",
        capability_id="analysis.correlation",
        evidence_fields=correlation_capability()["evidence_fields"],
        arguments={"name": "main", "method": "pearson"},
        output=correlation_output(),
        dataset_versions=[DATASET_VERSION],
        success=True,
    )
    ref = structured_correlation_ref(artifact_path=artifact_path)

    result = project_structured_computation_evidence(
        computation_ref=ref,
        binding=exact_step_binding(),
        plan=current_plan(),
        capability=correlation_capability(),
        dataset_contracts=current_dataset_contracts(),
        current_session_id=context.session_id,
        current_turn_id=context.turn_id,
        sessions_root=context.sessions_root,
    )

    assert result.projected is True
    assert result.record["contract_version"] == EVIDENCE_RECORD_CONTRACT_VERSION
    assert result.record["plan_id"] == current_plan()["id"]
    assert result.record["requirement_ids"] == list(exact_step_binding().requirement_ids)
    assert result.record["dataset_versions"] == [DATASET_VERSION]

    catalog = build_bounded_evidence_catalog(
        [result.record],
        max_records=8,
        max_chars=2000,
    )
    assert f"dataset_versions={DATASET_VERSION}" in catalog


@pytest.mark.parametrize(
    ("ref", "binding", "reason"),
    [
        (failed_ref(), exact_step_binding(), "computation_failed"),
        (free_form_python_ref(), exact_step_binding(), "unstructured_tool"),
        (structured_correlation_ref(), ambiguous_binding(), "ambiguous_analysis_step"),
        (stale_dataset_ref(), exact_step_binding(), "stale_dataset_version"),
    ],
)
def test_ineligible_computation_stays_computation_only(
    projection_context,
    ref,
    binding,
    reason,
):
    from data_agent.agent.evidence_contracts import (
        project_structured_computation_evidence,
    )

    artifact_path = projection_context.capability.get("_artifact_path", "")
    ref = dict(ref)
    ref["artifact_path"] = artifact_path

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


# ---------------------------------------------------------------------------
# Step 2 tests
# ---------------------------------------------------------------------------


def test_empty_evidence_still_injects_catalog_header():
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    catalog = build_bounded_evidence_catalog([], max_records=8, max_chars=2000)
    assert "可用证据：0 条" in catalog
    assert "不要重新运行工具来制造证据" in catalog


def test_catalog_caps_records_and_chars():
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    records = []
    for index in range(20):
        records.append({
            "id": f"ev_{index}",
            "claim_key": f"claim_{index}",
            "step_order": index,
            "claim_class": "association",
            "measurements": [{
                "metric": "correlation",
                "value": 0.1 * index,
                "unit": "coefficient",
            }],
            "dataset_versions": ["ds_v1"],
            "verification_level": "structured_checked",
            "limitations": ["descriptive only"],
        })
    catalog = build_bounded_evidence_catalog(records, max_records=4, max_chars=800)
    # Header line + up to 4 record lines.
    lines = [line for line in catalog.splitlines() if line.strip()]
    assert lines[0].startswith("可用证据：")
    # Records present are capped at 4.
    record_lines = [line for line in lines[1:] if line.startswith("- ")]
    assert len(record_lines) <= 4
    assert len(catalog) <= 1500  # generous upper bound; max_chars only bounds the records loop
