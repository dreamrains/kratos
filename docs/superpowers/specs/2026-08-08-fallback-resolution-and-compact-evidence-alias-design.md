# Fallback Resolution and Compact Evidence Alias Design

**Status:** Implemented and product-validated

**Date:** 2026-08-08

**Branch:** `codex/analysis-reliability`

**Implementation baseline:** `4cab45238af0547cc13b55908b6683913a9ee3fc`

**Current release-source digest:**
`sha256:de69f2f7ed103f8e812720b6393e0efcb348445f47c769cdb2780d769b0e4b20`

**Amends:**

- `docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md`
- `docs/superpowers/plans/2026-07-28-web-sse-and-live-release-validation.md`

## 1. Decision summary

The 2026-08-08 live-provider Gate F run exposed two execution-control defects
and one synthesis usability defect. The repair is intentionally narrower than
a new assurance architecture:

1. A fallback result becomes pending only after `run_python` succeeds. A
   failed fallback call does not create a result that must be resolved.
2. While a successful fallback result is pending, the next model prompt names
   the legal resolution actions before another analysis call can be attempted.
   A failed resolution action does not clear the pending state.
3. Synthesis uses short, turn-local aliases for exact evidence measurement
   identities. The server expands only aliases that were emitted in the exact
   bounded catalog for that synthesis turn.
4. Gate F counts repeated failures by canonical tool-call identity, not merely
   by tool name and error category, and separately rejects unresolved-fallback
   cascades.

This design does not weaken the final audit. It does not infer evidence from
similar wording or equal numeric values. Unknown, stale, or malformed aliases
remain unsupported and are downgraded by the existing tiered publisher.

## 2. Evidence from the failed live gate

The live receipt at
`C:\Users\duguy\AppData\Local\Temp\data-agent-live-gate-157edcdf-20260808-1\analysis_live_provider_gate.v1.json`
is authoritative for this diagnosis:

- run 1 published a complete Chinese answer after 12 tool outcomes;
- run 2 published a complete Chinese answer after 21 tool outcomes;
- run 3 published a complete Chinese answer after 38 tool outcomes but failed
  Gate F with `repeated_tool_failure_exceeded`;
- all three runs streamed progress before the final answer and persisted the
  same text that was streamed;
- all three runs ended with a blocked deterministic audit and tiered
  exploratory publication;
- the dominant audit failures were `missing_evidence_identity` and
  `evidence_check_failed`.

Conversation-level reconstruction showed the same fallback pattern in all
three runs:

```text
run_python succeeds
  -> pending_fallback_resolution becomes true
  -> the next prompt does not disclose that state
  -> the model calls another analysis tool
  -> execution control rejects the call
  -> the model records evidence or a limitation only after seeing the error
```

The state transition is also wrong on failure: `record_tool_call` currently
sets `pending_fallback_resolution` before the result is known. A failed
`run_python` therefore blocks later exploration even though no fallback result
exists. Conversely, a resolution tool currently clears the pending flag before
its success is known.

The synthesis prompt has a related usability problem. It tells the model to
use the exact marker shown in the catalog, but the catalog provides the full
EvidenceRecord ID and measurement key as separate long fields instead of
showing a ready-to-copy marker. The provider omitted every internal marker in
all three final drafts.

## 3. Goals and non-goals

### 3.1 Goals

- Make fallback state reflect successful results, not attempted calls.
- Tell the model how to resolve a pending fallback before it chooses more
  tools.
- Preserve an explicit, exact evidence choice while making the marker short
  enough for reliable synthesis.
- Detect genuine identical-call retry loops without merging different calls.
- Make the live gate prove that the fixed scenario produces at least one
  supported material claim, while still allowing other claims to be published
  as exploratory.
- Keep receipts privacy-safe and bound to the release-source digest.

### 3.2 Non-goals

- No semantic or fuzzy claim-to-evidence matching.
- No automatic promotion based on an equal value, unit, direction, or metric
  label.
- No relaxation of plan, dataset-version, computation, measurement, or
  verification-level checks.
- No requirement that every sentence in a comprehensive answer be supported;
  mixed supported and exploratory publication remains valid.
- No new unbounded retry, analysis-continuation, or evidence-recording loop.
- No reuse of the failed Gate F receipt or the stale Gate E receipt.

## 4. Execution-control design

### 4.1 Success-owned fallback state

`TurnExecutionState.record_tool_call` continues to count `run_python` against
the fallback and tool budgets, but it no longer changes
`pending_fallback_resolution`.

`record_tool_success` receives the successful tool name:

- successful `run_python` sets `pending_fallback_resolution = True`;
- a successful tool in the existing fallback-resolution allowlist clears it;
- unrelated successful tools leave it unchanged;
- a failed `run_python` or failed resolution tool leaves it unchanged.

The streaming, synchronous, and parallel result paths must all pass the tool
name to the same state transition. There must not be a second fallback state
authority in `AgentLoop`.

### 4.2 Proactive resolution hint

When `pending_fallback_resolution` is true, `prompt_hint()` adds a
highest-priority instruction before ordinary budget guidance:

```text
The previous run_python result is pending resolution. Before any additional
analysis tool, resolve it with exactly one allowed evidence, limitation, task,
or user-confirmation action. Do not call run_python again yet.
```

The prompt may name the existing allowlisted tool names, but it must not expose
raw fallback output. The runtime enforcement in `ensure_can_call` remains the
authority; the hint prevents predictable errors but cannot override the gate.

## 5. Compact evidence alias design

### 5.1 Alias catalog

The bounded synthesis catalog assigns deterministic aliases only to
measurement entries that are actually emitted after current-plan filtering,
deduplication, record limits, and character limits. Example:

```text
- marker=[[evidence:ae01#am01]] | metric_label=Revenue | value=... |
  claim_key=analysis.correlation | verification_level=structured_checked
```

Aliases are ordered by the same canonical `(step_order, evidence_id,
measurement_order)` sequence used by the bounded catalog. They are scoped to
one synthesis turn and are not persisted as new evidence identities.

The catalog builder returns both:

- the compact text shown to the model;
- an immutable alias map from `(alias_evidence_id, alias_measurement_key)` to
  the full `(evidence_id, measurement_key)` pair.

Only entries present in the final bounded text may appear in the alias map.

### 5.2 Exact expansion before audit

`AgentLoop` retains the alias map used for the current synthesis prompt. Before
calling `audit_final_answer_draft`, it expands exact alias markers to the full
existing marker form:

```text
[[evidence:ae01#am01]]
  -> [[evidence:<full EvidenceRecord ID>#<full measurement_key>]]
```

Expansion is lexical and exact. It does not inspect claim text, values,
metrics, units, or directions. The existing final audit then performs all
semantic, plan, step, requirement, dataset-version, computation, value, unit,
scope, and verification checks against the full identity.

An alias that was not in the current prompt map is not expanded. The existing
audit treats it as an unknown evidence identity, and marker stripping prevents
it from reaching the user. A prior-turn alias cannot authorize a later turn.

The alias map is reset with the rest of the turn tracking state and refreshed
whenever synthesis policy is rebuilt after new evidence projection.

### 5.3 Publication behavior

The existing tiered behavior remains authoritative:

- supported claims publish normally;
- claims with missing or invalid aliases publish with the existing exploratory
  limitation when safe;
- unsupported claims are removed or explicitly downgraded according to the
  current deterministic audit action;
- the whole answer is not replaced by a generic English warning.

## 6. Gate F identity and quality semantics

### 6.1 Exact repeated-failure identity

`_session_tool_outcomes` reconstructs a canonical arguments hash from each
assistant tool call. The repeated-failure key becomes:

```text
(tool_name, error_category, canonical_arguments_hash)
```

This matches the execution controller's existing same-call identity. The live
receipt continues to store only `repeated_failure_max`; it does not store raw
arguments, code, prompts, or tool output.

### 6.2 Separate fallback-cascade signal

The live runner records a bounded count of failures caused by unresolved
fallback state. Gate F requires this count to be zero. This prevents the exact
problem found in all three live runs from disappearing merely because each
blocked call had different arguments.

### 6.3 Supported-claim proof

For the fixed live scenario, each run must publish at least one material claim
whose publication action is `verified`. The receipt records the bounded count
as `verified_material_claims`. Other claims may remain `exploratory` or
`unsupported`. This proves that compact aliases are usable without turning the
soft publication policy back into a whole-answer hard gate.

If the scenario produces no eligible measurement catalog, the run fails with
an explicit fixture or projection reason; it does not waive the supported-claim
requirement.

## 7. Error handling and safety invariants

- A failed fallback call never creates pending work.
- A failed resolution call never clears pending work.
- Prompt guidance never substitutes for runtime enforcement.
- Alias expansion accepts only the exact map used for the current prompt.
- Alias ordinals have no meaning outside their turn.
- Unknown aliases fail closed at claim level, not whole-answer level.
- Full EvidenceRecord and measurement identities remain server-owned.
- The live receipt contains counts, statuses, reason codes, and hashes only.
- Any implementation change invalidates all prior Gate E and Gate F receipts.

## 8. Test design

### 8.1 Execution-control RED tests

- attempted and failed `run_python` leaves no pending result;
- successful `run_python` creates a pending result;
- the pending prompt hint names the resolution requirement before budget hints;
- a failed resolution tool preserves pending state;
- a successful resolution tool clears pending state;
- streaming, synchronous, and parallel execution paths pass the successful
  tool name to the state transition.

### 8.2 Alias RED tests

- the bounded catalog emits deterministic ready-to-copy alias markers;
- the alias map contains exactly the entries that fit in the bounded catalog;
- exact aliases expand to the intended full identities before audit;
- aliases cannot cross turns or plans;
- unknown, malformed, and stale aliases do not bind;
- equal numbers for different metrics remain unable to cross-bind;
- full and alias markers are both removed from public Markdown;
- one supported claim plus exploratory claims renders as a complete mixed-tier
  answer.

### 8.3 Gate F RED tests

- same tool and error category with different canonical arguments count as
  distinct failures;
- the exact same call failing three times produces
  `repeated_tool_failure_exceeded`;
- any unresolved-fallback blocked call fails the run;
- a run with `verified_material_claims == 0` fails the fixed live scenario;
- FAIL and BLOCKED receipts still obey the same privacy whitelist as PASS.

### 8.4 Release verification

After focused and full deterministic tests pass:

1. recompute the release-source digest;
2. regenerate actual Browser Gate E for that digest;
3. obtain explicit authorization for exactly three new real-provider calls;
4. regenerate Gate F for the same digest;
5. run the product aggregator and require A-F PASS;
6. perform fresh specification-compliance and code-quality reviews;
7. update completion documentation only after the reviews and product gate
   pass.

## 9. Rejected alternatives

### 9.1 Gate-only repair

Changing only the repeated-failure grouping could make the failed run pass but
would preserve the fallback cascade and all-exploratory audit outcome. That is
a false-green repair and is rejected.

### 9.2 Semantic automatic binding

Binding markerless claims by similar text, equal values, labels, or a unique
heuristic match can attach revenue evidence to profit or another same-valued
metric. It conflicts with the existing measurement-identity safety proof and
is rejected.

### 9.3 Full-answer strict blocking

Requiring every claim to verify would recreate the original empty or stripped
answer problem. The live gate requires a nonzero supported core, not universal
support, and preserves mixed-tier publication.

## 10. Completion criteria

This amendment is implemented only when:

1. fallback pending state follows success and resolution outcomes exactly;
2. no deterministic test path produces an avoidable unresolved-fallback
   cascade;
3. the alias catalog and audit expansion preserve exact measurement identity;
4. the fixed live scenario produces `verified_material_claims >= 1` in each of
   three fresh runs;
5. the three runs have zero unresolved-fallback blocked calls and no identical
   failure more than twice;
6. Gate E and Gate F receipts match the same final release-source digest;
7. the product aggregator reports A-F PASS;
8. final reviews contain no unresolved high- or medium-severity finding.

Until all eight conditions hold, Task 12 remains on HOLD.

## 11. Validation record

The uncommitted implementation at baseline commit
`4cab45238af0547cc13b55908b6683913a9ee3fc` satisfied all eight completion
conditions on 2026-08-09 for release-source digest
`sha256:7ff6b3aba6a9b8c80ab22a7a318b38f26450e8fa393bade03bf57afc2097143c`:

- the full suite reported `2965 passed, 11 skipped`, and the direct tool
  runner reported `108 PASS, 0 FAIL, 2 SKIP`;
- actual in-app Browser Gate E passed all 10 required observations, including
  the native interruption confirmation path;
- exactly three fresh Gate F sessions, `live_1` through `live_3`, passed with
  7, 11, and 14 verified material claims, repeated-failure maxima of 1, and
  zero unresolved-fallback blocked calls;
- the tiered publisher retained findings, recommendations, and limitations in
  all three runs while unsupported raw claims remained blocked or downgraded;
- the product aggregator reported Gates A-F `PASS` with
  `product_release_passed=true`; and
- the final specification-compliance and code-quality review found no
  unresolved high- or medium-severity issue.

Receipts and report:

- Gate E: `C:\Users\duguy\AppData\Local\Temp\data-agent-browser-gate-7ff6b3-20260809-05\analysis_browser_gate.v1.json`
- Gate F: `C:\Users\duguy\AppData\Local\Temp\data-agent-live-gate-7ff6b3-20260809-01\analysis_live_provider_gate.v1.json`
- Product A-F: `C:\Users\duguy\AppData\Local\Temp\data-agent-product-gates-7ff6b3-20260809-01\analysis_reliability_release.v1.json`

Task 12 is therefore implementation- and product-gate complete in this
worktree. Commit, merge, and push remain separate user-authorized actions.

## 12. Post-merge source-identity portability repair

After commit `a3fd32c46015082d283ed0871778e6739fe257a0` was fast-forwarded to
`main`, the same Git commit produced different release-source digests across
the pre-commit worktree, the Windows `core.autocrlf=true` main checkout, and
the canonical Git blobs. All 150 differing release files were byte-identical
after line-ending normalization. The original digest therefore represented a
checkout encoding, not a portable source identity, and the prior Gate E/F
receipts became formally stale on merged `main`.

The minimal repair hashes each selected current file through Git's configured
clean filters and incorporates its blob identity. It continues to include
dirty and untracked release files, preserves binary byte sensitivity, and does
not add a gate or relax stale-receipt validation. The repair is frozen at
`sha256:de69f2f7ed103f8e812720b6393e0efcb348445f47c769cdb2780d769b0e4b20`.
The full suite reports `2967 passed, 11 skipped`; the direct tool runner reports
`108 PASS, 0 FAIL, 2 SKIP`; deterministic Gates A-D pass; and a fresh actual
in-app Browser Gate E passes all 10 observations. Gate E receipt:
`C:\Users\duguy\AppData\Local\Temp\data-agent-browser-gate-de69f2-20260809-01\analysis_browser_gate.v1.json`.
A fresh same-digest Gate F ran exactly three real-provider sessions and passed.
Gate F receipt:
`C:\Users\duguy\AppData\Local\Temp\data-agent-live-gate-de69f2-20260809-01\analysis_live_provider_gate.v1.json`
(`sha256:9b1dd013f7d52f676d147ac3517bd457dd3aba74fe8e08ed2934db87209514a0`).
The product A-F aggregator then passed all six gates. Product receipt:
`C:\Users\duguy\AppData\Local\Temp\data-agent-product-gates-de69f2-20260809-01\analysis_reliability_release.v1.json`
(`sha256:194175b737288be51c610ab6c20cca560fd6405872f31100d94a9eee7baadaee`).
Task 12 is therefore product-gate complete for the portability-repaired source.
