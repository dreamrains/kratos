# Intent Planning And Report Artifact Design

## Decision

Data Agent should not replace keyword intent rules with an LLM-only classifier. It should keep a small deterministic gate for high-confidence, low-value turns, then use an LLM semantic planner for analysis-like requests. Tool routing should move from keyword-heavy intent groups toward capability routing driven by the semantic plan, analysis state, and data features.

Brief reports should be removed from the default product path or hidden as a legacy/export-only artifact. Formal reports should be retained, but repositioned as explicit deliverables generated only when the user asks for a shareable or auditable artifact.

## Current Problems

The current intent system already has a rule path plus LLM fallback, but rules still decide too much. A keyword match can mark a complex request as clear before the LLM has a chance to evaluate business meaning, ambiguity, data readiness, or method risk. Intent is also used for too many downstream decisions: prompt level, tool groups, budget profile, playbook selection, workflow tasks, and quality guards.

The current report system has stronger foundations than it first appears. `generate_analysis_brief` and `generate_formal_report` both consume EvidenceRecord, and formal reports create evidence-gap tasks when evidence is missing. The weakness is product positioning and depth: brief overlaps with normal dialogue, while formal reports are mostly template synthesis and can feel shallow when upstream evidence or insight records are thin.

## Target Architecture

### 1. Deterministic Gate

Keep a narrow fast path for cases where an LLM adds little value:

- greetings, thanks, and confirmations
- explicit simple operations such as export, filter, sort, or rename
- explicit file/data references used to infer load readiness
- explicit report requests such as "generate report" or "formal report"
- pure knowledge questions with clear definition/explanation phrasing

The deterministic gate should avoid broad analysis keywords. Terms like "look at this", "is this working", "how are sales", "worth continuing", or domain-specific business wording should go to semantic planning.

### 2. LLM Semantic Planner

For analysis-like or ambiguous turns, call the LLM once to produce a structured plan. This should replace the current narrow `intent_type + ambiguities` result with a richer object:

```json
{
  "intent_type": "directed_analysis | intent_negotiation | data_operation | comprehensive_report | knowledge_qa | result_followup",
  "goal": "business or analytical goal",
  "answer_mode": "conversation | operation | analysis | deliverable",
  "metrics": [],
  "dimensions": [],
  "time_scope": "",
  "data_need": {
    "readiness": "ready | pending_load | missing_data | insufficient_data",
    "referenced_files": [],
    "missing_fields": []
  },
  "ambiguities": [],
  "risk_level": "low | medium | high",
  "suggested_capabilities": [],
  "report_intent": {
    "requested": false,
    "artifact_type": "none | formal_report | conversation_export"
  }
}
```

This plan becomes the single source of truth for the turn. `AgentLoop._prepare_analysis_turn`, prompt construction, budget selection, playbook selection, and quality guards should reuse the same plan instead of recalculating intent independently.

### 3. Capability Router

Tool activation should become capability-first:

- core read/list/load tools are always available
- low-risk analysis capabilities are activated from `suggested_capabilities`, data features, and AnalysisSpec
- high-risk capabilities such as causal analysis, forecasting, experiments, and predictive modeling still require confirmation gates
- keyword tool-group activation remains only as a fallback for old flows and explicit simple operations

This keeps the safety benefits of tool gating without forcing intent classification to predict every tool group perfectly.

### 4. Post-Load Replanning

When a turn loads data and the original user request contains an analysis or report goal, the system should re-run semantic planning after the data profile is available. The second plan should incorporate schema, field semantics, data quality, and feasible methods before analysis execution begins.

## Report And Brief Design

### Brief

Brief should no longer be presented as a first-class report action. It is mostly a lightweight formatting of EvidenceRecord and overlaps with normal chat output.

Recommended treatment:

- remove or hide brief buttons from the default web workbench
- keep the tool temporarily for backward compatibility and tests
- optionally map brief-style needs to conversation export or "summarize current findings" inside chat
- do not auto-generate brief after data preview or routine analysis

### Formal Report

Formal report should stay because it serves a different user need: shareable, auditable, cross-session deliverables.

New rules:

- generate only when the user explicitly asks for a report, document, export, handoff, review artifact, or similar deliverable
- require EvidenceRecord coverage before generation
- return an evidence-gap checklist instead of producing a weak report when evidence is insufficient
- include evidence IDs, methods, limitations, confidence, and validated charts
- add an evidence-bound LLM synthesis layer so the report reads like an expert analysis rather than a template dump
- never allow report synthesis to invent unsupported conclusions

## User Experience

The default analysis result should be conversational: direct conclusions, key numbers, method notes, limitations, and suggested next steps in the chat. Reports are explicit artifacts, not default answers.

When the user asks for a formal report, the agent should explain whether the current evidence is sufficient. If not sufficient, it should list missing evidence and propose the next analysis steps needed to produce a credible report.

## Implementation Phases

### Phase 1: Planning Foundation

1. Add a structured semantic plan model.
2. Refactor intent planning so fast rules only cover high-confidence deterministic cases.
3. Ensure each turn computes the plan once and stores it on context.
4. Update prompt building to consume the stored plan instead of recalculating intent.
5. Add tests for semantic plan reuse, post-load readiness, and ambiguous business phrasing.

### Phase 2: Capability Routing

1. Introduce capability routing from semantic plan, AnalysisSpec, and data features.
2. Reduce reliance on registry keyword activation.
3. Keep confirmation gates for high-risk analysis.
4. Add regression tests for tool visibility and blocked high-risk tools.

### Phase 3: Artifact Repositioning

1. Hide or remove brief report actions from the default UI.
2. Keep conversation export available.
3. Gate formal reports behind explicit deliverable intent.
4. Add evidence sufficiency checks before formal report generation.
5. Add evidence-bound LLM synthesis for formal reports.

## Acceptance Criteria

- A vague business request such as "How are these products selling?" is treated as analysis-like semantic planning, not simple keyword fallback.
- Clear simple requests still complete without an extra LLM classification call.
- A single user turn does not recompute inconsistent intent decisions across loop preparation and prompt building.
- Tool routing can activate analysis capabilities from plan/data signals without relying on broad analysis keywords.
- Brief is no longer a default user-facing report path.
- Formal report remains available only as an explicit deliverable and refuses shallow generation when evidence is missing.
