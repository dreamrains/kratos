from types import SimpleNamespace
from data_agent.agent.loop import AgentLoop
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.llm.client import Response, ToolCall


def _audit_blocked_no_evidence():
    return {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_block",
        "status": "blocked",
        "public_text": "",
        "claims": [{"id": "claim_1", "text": "本月收入增长了 5%。", "claim_type": "numeric", "material": True}],
        "claim_checks": [{"claim_id": "claim_1", "status": "failed", "reason_codes": ["missing_evidence_identity"]}],
    }


def test_publication_is_non_destructive_even_when_config_says_strict(monkeypatch):
    """The loop must publish transparently regardless of assurance_publication_mode."""
    loop = AgentLoop(client=object(), session_id="m1_pub")
    loop._publication_mode = lambda: "strict"  # simulate a strict config
    loop._last_turn_intent = SimpleNamespace(intent_type="directed_analysis", execution_readiness="ready")
    state = SimpleNamespace(evidence_records=[{"id": "ev_1"}], verification_reports=[], turn_diagnostics=[])
    state.append_turn_diagnostic = state.turn_diagnostics.append
    loop.context.analysis_state = state
    monkeypatch.setattr(runtime, "audit_final_answer_draft", lambda *_a, **_k: {
        "contract_version": "final_answer_audit.v1", "id": "ref", "status": "blocked",
        "artifact_path": "f.json", "artifact_digest": "0" * 64})
    monkeypatch.setattr(runtime, "hydrate_final_answer_audit_ref", lambda _r: _audit_blocked_no_evidence())
    monkeypatch.setattr(loop, "_evaluate_turn_completion", lambda: SimpleNamespace(status="complete", is_terminal=True))

    text = loop._render_audited_publication(
        "本月收入增长了 5%。这是完整分析。", _audit_blocked_no_evidence())

    assert "本月收入增长了 5%" in text            # claim relayed, NOT deleted
    assert "这是完整分析" in text
    assert "无法发布" not in text                 # no placeholder, even though config=strict
    assert "当前可追踪证据不足" not in text
    # bookkeeping-only failure produces no alarming footer (Phase 0 refinement)
    assert "局限说明" not in text
