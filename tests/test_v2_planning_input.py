from __future__ import annotations

import pytest

from data_agent.v2.planning_input import (
    PlanningInputConflict,
    PlanningInputStore,
    planning_question_id,
)


def _questions(plan_id: str) -> tuple[dict[str, str], ...]:
    return (
        {
            "question_id": planning_question_id(plan_id, 1),
            "text": "每行代表订单还是客户？",
        },
        {
            "question_id": planning_question_id(plan_id, 2),
            "text": "希望比较哪个指标？",
        },
    )


def test_planning_input_is_append_only_idempotent_and_refreshable(tmp_path):
    store = PlanningInputStore(tmp_path, "session_input")
    questions = _questions("plan_source")
    answers = (
        {"question_id": questions[0]["question_id"], "answer": "每行是订单"},
        {"question_id": questions[1]["question_id"], "answer": "比较销售额"},
    )

    first = store.record(
        source_plan_id="plan_source",
        client_reply_id="reply_once",
        questions=questions,
        answers=answers,
    )
    repeated = store.record(
        source_plan_id="plan_source",
        client_reply_id="reply_once",
        questions=questions,
        answers=answers,
    )

    assert first == repeated
    assert first.planning_input_id.startswith("planning_input_")
    assert PlanningInputStore(tmp_path, "session_input").get(
        first.planning_input_id
    ) == first
    assert first.clarifications == (
        {"question": "每行代表订单还是客户？", "answer": "每行是订单"},
        {"question": "希望比较哪个指标？", "answer": "比较销售额"},
    )


def test_planning_input_requires_one_nonempty_answer_per_stable_question(tmp_path):
    store = PlanningInputStore(tmp_path, "session_input_exact")
    questions = _questions("plan_source")

    with pytest.raises(ValueError, match="exactly once"):
        store.record(
            source_plan_id="plan_source",
            client_reply_id="reply_missing",
            questions=questions,
            answers=(
                {
                    "question_id": questions[0]["question_id"],
                    "answer": "每行是订单",
                },
            ),
        )
    with pytest.raises(ValueError, match="answer is required"):
        store.record(
            source_plan_id="plan_source",
            client_reply_id="reply_empty",
            questions=questions,
            answers=(
                {"question_id": item["question_id"], "answer": ""}
                for item in questions
            ),
        )


def test_planning_input_reply_identity_cannot_change_content(tmp_path):
    store = PlanningInputStore(tmp_path, "session_input_conflict")
    questions = _questions("plan_source")
    answers = tuple(
        {"question_id": item["question_id"], "answer": f"answer {index}"}
        for index, item in enumerate(questions, start=1)
    )
    store.record(
        source_plan_id="plan_source",
        client_reply_id="reply_conflict",
        questions=questions,
        answers=answers,
    )

    changed = list(answers)
    changed[0] = {**changed[0], "answer": "changed"}
    with pytest.raises(PlanningInputConflict, match="different reply content"):
        store.record(
            source_plan_id="plan_source",
            client_reply_id="reply_conflict",
            questions=questions,
            answers=tuple(changed),
        )
