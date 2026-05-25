# Memory Candidate Extraction and Context Budgeting Design

## Summary

Phase 2 adds a conservative learning loop on top of the Phase 1.5 knowledge, memory, and evidence foundation.

The system should automatically discover possible memory candidates from saved conversations and evidence, but it must not automatically turn those candidates into trusted knowledge. Candidate memories must be small, traceable, deduplicated, reviewable, and excluded from prompt retrieval until confirmed.

The second half of this phase is context budget protection. Dynamic knowledge and memory retrieval must help data analysis, not compete with the data, analysis state, evidence records, and user request for context space.

## Goals

1. Generate useful memory candidates automatically from sessions and evidence.
2. Keep every candidate traceable to source evidence and extraction reason.
3. Prevent candidate memories from entering prompts before user confirmation.
4. Add deduplication so repeated saves do not create noisy memory spam.
5. Add light conflict marking for candidates that appear to contradict confirmed memory or formal knowledge.
6. Add retrieval context budgets so knowledge and memory cannot degrade data-analysis quality.
7. Improve the management center so users can understand, edit, confirm, reject, delete, or promote candidates.

## Non-Goals

Phase 2 intentionally does not implement:

- Full Persona / user-profile pyramid.
- Vector database or embedding-first retrieval.
- Automatic Skill generation.
- Automatic formal Knowledge creation from unreviewed candidates.
- Complex conflict arbitration with blocking user questions.
- Large knowledge graph or relationship visualization.
- Full historical version diff UI for knowledge.
- LLM-only memory extraction as the default path.

These are valid future directions, but they are too heavy for the next increment.

## Reference Lessons

### Hermes Agent

Hermes is useful as a product-level reference for a closed learning loop: agent-curated memory, periodic nudges to persist useful information, cross-session search, and eventual skill creation from experience.

For this project, the useful principle is not "let the agent autonomously write everything." The useful principle is:

- The agent should notice repeated or explicit learnable information.
- The agent should surface it in a reviewable way.
- Repeated stable workflows can later become Skill candidates.

Skill generation should remain out of Phase 2.

### TencentDB Agent Memory

TencentDB Agent Memory is useful as an architecture reference for layered memory, progressive disclosure, and traceability. Its L0 -> L1 -> L2 -> L3 model can be mapped into this project more simply:

- L0 Conversation -> existing Session files and Evidence records.
- L1 Atom -> atomic Memory candidates and confirmed Memory.
- L2 Scenario -> future workflow or analysis-pattern summaries.
- L3 Persona -> future user profile or durable preference layer.

For Phase 2, only the L0 -> L1 part is needed.

The most important lesson is that compression and recall must remain auditable. Upper layers can summarize or guide, but lower layers must preserve evidence and precision.

## Existing Foundation

Phase 1.5 already provides:

- `EvidenceStore` with automatic indexing after `save_session`.
- Typed evidence records for messages, tool calls, analysis results, user corrections, and reports.
- `MemoryStore` lifecycle: candidate, confirmed, rejected, deprecated, promoted.
- Memory edit, delete candidate/rejected, confirm, reject, deprecate, promote-to-knowledge.
- Formal `KnowledgeLibrary`.
- Dynamic retrieval of active knowledge and confirmed memory.
- Management APIs and UI for core memory/knowledge review operations.
- Domain-aware retrieval and Chinese query handling.

Phase 2 should extend this foundation rather than replace it.

## Data Model Changes

### Memory Item Metadata

Memory records should gain additional review metadata:

- `reason`: short explanation of why the candidate was created.
- `source_evidence_ids`: list of evidence IDs that support the candidate.
- `needs_review`: boolean flag for candidates requiring extra attention.
- `review_note`: optional note from the system or user.
- `dedup_key`: stable normalized key used to avoid duplicate candidates.

These fields belong on `memory_items` because they are part of the memory review lifecycle.

### Candidate Shape

Each candidate must be atomic. It should express one fact, preference, correction, or workflow pattern.

Good:

```text
GMV should exclude canceled and refunded orders.
```

Bad:

```text
The user discussed ecommerce metrics, wanted GMV, asked about retention,
and prefers short answers with charts.
```

When one evidence item contains multiple learnable facts, the extractor should create multiple candidates.

## Memory Candidate Extractor

### Location

Add a focused module:

```text
src/data_agent/knowledge/candidates.py
```

Suggested classes:

```python
MemoryCandidateExtractor
CandidateExtractionResult
CandidateDraft
```

### Input

The extractor receives:

- `session_id`
- optional `project_id`
- indexed evidence records
- existing confirmed/candidate memories for deduplication
- active formal knowledge for light conflict detection

### Output

The extractor returns candidate drafts and creation stats:

```python
CandidateDraft(
    text="GMV should exclude canceled and refunded orders.",
    summary="GMV exclusion rule",
    memory_type=MemoryType.DOMAIN_FACT,
    confidence=0.8,
    domain="ecommerce",
    tags=["gmv", "metric_definition"],
    reason="User stated an explicit metric rule.",
    source_evidence_ids=["ev_session_3"],
    needs_review=False,
    dedup_key="domain_fact:ecommerce:gmv:exclude:canceled:refunded",
)
```

### Extraction Rules

Phase 2 should be rule-first. LLM extraction can be added later as an optional mode.

Initial rule families:

1. Explicit memory intent
   - Chinese: "记住", "以后", "下次", "默认", "固定", "总是"
   - English: "remember", "from now on", "next time", "default", "always"
   - Type: preference or workflow pattern.

2. User correction
   - Chinese: "纠正", "更正", "不是", "不对", "应该是", "口径不对"
   - English: "correction", "actually", "not correct", "should be"
   - Type: correction or domain fact.

3. Metric definition
   - Markers: "=", "定义", "口径", "计算", "公式", "exclude", "include", "排除", "包含"
   - Type: domain fact.

4. Report / style preference
   - Markers: "报告", "图表", "先给结论", "详细解释", "简洁", "中文", "保留两位"
   - Type: preference.

5. Workflow pattern
   - Markers: "先...再...", "每次都", "流程", "步骤", "检查后再"
   - Type: workflow pattern.

### Domain Inference

Use a simple deterministic domain inference helper first:

- Existing project name.
- Evidence project ID.
- Keyword mapping.
- Existing knowledge domains.

If no domain is confidently inferred, use `general`.

### Confidence

Confidence should be conservative:

- `0.85`: explicit "remember/default/以后" instruction.
- `0.75`: user correction or clear metric definition.
- `0.65`: workflow pattern.
- `0.55`: weak preference.

Low confidence candidates should still be candidates, not discarded, unless they are empty or duplicate.

## Deduplication

Deduplication should prevent review noise.

Rules:

- Never create a candidate with the same `dedup_key`.
- Do not create a candidate if a confirmed memory with the same `dedup_key` already exists.
- If text similarity is high within the same domain and type, skip or link as duplicate.

Phase 2 can use simple normalized-token Jaccard similarity:

```text
similarity >= 0.85 -> duplicate
similarity >= 0.65 -> needs_review duplicate-like candidate
```

No vector dependency is needed.

## Light Conflict Marking

Phase 2 should mark possible conflicts, not resolve them.

Conflict signals:

- Same metric keyword but different include/exclude markers.
- Same keyword but different numeric threshold.
- Candidate correction contradicts confirmed memory or active knowledge.

Behavior:

- Candidate is created with `needs_review=True`.
- `reason` includes the conflict summary.
- Candidate is not injected into prompts.
- UI shows it as requiring review.

Blocking `ask_user_question` conflict resolution is out of scope for Phase 2.

## Triggering Extraction

Extraction should happen after evidence indexing, not before.

Recommended triggers:

1. After `save_session()` completes and `EvidenceStore.index_session(session_id)` succeeds.
2. Manual management API: `POST /api/management/memory/extract`.
3. Optional CLI/tool command later: `extract_memory_candidates(session_id)`.

Guardrails:

- Extraction should be best-effort.
- Failures must not break session saving.
- Extraction should have a per-session idempotency guard using `dedup_key`.
- Extraction should have a limit per pass, for example `max_candidates_per_session=10`.

## Context Budgeting

Dynamic retrieval must be budget-aware.

### Principles

- Data analysis context has priority over memory context.
- Evidence is not injected by default.
- Candidate memories are never injected.
- Confirmed memory is lower priority than formal knowledge.
- If retrieval is slow or too large, skip or trim retrieval instead of blocking analysis.

### Suggested Defaults

```text
knowledge_limit = 3
memory_limit = 3
evidence_limit = 0 by default
max_knowledge_chars = 1800
max_memory_chars = 720
max_evidence_chars = 0 by default
max_total_retrieval_chars = 2600
recall_timeout_ms = 1500
```

These numbers should be configurable later. For Phase 2, constants are acceptable if tested.

### Budget Metadata

`RetrievedContext.metadata` should record:

- `knowledge_chars`
- `memory_chars`
- `evidence_chars`
- `total_retrieval_chars`
- `trimmed`
- `trim_reason`
- `recall_timeout_ms`

This makes the system debuggable and testable.

### Data Analysis Flow Protection

The agent should favor:

1. User's latest instruction.
2. Dataset schema and data features.
3. Current analysis state and evidence records.
4. Formal knowledge.
5. Confirmed memory.
6. Historical evidence only when explicitly needed.

This priority should be reflected in prompt composition and tests.

## Management Center UI

Phase 2 UI should enhance the existing management center, not create a separate dashboard.

### Memory List

Add filters:

- Candidate
- Needs review
- Confirmed
- Rejected
- Promoted
- Deprecated

Add visible fields:

- Memory type
- Confidence
- Reason
- Source evidence count
- Domain
- Status
- Needs review badge

### Memory Detail Drawer

Show:

- Text
- Summary
- Type
- Domain
- Tags
- Confidence
- Reason
- Review note
- Source evidence IDs
- Source evidence summaries

Actions:

- Edit
- Confirm
- Reject
- Delete candidate/rejected
- Promote confirmed memory to knowledge

### Extraction Controls

Add a lightweight action:

```text
Extract from current session
```

This calls the manual extraction API and refreshes the candidate list.

### What UI Should Not Do Yet

- No graph UI.
- No Persona editor.
- No automatic Skill generation panel.
- No complex conflict-resolution wizard.
- No full conversation replay.

## APIs

Suggested additions:

```text
POST /api/management/memory/extract
GET  /api/management/memory?status=candidate&needs_review=true
GET  /api/management/memory/<id>/sources
PATCH /api/management/memory/<id>
POST /api/management/memory/<id>/confirm
POST /api/management/memory/<id>/reject
DELETE /api/management/memory/<id>
```

Existing endpoints already cover several of these. Phase 2 should add extraction and source lookup, and extend list filters.

## CLI / Agent Tools

Phase 2 can add tools, but keep them narrow:

```text
extract_memory_candidates(session_id="")
list_memory_candidates(needs_review=False)
```

The agent should not get a tool that promotes unreviewed memory to formal knowledge without user confirmation.

## Prompt Safety

Extraction candidates are untrusted until confirmed.

Rules:

- Candidate memories are never injected into `memory_hints`.
- Confirmed memories remain low priority.
- Formal knowledge is still reference material, not instructions.
- Retrieved memory must not override system, developer, or explicit user instructions.

## Observability

Add lightweight logs or metadata for:

- extraction attempted
- evidence records scanned
- candidates created
- candidates skipped as duplicates
- candidates marked needs_review
- retrieval context trimmed

This helps debug false positives and missed candidates.

## Risks and Mitigations

### Risk: Candidate spam

Mitigation:

- Rule-first extraction.
- Per-session candidate limit.
- Dedup keys.
- Only high-signal phrases create candidates.

### Risk: Memory harms analysis quality

Mitigation:

- Candidate memories excluded from retrieval.
- Strict context budget.
- Evidence default off.
- Formal analysis context priority preserved.

### Risk: Wrong business rules become trusted

Mitigation:

- User confirmation required.
- Source evidence visible.
- Conflicts marked as needs_review.
- Promotion to knowledge remains explicit.

### Risk: UI becomes too complex

Mitigation:

- Only enhance Memory view and drawer.
- No separate governance dashboard yet.
- No graph/Persona/Skill UI in Phase 2.

## Acceptance Criteria

1. Saving a session with explicit "remember/default/correction/metric definition" language creates candidate memories.
2. Saving ordinary conversation does not create noisy candidates.
3. Re-saving the same session does not duplicate candidates.
4. Candidate memories include reason and source evidence IDs.
5. Candidate memories do not appear in retrieval prompt context.
6. Confirmed memories continue to appear in retrieval within the budget.
7. Retrieval metadata reports character usage and trimming.
8. Web Memory view shows reason, source, confidence, and needs-review status.
9. Manual extraction can be triggered from Web.
10. All extraction failures are best-effort and do not break session saving.

## Recommended Implementation Order

1. Add memory metadata schema fields and migration-safe defaults.
2. Add `MemoryCandidateExtractor` with deterministic rule extraction.
3. Wire extraction after evidence indexing with best-effort error handling.
4. Add deduplication and candidate limits.
5. Add context budget enforcement in retrieval.
6. Add management APIs for extraction and source evidence lookup.
7. Enhance Memory UI with source/reason/review details.
8. Add integration tests with realistic data-analysis conversations.

## Open Questions

1. Should automatic extraction be enabled by default, or behind a config flag for the first release?
2. Should extraction run on every `save_session`, or only when new evidence includes high-signal markers?
3. Should `needs_review=True` candidates be visually separated from ordinary candidates?
4. Should source evidence previews show full content or only summaries in Phase 2?

My recommendation:

- Enable extraction by default, but only rule-triggered.
- Run after `save_session`, but create nothing if no high-signal marker appears.
- Separate `needs_review` candidates visually.
- Show evidence summaries first; full conversation replay can wait.
