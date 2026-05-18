# Synthesis Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight synthesis policy that guides final analysis answers so they adapt to intent, evidence strength, business context, and risk boundaries.

**Architecture:** Create a deterministic `SynthesisPolicy` helper that reads existing turn intent, analysis state, analysis spec, evidence, user requirements, and tool-error signals. Inject a compact policy instruction before the model writes the final analysis answer, without persisting the policy in `analysis_state` or changing upstream playbook/task/evidence flow.

**Tech Stack:** Python, pytest, existing `AgentLoop`, dataclasses, current prompt/message loop.

---

## File Map

- Add: `src/data_agent/agent/synthesis_policy.py`
  - Owns the `SynthesisPolicy` dataclass, enum-like constants, deterministic derivation rules, and compact final-answer instruction formatting.

- Add: `tests/test_synthesis_policy.py`
  - Unit tests for direct, analytical, advisory, exploratory, insufficient-evidence, tool-error downgrade, user-proficiency wording, and user-requirement handling.

- Modify: `src/data_agent/agent/loop.py`
  - Add one final-answer policy injection path for analysis turns.
  - Track whether the current turn has already received a synthesis policy instruction.
  - Keep streaming and non-streaming behavior aligned.

- Modify: `tests/test_execution_control.py`
  - Add a focused loop test proving the synthesis instruction is injected before the final model answer after evidence exists.

- Modify: `docs/superpowers/specs/2026-05-18-synthesis-policy-design.md`
  - Keep the resolved design decisions as the source of truth.

---

## Task 1: Add Failing Unit Tests For Policy Derivation

**Files:**
- Add: `tests/test_synthesis_policy.py`

- [ ] **Step 1: Create policy test file with direct and analytical cases**

Create `tests/test_synthesis_policy.py`:

```python
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.synthesis_policy import derive_synthesis_policy


def _intent(intent_type="directed_analysis", clarity="clear", action="run_analysis"):
    return TurnIntent(
        intent_type=intent_type,
        clarity=clarity,
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action=action,
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )


def _state_with_evidence(confidence="high"):
    state = AnalysisSessionState(session_id="synthesis_test")
    state.analysis_spec = {
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "confirmation_policy": {"requires_confirmation": False},
        "limitations": ["aggregate retention data"],
    }
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention follows a power-law curve",
        "result_summary": "R(t)=0.1917*t^(-0.7335), R2=0.9743",
        "confidence": confidence,
        "limitations": "Aggregated data only",
        "method": "log-linear least squares",
    }]
    return state


def test_direct_operation_has_no_business_translation():
    policy = derive_synthesis_policy(
        intent=_intent(intent_type="data_operation", action="execute_operation"),
        state=AnalysisSessionState(session_id="direct"),
        user_input="导出这个表",
    )

    assert policy.answer_mode == "direct"
    assert policy.insight_depth == "none"
    assert policy.business_translation == "not_applicable"
    assert "business_meaning" not in policy.required_moves


def test_formula_fitting_gets_light_cautious_business_meaning():
    policy = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="根据数据拟合留存率公式",
        data_profile="grain=daily_aggregate; no dimensions; retention metrics",
    )

    assert policy.answer_mode == "analytical"
    assert policy.insight_depth == "light"
    assert policy.business_translation == "cautious"
    assert policy.risk_boundary == "descriptive"
    assert policy.required_moves == [
        "core_answer",
        "evidence",
        "method_note",
        "limitation",
        "business_meaning",
        "next_step",
    ]
```

- [ ] **Step 2: Add advisory, exploratory, and downgrade tests**

Append:

```python
def test_ltv_followup_gets_standard_cautious_advisory_policy():
    policy = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="用这个公式做 LTV 预测",
        data_profile="grain=daily_aggregate; retention metrics; no revenue metric",
    )

    assert policy.answer_mode == "advisory"
    assert policy.insight_depth == "standard"
    assert policy.business_translation == "cautious"
    assert policy.risk_boundary == "predictive"
    assert "assumptions" in policy.required_moves


def test_no_evidence_is_exploratory_and_does_not_advise():
    state = AnalysisSessionState(session_id="no_evidence")
    state.analysis_spec = {"playbook_id": "retention_lifecycle", "question_type": "diagnostic"}

    policy = derive_synthesis_policy(
        intent=_intent(),
        state=state,
        user_input="分析一下留存",
    )

    assert policy.answer_mode == "exploratory"
    assert policy.insight_depth == "none"
    assert policy.business_translation == "not_applicable"
    assert policy.required_moves == ["core_answer", "limitation", "next_step"]


def test_tool_errors_downgrade_deep_business_translation():
    policy = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="预测 LTV 并给我决策建议",
        tool_error_count=3,
    )

    assert policy.answer_mode == "advisory"
    assert policy.insight_depth == "standard"
    assert policy.business_translation == "cautious"
    assert "tool errors" in policy.reason.lower()


def test_beginner_proficiency_changes_wording_only_not_depth():
    beginner = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="根据数据拟合留存率公式",
        proficiency="beginner",
    )
    advanced = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="根据数据拟合留存率公式",
        proficiency="advanced",
    )

    assert beginner.insight_depth == advanced.insight_depth == "light"
    assert beginner.wording_style == "plain_language"
    assert advanced.wording_style == "technical_concise"


def test_explicit_terse_requirement_suppresses_business_meaning():
    policy = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="只给我公式，不要解释",
        user_requirements="只给公式，不要解释",
    )

    assert policy.answer_mode == "direct"
    assert policy.insight_depth == "none"
    assert "business_meaning" not in policy.required_moves
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```bash
pytest tests/test_synthesis_policy.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'data_agent.agent.synthesis_policy'`.

---

## Task 2: Implement Deterministic Synthesis Policy

**Files:**
- Add: `src/data_agent/agent/synthesis_policy.py`

- [ ] **Step 1: Create the policy dataclass and constants**

Create `src/data_agent/agent/synthesis_policy.py`:

```python
"""Final-answer synthesis policy.

The policy decides how to frame the user-facing answer from existing
analysis state. It does not execute tools, mutate state, or create evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent

AnswerMode = Literal["direct", "analytical", "advisory", "exploratory"]
InsightDepth = Literal["none", "light", "standard", "deep"]
BusinessTranslation = Literal["not_applicable", "cautious", "allowed"]
RiskBoundary = Literal["descriptive", "predictive", "causal_sensitive", "decision_sensitive"]
WordingStyle = Literal["plain_language", "balanced", "technical_concise"]


@dataclass(frozen=True)
class SynthesisPolicy:
    answer_mode: AnswerMode
    insight_depth: InsightDepth
    business_translation: BusinessTranslation
    risk_boundary: RiskBoundary
    required_moves: list[str] = field(default_factory=list)
    suppressed_moves: list[str] = field(default_factory=list)
    wording_style: WordingStyle = "balanced"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 2: Add rule helpers**

Append:

```python
_TERSE_MARKERS = ("只给", "不要解释", "简短", "直接给", "terse", "brief", "no explanation")
_ADVISORY_MARKERS = (
    "ltv", "roi", "预测", "预估", "决策", "建议", "优化", "是否值得",
    "继续做", "增长", "策略", "funnel", "漏斗", "生命周期",
)
_PREDICTIVE_MARKERS = ("ltv", "预测", "预估", "forecast", "simulate", "模拟")
_CAUSAL_MARKERS = ("因果", "导致", "影响", "效果", "ab", "a/b", "实验")
_OPERATION_INTENTS = {"data_operation", "simple_response", "knowledge_qa"}


def _text(*parts: object) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _evidence_records(state: AnalysisSessionState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    return list(getattr(state, "evidence_records", []) or [])


def _analysis_spec(state: AnalysisSessionState | None) -> dict[str, Any]:
    if state is None:
        return {}
    spec = getattr(state, "analysis_spec", None)
    return spec if isinstance(spec, dict) else {}


def _wording_style(proficiency: str) -> WordingStyle:
    if proficiency == "beginner":
        return "plain_language"
    if proficiency == "advanced":
        return "technical_concise"
    return "balanced"
```

- [ ] **Step 3: Add required move construction**

Append:

```python
def _moves_for(mode: AnswerMode, depth: InsightDepth, risk: RiskBoundary) -> list[str]:
    if mode == "direct":
        return ["core_answer", "method_note"] if depth != "none" else ["core_answer"]
    if mode == "exploratory":
        return ["core_answer", "limitation", "next_step"]

    moves = ["core_answer", "evidence", "method_note", "limitation"]
    if risk in {"predictive", "decision_sensitive"}:
        moves.insert(1, "assumptions")
    if depth in {"light", "standard", "deep"}:
        moves.append("business_meaning")
    moves.append("next_step")
    if risk == "causal_sensitive":
        moves.append("causal_boundary")
    return list(dict.fromkeys(moves))
```

- [ ] **Step 4: Add the derivation function**

Append:

```python
def derive_synthesis_policy(
    *,
    intent: TurnIntent | None,
    state: AnalysisSessionState | None,
    user_input: str = "",
    data_profile: str = "",
    tool_error_count: int = 0,
    user_requirements: str = "",
    proficiency: str = "intermediate",
) -> SynthesisPolicy:
    """Derive final-answer framing from existing state.

    This function is intentionally deterministic for testability.
    """
    intent_type = getattr(intent, "intent_type", "")
    spec = _analysis_spec(state)
    evidence = _evidence_records(state)
    combined = _text(user_input, user_requirements, data_profile, spec.get("playbook_id"), spec.get("question_type"))
    reasons: list[str] = []

    if intent_type in _OPERATION_INTENTS or _has_any(combined, _TERSE_MARKERS):
        reason = "direct operation or terse user requirement"
        return SynthesisPolicy(
            answer_mode="direct",
            insight_depth="none",
            business_translation="not_applicable",
            risk_boundary="descriptive",
            required_moves=["core_answer"],
            wording_style=_wording_style(proficiency),
            reason=reason,
        )

    if not evidence:
        return SynthesisPolicy(
            answer_mode="exploratory",
            insight_depth="none",
            business_translation="not_applicable",
            risk_boundary="descriptive",
            required_moves=["core_answer", "limitation", "next_step"],
            wording_style=_wording_style(proficiency),
            reason="no evidence records available",
        )

    advisory = _has_any(combined, _ADVISORY_MARKERS)
    predictive = _has_any(combined, _PREDICTIVE_MARKERS)
    causal = _has_any(combined, _CAUSAL_MARKERS)
    aggregate = "aggregate" in combined or "聚合" in combined or "no dimensions" in combined

    mode: AnswerMode = "advisory" if advisory else "analytical"
    risk: RiskBoundary = "predictive" if predictive else "descriptive"
    if causal:
        risk = "causal_sensitive"
    if "decision" in combined or "决策" in combined or "是否值得" in combined:
        risk = "decision_sensitive" if not causal else risk

    if mode == "advisory":
        depth: InsightDepth = "standard"
    else:
        depth = "light"

    business: BusinessTranslation = "allowed"
    if aggregate or risk in {"predictive", "causal_sensitive", "decision_sensitive"}:
        business = "cautious"
        reasons.append("bounded by aggregate data or risk boundary")

    if tool_error_count >= 2:
        if depth == "deep":
            depth = "standard"
        business = "cautious"
        reasons.append("tool errors require cautious synthesis")

    if any(str(rec.get("confidence", "")).lower() in {"low", "speculative"} for rec in evidence):
        depth = "light" if mode == "advisory" else "none"
        business = "cautious"
        reasons.append("low-confidence evidence limits insight depth")

    return SynthesisPolicy(
        answer_mode=mode,
        insight_depth=depth,
        business_translation=business,
        risk_boundary=risk,
        required_moves=_moves_for(mode, depth, risk),
        wording_style=_wording_style(proficiency),
        reason="; ".join(reasons) or "derived from intent, evidence, and risk signals",
    )
```

- [ ] **Step 5: Add compact prompt instruction formatter**

Append:

```python
def build_synthesis_instruction(policy: SynthesisPolicy) -> str:
    moves = ", ".join(policy.required_moves)
    suppressed = ", ".join(policy.suppressed_moves) if policy.suppressed_moves else "none"
    return (
        "<synthesis_policy>\n"
        f"answer_mode: {policy.answer_mode}\n"
        f"insight_depth: {policy.insight_depth}\n"
        f"business_translation: {policy.business_translation}\n"
        f"risk_boundary: {policy.risk_boundary}\n"
        f"wording_style: {policy.wording_style}\n"
        f"required_moves: {moves}\n"
        f"suppressed_moves: {suppressed}\n"
        f"reason: {policy.reason}\n"
        "Use this policy to write the final user-facing answer. "
        "Do not invent unsupported findings. Keep business meaning bounded by evidence and limitations.\n"
        "</synthesis_policy>"
    )
```

- [ ] **Step 6: Run policy tests and verify they pass**

Run:

```bash
pytest tests/test_synthesis_policy.py -q
```

Expected: all tests in `tests/test_synthesis_policy.py` pass.

---

## Task 3: Add Loop Injection Tests

**Files:**
- Modify: `tests/test_execution_control.py`

- [ ] **Step 1: Add a client that records system prompts**

Append near the existing loop test helpers:

```python
class _PolicyPromptClient:
    def __init__(self):
        self.system_prompts = []
        self._calls = [
            Response(tool_calls=[ToolCall("tc_evidence", "record_evidence_record", {
                "record_json": json.dumps({
                    "claim": "Retention follows a power-law curve",
                    "dataset": "retention",
                    "method": "log-linear fit",
                    "tool_calls": ["run_python"],
                    "result_summary": "R(t)=0.1917*t^(-0.7335), R2=0.9743",
                    "limitations": "aggregate data only",
                    "confidence": "high",
                }, ensure_ascii=False)
            })]),
            Response(text="final answer"),
        ]

    def chat(self, messages, tools=None, system=None):
        self.system_prompts.append(system or "")
        if not self._calls:
            return Response(text="final answer")
        return self._calls.pop(0)
```

- [ ] **Step 2: Add non-streaming injection test**

Append:

```python
def test_loop_injects_synthesis_policy_before_final_answer(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig

    old_cfg = config._config
    config._config = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=tmp_path / "sessions",
    )
    client = _PolicyPromptClient()
    loop = AgentLoop(client=client, session_id="synthesis_loop")
    loop.context.analysis_state.analysis_spec = {
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "confirmation_policy": {"requires_confirmation": False},
    }

    try:
        result = loop.run_turn("根据数据拟合留存率公式")

        assert result == "final answer"
        assert any("<synthesis_policy>" in prompt for prompt in client.system_prompts[1:])
        final_prompt = client.system_prompts[-1]
        assert "answer_mode: analytical" in final_prompt
        assert "insight_depth: light" in final_prompt
        assert "business_translation: cautious" in final_prompt
    finally:
        config._config = old_cfg
```

- [ ] **Step 3: Run focused test and verify it fails**

Run:

```bash
pytest tests/test_execution_control.py::test_loop_injects_synthesis_policy_before_final_answer -q
```

Expected: FAIL because `AgentLoop` does not yet inject `<synthesis_policy>`.

---

## Task 4: Integrate Policy Injection Into AgentLoop

**Files:**
- Modify: `src/data_agent/agent/loop.py`

- [ ] **Step 1: Reset synthesis injection tracking per turn**

In `_reset_turn_tracking()`, add:

```python
        self._turn_synthesis_policy_injected = False
```

- [ ] **Step 2: Add helpers to count errors and inject the policy**

Add these methods near `_maybe_inject_quality_reminder()`:

```python
    def _turn_tool_error_count(self) -> int:
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return 0
        return len(getattr(turn_state, "tool_errors", []) or [])

    def _maybe_inject_synthesis_policy(self, user_input: str) -> None:
        if getattr(self, "_turn_synthesis_policy_injected", False):
            return
        intent = getattr(self, "_last_turn_intent", None)
        if intent is None or intent.intent_type not in ("directed_analysis", "comprehensive_report"):
            return
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        evidence = getattr(state, "evidence_records", []) or []
        if not evidence:
            return

        from data_agent.agent.synthesis_policy import (
            build_synthesis_instruction,
            derive_synthesis_policy,
        )

        datasets = self.context.workspace.list_datasets() if self.context.workspace else {}
        data_profile = "\n".join(
            f"- {name}: {info.get('rows')} rows x {info.get('columns')} cols"
            for name, info in datasets.items()
        )
        policy = derive_synthesis_policy(
            intent=intent,
            state=state,
            user_input=user_input,
            data_profile=data_profile,
            tool_error_count=self._turn_tool_error_count(),
            user_requirements=self.context.user_quality_requirements,
            proficiency=self.context.user_proficiency,
        )
        self.messages.append({"role": "system", "content": build_synthesis_instruction(policy)})
        self._turn_synthesis_policy_injected = True
        self._prompt_cache_dirty = True
```

- [ ] **Step 3: Call the injection helper after tool execution in non-streaming loop**

In `_loop()` or the equivalent non-streaming tool loop, after tool calls are processed and after `_maybe_replan_after_data_load(user_input)`, add:

```python
            self._maybe_inject_synthesis_policy(user_input)
```

Place it before the next LLM round begins so the model sees the policy before writing the first no-tool final answer.

- [ ] **Step 4: Call the injection helper after tool execution in `stream_turn()`**

In `stream_turn()`, after `_maybe_replan_after_data_load(user_input)` and before the next `while` iteration can call the model, add:

```python
            self._maybe_inject_synthesis_policy(user_input)
```

- [ ] **Step 5: Call the injection helper in `resume_turn_streaming()`**

In `resume_turn_streaming()`, after `_maybe_replan_after_data_load(resumed_input)`, add:

```python
            self._maybe_inject_synthesis_policy(resumed_input)
```

- [ ] **Step 6: Run the loop injection test**

Run:

```bash
pytest tests/test_execution_control.py::test_loop_injects_synthesis_policy_before_final_answer -q
```

Expected: PASS.

---

## Task 5: Add Regression Coverage For Retention Scenarios

**Files:**
- Modify: `tests/test_synthesis_policy.py`

- [ ] **Step 1: Add regression tests for the two motivating session patterns**

Append:

```python
def test_retention_formula_regression_matches_expected_policy_shape():
    state = _state_with_evidence()
    state.analysis_spec.update({
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "output_sections": [],
    })

    policy = derive_synthesis_policy(
        intent=_intent(),
        state=state,
        user_input="这是一个游戏的新用户留存率数据，请根据数据为我拟合留存率的公式",
        data_profile="daily_aggregate retention table, no channel dimension",
    )

    assert policy.answer_mode == "analytical"
    assert policy.insight_depth == "light"
    assert policy.business_translation == "cautious"
    assert policy.risk_boundary == "descriptive"
    assert "business_meaning" in policy.required_moves
    assert "next_step" in policy.required_moves


def test_ltv_regression_requires_assumptions_and_caution():
    policy = derive_synthesis_policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="用这个公式做LTV（用户生命周期价值）预测",
        data_profile="daily_aggregate retention table, no revenue metric",
    )

    assert policy.answer_mode == "advisory"
    assert policy.risk_boundary == "predictive"
    assert policy.business_translation == "cautious"
    assert "assumptions" in policy.required_moves
    assert "business_meaning" in policy.required_moves
    assert "next_step" in policy.required_moves
```

- [ ] **Step 2: Run synthesis policy tests**

Run:

```bash
pytest tests/test_synthesis_policy.py -q
```

Expected: PASS.

---

## Task 6: Full Verification And Commit

**Files:**
- Verify: `src/data_agent/agent/synthesis_policy.py`
- Verify: `src/data_agent/agent/loop.py`
- Verify: `tests/test_synthesis_policy.py`
- Verify: `tests/test_execution_control.py`
- Verify: `docs/superpowers/specs/2026-05-18-synthesis-policy-design.md`
- Verify: `docs/superpowers/plans/2026-05-18-synthesis-policy.md`

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_synthesis_policy.py tests/test_execution_control.py::test_loop_injects_synthesis_policy_before_final_answer -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent analysis-flow tests**

Run:

```bash
pytest tests/test_method_playbooks.py tests/test_analysis_quality.py -q
```

Expected: PASS or known unrelated failures documented in the final implementation note.

- [ ] **Step 3: Check diff scope**

Run:

```bash
git diff -- src/data_agent/agent/synthesis_policy.py src/data_agent/agent/loop.py tests/test_synthesis_policy.py tests/test_execution_control.py docs/superpowers/specs/2026-05-18-synthesis-policy-design.md docs/superpowers/plans/2026-05-18-synthesis-policy.md
```

Expected: diff only covers synthesis policy, final-answer injection, tests, and docs.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add src/data_agent/agent/synthesis_policy.py src/data_agent/agent/loop.py tests/test_synthesis_policy.py tests/test_execution_control.py docs/superpowers/specs/2026-05-18-synthesis-policy-design.md docs/superpowers/plans/2026-05-18-synthesis-policy.md
git commit -m "feat: add synthesis policy for analysis answers"
```

Expected: commit succeeds.

---

## Self-Review Checklist

- Spec coverage: The plan covers Phase 1 policy helper/tests and Phase 2 final-answer integration. Phase 3 playbook hints and Phase 4 report reuse remain future phases by design.
- No persistence: The plan does not write policy into `analysis_state`.
- User proficiency: The plan only changes `wording_style`, not `insight_depth`.
- Final response strategy: The plan injects policy before the final answer and does not add regeneration.
- UI visibility: The plan keeps policy internal; debug visibility is through tests and prompt inspection.
- Complexity boundary: The new module does not execute tools, create tasks, write evidence, or mutate state.
