from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.agent.golden_answer_runner import (
    load_golden_manifest,
    GoldenManifestError,
)
from data_agent.agent.evidence_contracts import (
    analysis_plan_semantic_digest,
    analysis_step_semantic_digest,
)
from data_agent.session.workspace import Workspace
from tests.fixtures.measurement_identity import bind_validated_measurement_identity

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = next(
    (
        p
        for p in (
            WORKTREE_ROOT / "reference" / "test_doc",
            WORKTREE_ROOT.parents[1] / "reference" / "test_doc",
        )
        if p.is_dir()
    ),
    None,
)
MANIFEST = WORKTREE_ROOT / "tests" / "real_data" / "golden_answer_manifest.json"


def test_load_golden_manifest_valid():
    manifest = load_golden_manifest(MANIFEST)
    assert manifest["schema_version"] == "golden_answer_scenarios.v1"
    ids = [s["id"] for s in manifest["scenarios"]]
    assert ids == [
        "savings_card_business_overview",
        "game_a_multimetric_synthesis",
        "game_b_retention_depth",
        "unrelated_files_false_join_prevention",
    ]
    for scenario in manifest["scenarios"]:
        assert scenario["business_question"]
        assert isinstance(scenario["required_files"], list) and scenario["required_files"]


def test_load_golden_manifest_rejects_missing_schema(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    with pytest.raises(GoldenManifestError):
        load_golden_manifest(bad)


def test_load_golden_manifest_rejects_empty_required_files(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "golden_answer_scenarios.v1",
                "scenarios": [
                    {"id": "s1", "required_files": [], "business_question": "q?"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GoldenManifestError):
        load_golden_manifest(bad)


@pytest.mark.skipif(DATA_DIR is None, reason="reference/test_doc not found")
def test_golden_manifest_files_exist():
    manifest = load_golden_manifest(MANIFEST)
    for scenario in manifest["scenarios"]:
        for name in scenario["required_files"]:
            assert (DATA_DIR / name).is_file(), f"missing {name} for {scenario['id']}"


from data_agent.agent import answer_quality as aq


def test_soft_dimensions_complete():
    keys = set(aq.SOFT_DIMENSIONS)
    assert keys == {"rigor", "insight_depth", "guidance", "data_explanation", "direction_expansion"}
    for spec in aq.SOFT_DIMENSIONS.values():
        assert all(k in spec for k in ("name", "what", "anchor_1", "anchor_3", "anchor_5"))


def test_extract_material_claims_marks_numeric_sentences():
    text = "整体收入增长了20%。其中复购贡献最大。请注意数据范围。"
    claims = aq.extract_material_claims(text)
    material = [c for c in claims if c["material"]]
    non_material = [c for c in claims if not c["material"]]
    assert any("20%" in c["text"] for c in material)
    assert any("数据范围" in c["text"] for c in non_material)
    assert all("claim_key" in c and "text" in c for c in claims)


def test_is_supported_by_evidence():
    evidence = [{"claim": "复购贡献最大", "result_summary": "老客收入+18%"}]
    assert aq.is_supported_by_evidence("复购贡献最大", evidence) is True
    assert aq.is_supported_by_evidence("优惠券导致复购提升", evidence) is False


class _FakeState:
    def __init__(
        self,
        evidence,
        verification_reports=None,
        *,
        analysis_plan=None,
    ):
        self.evidence_records = evidence
        self.verification_reports = verification_reports or []
        self.route_proposals = []
        self.cleaning_logs = []
        self.file_relationships = []
        self.data_understanding_bundles = []
        self.analysis_plan = analysis_plan or {}


def _purchase_evidence_context():
    plan = {
        "id": "plan_purchase",
        "contract_version": "analysis_plan.v1",
        "goal": "Compare spending before and after card purchase.",
        "method_plan": [{
            "step_id": "step_purchase",
            "goal": "Compute the descriptive spending change.",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "required_claim_keys": ["spending_change"],
            "requirement_ids": ["req_spending_change"],
        }],
        "analysis_requirements": {
            "step_purchase": [{
                "contract_version": "analysis_requirement.v1",
                "id": "req_spending_change",
                "step_id": "step_purchase",
                "name": "metric_delta",
                "trigger": "Purchase comparison requires canonical measurement evidence.",
                "category": "measurement",
                "necessity": "required",
                "status": "pending",
                "required_evidence_fields": ["metric_delta"],
                "assumption_checks": [],
                "unmet_action": "disclose",
                "evidence_ids": [],
                "reason": "",
            }],
        },
    }
    workspace = Workspace()
    frame = pd.DataFrame({"spending": [100.0, 150.0]})
    raw = workspace.register_raw_snapshot(
        "orders",
        frame,
        frame_fingerprint(frame),
    )
    active = workspace.promote_analysis_copy(
        "orders",
        frame,
        raw["dataset_id"],
        {"operation": "load_golden_purchase_fixture"},
    )
    dataset_version = active["dataset_id"]
    computation_ref = {
        "contract_version": "computation_ref.v1",
        "session_id": "session_purchase",
        "turn_id": "turn_purchase",
        "tool_call_id": "call_purchase_compare",
        "tool_name": "period_compare",
        "output_digest": "sha256:purchase_compare",
        "plan_id": plan["id"],
        "plan_digest": analysis_plan_semantic_digest(plan),
        "step_id": "step_purchase",
        "step_digest": analysis_step_semantic_digest(plan["method_plan"][0]),
        "dataset_versions": [dataset_version],
        "verification_level": "structured_checked",
        "claim_key": "spending_change",
        "requirement_ids": ["req_spending_change"],
    }
    record = {
        "plan_id": plan["id"],
        "step_id": "step_purchase",
        "claim_key": "spending_change",
        "claim": "买卡后消费提升50%",
        "dataset": "orders",
        "dataset_contract_id": "contract_orders",
        "method": "period_compare",
        "tool_calls": ["call_purchase_compare"],
        "result_summary": "前后对比 +50%",
        "sample_size": 100,
        "time_scope": "fixture period",
        "calculation_method": "before-after ratio",
        "method_detail": "compared spending before and after purchase",
        "metric_delta": {"value": 0.5, "unit": "ratio"},
        "limitations": ["descriptive comparison only"],
        "confidence": "medium",
        "evidence_requirement": "req_spending_change",
        "measurements": [{
            "metric": "消费",
            "definition": "买卡前后消费变化。",
            "value": 0.5,
            "unit": "ratio",
            "grain": "card_buyer",
            "population_scope": "card buyers",
            "time_scope": "fixture period",
            "method": "period_compare",
            "denominator": "spending before purchase",
            "limitations": ["descriptive comparison only"],
            "direction": "increase",
        }],
    }
    evidence = bind_validated_measurement_identity(
        record,
        computation_ref=computation_ref,
        metric_label="消费",
        metric_aliases=["买卡后消费"],
        allowed_claim_class="comparison",
    )
    marker = (
        f"[[evidence:{evidence['id']}#"
        f"{evidence['measurements'][0]['identity']['measurement_key']}]]"
    )
    state = AnalysisSessionState(
        session_id="session_purchase",
        analysis_plan=plan,
        evidence_records=[evidence],
    )
    context = AgentContext(
        session_id=state.session_id,
        workspace=workspace,
        analysis_state=state,
    )
    return state, marker, context


def test_evaluate_fatal_blocks_unsupported_material_claim():
    state = _FakeState(evidence=[{"claim": "留存下降", "result_summary": "D7 较低"}])
    result = aq.evaluate_fatal(
        "买卡后消费提升了50%，是省钱卡直接导致的。", state
    )
    assert result["claim_delivery_ready"] is False
    assert any(b.startswith("unsupported_material_claim") for b in result["blockers"])


def test_evaluate_fatal_passes_when_claim_supported():
    state, marker, context = _purchase_evidence_context()
    assert isinstance(state, AnalysisSessionState)
    with use_agent_context(context):
        result = aq.evaluate_fatal(
            f"买卡后消费提升了50% {marker}。局限：这只是描述性前后对比。",
            state,
        )
    assert result["claim_delivery_ready"] is True
    assert result["blockers"] == []


def test_evaluate_fatal_does_not_accept_fuzzy_support_without_internal_identity():
    state = _FakeState(evidence=[{"id": "ev_purchase", "claim": "买卡后消费提升50%", "result_summary": "前后对比 +50%"}])

    result = aq.evaluate_fatal("买卡后消费提升了50%。", state)

    assert result["claim_delivery_ready"] is False
    assert any(blocker.startswith("unsupported_material_claim") for blocker in result["blockers"])


def test_evaluate_fatal_folds_in_failed_agent_verification():
    state = _FakeState(
        evidence=[{"claim": "x", "result_summary": "x"}],
        verification_reports=[{"overall_status": "fail", "failed_count": 1, "downgraded_count": 0}],
    )
    result = aq.evaluate_fatal("x。", state)
    assert result["claim_delivery_ready"] is False
    assert "agent_verification_failed" in result["blockers"]


def test_evaluate_fatal_no_unsupported_blockers_when_no_evidence():
    # The diagnostic sentence is allowed without positive evidence, but the
    # separate +20% factual claim must still be blocked.
    state = _FakeState(evidence=[])
    result = aq.evaluate_fatal("两个文件没有关联键，不能合并。收入增长20%。", state)
    assert result["claim_delivery_ready"] is False
    assert any(b.startswith("unsupported_material_claim") for b in result["blockers"])


from data_agent.agent import quality_judge as qj


class _StubClient:
    def __init__(self, payload: str):
        self._payload = payload

    def chat(self, messages, tools=None, system=None):
        from data_agent.llm.client import Response

        return Response(text=self._payload)


def test_judge_absolute_parses_scores(monkeypatch):
    payload = '{"insight_depth": {"score": 4, "rationale": "解读到位"}, "rigor": {"score": 3, "rationale": "口径略缺"}}'
    out = qj.judge_absolute(
        answer_text="买卡后消费+50%，主要来自复购。",
        question="省钱卡表现如何？",
        data_brief={"datasets": [], "relationships": []},
        dimensions=["insight_depth", "rigor"],
        client=_StubClient(payload),
    )
    assert out["insight_depth"]["score"] == 4
    assert out["rigor"]["score"] == 3


def test_judge_absolute_returns_empty_on_garbage():
    out = qj.judge_absolute(
        answer_text="x",
        question="q",
        data_brief={"datasets": []},
        dimensions=["insight_depth"],
        client=_StubClient("not json at all"),
    )
    assert out == {}


def test_judge_pairwise_parses_verdicts():
    payload = '{"insight_depth": {"verdict": "worse", "rationale": "新答案更浅"}}'
    out = qj.judge_pairwise(
        baseline_answer="深答案",
        new_answer="浅答案",
        question="q",
        data_brief={"datasets": []},
        dimensions=["insight_depth"],
        client=_StubClient(payload),
    )
    assert out["insight_depth"]["verdict"] == "worse"


def test_judge_normalizes_verdict_casing_and_clamps_score():
    # Live judges sometimes return "Better" / out-of-range scores (e.g. 9).
    payload = '{"insight_depth": {"verdict": "Better", "score": 9, "rationale": "x"}}'
    out = qj.judge_absolute(
        answer_text="ans",
        question="q",
        data_brief={"datasets": []},
        dimensions=["insight_depth"],
        client=_StubClient(payload),
    )
    assert out["insight_depth"]["verdict"] == "better"
    assert out["insight_depth"]["score"] == 5
    assert out["insight_depth"]["rationale"] == "x"


def test_judge_normalizes_worsen_variant_to_worse():
    payload = '{"insight_depth": {"verdict": "Worsen", "rationale": "更浅"}}'
    out = qj.judge_pairwise(
        baseline_answer="深",
        new_answer="浅",
        question="q",
        data_brief={"datasets": []},
        dimensions=["insight_depth"],
        client=_StubClient(payload),
    )
    assert out["insight_depth"]["verdict"] == "worse"


from data_agent.agent import golden_answer_runner as gar


def test_evaluate_answer_composes_fatal_and_soft():
    state, marker, context = _purchase_evidence_context()
    payload = '{"insight_depth": {"score": 2, "rationale": "基本是数值描述"}}'
    with use_agent_context(context):
        out = gar.evaluate_answer(
            answer_text=f"买卡后消费提升了50% {marker}。局限：这只是描述性前后对比。",
            state=state,
            question="省钱卡表现？",
            dimensions=["insight_depth"],
            judge_client=_StubClient(payload),
        )
    assert out["fatal"]["claim_delivery_ready"] is True
    assert out["soft"]["absolute"]["insight_depth"]["score"] == 2
    assert out["soft"]["pairwise"] is None


def test_evaluate_answer_pairwise_when_baseline_given():
    state = _FakeState(evidence=[{"claim": "x", "result_summary": "x"}])
    payload = '{"insight_depth": {"verdict": "worse", "rationale": "更浅"}}'
    out = gar.evaluate_answer(
        answer_text="新答案",
        state=state,
        question="q",
        dimensions=["insight_depth"],
        baseline_answer="旧答案",
        judge_client=_StubClient(payload),
    )
    assert out["soft"]["pairwise"]["insight_depth"]["verdict"] == "worse"


def test_baseline_roundtrip(tmp_path):
    assert gar.read_baseline(tmp_path, "s1") is None
    gar.write_baseline(tmp_path, "s1", "旧答案")
    assert gar.read_baseline(tmp_path, "s1") == "旧答案"


import subprocess
import sys


@pytest.mark.skipif(DATA_DIR is None, reason="reference/test_doc not found")
def test_cli_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.run_golden_answer_quality", "--help"],
        cwd=WORKTREE_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--manifest" in proc.stdout
    assert "--update-baseline" in proc.stdout


# --- Task 8: deterministic regression meta-tests (no live LLM) ---


def test_shallow_answer_scores_low_on_insight_depth():
    state = _FakeState(evidence=[{"claim": "消费提升50%", "result_summary": "+50%"}])
    shallow = "买卡后消费提升了50%。代金券使用1075次。订单71单。"
    payload = '{"insight_depth": {"score": 1, "rationale": "纯数值描述"}}'
    out = gar.evaluate_answer(
        shallow, state, "省钱卡表现？", ["insight_depth"], judge_client=_StubClient(payload)
    )
    assert out["soft"]["absolute"]["insight_depth"]["score"] == 1


def test_unsupported_causal_claim_is_fatal():
    state = _FakeState(evidence=[{"claim": "留存", "result_summary": "留存下降"}])
    out = gar.evaluate_answer(
        "省钱卡直接导致了复购提升30%。", state, "q", ["insight_depth"],
        judge_client=_StubClient('{"insight_depth": {"score": 5, "rationale": "x"}}'),
    )
    assert out["fatal"]["claim_delivery_ready"] is False


def test_pairwise_detects_regression():
    state = _FakeState(evidence=[{"claim": "x", "result_summary": "x"}])
    out = gar.evaluate_answer(
        "浅答案", state, "q", ["insight_depth"],
        baseline_answer="深答案",
        judge_client=_StubClient('{"insight_depth": {"verdict": "worse", "rationale": "新答案更浅"}}'),
    )
    assert out["soft"]["pairwise"]["insight_depth"]["verdict"] == "worse"


# --- Task 8: live smoke (OPT-IN, deviations from brief per controller) ---
# Brief gated on DATA_DIR + config.api_key, but this repo's .env ships a real
# API_KEY, so that gate would fire a live multi-minute full-agent turn inside
# the default pytest run. Gate on an explicit env var instead so the smoke
# only runs when a developer opts in.


@pytest.mark.skipif(
    os.environ.get("GOLDEN_LIVE_SMOKE") != "1",
    reason="live agent smoke; set GOLDEN_LIVE_SMOKE=1 to run",
)
def test_live_smoke_single_scenario():
    """Live LLM smoke: drives the real agent on one scenario. Opt-in only."""
    manifest = load_golden_manifest(MANIFEST)
    scenario = manifest["scenarios"][2]  # game_b_retention_depth (single file, cheapest)
    answer_text, state, _model_id = gar.drive_agent_for_scenario(scenario, DATA_DIR)
    assert answer_text
    out = gar.evaluate_answer(
        answer_text, state, scenario["business_question"], scenario["soft_dimension_focus"]
    )
    assert "fatal" in out and "soft" in out
    assert isinstance(out["soft"]["absolute"], dict)
