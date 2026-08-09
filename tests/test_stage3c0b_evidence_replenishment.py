from data_agent.agent.synthesis_policy import (
    build_synthesis_instruction,
    derive_synthesis_policy,
)


def test_synthesis_instruction_injects_bounded_catalog_without_tool_ritual():
    """Task 9: auto-projection replaces the bounded_evidence_replenishment ritual.

    The catalog is always injected (even when empty). The synthesis
    instruction must NOT direct the model to call analysis tools or
    ``record_evidence_record`` during final answer generation; that is
    the deterministic contract the new auto-projection upholds.
    """

    policy = derive_synthesis_policy(
        user_input="Synthesize findings from the available evidence.",
        evidence_records=[{
            "id": "ev_revenue",
            "plan_id": "plan_current",
            "claim": "Revenue per user increased.",
            "confidence": "medium",
            "result_summary": "Revenue per user increased by 8%.",
        }],
        analysis_plan={"id": "plan_current", "method_plan": []},
    )

    instruction = build_synthesis_instruction(policy)

    assert "bounded_evidence_catalog" in instruction
    assert "可用证据测量：" in instruction
    assert "do not read raw datasets during synthesis" in instruction.lower()
    # The old ritual that asked for tool calls during synthesis is gone.
    assert "bounded_evidence_replenishment" not in instruction
    assert "record_analysis_plan" not in instruction
    assert "record_evidence_record" not in instruction


def test_synthesis_instruction_avoids_brittle_coverage_gates_and_magic_scores():
    policy = derive_synthesis_policy(
        user_input="Synthesize findings from the available evidence.",
        evidence_records=[{
            "claim": "Retention is stable.",
            "confidence": "high",
            "result_summary": "Retention varied within normal range.",
        }],
    )

    instruction = build_synthesis_instruction(policy).lower()

    assert "question_id" not in instruction
    assert "magic threshold" not in instruction
    assert "score =" not in instruction
