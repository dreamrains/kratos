# Core Contracts and Analysis Copy Design

**Status:** Draft for written review

**Date:** 2026-07-18

## Objective

Create one authoritative analysis-planning contract and a non-destructive data-preparation workflow. User-uploaded files and their raw in-memory snapshots remain immutable. All parsing, cleaning, and correction work happens in versioned analysis copies with auditable lineage.

This is the first implementation slice of the broader trustworthy-analysis improvement program. Context-budget management, statistical-method hardening, computation-bound evidence, and final-answer claim auditing remain separate follow-up slices so this change does not create another cross-cutting partial implementation.

## Product Decisions

1. The project governs data intake, usability, quality discovery, and correction provenance.
2. When several files are uploaded, each file is assessed independently for usability and relevance. The LLM decides later whether an analysis needs one file, several independent analyses, aggregation, or a join.
3. The LLM may choose a multi-dataset operation, but the execution primitive still enforces generic data-operation safety. This design does not add a multi-file planner or relationship engine.
4. The uploaded file and the first raw `DataFrame` snapshot are immutable after registration.
5. Analysis uses a versioned working copy. No cleaning function may overwrite the raw snapshot.
6. Technical parsing may be applied automatically to a working copy only when it is reversible or round-trip validated.
7. A transformation that removes observations, imputes values, caps outliers, changes units, changes metric meaning, changes denominators, or otherwise changes a material conclusion requires confirmation unless a sensitivity comparison proves the material conclusions are invariant and the result is explicitly disclosed.
8. `AnalysisPlan` is the only writable planning object. `AnalysisSpec` becomes a compatibility input during migration and is not an independent source of truth.

## Non-Goals

- Building a deterministic multi-table join or aggregation planner.
- Automatically joining files because they share a column name.
- Expanding statistical methods in this slice.
- Implementing the final-answer claim auditor in this slice.
- Replacing the existing workspace or artifact persistence layer wholesale.
- Mechanically deduplicating harmless local helpers that do not encode business rules.

## Chosen Approach

### 1. Consolidate planning at the boundary

Introduce one normalized `AnalysisPlan` boundary representation. All writers pass through one validator and one state setter. Existing `record_analysis_spec` payloads are normalized into `AnalysisPlan` during a bounded compatibility period, but new runtime code cannot write `state.analysis_spec` directly.

The normalized plan owns:

- goal and question type;
- dataset scope;
- metrics and dimensions;
- method steps;
- evidence requirements;
- assumptions and confirmation requirements;
- analysis-depth and budget intent.

Route selection, required-question detection, confirmation checks, and Workbench projection consume normalized plan/requirement objects rather than reinterpreting raw dictionaries independently.

### 2. Preserve raw data and create analysis copies

Workspace registration distinguishes two dataset roles:

- `raw`: immutable snapshot loaded from a user source;
- `analysis_copy`: versioned mutable copy derived from a raw snapshot or an earlier analysis copy.

Loading a file performs the following sequence:

1. Read the source into a raw `DataFrame`.
2. Compute a stable source fingerprint from source identity, schema, row count, and content hashing already available to the project.
3. Register the raw snapshot without calling `auto_clean` on it.
4. Scan schema, quality, and candidate type interpretations against the raw snapshot.
5. Create an analysis copy.
6. Apply only safe parsing operations to the analysis copy.
7. Record all proposed and applied operations in a transformation record.
8. Expose the analysis copy as the default dataset for analysis while retaining explicit access to the raw snapshot for comparison and audit.

The original uploaded file is never written by this flow.

### 3. Classify transformations by decision risk

Every transformation proposal has one of three policies:

#### `auto_safe`

Allowed on an analysis copy without interruption when validation shows no information loss. Examples include adding a parsed companion field, adding a quality flag, or converting a value with successful round-trip validation while retaining the original field.

#### `compare_then_continue`

Applied to a candidate copy, followed by deterministic before/after comparison of row count, missingness, distribution, and identified key metrics. The agent may continue without interruption only when material findings are invariant. The final answer must disclose that a candidate correction was used.

#### `confirmation_required`

Required for row deletion, deduplication, imputation, outlier removal/capping, unit conversion, category remapping, denominator changes, grain changes, or any candidate whose sensitivity comparison changes a material finding.

### 4. Record lineage as a first-class contract

Each analysis copy stores a `TransformationRecord` with:

```text
id
parent_dataset_id
raw_dataset_id
source_fingerprint
derived_dataset_id
version
operations
affected_columns
affected_row_count
before_after_metrics
information_loss
decision_policy
confirmation_status
created_at
```

The record is produced by transformation code, not authored free-form by the LLM. User-facing summaries are projections of this record.

## Canonical Ownership

The implementation must preserve one owner for each business rule:

| Responsibility | Authoritative owner |
|---|---|
| Plan normalization and validation | `src/data_agent/agent/analysis_plan_contracts.py` |
| Plan persistence in session state | `src/data_agent/agent/analysis_state.py` |
| Plan tool entry point and legacy adapter | `src/data_agent/tools/analysis_flow.py` |
| Raw/copy dataset identity and metadata | `src/data_agent/session/workspace.py` |
| Transformation policy and lineage | `src/data_agent/tools/data_clean.py` plus a focused contract module only if the existing file cannot hold the typed record cleanly |
| File load orchestration | `src/data_agent/tools/data_io.py` |

No other module may create a second plan schema or infer a second transformation policy. Presentation modules may project these contracts but cannot rewrite their status.

## Compatibility and Migration

1. Existing saved sessions containing only `analysis_spec` load it through the plan normalizer.
2. During migration, reading `state.analysis_spec` returns the normalized plan for compatibility, but only `set_analysis_plan` persists new state.
3. `record_analysis_spec` remains callable as a deprecated adapter and returns the canonical `analysis_plan_id`.
4. Tests and runtime callers migrate to `analysis_plan` before the compatibility property is removed.
5. Existing dataset names continue to resolve to the analysis-ready copy so normal user prompts do not need to change.
6. Raw snapshots receive an internal stable identifier and remain available through explicit audit/comparison APIs rather than cluttering the default dataset list.

## Failure Handling

- If raw registration fails, loading fails without registering a partial dataset.
- If analysis-copy creation fails, the raw snapshot remains registered and the result reports that analysis preparation is incomplete.
- If an automatic parse is not round-trip safe, it becomes a proposal instead of mutating the copy.
- If transformation recording fails, the transformed copy is not promoted as analysis-ready.
- If confirmation is required, analysis may continue on the unmodified analysis copy but cannot silently use the proposed correction.
- A correction never mutates its parent; retry creates or replaces only the unpromoted candidate version.

## Testing Strategy

Testing follows end-to-end contracts rather than isolated mocks.

Required regression coverage:

1. `load_data` preserves a raw value that current `auto_clean` would convert.
2. The default analysis dataset is a distinct object from the raw snapshot.
3. Safe parsing records lineage and retains the original value or field.
4. Destructive cleaning creates a new version and leaves both raw and prior analysis copies unchanged.
5. A material operation is blocked or held as a candidate until confirmation.
6. A failed transformation does not promote a partial analysis-ready dataset.
7. Old `record_analysis_spec` input and new `record_analysis_plan` input produce the same canonical stored object.
8. Real load-to-plan integration preserves evidence requirements through all consumers.
9. Saved legacy sessions migrate without losing the active goal or plan identifier.

Focused tests should be added next to the existing workspace, loading, cleaning, analysis-state, and trust-contract suites. The full suite remains the final regression gate.

## Delivery Sequence

1. Add failing characterization and desired-behavior tests.
2. Consolidate plan normalization and state writes while keeping the compatibility adapter.
3. Add raw/analysis-copy metadata and immutable registration behavior.
4. Change `load_data` to register raw first and prepare a copy second.
5. Move cleaning operations to copy-on-write and emit deterministic transformation records.
6. Add confirmation/sensitivity handling for material transformations.
7. Migrate callers and remove duplicate writable paths.
8. Run focused and full regression suites, then review the remaining compatibility surface before scheduling its removal.

## Acceptance Criteria

- User-uploaded files and raw snapshots are never modified by loading or cleaning.
- The normal analysis path receives a prepared copy without requiring confirmation for safe, reversible parsing.
- Every applied correction can be traced to a parent dataset and deterministic transformation record.
- Material corrections cannot silently affect analysis conclusions.
- `AnalysisPlan` is the sole writable planning contract.
- Load-to-plan integration does not lose evidence requirements.
- No new multi-file planning subsystem is introduced.
- Existing sessions and normal dataset references continue to work through documented compatibility behavior.
