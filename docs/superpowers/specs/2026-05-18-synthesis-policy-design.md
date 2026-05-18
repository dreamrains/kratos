# Synthesis Policy Design

## Decision

Data Agent should add a lightweight synthesis policy layer between analysis execution and the final user-facing answer. The policy should decide how the answer should be framed from the evidence already produced: direct answer, analytical summary, advisory interpretation, or exploratory guidance.

This is not a dedicated So What feature. So What is one possible output move when the user intent, evidence strength, data grain, and business context make business translation useful. The goal is to make final answers consistently useful without forcing every analysis into a heavy consulting report.

## Current Problems

The analysis flow has become more structured over time, but final answer synthesis is still mostly prompt-driven. The system can classify intent, choose playbooks, create tasks, execute tools, and record evidence, yet the final response is assembled by the model with broad prompt instructions.

This creates two failure modes:

1. Free-form synthesis can produce rich business interpretation, but numeric and methodological claims may drift.
2. Workflow-driven synthesis can be more rigorous, but the response can become mechanical and under-explain the business meaning.

The project already has the pieces needed for better final answers: intent, playbooks, analysis state, evidence records, task progress, data profiles, quality guards, and report generation. The missing piece is a small coordinator that tells the final answer which moves are appropriate for this turn.

## Goals

1. Make final answers adapt automatically to user intent, evidence strength, and business context.
2. Preserve rigor: business implications must be bounded by evidence and limitations.
3. Avoid a template explosion where every playbook grows its own report format.
4. Avoid turning every simple request into a consulting-style answer.
5. Give So What content when it is useful, not because a fixed section is mandatory.
6. Reuse existing analysis artifacts instead of adding a parallel workflow.

## Non-Goals

1. Do not replace the intent planner, playbook selector, task system, or evidence model in this phase.
2. Do not require every analysis turn to create a formal report.
3. Do not force So What into pure data operations, simple lookups, or user-requested terse answers.
4. Do not let the synthesis layer execute analysis tools. It only decides output framing from existing state.
5. Do not solve all report-generation quality issues. Formal report synthesis can later reuse the same policy.

## Target Architecture

### 1. Synthesis Policy

Introduce a structured policy object generated near the end of an analysis turn:

```json
{
  "answer_mode": "direct | analytical | advisory | exploratory",
  "insight_depth": "none | light | standard | deep",
  "business_translation": "not_applicable | cautious | allowed",
  "risk_boundary": "descriptive | predictive | causal_sensitive | decision_sensitive",
  "required_moves": [
    "core_answer",
    "evidence",
    "method_note",
    "limitation",
    "business_meaning",
    "next_step"
  ],
  "suppressed_moves": [],
  "reason": "short explanation for debugging and tests"
}
```

The policy should be deterministic or mostly deterministic at first. It can be built from existing structured state rather than another LLM call.

### 2. Inputs

The policy should read:

- `TurnIntent`: user intent type, execution readiness, clarity, and ambiguities.
- `AnalysisSpec`: playbook id, question type, method plan, output sections, limitations, confirmation policy.
- `AnalysisSessionState`: evidence records, insight records, pending confirmations, stage, and data state.
- Data profile signals: grain, dimensions, metrics, time range, quality warnings.
- Tool execution signals: whether the turn produced substantive analysis, only profiling, repeated errors, or fallback Python evidence.
- User requirements: explicit requests for detail, brevity, business advice, rigor, or format.

### 3. Answer Modes

`direct` is for simple answers, formulas, one-off metrics, or operations. It should include the answer and only the minimum supporting note.

`analytical` is for standard data analysis. It should include conclusion, evidence, method note, confidence or limitation, and a concise next step.

`advisory` is for business-facing questions where the result should inform action, such as retention interpretation, LTV, ROI, funnel optimization, product effect, or whether something is worth continuing.

`exploratory` is for ambiguous, insufficient, or early-stage analysis where the best answer is a careful framing of what can be checked next.

### 4. Insight Depth

`none`: no business interpretation. Use for file operations, data preview, pure schema questions, or when the user explicitly asks for terse output.

`light`: one or two sentences translating the result into meaning. Use for narrow analytical requests, such as fitting a formula or calculating a metric.

`standard`: include several practical implications and a next-step recommendation. Use when evidence is strong enough and the request is analysis-oriented.

`deep`: include business hypotheses, action paths, risk boundaries, and follow-up analysis. Use only when the user requests strategy, decision support, forecast, LTV, ROI, effect evaluation, or comprehensive analysis.

### 5. Business Translation Rules

Business translation should be `allowed` when:

- The user asks for diagnosis, forecast, decision support, optimization, ROI, LTV, lifecycle, funnel, effect, or growth opportunity.
- Evidence contains a clear quantitative result and limitations are recorded.
- The data grain supports the level of claim.

Business translation should be `cautious` when:

- The data is aggregated and lacks user/channel/segment detail.
- The result is descriptive but naturally invites action.
- The analysis had tool errors but still has enough verified evidence.
- The question involves prediction or decision support without all required assumptions.

Business translation should be `not_applicable` when:

- The request is a pure operation or schema/data overview.
- Evidence is insufficient.
- The user asks only for a narrow technical answer.

### 6. Risk Boundaries

The policy should separate descriptive, predictive, causal, and decision-sensitive output:

- `descriptive`: describe what the data shows and optionally give lightweight implications.
- `predictive`: include assumptions, uncertainty, and validation needs.
- `causal_sensitive`: avoid causal wording unless design supports it.
- `decision_sensitive`: frame recommendations as decision inputs, not guarantees.

This keeps richer business interpretation from weakening statistical discipline.

## Placement In The Existing Flow

The policy should be generated after tool execution and before final answer generation. It should not alter upstream analysis decisions.

Recommended insertion point:

```text
AgentLoop receives final no-tool response candidate
→ if analysis turn, compute SynthesisPolicy from current context
→ inject compact synthesis instruction into messages or system prompt
→ ask model to produce final answer using that policy
```

For streaming, the same policy can be injected when the loop determines it is ready to summarize. For non-streaming, it can be applied before returning the final `FinalResponse`.

The first implementation can be a pure helper module, for example `agent/synthesis_policy.py`, with no external persistence requirement. Later, the policy can be stored in `analysis_state` for debugging and regression tests.

## Relationship To Existing Components

### Intent

Intent should continue answering what the user wants. Synthesis policy should answer how the final answer should be framed. This prevents intent from becoming overloaded with output-format decisions.

### Playbooks

Playbooks should keep method defaults and analysis expectations. They can provide hints such as default answer mode, default insight depth, and risk level, but they should not own the final response template.

### Tasks

Tasks should remain durable workflow items. The synthesis layer may inspect task progress, but task completion should not automatically imply final answer readiness.

### Evidence

Evidence should remain the source of truth for claims, confidence, method, and limitations. The synthesis layer should not invent unsupported findings. If business meaning is generated, it must be traceable to evidence or marked as a hypothesis.

### Reports

Formal reports can later reuse the synthesis policy, but normal chat answers should not require report generation. The policy should improve the default chat answer first.

## Example: Retention Formula Fitting

User asks: "根据数据拟合留存率公式."

Expected policy:

```json
{
  "answer_mode": "analytical",
  "insight_depth": "light",
  "business_translation": "cautious",
  "risk_boundary": "descriptive",
  "required_moves": ["core_answer", "evidence", "method_note", "limitation", "business_meaning", "next_step"]
}
```

The answer should give the formula, model comparison, fit quality, and a brief explanation such as "this curve can be used as an input to LTV or retention monitoring, but channel/user-level differences are not visible in this aggregate data."

It should not automatically produce a long strategy section unless the user asks for LTV, optimization, or decision support.

## Example: LTV Prediction

User asks: "用这个公式做 LTV 预测."

Expected policy:

```json
{
  "answer_mode": "advisory",
  "insight_depth": "standard",
  "business_translation": "cautious",
  "risk_boundary": "predictive",
  "required_moves": ["core_answer", "assumptions", "evidence", "limitation", "business_meaning", "next_step"]
}
```

The answer should explain that retention is available but ARPU or revenue assumptions are required. It can provide the LTV formula and a sensitivity framework, but should not present actual LTV as factual without revenue data.

## Implementation Phases

### Phase 1: Policy Helper And Tests

1. Add a small `SynthesisPolicy` model.
2. Add deterministic policy derivation from intent, analysis spec, state, and data profile.
3. Add unit tests for direct, analytical, advisory, exploratory, and insufficient-evidence cases.
4. Add regression fixtures for the two retention sessions:
   - formula fitting should produce light business meaning
   - LTV follow-up should produce standard cautious advisory output

### Phase 2: Final Answer Integration

1. Inject the policy into final answer generation for analysis turns.
2. Keep casual conversation, quick operations, and explicit report generation unchanged.
3. Add guardrails so the final answer cannot omit required moves when evidence exists.
4. Add a fallback response when evidence is insufficient: explain what is known and what must be analyzed next.

### Phase 3: Playbook Hints

1. Add optional playbook-level synthesis hints.
2. Keep hints small: default answer mode, default insight depth, and risk boundary.
3. Avoid per-playbook templates unless a domain truly needs them.

### Phase 4: Report Reuse

1. Let formal report generation reuse the same policy.
2. Improve `EvidenceRecord` to `InsightRecord` conversion so business meaning and recommendation are evidence-bound.
3. Keep report generation explicit and separate from normal chat answers.

## Acceptance Criteria

- A narrow formula-fitting request gets the formula, evidence, method, limitation, and light business meaning.
- A decision-oriented request gets business implications and next steps, but includes assumptions and risk boundaries.
- A pure data operation does not receive unnecessary So What content.
- Aggregated data does not produce unsupported user-level or causal recommendations.
- Tool failures or incomplete evidence downgrade insight depth instead of producing confident advice.
- Playbook output sections do not become the only mechanism for final answer quality.
- Tests can verify the selected policy without depending on exact LLM wording.

## Resolved Design Decisions

1. Do not persist the policy in `analysis_state` during Phase 1. Keep it testable through unit tests and visible through debug output. Add a future-compatible path for `last_synthesis_policy` only after the policy proves stable.
2. User proficiency should mainly affect wording complexity, not insight depth. The task, evidence, and risk boundary should decide depth; proficiency can change how technical or explanatory the final answer sounds.
3. Inject the policy before the model writes the final answer. Do not add a regenerate-on-violation loop in Phase 1 because it adds latency, streaming complexity, and another failure path.
4. Keep policy details hidden from the normal user UI. Show them only in developer/debug surfaces at first; a future analysis-detail panel can expose the policy in a collapsed diagnostic view if it becomes useful.
