# Analysis Execution and Publication Reliability Design

**Status:** Implemented and product-validated

**Date:** 2026-07-27

**Baseline:** `main` at `a44f859`

## 1. Objective

Restore the product's ability to complete useful, trustworthy data analysis from
uploaded files.

The change must close four connected but independently testable failure chains:

1. tools must receive valid arguments and execute reliably;
2. the selected analysis method must be sufficient for the user's question;
3. successful computations must become usable evidence without depending on the
   model remembering a separate bookkeeping call;
4. users must receive live, safe progress and a complete audited answer instead
   of an unaudited dump or an empty fallback.

The target is not to make every answer confident. The target is to make every
answer operationally complete and to make its claim strength match the evidence.

## 2. Evidence and confirmed baseline

### 2.1 Primary comparison

The same prompt and workbook produced materially different executions:

| Dimension | `fe064bcfae31` | `2af964cc1ae7` |
|---|---:|---:|
| Tool calls | 29 | 6 |
| Unique tools | 13 | 6 |
| Tool errors | 4 | 1 |
| Evidence records | 2 legacy records | 0 |
| Computation refs | legacy state | 6 current refs |
| Final-answer size | about 2,199 characters | about 435 published characters |
| Coverage | quality, correlation, attribution, time, charts, evidence | profile, correlation, failed regression, attribution |

The older answer was broader but not a correctness reference. It made
high-confidence driver and elasticity-style claims without adequate inference,
stability, or causal support. The newer answer was shallower, still overclaimed
internally, then lost most of its content at publication.

### 2.2 Confirmed systemic execution failures

- `ToolRegistry` currently exposes `regression_analysis.cv_folds` as a string.
  The problem session passed `"0"` and the tool failed while comparing it with
  an integer.
- In a focused current-code diagnostic, `run_python("import pandas as pd")`
  still returns `ImportError: __import__ not found`.
- At least five of six sampled real analysis sessions contain the same sandbox
  import failure. Several then contain `NoneType` follow-on failures.
- Session `1fa21df491e9` terminated after a Windows GBK
  `UnicodeEncodeError` while emitting text containing an emoji variation
  selector. Direct current-host checks confirm that CP936/GBK still cannot
  encode the relevant Unicode code points. The supported CLI, web, and REPL
  entry points already reconfigure standard streams to UTF-8, so this is a
  current host/sink compatibility hazard rather than proof that every supported
  launcher still fails.
- Repeated real sessions show opaque-plan and argument drift, including
  `record_analysis_plan` missing `method_plan` and
  `visualization_strategy`, `task_create(title=...)`, string booleans, and
  string integers.
- `create_chart` now validates explicit x/y/color columns, but an explicitly
  unknown dataset may still fall back to a different workspace dataset.

### 2.3 Confirmed assurance integration failures

- Every sampled conversation has zero internal `[[evidence:...]]` citations.
- Several older sessions contain legacy evidence, but it is unbound and cannot
  authorize new high-confidence claims.
- The problem session has six server-owned computation refs but no
  `evidence_record.v2`.
- `missing_evidence_identity` triggers neither useful automatic evidence
  projection nor a computation repair when evidence is empty.
- the final fallback retains passed sentence fragments and adds a generic
  English warning, so headings and table shells can survive without the
  analysis they describe.
- all analysis-candidate text is buffered. Tool events still exist, but safe
  analysis progress is not presented as a useful live narrative.

### 2.4 Causality decision

The recent publish gate did not directly suppress tool execution:

- the core analysis prompt did not become more conservative after gate launch;
- `block_analysis` is not used as a mid-turn tool-call interrupt;
- the quality guard points toward more analysis, although its completion test
  is too weak.

The gate directly caused the empty publication and non-live experience. The
analysis breadth and quality loss came primarily from tool contracts, routing,
method capability, and premature completion. Assurance amplified those defects
because incomplete work could no longer be published as confident analysis.

## 3. Product decisions

1. Remove response-level hard blocking for partially unsupported analyses.
2. Retain claim-level hard blocking for fabricated, contradictory, stale,
   cross-scope, or causally invalid claims.
3. Preserve the full answer structure. A blocked claim becomes an explicit
   diagnostic gap; it is not silently deleted.
4. Successful structured tools automatically project eligible evidence.
   Arbitrary or failed tool output never becomes trusted evidence automatically.
5. Every directed analytical turn receives a server-owned canonical execution
   envelope before its first substantive tool call. Evidence identity cannot
   depend on the model voluntarily recording a plan.
6. Final analytical findings remain buffered until audit. Server-generated
   progress, method narration, and tool-stage events stream live.
7. Process narration describes method and state only. It never exposes raw
   reasoning, unaudited values, rankings, significance, or causal findings.
8. Analysis completion is a bounded terminal-state decision, not a retry loop.
   Missing evidence projection or answer wording cannot trigger recomputation.
9. `analysis_requirement.v1`, `evidence_record.v2`, and
   `final_answer_audit.v1` remain the sole authorities. This work extends their
   runtime integration and does not create parallel contracts.
10. Descriptive analysis does not require universal significance testing.
    "Significant", inferential, and causal requests receive method-specific
    requirements.
11. A lower execution or context budget may reduce breadth, but it may not
    strengthen the claim class.
12. Production rollout may fail safer through tiered or strict publication,
    but it may not disable minimum deterministic assurance checks.

## 4. Architecture

```text
User question and uploaded data
              |
              v
Intent + server-owned canonical execution envelope
              |
              v
Typed tool contract -> tool execution -> computation_ref.v1
        |                    |                 |
        |                    | failure         | eligible structured result
        |                    v                 v
        |             bounded recovery   evidence_record.v2
        |                                      |
        +------------ completion evaluation ---+
                                               |
                                               v
                                bounded evidence catalog
                                               |
                                               v
                                      synthesis draft
                                               |
                                               v
                                   claim-level final audit
                                  /           |           \
                           verified      exploratory     unsupported
                              |               |               |
                              +------- complete public answer-+
```

The runtime is divided into four layers. Each layer has one owner and can be
tested without invoking the others.

### 4.1 Layer A: execution reliability

#### Typed registry schemas

`src/data_agent/tools/registry.py` remains the owner of LLM-visible tool
schemas and runtime argument validation.

The registry must:

- resolve postponed annotations with `typing.get_type_hints`;
- support primitives, `Optional`/union, lists, dictionaries, and literal/enum
  values used by current tools;
- distinguish required parameters from defaults;
- reject unknown parameters unless an explicit compatibility alias exists;
- perform only lossless primitive normalization, such as `"0"` to integer `0`
  or `"false"` to Boolean `False`;
- return a structured `invalid_tool_arguments` error when normalization would
  be ambiguous;
- test every registered native tool schema for compatibility with its Python
  signature.

Known compatibility aliases may be normalized at the registry boundary, for
example `task_create.title -> subject` when `subject` is absent. Conflicting
canonical and alias values must be rejected.

Opaque JSON-string tools must not rely on a short natural-language description
to communicate a large nested contract. `record_analysis_plan` will expose the
canonical plan as a real object schema to the model. Its existing string input
remains a compatibility-only reader and does not become a second plan
authority.

#### Sandbox execution contract

`src/data_agent/tools/sandbox.py` and `src/data_agent/tools/_utils.py` remain
the owners of custom Python execution.

The supported observable contract is:

- `pd`, `np`, `math`, `statistics`, `json`, and `stats` (`scipy.stats`) are
  available under fixed names;
- an AST-based normalizer accepts redundant imports from the preloaded module
  allowlist: root modules `pandas`, `numpy`, `math`, `statistics`, and `json`,
  plus the explicitly allowed `scipy.stats`;
- ordinary aliases and public symbol imports bind to the preloaded objects.
  Supported shapes include `import pandas`, `import pandas as frame_lib`,
  `from pandas import DataFrame`, `import numpy`, and
  `from scipy import stats`; no runtime `__import__` is executed;
- unknown modules, unapproved dotted submodules, star imports, and private or
  dunder symbols are rejected before execution with
  `sandbox_import_not_allowed`;
- network, file, process, dynamic import, reflection, and arbitrary package
  access remain forbidden;
- `get_dataset(name)` returns a DataFrame or raises a structured
  `dataset_not_found` error containing allowed dataset names; it never returns
  `None`;
- an execution error returns its error type, dataset reads, failed operation,
  and safe alternatives;
- repeated identical sandbox failures within a turn are not retried.

This is not a general secure Python environment. It is a bounded analytical
fallback. Structured tools remain preferred.

#### Failure propagation and recovery

Tool failures must be first-class execution outcomes. A failed tool cannot
silently satisfy a plan step or feed a later step.

For a critical step:

1. normalize or correct the same tool call once if the error is recoverable;
2. use a declared fallback capability once if it can satisfy the same
   requirement;
3. otherwise mark the requirement unmet and continue to a diagnostic answer.

The model must not repeatedly rediscover the same import, schema, or missing
dataset error. Recovery state is persisted in turn diagnostics.

#### Windows Unicode boundary

CLI and web entry points use one shared UTF-8 stream configuration helper.
Background runner, logging, and console status paths must not propagate an
encoding error into the analysis turn.

User-visible browser/JSON text preserves Unicode. Console-only sinks use a
replacement-safe policy when the host stream cannot represent a character,
including when stream reconfiguration is unavailable, bypassed, or performed
after a background/logging sink has already been captured. Regression coverage
includes emoji, variation selectors, Chinese punctuation, every supported
launcher, and a simulated CP936/GBK output stream.

#### Chart source identity

When `create_chart(data=...)` receives a dataset name, that exact dataset must
exist. It may not fall back to another dataset.

Automatic default selection is allowed only when `data` is omitted and there
is exactly one eligible dataset. Multiple eligible datasets produce a
structured ambiguity error. Existing column and semantic chart validation
remain authoritative.

### 4.2 Layer B: method routing and completion

#### Factor/significance route

`src/data_agent/agent/intent.py` and
`src/data_agent/agent/method_playbooks.py` add a dedicated
factor-relationship route for requests such as:

- 影响因素;
- 显著影响;
- 驱动因素;
- 哪些变量与目标相关;
- factors associated with a target.

This route is not the existing period-change driver decomposition route.

For a request containing "显著", the plan distinguishes:

- exploratory association;
- inferential association or coefficient significance;
- predictive importance;
- causal effect.

The answer may use only the claim class supported by the executed method.
Feature importance cannot become coefficient significance or causal impact.

The standard plan evaluates, when applicable:

1. dataset grain, target definition, candidate features, time structure, and
   missingness;
2. effective sample structure and univariate association;
3. an appropriate inferential or predictive multivariable method;
4. multiplicity, collinearity, stability/validation, and time dependence;
5. effect size or predictive contribution;
6. limitations and alternative explanations.

If the data cannot support inferential significance, the route still returns
useful exploratory associations with an explicit downgrade.

#### Capability truthfulness

Tool capability metadata may list an evidence field only if the structured
output actually contains and validates that field.

Examples:

- correlation cannot advertise `p_value` until it emits per-pair effective N
  and a validated p-value;
- attribution cannot advertise `limitations` unless the output contains
  method-appropriate limitations;
- predictive feature importance cannot advertise inferential significance.

A registry-wide contract test compares declared evidence fields with
representative successful output.

#### Completion evaluator

The existing canonical requirement evaluator is extended; no new readiness
authority is introduced.

Before synthesis, completion checks execution obligations separately from
publication obligations.

Execution obligations are:

- required plan steps attempted;
- critical tools succeeded or have explicit unresolved diagnostics;
- required structured fields are present;
- the requested claim class has not exceeded the method.

Publication obligations are:

- eligible evidence has been projected for completed claims;
- required limitations and downgrade semantics can be rendered;
- unsupported claim classes are excluded from synthesis.

A publication-obligation failure never returns execution to the tool-running
state. When a successful traceable computation exists but projection or
presentation remains incomplete, completion becomes `complete_with_limits` and
the publication layer applies an exploratory or unsupported claim action. When
no successful computation exists, the existing data, tool, or budget terminal
state remains authoritative.

The evaluator returns one of five terminal states:

| State | Meaning | Next action |
|---|---|---|
| `complete` | Requested analysis obligations are satisfied | Synthesize at the supported claim class |
| `complete_with_limits` | Useful computation exists, but the requested class is not attainable | Synthesize exploratory findings with specific limitations |
| `blocked_by_data` | Required fields, grain, sample structure, or design are absent | Publish completed work and an exact data gap |
| `blocked_by_tool` | A critical method and its declared fallback both failed | Publish completed work and the failed-method diagnostic |
| `budget_limited` | Reserved execution budget is exhausted | Synthesize the best supported partial answer |

The current "one substantive tool is enough" guard is replaced by this
requirement-based result, but the evaluator must converge:

- each critical requirement receives at most one corrected retry and one
  declared fallback as defined in Layer A;
- the quality guard may request at most one additional analysis continuation
  for the entire turn;
- that continuation is allowed only when a missing hard computation is still
  recoverable and the synthesis/audit reserve remains intact;
- missing evidence projection, missing evidence markers, or missing limitation
  wording never triggers a repeated computation;
- no tool may be called solely to populate evidence bookkeeping;
- once the highest attainable claim class is known, the evaluator returns a
  terminal state and synthesis begins.

Budget exhaustion therefore produces an incomplete-but-usable answer, not
silent early completion or an evidence-completion loop.

### 4.3 Layer C: evidence and publication

#### Canonical execution envelope

Before the first substantive analytical tool call in every directed or
comprehensive analysis turn, the server materializes a lightweight executable
plan through the existing canonical `AnalysisPlan` writer and
`analysis_requirement.v1` compiler. This is a default instance of the existing
authority, not a parallel ad-hoc plan type.

The envelope contains:

- session and turn identity;
- canonical plan ID and version;
- current step ID;
- active dataset names, fingerprints, and versions;
- selected method route and maximum requested claim class;
- canonical claim keys and requirement IDs for each executable step.

An explicit `record_analysis_plan` call may provide a richer plan before
substantive execution, but the absence of that call cannot leave new
computations with an empty plan or step identity. The runtime scheduler binds a
tool call to a step only when the current step or a single compatible pending
step matches the tool capability. Ambiguous calls remain computation refs and
produce a structured binding diagnostic; they are not guessed into trusted
evidence.

If envelope creation fails, the turn may still run bounded diagnostics.
Resulting computations remain traceable computation refs, the terminal state
cannot be `complete`, and the public answer is exploratory or diagnostic. The
runtime never invents plan, requirement, dataset, or claim identity after the
fact.

#### Automatic evidence projection

The existing tool-output persistence path continues to create
`computation_ref.v1`. After a successful tool call, the server may project an
`evidence_record.v2` only when all of the following hold:

- the computation is successful;
- the call is bound through the canonical execution envelope to the current
  session, turn, plan, step, and active dataset version;
- the tool has a truthful structured capability contract;
- required evidence fields are present and validate;
- the current step has a canonical claim key and matching requirement IDs.

The server owns provenance, verification level, computation IDs, dataset
versions, and structured measurements. The projected record contains a
claim-neutral canonical result summary and an allowed claim class.

Free-form `run_python`, unstructured text, failed tools, and computations with
an empty plan step remain computation refs only. They may support a manually
bound low-level evidence record after validation, but they are never
automatically upgraded.

`record_evidence_record` remains for bounded semantic claims and old-session
compatibility. It is no longer required for every ordinary structured result.

#### Evidence catalog injection

Before synthesis, the server injects a bounded catalog containing:

- evidence ID and claim key;
- dataset and active version;
- result summary and structured measurements;
- verification level;
- allowed and forbidden claim semantics;
- required limitations.

The prompt cache is invalidated whenever the catalog changes. Internal evidence
markers remain synthesis-only and are stripped before publication.

#### Three publication levels

| Level | Conditions | Public behavior |
|---|---|---|
| Verified | Exact current evidence; values, direction, units, scope, method, and blocking requirements match | Publish normally |
| Exploratory | Bound computation exists, but independent recomputation, stability, assumptions, or inferential support is incomplete | Publish the finding with downgraded semantics and a specific limitation |
| Unsupported | Missing/failed computation, value or scope mismatch, stale/cross-plan evidence, invalid grain, or unsupported causal/inferential semantics | Replace the assertion with an explicit diagnostic gap |

"未经独立校验" is used only when a traceable or structured computation really
exists but has not been independently recomputed. It is not a disclaimer that
can legalize a fabricated number.

#### Complete-answer publication

The final gate acts on claims, not on the whole response.

1. Audit the first synthesis draft.
2. Allow one synthesis-only revision using machine-readable claim actions.
3. Re-audit.
4. If unsupported claims remain, render a deterministic partial answer with:
   - completed analyses;
   - verified findings;
   - exploratory findings and their limitations;
   - unresolved or failed analyses;
   - method/data limitations;
   - the next safe action.

The deterministic partial renderer does not copy blocked numerical tables or
unsupported prose. It preserves semantic completeness, not the verbatim unsafe
draft.

Response-level failure remains only for an unavailable/corrupt runtime state.
That path emits a Chinese diagnostic with no analytical assertions.

#### Rollout and rollback controls

Production supports two publication modes:

| Mode | Purpose | Behavior |
|---|---|---|
| `tiered` | Default product behavior | Use verified, exploratory, and unsupported claim actions to preserve a complete bounded answer |
| `strict` | Fail-safe migration rollback | Retain minimum deterministic blockers and emit a Chinese diagnostic when the tiered renderer cannot safely recover |

There is no production `off` mode. Value, direction, unit, scope, dataset
version, failed-computation, invalid-grain, and unsupported
causal/inferential blockers remain active in every production mode.

`auto_evidence_projection_enabled` and `live_progress_enabled` are independent
migration flags so either new integration can be rolled back without disabling
the assurance kernel. Disabling automatic projection falls back to explicit
v2 evidence recording and strict publication; it never upgrades unbound
computations. An audit-only shadow mode is permitted in deterministic tests and
offline replay, but cannot authorize live user-visible claims.

#### Qualitative and grain claims

Final claim extraction expands beyond numeric and causal sentences to include:

- demographic/profile attributes;
- preference, loyalty, repurchase, and behavioral-segment assertions;
- individual-level claims derived from aggregate data;
- distribution claims derived only from averages;
- unsupported field-presence assertions.

An aggregate daily table cannot support statements such as "中青年用户",
"复购率高", or "83% 的用户低消费" without the corresponding user-level fields
and grain.

### 4.4 Layer D: live progress and observability

Final analytical claims remain buffered until audit. The backend emits
server-owned progress events and non-conclusion method narration in real time:

- analysis plan selected;
- step started/completed/failed;
- tool started/completed/recovering;
- evidence projected;
- synthesis started;
- audit revising/publishing;
- partial-result reason.

Method narration is generated from canonical plan, step, and tool metadata,
using stable Chinese templates such as:

- "正在检查字段、数据粒度和缺失值";
- "正在评估变量关系与有效样本结构";
- "当前方法执行失败，正在尝试已声明的替代方法";
- "数据不足以支持显著性判断，将降级为探索性分析".

These events contain no unaudited analytical conclusion. They must not include
raw chain-of-thought, draft-answer prose, numeric findings, rankings,
significance statements, effect directions, or causal claims. Existing tool
events may be reused, but the UI receives stable Chinese labels, step identity,
and an event class that lets it distinguish progress from final content.

Persisted turn diagnostics include:

- tool call counts and failures by type;
- recovery attempts and outcomes;
- completed/unmet analysis requirements;
- projected and rejected evidence counts;
- synthesis/audit token reserves and actual usage;
- final claim counts by publication level;
- time to first progress event and time to final answer.

This makes future diagnosis possible without reconstructing the whole
conversation manually.

## 5. Error policy

| Failure | Runtime action | User-visible action |
|---|---|---|
| Invalid primitive tool argument | Lossless normalize once or reject before call | Continue after correction; otherwise report failed step |
| Sandbox redundant approved import | Normalize to preloaded namespace | No interruption |
| Sandbox forbidden import | Reject before execution; no identical retry | Explain bounded sandbox alternative only if analysis is affected |
| Missing dataset/column | Return structured available candidates; one corrected retry | Report exact unresolved input if recovery fails |
| Critical statistical tool failure | Use declared equivalent fallback once | Downgrade to exploratory or state no result |
| Canonical envelope creation failure | Keep subsequent results traceable-only; do not synthesize a verified claim | Continue with bounded diagnostics and state the execution-identity limitation |
| Ambiguous step binding | Retain computation ref; do not guess a plan/step identity | Continue with other supported work or report the unresolved method step |
| Evidence projection ineligible | Retain computation ref; mark requirement unmet | Do not describe as verified |
| Missing explicit marker with one exact existing evidence match (claim class, quantities, direction, units, and scope) | Server attaches that existing internal identity deterministically; it never creates evidence or reconstructs plan scope | No user-facing warning |
| Ambiguous evidence match | No fuzzy authorization | Revision or explicit evidence gap |
| Numeric/direction/unit/scope mismatch | Claim-level hard block | Replace claim with mismatch diagnostic |
| Missing limitation/exploratory label | One synthesis revision | Publish with specific limitation |
| Completion recovery exhausted | Return the applicable terminal state; do not continue for evidence bookkeeping | Publish the best supported complete-with-limits or diagnostic answer |
| Audit infrastructure failure | Do not publish analytical assertions | Chinese system diagnostic; retain progress history |

## 6. Compatibility and migration

1. Current persisted plans, legacy EvidenceRecords, conversations, and charts
   continue to load.
2. Legacy evidence remains `legacy_unbound`; it is not bulk-upgraded or
   backfilled into trusted v2 evidence.
3. New successful eligible computations write only `evidence_record.v2`.
4. Existing opaque plan JSON is accepted only at the compatibility boundary.
   New LLM-visible calls use the typed object contract.
5. Existing confirmation, immutable raw snapshot, analysis-copy, and context
   budget behavior is preserved.
6. No historical conversation or artifact is overwritten. Verification uses
   new sessions or explicit replay fixtures.
7. `publication_mode=tiered` is the production default. `strict` is a
   fail-safer migration rollback; no production configuration disables the
   minimum deterministic blockers.
8. Migration flags for automatic evidence projection and live progress are
   independent and default on after their focused regression gates pass.

## 7. Testing strategy

### 7.1 Unit and contract tests

- registry annotation resolution for int, float, bool, optional, list, dict,
  and enum/literal;
- lossless normalization and ambiguous-argument rejection;
- all registered tools' schemas match callable signatures;
- AST-based sandbox import normalization for root imports, arbitrary aliases,
  public symbol imports, and the approved `scipy.stats` form;
- sandbox rejection of unknown modules, unapproved dotted modules, star
  imports, and private/dunder symbols;
- `get_dataset` success and structured not-found behavior;
- failed tools cannot satisfy a plan step or produce auto evidence;
- Windows CP936/GBK console simulation with Chinese and emoji variation
  selectors;
- explicit unknown chart dataset never falls back;
- factor/significance intent and playbook classification;
- correlation, attribution, regression, and chart capability/output parity;
- completion evaluation for all five terminal states;
- completion continuation, corrected retry, and fallback bounds;
- evidence-projection or limitation failures cannot cause recomputation;
- synthesis/audit budget reserve is preserved before any continuation;
- canonical execution envelopes for explicit plans and ad-hoc analysis turns;
- deterministic step binding plus ambiguous-binding rejection;
- automatic evidence projection identity and rejection cases;
- all three publication levels;
- tiered/strict migration modes preserve minimum deterministic blockers;
- disabled automatic projection falls back to explicit v2 recording and strict
  publication rather than unbound authorization;
- demographic/grain hallucination regression;
- deterministic partial answer retains useful sections without blocked
  assertions;
- streaming progress and non-conclusion method narration occur before the final
  audited text;
- progress payloads exclude raw reasoning, draft conclusions, values, rankings,
  directions, significance, and causal language.

### 7.2 Real-session regression scenarios

#### `2af964cc1ae7`

Replay the same user question and equivalent 32x21 dataset schema.

Acceptance:

- regression arguments are correctly typed;
- the plan uses factor/significance semantics rather than generic data
  understanding;
- a replay variant that omits `record_analysis_plan` still receives a
  server-owned canonical execution envelope before substantive analysis;
- a critical method failure triggers recovery or an explicit downgrade;
- at least one eligible structured computation becomes v2 evidence;
- execution reaches the applicable minimum analytical coverage rather than
  stopping after one substantive tool:
  1. grain, target, feature scope, and missingness;
  2. univariate relationship with effective sample structure;
  3. an appropriate multivariable method or an exact failure diagnostic;
  4. applicable collinearity, stability, validation, or time-dependence
     checks;
  5. limitations and alternative explanations;
- final output is non-empty, Chinese, and methodologically bounded;
- safe progress and method narration arrive before the final answer;
- the run terminates in a declared completion state without repeated tool or
  evidence-bookkeeping loops;
- no generic English publish warning appears.

The original local session remains unchanged. A tracked fixture must be
canonical and privacy-safe; local manual validation may additionally use the
original uploaded file. Tool-call count is diagnostic only and is not a depth
metric.

When a configured external provider is available, run three fresh target-prompt
sessions outside deterministic CI. Every run must terminate without a repeated
error loop and must either satisfy the minimum applicable coverage above or
return `complete_with_limits`, `blocked_by_data`, or `blocked_by_tool` with an
exact reason. This provider check validates behavioral consistency; the
deterministic route, completion, and publication contracts remain the CI gate.

#### Sandbox-heavy uploaded-file analyses

Replay representative savings-card and retention calculations.

Acceptance:

- approved imports do not fail with `__import__ not found`;
- equivalent allowlisted aliases and public symbol imports behave consistently;
- missing datasets do not become `NoneType` cascades;
- identical failed code is not called repeatedly;
- structured tools are preferred when they cover the calculation.

#### `1fa21df491e9`

Replay the progress text containing emoji and variation selectors under each
supported CLI/web launcher and a simulated GBK stream.

Acceptance:

- the turn does not abort because a console sink cannot encode text;
- browser and persisted conversation keep valid Unicode;
- console fallback does not change analytical content;
- coverage includes the supported CLI, web, and REPL launch paths plus a sink
  captured before UTF-8 reconfiguration.

#### `3645266455a5`

Use an aggregate-only payment fixture and request a user profile.

Acceptance:

- aggregate trends and averages may be reported;
- age, individual repurchase, individual spending distribution, and invented
  persona claims are blocked or diagnosed;
- the answer asks for user-level fields when those claims are required.

### 7.3 Broad regression

Run focused suites after each layer, then all existing analysis-assurance,
execution-control, chart, web-streaming, confirmation, and real-data suites.
Before completion run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src/data_agent
git diff --check
```

External model behavior must be tested through new local sessions when the
configured provider is available. Deterministic fixtures must cover the same
contracts offline.

## 8. Acceptance gate

Do not claim the project can "normally perform data analysis" until all are
true:

1. No registered tool exposes an incorrect primitive type in its LLM schema.
2. The supported sandbox contract does not produce `__import__ not found`.
3. A failed data/tool dependency cannot cascade as an unexplained `NoneType`
   failure.
4. Supported Windows launch paths survive Chinese and emoji output.
5. The factor/significance question receives the correct plan and bounded
   claim class.
6. Directed analysis receives a canonical execution envelope even when the
   model does not explicitly record a plan.
7. Completion is requirement-based, reaches an applicable minimum analytical
   coverage, and converges to one of the five terminal states without evidence
   rituals or repeated tool loops.
8. Eligible structured computations automatically create current-plan v2
   evidence.
9. Missing evidence does not erase the whole answer.
10. Unsupported values, causal language, grain, or demographic claims are not
   published as assertions.
11. Exploratory findings remain visible with precise limitations.
12. Live progress and safe method narration precede the final audited answer.
13. Tiered and strict modes retain minimum deterministic blockers; production
    has no assurance-off path.
14. The two target sessions and the additional systemic regression scenarios
   meet their acceptance criteria.
15. Existing confirmation, data-version, and causal safeguards remain passing.
16. `artifacts/` and `tmp/` remain untouched unless a test uses an isolated
   temporary directory.

## 9. Non-goals

- Building a general-purpose secure Python notebook sandbox.
- Allowing arbitrary package, filesystem, network, or process access.
- Replacing the canonical planning, evidence, verification, or confirmation
  authorities.
- Treating feature importance as statistical significance.
- Guaranteeing a causal conclusion when the supplied design cannot identify
  one.
- Rewriting the complete visualization engine.
- Backfilling historical legacy evidence into trusted v2 evidence.
- Mutating or deleting the reported historical sessions.
- Expanding into the reference-only Stage 3C1A/3C1B multi-file execution
  slices.

## 10. Delivery order

The implementation plan must preserve this dependency order:

1. Add regression fixtures and observability assertions for the confirmed
   failures.
2. Repair registry schemas, runtime argument validation, sandbox imports,
   failure propagation, Unicode boundaries, and explicit chart source identity.
3. Materialize the server-owned canonical execution envelope and deterministic
   step binding for explicit and ad-hoc analysis turns.
4. Add factor/significance routing, truthful capabilities, and bounded
   terminal-state completion.
5. Add automatic evidence projection and bounded evidence-catalog injection.
6. Replace response-level blocking with three-level claim publication, the
   deterministic partial renderer, and fail-safer rollout controls.
7. Add safe real-time progress events and method narration.
8. Run target-session replays, depth/coverage checks, additional real-session
   scenarios, broad tests, and browser verification.

No later layer may be used to hide a failing earlier layer. In particular,
publication labels cannot compensate for a calculation that never executed.
