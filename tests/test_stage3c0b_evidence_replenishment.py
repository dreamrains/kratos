from data_agent.agent.synthesis_policy import (
    build_synthesis_instruction,
    derive_synthesis_policy,
)


def test_synthesis_instruction_allows_bounded_evidence_replenishment_without_raw_reads():
    policy = derive_synthesis_policy(
        user_input="Synthesize findings from the available evidence.",
        evidence_records=[{
            "claim": "Revenue per user increased.",
            "confidence": "medium",
            "result_summary": "Revenue per user increased by 8%.",
        }],
    )

    instruction = build_synthesis_instruction(policy)

    assert "bounded_evidence_replenishment" in instruction
    assert "record_analysis_plan" in instruction
    assert "independent" in instruction
    assert "do not read raw datasets during synthesis" in instruction.lower()


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
