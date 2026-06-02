# Trustworthy Analysis Workflow Design

## Decision

Data Agent should move from "an AI agent that can analyze data" toward "a trustworthy business analysis workflow system."

The next phase should not prioritize adding more standalone tools. It should instead make data understanding, cleaning decisions, intent refinement, evidence production, and final conclusion verification into a structured workflow that survives context compression and can be audited after the fact.

The central product promise is:

> Every important conclusion should be traceable to data, cleaning decisions, analysis route, evidence, limitations, and verification status.

## Current Assessment

The project already has substantial foundations:

- `load_data` loads files and automatically runs type cleaning, compact profiling, semantic interpretation, quality scanning, active insight scanning, cross-dataset hints, and domain matching.
- `quick_profile`, `interpret_dataset`, and `data_features` already identify columns, quality issues, grain, analysis signals, and recommended analysis directions.
- `TurnIntent` and the LLM fallback classifier route turns into conversation, guidance, quick operation, directed analysis, and comprehensive analysis.
- `record_evidence_record`, `record_analysis_plan`, and `AnalysisSessionState` already support evidence and staged analysis state.
- `synthesis_policy` already constrains final answer framing from intent and evidence strength.
- `compact.py` already persists large outputs and compresses old tool results to protect context budget.
- Knowledge, memory, evidence, and project rules already support longer-term reuse.

The main weakness is that these parts are not yet tied together as a hard workflow contract.

Several important safeguards are still prompt-driven or only partially enforced:

- Data understanding is returned as text and tool output, not as a stable required contract for later stages.
- Automatic cleaning affects downstream analysis, but its decisions are not always treated as first-class evidence.
- Intent recognition is not fully data-aware; it can classify what the user said without fully checking what the loaded data supports.
- Analysis route recommendations exist, but they are not yet binding evidence requirements for execution or final verification.
- Final conclusion quality is mostly controlled by prompt instructions, synthesis policy, and evidence metadata, but there is no independent verification layer that audits claims before the user sees them.
- Context compression can preserve summaries, but critical analysis contracts should not rely on chat history remaining intact.

## Goals

1. Make dataset understanding a persistent structured contract, not just a prompt snippet.
2. Make automatic cleaning decisions traceable and available to planning, verification, and final answers.
3. Refine user intent with actual data capability, quality, grain, and available fields.
4. Turn analysis recommendations into explicit route proposals with evidence requirements.
5. Add a verification layer that checks important conclusions before final synthesis.
6. Protect context budget by separating hot context, evidence context, and cold persisted detail.
7. Preserve existing tool and prompt architecture where possible.

## Non-Goals

This phase should not:

- Add many new statistical or ML tools.
- Replace the existing `ToolRegistry`, `AgentLoop`, or evidence model.
- Build a full multi-agent architecture immediately.
- Solve every domain playbook in one pass.
- Make the system refuse all uncertain analysis. Exploratory analysis remains useful, but it must be labeled correctly.
- Require every turn to produce a heavy report.

## Target Workflow

The target workflow is:

```text
Data input
-> Raw scan
-> Cleaning plan and safe cleaning
-> DatasetUnderstandingContract
-> PreviewDigest
-> AnalysisRouteProposal
-> Data-aware intent refinement
-> Analysis plan
-> Tool execution and evidence records
-> VerificationReport
-> Final answer
```

This workflow should create durable structured state at each important boundary. The LLM may still plan and explain, but it should not be the only place where important analysis state exists.

## Context Budget Model

The workflow should divide context into three layers.

### Hot Context

Hot context is the small summary that must be injected into the current turn:

- Dataset names and shapes.
- Field roles.
- Data quality status.
- Grain.
- Supported and unsupported analysis types.
- Current route proposal.
- Active evidence IDs and verification status.

Hot context must be compact enough to survive normal turns.

### Evidence Context

Evidence context is the structured set of records that conclusions depend on:

- Evidence records.
- Cleaning decision IDs.
- Analysis route proposal IDs.
- Verification report IDs.
- Chart or artifact IDs.

The final answer should cite these records conceptually, without expanding full tool outputs unless needed.

### Cold Context

Cold context is persisted detail:

- Full preview output.
- Full profile output.
- Full interpretation data.
- Raw tool outputs.
- Transcript snapshots.
- Detailed verification diagnostics.

Cold context should be retrieved only when needed. It should not compete with core reasoning space.

## Core Artifacts

### 1. DatasetUnderstandingContract

This contract should summarize what the system knows about a loaded dataset after safe cleaning and interpretation.

Suggested shape:

```json
{
  "id": "duc_main_20260602_001",
  "dataset": "main",
  "shape": {"rows": 1000, "columns": 12},
  "field_roles": {
    "date": ["date"],
    "metrics": ["gmv", "orders"],
    "rate_metrics": ["conversion_rate"],
    "dimensions": ["channel", "category"],
    "ids": ["user_id"],
    "text": [],
    "unknown": []
  },
  "grain": "daily_aggregate",
  "quality": {
    "status": "ready_with_warnings",
    "score": 86,
    "blocks": [],
    "warnings": ["Column 'gmv' has 8% missing values"]
  },
  "time_range": {
    "column": "date",
    "min": "2026-01-01",
    "max": "2026-05-31",
    "span_days": 150
  },
  "supported_analyses": ["trend", "period_compare", "dimension_decomposition"],
  "unsupported_analyses": [
    {
      "type": "user_level_retention",
      "reason": "Data grain is aggregate and lacks user-level event history"
    }
  ],
  "cleaning_log_ids": ["clean_main_001"],
  "preview_digest_id": "preview_main_001",
  "detail_path": "tool_outputs/load_main_detail.json"
}
```

This contract should be generated by reusing existing `quick_profile`, `interpret_dataset`, `scan_data_quality`, and `build_data_characteristics_card` logic. The immediate goal is consolidation, not rewriting.

### 2. CleaningDecisionLog

Cleaning must be treated as part of the analysis evidence chain.

Suggested shape:

```json
{
  "id": "clean_main_001",
  "dataset": "main",
  "decisions": [
    {
      "column": "date",
      "decision_type": "safe_auto",
      "from_dtype": "object",
      "to_dtype": "datetime64[ns]",
      "reason": "High-confidence date format",
      "impact": "Enables time-series and period comparison analysis"
    },
    {
      "column": "channel_code",
      "decision_type": "needs_confirmation",
      "from_dtype": "int64",
      "suggested_role": "dimension",
      "reason": "Low-cardinality integer may be categorical encoding",
      "impact": "Should not be treated as continuous numeric metric"
    }
  ],
  "summary": {
    "safe_auto": 1,
    "notify_auto": 0,
    "needs_confirmation": 1,
    "blocked": 0
  }
}
```

Cleaning decision levels:

- `safe_auto`: high-confidence transformations such as clear datetime, percentage, and boolean conversions.
- `notify_auto`: transformations likely to be correct but meaningful, such as numeric strings or numeric suffixes.
- `needs_confirmation`: transformations that may change business meaning, such as low-cardinality integer category encoding or suspected IDs.
- `blocked`: quality or conversion issues that should stop formal analysis until resolved.

### 3. PreviewDigest

The current `preview_data` tool is useful, but raw previews can consume budget and may not guide analysis well. A preview digest should summarize examples and risks.

Suggested shape:

```json
{
  "id": "preview_main_001",
  "dataset": "main",
  "sample_rows_count": 5,
  "sample_rows_path": "tool_outputs/preview_main_rows.json",
  "column_examples": {
    "date": ["2026-01-01", "2026-01-02"],
    "channel": ["organic", "paid"]
  },
  "notable_patterns": [
    "channel has 4 unique values",
    "gmv contains missing values"
  ],
  "risks": [
    "Low-cardinality integer columns should be confirmed before metric analysis"
  ]
}
```

The prompt should receive only the digest, not large raw previews, unless the user explicitly asks to inspect rows.

### 4. AnalysisRouteProposal

Analysis recommendations should become structured route proposals rather than loose text.

Suggested shape:

```json
{
  "id": "route_main_001",
  "dataset": "main",
  "direction": "sales_fluctuation_diagnosis",
  "user_facing_label": "Sales fluctuation diagnosis",
  "why_recommended": "Data has date, GMV, order count, and channel dimension",
  "required_fields": ["date", "gmv"],
  "optional_fields": ["channel", "category", "campaign"],
  "field_coverage": {
    "required": "complete",
    "optional": "partial"
  },
  "tool_chain": ["compare_periods", "contribute_decomposition", "record_evidence_record"],
  "expected_evidence": [
    "metric_delta",
    "period_comparability",
    "dimension_contribution",
    "limitations"
  ],
  "known_risks": [
    "No campaign budget data, so causal marketing effectiveness cannot be concluded"
  ],
  "budget_level": "standard"
}
```

The route proposal should be used by:

- Guidance mode to recommend 2-3 directions.
- Analysis mode to build the plan.
- Verification to check whether expected evidence was actually produced.

### 5. Data-Aware Intent Refinement

Intent classification should combine user text with dataset capability.

Current intent classification already has `TurnIntent`. The next phase should add a refinement step:

```text
TurnIntent + DatasetUnderstandingContract + CleaningDecisionLog + AnalysisRouteProposal
-> refined TurnIntent
```

Examples:

- User says "help me look at this data"; dataset has time, GMV, and channel. Refine to `intent_negotiation` with sales fluctuation and channel contribution suggestions.
- User asks for retention, but the data is aggregate and lacks user ID or event time. Refine to `directed_analysis` with `execution_readiness=insufficient_data`, then explain what data is missing.
- User asks for causal effect, but the data has only before/after aggregate periods. Refine to a descriptive evaluation route and mark causal claims unsupported.

### 6. VerificationReport

The verification layer should audit important claims before the final answer.

Suggested shape:

```json
{
  "id": "verify_turn_001",
  "session_id": "session_x",
  "claim_checks": [
    {
      "claim": "Channel A is the main driver of GMV decline",
      "evidence_ids": ["ev_001", "ev_002"],
      "status": "downgraded",
      "strength": "likely",
      "issues": [
        "Contribution evidence exists, but campaign budget and exposure data are missing",
        "Alternative explanation 'product mix shift' was not tested"
      ],
      "required_action": "Phrase as likely contributor, not proven root cause"
    }
  ],
  "overall_status": "pass_with_downgrades"
}
```

Claim strength levels:

- `confirmed`: strong evidence, appropriate method, necessary assumptions satisfied.
- `likely`: evidence supports the claim but some limitations remain.
- `exploratory`: useful signal, but not enough for decision-grade conclusion.
- `unsupported`: current data does not support the claim.

Verification checks:

- Evidence binding: every important claim should cite evidence.
- Evidence completeness: dataset, metric, sample size, method, time range, and limitations should be present where relevant.
- Route coverage: expected evidence from the chosen route should be produced or explicitly marked missing.
- Cleaning risk: claims depending on risky cleaning decisions should be downgraded or flagged.
- Language risk: words like "significant", "caused", "proved", "main reason", and "effective" require stronger support.
- Causal sensitivity: before/after or correlation cannot become causal proof without appropriate assumptions.
- Prediction sensitivity: forecasts require holdout, backtest, or clear low-confidence labeling.
- Internal consistency: final claims should not contradict each other.

## Integration Points

### `load_data`

`load_data` should continue to be the entry point, but its outputs should be reorganized:

- Keep compact user-facing summary.
- Persist full detail as today.
- Create or update `CleaningDecisionLog`.
- Create `DatasetUnderstandingContract`.
- Create `PreviewDigest`.
- Create initial `AnalysisRouteProposal` entries.

### `quick_profile`, `interpret_dataset`, and `data_features`

These should remain source functions for the new contract. The contract layer should reuse their outputs and normalize them.

### Intent System

`plan_turn_intent` should remain the first classifier. A new refinement step should run after data contracts are available.

### Analysis State

`AnalysisSessionState` should reference:

- active dataset contract IDs,
- active cleaning log IDs,
- active route proposal ID,
- verification report IDs.

### Evidence Records

Evidence records should optionally reference:

- dataset contract ID,
- route proposal ID,
- cleaning log IDs,
- expected evidence category.

### Synthesis Policy

`synthesis_policy` should read verification status. If verification downgrades a claim, the final answer must use the downgraded claim strength and cautious language.

### Context Compaction

Compaction summaries should preserve IDs and statuses, not full details:

- dataset contract ID and key status,
- route proposal ID,
- evidence IDs,
- verification report ID,
- unresolved confirmations.

## MVP Scope

The first implementation should focus on four artifacts:

1. `DatasetUnderstandingContract`
2. `CleaningDecisionLog`
3. `AnalysisRouteProposal`
4. `VerificationReport`

The MVP should not fully redesign the UI or build full domain playbooks. It should make the existing pipeline produce and consume these records.

## Phased Plan

### Phase 1: Data Understanding Contract

- Add a module for building dataset contracts from existing profile, interpretation, and quality scan outputs.
- Persist contracts under session tool outputs or a dedicated analysis state path.
- Inject only compact contract summaries into prompt context.
- Add tests for field roles, grain, quality status, and supported/unsupported analysis types.

### Phase 2: Cleaning Decision Log

- Normalize `auto_clean` applied and needs-confirm outputs into decision records.
- Mark decisions by risk level.
- Ensure risky decisions can influence readiness and final limitations.
- Add tests for date conversion, percent conversion, numeric suffix conversion, and category-like integer handling.

### Phase 3: Route Proposal and Data-Aware Intent

- Convert `interpret_dataset.suggested_analyses` into route proposal records.
- Add route evidence requirements.
- Add intent refinement from user input plus dataset contracts.
- Add tests for vague user requests, unsupported analysis requests, and ambiguous data capability.

### Phase 4: Verification Layer

- Add deterministic verification checks over evidence records and route requirements.
- Add claim strength classification.
- Add language-risk downgrade rules.
- Feed verification status into final answer synthesis.
- Add tests for unsupported causal claims, missing evidence, risky cleaning dependency, and route coverage.

### Phase 5: Hypothesis and Domain Playbooks

- Add hypothesis records for diagnosis workflows.
- Start with one domain playbook, such as ecommerce sales fluctuation or game retention diagnosis.
- Include common hypotheses, required evidence, counter-evidence paths, and downgrade rules.

## Open Design Questions

1. Where should durable contracts live: inside `AnalysisSessionState`, the SQLite knowledge/evidence database, or session-local JSON artifacts?
2. Should verification be purely deterministic at first, or should it optionally call a separate verifier LLM after deterministic checks?
3. Should unsupported user requests immediately ask for more data, or offer a reduced descriptive analysis path?
4. Should route proposals be shown in the Web UI as selectable cards in the first MVP, or only used internally?

## Recommended Defaults

1. Store the first MVP records as session-local JSON artifacts and reference their IDs from `AnalysisSessionState`. This avoids premature database coupling.
2. Start verification as deterministic. Add an optional independent verifier later if needed.
3. When the requested analysis is unsupported, offer a reduced path and clearly explain the missing data.
4. Use route proposals internally first. Web UI cards can follow once the behavior is stable.

## Success Criteria

The phase is successful when:

- Loading data creates a compact, persistent dataset contract.
- Cleaning decisions are visible to later analysis and final answer limitations.
- Vague requests produce data-supported analysis route suggestions.
- Unsupported requests are downgraded or redirected before execution.
- Important final claims have verification status.
- Context compression preserves contract, route, evidence, and verification IDs.
- Final answers are more cautious when evidence is weak, without becoming unhelpful.

## Product Positioning

This direction gives Data Agent a clearer distinction from general coding agents.

General coding agents are strong at generating custom analysis code on demand. Data Agent should be strong at repeatedly delivering business-facing analysis with traceable data understanding, cleaning decisions, evidence, verification, and confidence boundaries.

The durable advantage is not that every tool is impossible to copy. The advantage is the enforced workflow:

```text
Data understanding
-> cleaning traceability
-> data-aware intent
-> route evidence requirements
-> evidence-backed execution
-> independent verification
-> bounded final synthesis
```

That workflow is the next product layer.
