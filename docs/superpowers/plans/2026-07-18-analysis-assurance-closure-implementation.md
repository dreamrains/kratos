# Analysis Assurance Closure Implementation Plan

**Status:** Ready for implementation in a fresh conversation.

**Baseline:** Start from commit `dc6e916` (`feat: add canonical plans and versioned analysis copies`). The earlier core-contract and analysis-copy plan is functionally complete. Do not reimplement its Tasks 1-7.

**Goal:** Close four remaining trust boundaries without creating parallel subsystems:

1. bind every material data-change approval to the exact dataset version and transformation proposal;
2. compile method-appropriate statistical, time-series, experiment, and causal requirements into the canonical analysis plan;
3. bind final natural-language claims to recorded computation evidence and audit the final draft before publication;
4. allocate and evaluate context budget so compression cannot silently remove trust-critical state or reduce analysis quality.

**Architecture:** Reuse the existing confirmation kernel, canonical `AnalysisPlan`, route `evidence_requirements`, `EvidenceRecord`, answer-quality extraction, verification layer, turn execution budget, context compaction, and artifact-reference mechanism. Add only one new authoritative business-rule module, `analysis_requirements.py`. Other changes extend the current owners instead of introducing replacement confirmation, evidence, audit, or context managers.

**Implementation strategy:** Deliver vertical checkpoints in dependency order. A checkpoint is not complete merely because a schema exists: its route, execution, evidence, final-answer, recovery, and low-context behavior must be exercised where applicable.

---

## 1. Fixed Product Decisions

- Do not modify user-uploaded source files or raw snapshots. Every transformation still operates on a versioned analysis copy.
- Do not build a deterministic multi-table join or aggregation planner. The LLM may plan and execute multi-table work through existing tools when needed.
- Do not use historical stage names as the new product model or new public contract.
- Do not create a second confirmation store, receipt database, evidence store, final-answer verifier, or context compressor.
- Do not treat a p-value as universally required or sufficient. Statistical requirements depend on the claim and method.
- Do not use a universal row-count cutoff such as `n < 30` as a proxy for statistical adequacy. Effective sample size is design-, estimand-, grouping-, clustering-, and method-dependent.
- Do not allow an LLM-authored `EvidenceRecord` to become high-confidence evidence merely because required text fields are present.
- Deterministic blockers are authoritative. An optional LLM judge may add concerns but cannot override a deterministic failure.
- Full proposal, computation, evidence, and audit payloads live in artifacts. State and prompts carry compact, bounded references.
- Existing untracked `artifacts/` and `tmp/` content must remain untouched and uncommitted.

---

## 2. Current Baseline and Exact Gaps

### 2.1 Data-change confirmation

Already implemented:

- `Workspace` retains immutable raw snapshots and versioned analysis copies.
- `clean_data` and `apply_type_conversion` build candidates and do not promote unconfirmed material changes.
- The confirmation kernel already provides decision identity, `data_version`, `spec_version`, optimistic record versions, idempotency keys, recovery, and typed resolution actions.

Gap:

- `confirmed=True` is only a Boolean supplied by the caller. It does not prove which dataset version and proposal the user approved.
- Cleaning proposals are not yet first-class producers of the existing confirmation runtime.

### 2.2 Analysis requirements

Already implemented:

- Routes emit canonical `evidence_requirements` string IDs.
- Method playbooks contain partial `statistical_requirements`.
- `EvidenceRecord` supports sample size and optional statistical details.
- Verification already restricts causal wording when the recorded method is non-causal.

Gap:

- Requirements are distributed across route templates, playbooks, prompts, and evidence validation.
- There is no deterministic compiler that decides which requirements are required, conditional, not applicable, satisfied, or blocking for a concrete plan and claim type.
- Seasonality, experimental design readiness, causal identification, confidence intervals, assumptions, and multiplicity are not enforced end to end.

### 2.3 Final-answer audit

Already implemented:

- `answer_quality.py` performs conservative sentence extraction and materiality detection for golden-answer measurement.
- `verification.py` validates structured claims against `EvidenceRecord`, cleaning risks, and causal-method boundaries.
- `trust_workflow_runtime.py` verifies claims already present in evidence records before synthesis.
- `analysis_quality_rubric.py` exposes publish-gate semantics.

Gap:

- Runtime verification operates mainly on claims recorded before final synthesis, not on the final natural-language draft.
- Current final-answer extraction uses sentence hints and fuzzy overlap; it does not reliably bind quantities, units, time scopes, comparison direction, or claim strength to exact evidence IDs.
- The streaming path may emit draft text before a full independent final-answer audit.

### 2.4 Context budget

Already implemented:

- `TurnExecutionState` tracks tool and approximate token budgets.
- `compact.py` persists large outputs and compresses conversation history.
- Analysis state uses compact artifact references.
- Data lineage is excluded from ordinary planning context except for a concise summary.

Gap:

- Budgeting is coarse-grained; there is no allocation by history, requirements, evidence, synthesis, audit, and repair reserve.
- Compression has no explicit trust capsule containing all non-droppable analysis identities and unresolved blockers.
- There is no degradation harness proving that lower budgets do not produce stronger, less-supported conclusions.

---

## 3. Authoritative Ownership

| Concern | Authoritative owner | Rule |
|---|---|---|
| Confirmation lifecycle and durable answer | `agent/confirmation/models.py`, `service.py`, `runtime.py` | Data cleaning must become a producer/consumer of this runtime; no new receipt store. |
| Dataset identity and transformation identity | `agent/data_lineage.py` | Proposal IDs and transformation fingerprints are deterministic and pure. |
| Candidate construction and application | `tools/data_clean.py` | Build/recompute candidates here; never persist candidate DataFrames in confirmation records. |
| Statistical and methodological requirements | new `agent/analysis_requirements.py` | The only compiler and satisfaction evaluator. Routes and playbooks provide inputs, not independent rules. |
| Evidence schema and provenance | `agent/evidence_contracts.py` | Canonical validation and compatibility normalization live here. |
| Evidence recording | `tools/analysis_flow.py` | Resolves trusted computation refs; the model cannot mint provenance. |
| Final-text claim extraction | `agent/answer_quality.py` | Extend the existing extractor; do not create another extractor module. |
| Claim/evidence/requirement audit | `agent/verification.py` | Extend the existing deterministic verifier. |
| Runtime orchestration | `agent/trust_workflow_runtime.py`, `agent/loop.py` | Orchestrate only; do not duplicate business rules. |
| Budget accounting and convergence | `agent/execution_control.py` | Extend the current budget owner. |
| History compression and large-output persistence | `agent/compact.py` | Preserve trust capsule; do not add another compressor. |

Removal rule: a compatibility alias may read legacy records, but no compatibility path may remain a second writable authority.

---

## 4. Target Contracts

### 4.1 TransformationProposal

`data_lineage.py` produces a deterministic `transformation_proposal.v1` mapping:

```python
{
    "contract_version": "transformation_proposal.v1",
    "proposal_id": "proposal_<digest>",
    "logical_dataset": "orders",
    "dataset_version_id": "orders_v2_<digest>",
    "raw_dataset_id": "raw_orders_<digest>",
    "source_fingerprint": "<frame fingerprint>",
    "operation": "clean_data",
    "parameters": {...},
    "parameters_fingerprint": "<digest>",
    "transformation_fingerprint": "<digest>",
    "impact": {
        "row_count_before": 100,
        "row_count_after": 97,
        "affected_columns": ["revenue"],
        "affected_row_count": 3,
        "information_loss": True,
    },
}
```

The existing `ConfirmationRecord` is the approval receipt:

- `data_version = "dataset:<dataset_version_id>:<source_fingerprint>"`
- `spec_version = "transformation:<transformation_fingerprint>"`
- `resolution_action = "approve_dataset_transformation"`
- `resolution_params` contains only the authoritative proposal artifact reference and compact identities.

No full DataFrame or unrestricted user answer is stored in the confirmation record.

### 4.2 AnalysisRequirement

Create `ANALYSIS_REQUIREMENT_CONTRACT_VERSION = "analysis_requirement.v1"`:

```python
{
    "id": "req_step_1_confidence_interval",
    "category": "inference",
    "name": "confidence_interval",
    "necessity": "required",        # required | conditional | not_applicable
    "trigger": "claim compares two groups with inferential wording",
    "status": "pending",            # pending | satisfied | unmet | not_applicable
    "required_evidence_fields": ["effective_sample_size", "effect_estimate", "confidence_interval"],
    "assumption_checks": ["independence", "distribution_or_robust_method"],
    "unmet_action": "block_claim",  # block_analysis | block_claim | downgrade_claim | disclose
    "evidence_ids": [],
    "reason": "",
}
```

Rules:

- Route and playbook requirement strings become canonical requirement IDs or compiler inputs.
- Structured requirement records are stored once under the canonical `AnalysisPlan`, grouped by `step_id`.
- `evidence_requirements` remains a compact compatibility projection during migration; it is not a second rule engine.
- Evidence records reference requirement IDs and are evaluated by the shared satisfaction evaluator.

### 4.3 Computation provenance

Extend the canonical EvidenceRecord with server-resolved provenance:

```python
{
    "contract_version": "evidence_record.v2",
    "id": "evidence_<digest>",
    "plan_id": "plan_...",
    "step_id": "step_1",
    "claim_key": "group_revenue_difference",
    "requirement_ids": ["req_step_1_effect_size", "req_step_1_confidence_interval"],
    "source_tool_call_ids": ["call_123"],
    "computation_refs": [{
        "tool_call_id": "call_123",
        "tool_name": "run_python",
        "arguments_digest": "...",
        "output_digest": "...",
        "artifact_path": "sessions/.../tool_outputs/call_123_detail.json",
        "dataset_versions": ["orders_v2_..."],
        "verification_level": "traceable",  # traceable | structured_checked | independently_recomputed
    }],
    "statistical_support": {
        "effective_sample_size": {"total": 200, "groups": {"A": 100, "B": 100}},
        "effect_estimate": {"value": 4.2, "unit": "CNY", "metric": "mean_difference"},
        "confidence_interval": {"level": 0.95, "lower": 1.1, "upper": 7.3},
        "test": {"name": "welch_t", "p_value": 0.008},
        "assumptions": [{"name": "independence", "status": "assumed", "reason": "..."}],
    },
}
```

The loop creates computation refs automatically from actual tool calls and persisted outputs. `record_evidence_record` accepts tool-call IDs but must resolve and hash them server-side. Unknown, cross-turn, cross-plan, or stale-dataset refs are rejected.

An output hash proves provenance and immutability, not mathematical correctness. High-confidence statistical claims require `structured_checked` or `independently_recomputed` support. Free-form Python output begins as `traceable`; it is upgraded only when a deterministic verifier checks the declared estimand and reported statistics against the current versioned dataset.

Legacy evidence is normalized as `provenance_status="legacy_unbound"`; it may support descriptive continuity but cannot support a new high-confidence inferential or causal claim.

### 4.4 ExtractedClaim and FinalAnswerAudit

Extend `answer_quality.py` to emit:

```python
{
    "claim_key": "claim_1",
    "text": "A组平均收入比B组高4.2元。",
    "claim_type": "comparison",  # descriptive | comparison | association | prediction | causal | recommendation
    "material": True,
    "quantities": [{"value": 4.2, "unit": "CNY", "direction": "higher"}],
    "time_scope": "",
    "population_scope": "A vs B",
    "evidence_ids": ["evidence_..."],
    "requirement_ids": ["req_..."],
}
```

The synthesis draft uses internal markers such as `[[evidence:evidence_id]]`. Markers are stripped only after audit passes.

`verification.py` produces `final_answer_audit.v1` with one check per material claim, requirement coverage, dataset-version coverage, blockers, downgrade instructions, and an overall status of `pass`, `revise`, or `blocked`.

### 4.5 Prompt budget report

Extend `TurnExecutionState` with component accounting rather than creating a new context manager:

```python
{
    "profile": "analysis",
    "estimated_prompt_tokens": 42000,
    "components": {
        "system_and_tools": 12000,
        "history": 16000,
        "analysis_state": 4000,
        "requirements": 2000,
        "evidence": 4000,
    },
    "reserved": {"synthesis": 2500, "audit_and_revision": 1500},
    "compression_actions": [...],
    "trust_capsule_digest": "...",
}
```

The report is diagnostic metadata, not a new prompt payload.

---

## 5. Statistical Guard Policy

| Analysis/claim type | Required checks | Important rule when unmet |
|---|---|---|
| Descriptive summary | effective sample size, missingness, denominator/grain, time and population scope | Disclose limitations; do not invent inferential significance. |
| Group or period comparison | per-group effective sample size, effect estimate, confidence interval, method, assumptions; significance and multiplicity when inferential wording is used | Allow descriptive difference, but block “significant”, “reliable difference”, or generalized claims without support. |
| Time series/trend | frequency, missing intervals, observation window, comparable periods, autocorrelation awareness, enough cycles for seasonality | If cycles are insufficient, mark seasonality not estimable; do not treat trend as causal. |
| Experiment | assignment unit, arms, exposure/outcome definitions, per-arm sample size, randomization/balance, attrition, effect estimate and interval, multiplicity | Power/MDE is required for design/detectability decisions; retrospective power must not be used as proof. |
| Observational causal analysis | treatment/outcome, design type, confounders, identification assumptions, overlap/balance or design-specific diagnostics, sensitivity/alternative explanations | If identification is not credible, downgrade to association or descriptive comparison and block causal language. |

Statistical defaults must not silently choose a test merely from column dtypes. Method choice must account for the estimand, sampling unit, paired/independent structure, clustering, repeated measures, and distribution/robustness needs. Sample adequacy must be expressed against the selected method and uncertainty target, not a universal `n < 30` warning.

---

## 6. Delivery Sequence

### Checkpoint A — Close mutation authorization

#### Task 1: Bind data-change confirmation to proposal and dataset version

**Files:**

- Modify `src/data_agent/agent/data_lineage.py`
- Modify `src/data_agent/tools/data_clean.py`
- Modify `src/data_agent/agent/confirmation/runtime.py`
- Modify `src/data_agent/agent/confirmation/models.py` only if a generic producer payload is required; reuse existing fields first
- Modify `src/data_agent/agent/loop.py` only for generic confirmation-producer plumbing
- Create `tests/test_data_clean_confirmation_receipt.py`
- Modify `tests/test_clean_data_copy_on_write.py`
- Modify `tests/test_confirmation_runtime.py`
- Modify `tests/test_confirmation_service.py`

**Steps:**

1. Add failing tests for deterministic proposal identity, exact data/spec versions, resolved approval, denial, duplicate response, restart recovery, and stale active-version rejection.
2. Add pure proposal construction and parameter/transformation fingerprinting in `data_lineage.py`.
3. On an unapproved material change, persist the proposal through the existing cleaning/trust artifact path and return only a compact proposal reference. Do not promote a version.
4. Add a data-cleaning confirmation producer that creates the existing `QuestionCandidate` with exact `data_version` and `spec_version`.
5. Register `approve_dataset_transformation` as a typed resolution action. It records approval identity; it does not store or mutate a DataFrame.
6. Add `apply_confirmed_transformation(confirmation_id)` in the data-cleaning domain. It loads the authoritative proposal, validates the resolved record, rechecks active dataset ID and both fingerprints, recomputes the candidate, and promotes only when the recomputed fingerprint matches.
7. Remove Boolean authority: keep `confirmed` temporarily only as a rejected/deprecated input with `error_type="confirmation_receipt_required"`. It must never authorize a material production mutation.
8. Ensure rejection/skip leaves the dataset unchanged and records an auditable decision.

**Acceptance:**

- The same approval cannot apply to a different dataset version, operation, column set, strategy, or fill value.
- A proposal approved before another version is promoted is stale and cannot be applied.
- Duplicate response/application is idempotent.
- Raw and all prior versions remain unchanged.
- Web, CLI, restart recovery, and ordinary session APIs expose the same canonical confirmation record.

**Checkpoint commit:** `feat: bind data changes to confirmation receipts`

---

### Checkpoint B — Establish one assurance contract

#### Task 2: Add the canonical requirement compiler

**Files:**

- Create `src/data_agent/agent/analysis_requirements.py`
- Modify `src/data_agent/agent/analysis_plan_contracts.py`
- Modify `src/data_agent/agent/analysis_state.py`
- Modify `src/data_agent/agent/trust_contracts.py`
- Modify `src/data_agent/agent/route_capabilities.py`
- Modify `src/data_agent/agent/method_playbooks.py`
- Modify `src/data_agent/tools/analysis_flow.py`
- Create `tests/test_analysis_requirements.py`
- Modify `tests/test_analysis_plan_consolidation.py`
- Modify `tests/test_load_to_route_requirements.py`
- Modify `tests/test_method_playbooks.py`

**Public interfaces:**

```python
compile_analysis_requirements(
    *, plan, route, playbook, dataset_contracts, user_intent
) -> list[dict]

evaluate_requirement_satisfaction(
    requirements, evidence_records
) -> list[dict]

requirement_ids_for_route(route) -> list[str]
```

**Steps:**

1. Write characterization tests showing current route and playbook strings are preserved as inputs.
2. Define `analysis_requirement.v1`, allowed categories, necessity, status, and unmet actions.
3. Centralize requirement definitions and triggers in `analysis_requirements.py`. Remove duplicated statistical decision rules from callers as they migrate.
4. During canonical plan normalization/recording, compile structured requirements deterministically. Reject an executable plan that deletes a compiler-required hard requirement.
5. Persist structured requirements only inside the canonical plan. Route payloads retain compact IDs/projections.
6. Add canonical names `validate_evidence_record` and `validate_measurement` in `evidence_contracts.py` when Task 3 starts; keep old function names as read-only compatibility aliases until fixtures and stored sessions are migrated.

**Acceptance:**

- The same plan inputs produce stable requirement IDs and ordering.
- Display-only plans may omit execution detail; executable plans cannot omit hard compiled requirements.
- One requirement is owned by one definition; route, playbook, and prompts cannot disagree silently.
- Current saved plans and route proposals still load through bounded compatibility normalization.

**Checkpoint commit:** `feat: compile canonical analysis requirements`

#### Task 3: Bind EvidenceRecord to real computation output

**Files:**

- Modify `src/data_agent/agent/evidence_contracts.py`
- Modify `src/data_agent/agent/analysis_state.py`
- Modify `src/data_agent/agent/execution_control.py`
- Modify `src/data_agent/agent/loop.py`
- Modify `src/data_agent/tools/analysis_flow.py`
- Modify `src/data_agent/agent/verification.py`
- Create `tests/test_computation_evidence_binding.py`
- Modify `tests/test_execution_control.py`
- Modify `tests/test_verification_layer.py`
- Modify `tests/test_trust_workflow_runtime.py`

**Steps:**

1. Add failing tests proving that fabricated/unknown tool-call IDs, stale dataset versions, and output-digest mismatches are rejected.
2. Extend the existing persisted tool-output path to generate compact computation refs with argument/output digests and active dataset version IDs.
3. Store only compact computation refs in analysis state; hydrate full results from the existing artifact path.
4. Introduce canonical `evidence_record.v2` normalization. Resolve `source_tool_call_ids` server-side in `record_evidence_record`.
5. Require `requirement_ids` and structured `statistical_support` when the compiled plan requires them.
6. Add provenance verification levels. Hash-bound/free-form output is `traceable`; validate structured tool results as `structured_checked`; independently recompute supported core statistics from the exact versioned dataset before using `independently_recomputed`.
7. Mark old records `legacy_unbound`; prevent them from supporting new high-confidence inferential or causal claims.
8. Verify that a tool result remains traceable after prompt compaction and process restart.

**Acceptance:**

- An LLM cannot mint trusted provenance or upgrade an unbound result to high confidence.
- Artifact hashes alone cannot upgrade statistical confidence; the verification level is reported explicitly.
- Every material numeric/inferential claim points to a current-plan EvidenceRecord and at least one real computation ref.
- Evidence tied to an old analysis-copy version is stale after an incompatible data transformation.
- Full tool output remains outside ordinary prompt context.

**Checkpoint commit:** `feat: bind evidence to computation outputs`

---

### Checkpoint C — Compile method-appropriate guards

#### Task 4: Implement comparison and time-series requirements

**Files:**

- Modify `src/data_agent/agent/analysis_requirements.py`
- Modify `src/data_agent/agent/trust_contracts.py`
- Modify `src/data_agent/agent/method_playbooks.py`
- Modify `src/data_agent/agent/route_capabilities.py`
- Modify `src/data_agent/agent/analysis_entry.py`
- Modify `src/data_agent/agent/question_need_detector.py`
- Modify `src/data_agent/tools/analysis_flow.py`
- Create `tests/test_statistical_route_requirements.py`
- Create `tests/test_time_series_route_requirements.py`
- Add focused real-data scenarios under `tests/real_data/`

**Steps:**

1. Add deterministic triggers for descriptive, group comparison, period comparison, and time-series claims.
2. Require effective sample size, denominators, missingness, estimand/effect, confidence interval, method, assumptions, and multiplicity when applicable.
3. Replace global small-sample confidence heuristics with method-specific adequacy and effective-sample checks, including per-group, paired, clustered, or repeated-measure structure.
4. Distinguish descriptive differences from inferential claims; do not require or manufacture significance for purely descriptive summaries.
5. For time series, compile frequency, missing interval, window comparability, autocorrelation awareness, and seasonality-estimability requirements.
6. Determine the minimum complete seasonal cycles from the selected method/frequency and report it explicitly. Fewer than the minimum marks seasonality `not_estimable`; marginal data may be `estimable_with_limits`, never silently high confidence.
7. Make missing user-definitional inputs a confirmation/question only when they materially change the estimand. Missing computable evidence should trigger analysis, not a user question.

**Acceptance scenarios:**

- Small groups cannot receive a high-confidence generalized difference claim without appropriate support.
- A large sample with a tiny effect must report effect magnitude and interval rather than only significance.
- Multiple segment comparisons require multiplicity handling or an explicit exploratory label.
- An eight-point monthly series cannot claim annual seasonality.
- Irregular or gapped time data cannot silently use ordinary period comparison assumptions.

**Checkpoint commit:** `feat: guard comparisons and time series`

#### Task 5: Implement experiment and causal-identification requirements

**Files:**

- Modify `src/data_agent/agent/analysis_requirements.py`
- Modify `src/data_agent/agent/method_playbooks.py`
- Modify `src/data_agent/agent/analysis_entry.py`
- Modify `src/data_agent/agent/question_need_detector.py`
- Modify `src/data_agent/agent/verification.py`
- Create `tests/test_experiment_route_requirements.py`
- Create `tests/test_causal_claim_guard.py`
- Add focused real-data scenarios under `tests/real_data/`

**Steps:**

1. Compile experiment requirements for assignment unit, arms, exposure, outcome, per-arm sample, randomization/balance, attrition, estimand, uncertainty, and multiplicity.
2. Require power/MDE for experiment planning or detectability decisions. Do not use retrospective power as evidence that an observed effect is real.
3. Compile causal requirements by design type. Examples: parallel trends for difference-in-differences, overlap/balance for matching/weighting, exclusion assumptions for instruments, and discontinuity diagnostics for regression discontinuity.
4. When the design does not identify a causal effect, automatically change the allowed claim class to association/descriptive comparison and require alternative explanations.
5. Ask the user only for unavailable business/design facts that materially change the estimand or identification; compute diagnostics from supplied data without confirmation.

**Acceptance scenarios:**

- Pre/post data without control cannot produce “the campaign caused the increase.”
- A randomized experiment with missing assignment-unit information remains blocked for causal publication.
- A valid effect estimate still discloses attrition, multiplicity, and uncertainty where applicable.
- An observational comparison may still produce a useful bounded association result.

**Checkpoint commit:** `feat: guard experiment and causal claims`

---

### Checkpoint D — Audit the actual final answer

#### Task 6: Upgrade final-text claim extraction and deterministic audit

**Files:**

- Modify `src/data_agent/agent/answer_quality.py`
- Modify `src/data_agent/agent/verification.py`
- Modify `src/data_agent/agent/analysis_quality_rubric.py`
- Modify `src/data_agent/agent/synthesis_policy.py`
- Modify `src/data_agent/agent/trust_workflow_runtime.py`
- Create `tests/test_final_answer_claim_audit.py`
- Modify `tests/real_data/test_golden_answer_quality.py`
- Modify `tests/test_verification_layer.py`
- Modify `tests/test_synthesis_policy.py`

**Steps:**

1. Preserve the existing conservative sentence splitter, then extend it to classify claim type and extract quantities, units, direction, scope, and internal evidence markers.
2. Require synthesis drafts to cite internal EvidenceRecord IDs for material numeric, comparison, association, prediction, causal, and recommendation claims.
3. Extend `verify_analysis_claims` rather than introducing another verifier. Check exact evidence identity, current plan/version, requirement satisfaction, numeric consistency, direction, units, scope, confidence, causal language, and cleaning risk.
4. Respect computation verification level: `traceable` proves source lineage only and cannot be described as independently verified statistical correctness.
5. Produce and persist `final_answer_audit.v1`; store only a compact ref in state.
6. Keep optional LLM critique separate and secondary. It can flag missing nuance or readability concerns but cannot change deterministic `blocked` to `pass`.
7. Retain the golden-quality runner as an offline regression consumer of the same extraction and audit functions.

**Deterministic publication rules:**

- Unsupported material numeric or causal claim: block.
- Evidence value, direction, unit, time scope, or population mismatch: block.
- Unmet `block_claim` requirement: remove/downgrade that claim.
- Missing limitation or exploratory label: revise.
- Purely diagnostic statements about missing data/evidence may pass without positive evidence if they make no unsupported factual claim.

**Acceptance:**

- The auditor checks the actual final draft, not only pre-synthesis EvidenceRecord claims.
- Fuzzy text similarity alone cannot authorize publication.
- Every blocked claim contains a machine-readable reason and safe downgrade action.
- Internal evidence markers never appear in the user-visible final response.

**Checkpoint commit:** `feat: audit final answer claims`

#### Task 7: Put the audit before every analysis response is emitted

**Files:**

- Modify `src/data_agent/agent/loop.py`
- Modify `src/data_agent/agent/trust_workflow_runtime.py`
- Modify `src/data_agent/agent/confirmation/runtime.py` only if publish blocking must expose canonical session state
- Modify `tests/test_comprehensive_analysis_flow.py`
- Modify `tests/test_confirmation_runtime.py`
- Create `tests/test_final_answer_publish_gate.py`

**Steps:**

1. Buffer candidate final text for directed analysis and comprehensive-report intents in synchronous and streaming paths.
2. Run the deterministic final-answer audit before yielding any text delta to the user.
3. If status is `revise`, allow one bounded synthesis-only revision using audit findings and allowed evidence IDs.
4. If status is `blocked` because computation evidence is missing, do not ask the model to wordsmith around it. Continue the required analysis if budget permits; otherwise return a safe partial result that states the evidence gap.
5. Re-audit the revised draft. After one failed revision, emit a bounded fallback containing only supported findings and explicit gaps.
6. Preserve the existing confirmation final guard: unresolved blocking confirmation takes precedence over publication.
7. Prevent audit/revision messages and internal markers from entering user-visible history.

**Acceptance:**

- No unaudited analysis draft is streamed.
- Audit repair is bounded to one revision and cannot create an infinite loop.
- Simple consultation and non-analytical chat do not pay the audit cost.
- A restart or resumed confirmation cannot bypass the publish gate.

**Checkpoint commit:** `feat: gate analysis publication on audit`

---

### Checkpoint E — Preserve depth under constrained context

#### Task 8: Add component budgets, trust capsule, and degradation evaluation

**Files:**

- Modify `src/data_agent/agent/execution_control.py`
- Modify `src/data_agent/agent/compact.py`
- Modify `src/data_agent/agent/analysis_state.py`
- Modify `src/data_agent/agent/loop.py`
- Modify `src/data_agent/agent/artifact_refs.py` if bounded bulk hydration is required
- Create `tests/test_analysis_context_budget.py`
- Modify `tests/test_analysis_quality.py`
- Modify `tests/test_execution_control.py`
- Modify `tests/regression_test.py`
- Create `tests/real_data/test_context_budget_degradation.py`

**Trust capsule must preserve:**

- current user goal and explicit quality/format requirements;
- canonical plan ID and contract version;
- active dataset names, dataset version IDs, and raw/source fingerprints;
- unresolved hard requirement IDs and their unmet actions;
- EvidenceRecord IDs and computation-ref digests used by material claims;
- active confirmation ID/version and transformation proposal identity;
- latest audit blockers and permitted downgrade actions.

**Steps:**

1. Add component-level prompt accounting and configurable synthesis/audit reserves to `TurnExecutionState`.
2. Measure prompt components at assembly time. Do not confuse approximate prompt size with provider-billed usage; name metrics accordingly.
3. Compact low-priority history and verbose outputs before touching trust-critical state.
4. Extend the existing analysis-state summary into a deterministic bounded trust capsule. Persist its digest in budget diagnostics.
5. Keep full requirements, evidence, computation outputs, proposals, and audit reports in artifacts; hydrate only requested IDs with per-component limits.
6. Reserve enough budget for final synthesis, deterministic audit, and at most one revision. Reaching the exploration budget must not consume the audit reserve.
7. Build forced-budget tests at representative full, medium, and low thresholds.
8. Compare invariant outcomes rather than exact prose: requirement retention, evidence binding, audit status, claim strength, completion, and latency/round counts.

**Quality degradation rules:**

- Lower budget may reduce breadth or detail, but may not strengthen a claim.
- Required evidence/confirmation identities may not disappear during compaction.
- If evidence cannot fit or be hydrated, the system must downgrade/disclose rather than hallucinate.
- The low-budget path must terminate predictably; it may not enter repeated compression or audit loops.

**Acceptance:**

- All trust-capsule identities survive forced compaction and restore.
- Medium/low budget outputs never have a stronger audit-approved claim class than the full-budget baseline without additional evidence.
- Audit and one repair attempt remain available after exploration reaches its budget.
- Prompt payloads remain bounded while full artifacts remain traceable.

**Checkpoint commit:** `feat: preserve analysis assurance under context limits`

---

### Checkpoint F — Migration and closure

#### Task 9: Remove duplicate runtime rules and close compatibility boundaries

**Files:**

- Modify affected tests and `CLAUDE.md`
- Update `docs/superpowers/plans/2026-07-18-core-contracts-and-analysis-copy-implementation.md` with a short completed-status note only; do not merge this plan into it
- Add a validation report under `docs/superpowers/validation/`

**Steps:**

1. Search production code for direct Boolean material-change authorization, duplicate requirement compilers, claim verifiers, and context compressors.
2. Verify new production evidence uses canonical `evidence_record.v2` and new plans use `analysis_requirement.v1`.
3. Keep legacy readers only at explicit normalization boundaries. Document their exact removal condition.
4. Document user-visible behavior: immutable raw data, version-bound approvals, statistical/causal limits, evidence-backed final claims, and bounded quality under context pressure.
5. Record verification commands, results, environmental warnings, and untested external dependencies in the validation report.

**Checkpoint commit:** `docs: close analysis assurance migration`

---

## 7. Required Verification

Run focused suites after each checkpoint. Before completion, run at least:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_data_clean_confirmation_receipt.py `
  tests/test_clean_data_copy_on_write.py `
  tests/test_confirmation_models.py `
  tests/test_confirmation_service.py `
  tests/test_confirmation_runtime.py `
  tests/test_analysis_requirements.py `
  tests/test_statistical_route_requirements.py `
  tests/test_time_series_route_requirements.py `
  tests/test_experiment_route_requirements.py `
  tests/test_causal_claim_guard.py `
  tests/test_computation_evidence_binding.py `
  tests/test_final_answer_claim_audit.py `
  tests/test_final_answer_publish_gate.py `
  tests/test_analysis_context_budget.py
```

Then run affected broad suites:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_analysis_plan_consolidation.py `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_flow_tools.py `
  tests/test_load_to_route_requirements.py `
  tests/test_route_capabilities.py `
  tests/test_analysis_entry.py `
  tests/test_question_need_detector.py `
  tests/test_method_playbooks.py `
  tests/test_execution_control.py `
  tests/test_verification_layer.py `
  tests/test_trust_workflow_runtime.py `
  tests/test_synthesis_policy.py `
  tests/test_comprehensive_analysis_flow.py `
  tests/test_analysis_quality.py `
  tests/real_data/test_golden_answer_quality.py `
  tests/real_data/test_context_budget_degradation.py
```

Repository checks:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src/data_agent
git diff --check
git status --short
```

Do not use `tests/test_tools_comprehensive.py` as an ordinary pytest file if its custom runner signature still prevents collection. Run its intended script entry point and report PASS/FAIL/SKIP separately.

---

## 8. Completion Gate

Do not claim the plan complete until all are true:

1. Material data changes require a resolved existing-runtime confirmation bound to exact dataset and transformation identities.
2. `confirmed=True` cannot authorize a material production mutation.
3. Statistical requirements are method- and claim-specific; significance is neither universal nor sufficient.
4. Seasonality, experiment design, and causal-identification insufficiency produce explicit bounded outcomes.
5. High-confidence inferential/causal EvidenceRecords are bound to real computation refs and current dataset versions.
6. The actual final answer is extracted and audited before any analysis text is emitted.
7. Deterministic audit blockers cannot be overridden by synthesis or an LLM judge.
8. Audit repair is bounded and failure produces a safe supported fallback.
9. Trust-critical identities survive compaction, persistence, restore, and constrained-budget execution.
10. Low-context execution may reduce breadth but cannot increase unsupported claim strength.
11. No new parallel confirmation, requirement, evidence, audit, or compaction subsystem exists.
12. Compatibility adapters and their removal conditions are reported explicitly.
13. `artifacts/` and `tmp/` remain untouched unless a test uses an isolated temporary directory.

---

## 9. Fresh-Conversation Handoff

In the new conversation:

1. Read this plan and inspect current code before editing; do not rely only on the plan's line references.
2. Confirm `git log -1 --oneline` includes baseline `dc6e916` or a descendant and inspect `git status --short`.
3. Treat the earlier core-contract/analysis-copy plan as completed baseline, not pending work.
4. Start with Task 1 only. Do not begin statistical or audit expansion until the version-bound confirmation tests pass.
5. At every checkpoint, inspect whether an existing module already owns the rule before adding a new function or field.
6. Keep implemented behavior, compatibility behavior, and future design separate in progress reports.
7. Stop and discuss any proposed change that would mutate raw data, create a second authority, force significance testing for descriptive analysis, or emit unaudited analytical text.
