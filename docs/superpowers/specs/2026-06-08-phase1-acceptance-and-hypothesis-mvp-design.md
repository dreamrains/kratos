# Phase 1 Acceptance And Hypothesis MVP Design

## Purpose

This document closes the current verification-skeleton phase and defines the entry point for the next phase.

The project should not move directly from data loading to richer domain playbooks. The next differentiating capability is to make analysis reasoning explicit: what the system believes, what evidence is needed, what the loaded data can verify, and which conclusions remain uncertain.

The near-term path is:

1. Finish Phase 1 acceptance for the trustworthy analysis skeleton.
2. Add a deterministic analysis entry decision layer.
3. Build a small Phase 2 hypothesis system MVP.
4. Defer domain playbooks until the skeleton and hypothesis loop are stable.

## Product Positioning

The project should differentiate from general coding agents by helping non-technical or semi-technical users avoid unsupported analysis paths.

General coding agents can generate Python code on demand. This project should win by maintaining a durable, inspectable analysis state across turns:

- data contract
- cleaning decisions
- preview digest
- supported and unsupported routes
- evidence records
- verification status
- hypothesis state

The user should be able to see not only the final answer, but also why the system believes the answer is safe, partial, or unsupported.

## Phase 1 Acceptance

Phase 1 is the verification skeleton. It is considered complete only when the system can reliably create, persist, display, and reuse the trust artifacts generated around data loading and analysis execution.

### Acceptance Criteria

After `load_data` succeeds:

- A dataset understanding contract exists for each loaded dataset.
- A preview digest exists or the missing preview is explicitly represented.
- Cleaning decisions are stored as structured state or artifact refs.
- Analysis route proposals are generated from data capability, grain, and field roles.
- Unsupported analyses are represented with reasons.
- Compact refs survive context compression and can be hydrated from persisted artifacts.
- Trust Inspector can display rows, columns, quality, key fields, preview notes, route limitations, unsupported-analysis risks, and cleaning risks.
- `GET /api/sessions/<session_id>/trust` is read-only and does not call LLMs, run tools, or mutate `analysis_state.json`.

After a normal analysis turn:

- Evidence records are stored for important claims when tools produce evidence.
- Verification can summarize whether evidence-backed claims pass, fail, or require downgrade.
- Final synthesis can see the latest verification summary.

### Real-Data Acceptance Probe

The reference directory `reference/test_doc` should remain the main Phase 1 probe set.

Minimum probe expectations:

- Aggregate retention data should expose daily grain, date and metric fields, trend and period comparison routes, and unsupported user-level retention.
- Order or transaction data should expose user or order identifiers, date fields, dimensions, metrics when present, and route limitations.
- Cleaning risks such as low-cardinality numeric fields should be visible as confirmation risks rather than silently treated as metrics.

The purpose is not to prove every analysis is correct. The purpose is to prove that the system exposes the boundaries before analysis starts.

### Phase 1 Non-Goals

Phase 1 should not add:

- a full guided wizard
- new statistical algorithms
- a broad domain template library
- hypothesis generation
- automatic execution from route cards
- claim extraction from free-form final prose

## Analysis Entry Decision Layer

Before adding hypothesis generation, the system needs one small deterministic decision layer that combines user intent and trust state.

### Inputs

- User request text.
- Current `TurnIntent`.
- Hydrated dataset contracts.
- Route proposals.
- Cleaning risks.
- Unsupported analyses.
- Latest verification summary, when available.

### Output Shape

The decision layer should return a compact decision record:

```json
{
  "decision": "direct_analysis",
  "reason": "The user asks for a trend and the loaded data has a date field plus numeric metrics.",
  "dataset": "main",
  "route": "trend",
  "confidence": "medium",
  "required_user_action": "",
  "limitations": ["Descriptive trend only unless supported by experimental evidence"],
  "evidence_requirements": [
    "time column",
    "metric column",
    "period coverage"
  ]
}
```

Allowed `decision` values:

- `direct_analysis`: the request matches a supported route and data quality does not block execution.
- `clarify_intent`: the request is too vague or multiple routes are plausible.
- `request_data`: the requested analysis requires fields or grain that are missing.
- `exploratory_only`: the system can explore patterns but should not produce strong causal or decision claims.
- `blocked`: data quality or cleaning issues must be resolved first.

### Rules

- Unsupported analyses should beat vague optimism. If the user requests retention but only aggregate data is loaded, return `request_data` or `exploratory_only`.
- Cleaning decisions marked `blocked` should return `blocked`.
- Cleaning decisions marked `needs_confirmation` should return `clarify_intent` unless the route does not depend on the affected field.
- If several supported routes fit, return `clarify_intent` with route options.
- The decision layer should be deterministic and testable. It should not call the LLM.

## Phase 2 Hypothesis System MVP

The hypothesis system should make competing explanations explicit before deep analysis.

### Goal

Given a user request and current trust state, generate a small set of candidate hypotheses that can guide evidence collection and final synthesis.

The MVP should answer:

- What could explain the observed or requested metric movement?
- What evidence would support or weaken each explanation?
- Can the currently loaded data verify it?
- What did the analysis eventually support, reject, or leave unresolved?

### Hypothesis Record

Suggested compact shape:

```json
{
  "id": "hyp_main_001",
  "dataset": "main",
  "route": "period_compare",
  "claim": "Revenue declined because conversion rate fell after the campaign period.",
  "status": "proposed",
  "verification_level": "partially_verifiable",
  "evidence_requirements": [
    {"kind": "metric", "field": "revenue", "required": true},
    {"kind": "rate_metric", "field": "conversion_rate", "required": true},
    {"kind": "time_comparison", "field": "date", "required": true},
    {"kind": "segment", "field": "campaign", "required": false}
  ],
  "supporting_evidence_ids": [],
  "conflicting_evidence_ids": [],
  "limitations": ["Campaign field is missing, so campaign attribution cannot be confirmed."]
}
```

Allowed `status` values:

- `proposed`: generated but not evaluated.
- `supported`: available evidence supports the hypothesis.
- `weakened`: available evidence conflicts with the hypothesis.
- `inconclusive`: evidence is insufficient or mixed.
- `unsupported_by_data`: required data is missing.

Allowed `verification_level` values:

- `verifiable`: required fields and grain are present.
- `partially_verifiable`: core analysis is possible but attribution or segmentation is limited.
- `not_verifiable`: required fields or grain are missing.

### MVP Generation Policy

The first version should not generate a large tree.

For one analysis request:

- Generate 2 to 4 hypotheses.
- Include at least one alternative explanation when possible.
- Include one null or baseline hypothesis when useful, such as seasonality, sampling, data quality, or random fluctuation.
- Bind each hypothesis to route and evidence requirements.
- Mark unverifiable hypotheses clearly instead of dropping them silently.

### MVP Evaluation Policy

After analysis tools run:

- Map evidence records to hypothesis requirements.
- Update hypothesis status using deterministic rules where possible.
- Do not claim a hypothesis is supported without evidence IDs.
- If evidence only supports a descriptive pattern, keep attribution hypotheses `inconclusive`.
- Final synthesis should mention the strongest supported hypothesis and important unresolved alternatives.

## State And Artifact Model

Hypothesis state should follow the existing compact-ref pattern.

In `AnalysisSessionState`, store compact refs:

```json
{
  "hypothesis_sets": [
    {
      "id": "hyps_main_period_compare_001",
      "dataset": "main",
      "route": "period_compare",
      "count": 3,
      "status_summary": {
        "proposed": 3,
        "supported": 0,
        "weakened": 0,
        "inconclusive": 0,
        "unsupported_by_data": 0
      },
      "artifact_path": "sessions/example/tool_outputs/hypotheses_main_period_compare.json"
    }
  ]
}
```

Persist full hypothesis details as JSON artifacts. View builders and synthesis helpers can hydrate the refs when needed.

## Trust Inspector Follow-Up

Trust Inspector should not become a full hypothesis workspace in the first Phase 2 task.

The minimal UI follow-up is:

- Show whether a hypothesis set exists for the current route.
- Show counts by status.
- Optionally show the top 2 hypothesis claims and their status.

No drag-and-drop hypothesis tree, no manual hypothesis editor, and no auto-run button are needed for the MVP.

## Testing Strategy

### Phase 1 Acceptance Tests

Add or maintain tests that prove:

- thin artifact refs hydrate into full Trust Inspector details
- trust API remains read-only
- malformed artifact refs do not crash the view
- real-data probe sessions expose route limitations and risks

### Decision Layer Tests

Add unit tests for:

- supported trend request returns `direct_analysis`
- vague request with multiple routes returns `clarify_intent`
- unsupported retention request returns `request_data`
- cleaning `needs_confirmation` on a required field returns `clarify_intent`
- blocked data quality returns `blocked`

### Hypothesis MVP Tests

Add unit tests for:

- generating 2 to 4 hypotheses from a supported route
- including evidence requirements for each hypothesis
- marking missing-grain hypotheses as `not_verifiable`
- updating status from evidence records
- preserving compact refs and hydrating full artifact details

Add integration tests for:

- a loaded dataset plus vague analysis request can produce an entry decision
- a directed analysis route can produce a hypothesis set
- final synthesis can see hypothesis status without loading raw tool output into hot context

## Success Criteria

This phase is successful when:

- Phase 1 has a documented acceptance checklist and real-data probe expectations.
- The system can deterministically decide whether a request should run, clarify, request data, remain exploratory, or block.
- A supported analysis request can create a compact hypothesis set.
- Each hypothesis has explicit evidence requirements and a verifiability label.
- Evidence records can update hypothesis status.
- Final answers can distinguish supported explanations from unresolved alternatives.
- Context budget is protected by storing compact refs in state and full details in artifacts.

## Risks And Mitigations

### Risk: Hypotheses become LLM prose without operational value

Mitigation:

- require evidence requirements for every hypothesis
- require route and dataset binding
- reject hypotheses without verifiability labels

### Risk: The system overstates causality

Mitigation:

- descriptive routes cannot mark causal hypotheses as supported
- final synthesis must keep attribution hypotheses inconclusive unless causal evidence exists

### Risk: Context budget grows again

Mitigation:

- store compact hypothesis refs in state
- persist full details as cold artifacts
- hydrate only in view builders or synthesis helpers that need details

### Risk: UI work distracts from reasoning quality

Mitigation:

- keep Phase 2 UI to summary counts and top claims
- defer hypothesis editing and rich visualization

## Implementation Order

Recommended order:

1. Lock Phase 1 acceptance tests around hydrated trust artifacts and real-data probe expectations.
2. Add the deterministic analysis entry decision layer.
3. Add hypothesis data models and artifact persistence.
4. Add hypothesis generation from entry decisions and route proposals.
5. Add evidence-to-hypothesis status updates.
6. Add compact hypothesis visibility to Trust Inspector.
7. Add synthesis integration so final answers reference supported and unresolved hypotheses.

Domain playbooks should start only after this order is complete enough to demonstrate one end-to-end hypothesis loop.
