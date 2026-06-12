# Multi-File Analysis And User Model Redesign

## Background

Recent real-file testing showed that the project has useful trustworthy-analysis scaffolding, but the user-facing experience has drifted toward implementation-state dumping.

The right-side workbench currently exposes routes, risks, verification counts, active data, relationships, and other internal summaries. Even with extra labels and help text, a non-professional user still cannot reliably answer:

- what these items help them decide,
- whether the current data can support their goal,
- what the system is assuming,
- what must be confirmed before analysis is trustworthy,
- why a result should be trusted, downgraded, or treated as exploratory.

The same test cycle also showed that multi-file analysis is the most important differentiator from generic AI and coding agents. Generic agents can write ad hoc pandas code, but they do not consistently maintain a session-level data inventory, reason about table relationships, detect ambiguous joins, ask required questions, and tie final claims back to evidence.

This phase pauses feature expansion and re-centers the project around a non-professional user's analysis journey.

## Product Position

The project should compete as a trustworthy data-analysis harness, not as a library of prewritten analysis functions.

Its core advantage should be:

1. understand what data the user has provided,
2. infer what can and cannot be analyzed,
3. recognize when multiple files can be combined,
4. stop before unsafe assumptions change the result,
5. ask the minimum necessary user questions,
6. produce evidence-linked conclusions with clear limitations.

The chat remains the primary interaction surface. The side workbench supports the chat by showing context, assumptions, risks, and evidence. It should not become a second route-selection product.

## Recommendation Validity Contract

Analysis direction recommendations must be evidence-scoped. A recommendation is valid only when it is grounded in one of these sources:

- loaded data profiles, contracts, previews, field roles, and active analysis scope,
- explicit user-provided business context,
- existing session goal, active bundle, or confirmed assumptions,
- known method knowledge when the user is asking for consultation rather than data execution.

When data is loaded, recommendations must not exceed what the data can support without saying so. If the system suggests an analysis that is outside the current data scope, it must label the suggestion as exploratory or data-needed and explain:

- what current data cannot support,
- what extra fields or files are needed,
- what conclusion would remain unsafe without those additions.

When no data is loaded, recommendations must be framed as consultation based on the user's stated goal. The system may recommend analysis methods or required data, but it must not imply feasibility from nonexistent data.

Examples:

- Valid loaded-data recommendation: "当前数据包含用户、订单金额和支付时间，因此可以做用户付费趋势和周期对比。"
- Valid exploratory recommendation: "可以考虑留存分析，但当前数据没有用户后续活跃或复购事件，因此只能说明所需数据，不能直接计算留存。"
- Invalid recommendation: "建议做留存、归因、预测" without linking each direction to fields, missing data, or user context.

This contract applies to chat recommendations, side workbench route explanations, data requirement guidance, and any future multi-file scope plan.

## User Archetype

Primary user: business, product, operations, or management user who can describe goals but may not know statistics, SQL, table grain, or join logic.

This user may:

- upload one or more files without explaining their schema,
- upload additional files later in the same session,
- ask conceptual questions without uploading files,
- ask what data is needed for a goal before collecting files,
- choose analysis directions through conversation rather than side-panel controls,
- need the system to say "I cannot safely answer yet" when assumptions are unresolved.

## Key Scenarios

### Scenario 1: Multi-File Analysis

Example user intent:

> I uploaded order, coupon, and user payment files. Help me evaluate whether the membership card is worth continuing.

The system should not merely list uploaded files. It should build an analysis scope plan:

- which files appear relevant,
- what each file likely represents,
- what grain each file has, such as user, order, event, daily aggregate, cohort, or product,
- which entity keys may connect them,
- whether key names are aliases, such as `user_id`, `主用户ID`, and `产品用户ID`,
- whether joins are one-to-one, one-to-many, or risky,
- what assumptions need confirmation,
- which analysis questions are safe now and which are blocked.

If the system believes files are related but a high-impact assumption is uncertain, it must ask a concrete question:

> 我推测 `代金券明细订单.主用户ID` 对应订单表的 `user_id`。如果确认，我会把代金券使用与用户订单行为关联分析；如果不是，代金券文件只能单独统计。是否按这个关系处理？

It should not ask vague questions such as "是否一起分析这些文件？" unless no better relationship hypothesis exists.

### Scenario 2: No File, General Consultation

Example user intent:

> I want to understand retention analysis.

The system should answer as an analyst, not force a data workflow. It should explain the method, when it is useful, common metrics, required data, and typical mistakes.

The side workbench should stay quiet or show a lightweight "no active data" state. It should not show stale routes or irrelevant verification states.

### Scenario 3: Analysis Method Consultation

Example user intent:

> Should I use retention analysis or repeat-purchase analysis?

The system should compare methods by business question:

- retention: whether users keep returning after a start event,
- repeat purchase: whether users make additional purchases,
- cohort analysis: how behavior changes by starting cohort,
- lifecycle analysis: how users move across stages.

If no data is loaded, it should avoid pretending to know feasibility. If data is loaded, it may add whether the current files appear to support each method.

### Scenario 4: Goal-To-Data Consultation

Example user intent:

> I want to judge whether the membership card should continue. What data do I need?

The system should produce a data requirement plan rather than analysis results:

- minimum required files,
- required fields,
- optional fields that improve confidence,
- comparison design,
- time window needs,
- risks if some files are missing,
- what conclusions are possible with partial data.

For the membership card example, minimum data may include purchase/order records, card purchase records, user id, timestamps, paid amount, refunds/cancellations if relevant, and a comparison period or control group. Optional data may include coupon usage, user acquisition source, product/category, activity exposure, and user lifecycle status.

## Existing Capability Reuse

The next implementation must improve current capabilities instead of creating parallel flows.

Existing functions and concepts to reuse:

- intent types such as `knowledge_qa`, `analysis_consultation`, `data_requirement`, `intent_negotiation`, and direct analysis intents,
- `decide_analysis_entry` as the deterministic entry guard for whether analysis can proceed,
- `build_route_capabilities` as the route support model, after tightening its evidence-scoping behavior,
- `dataset_contracts`, `preview_digests`, `route_proposals`, and `unsupported_analyses` as existing data-support signals,
- `active_scope`, `data_requirements`, and `last_recommended_paths` for consulting and data-needed scenarios,
- `ask_user_question` and `pending_confirmations` for structured user confirmation.

The redesign should not create a new "consulting mode" if the existing consultation intent can be refined. It should not create a second route recommendation engine if `route_capabilities` can be made stricter. It should not create side-panel-only confirmation if the existing suspension and confirmation system can be repaired.

Required review before implementation:

1. Identify the existing module responsible for the behavior.
2. Decide whether the module should be fixed, extended, or retired.
3. Add tests around the existing behavior before changing it.
4. Remove or hide obsolete UI surfaces only after confirming they are not the source of chat recommendations.

## Side Workbench Role

The side workbench should be an information companion, similar in spirit to Codex context panels. It should help users understand state and evidence, not make them operate the analysis through a duplicate interface.

### Keep

The workbench should focus on:

- current analysis scope,
- data readiness,
- unresolved questions,
- important assumptions,
- evidence and claim trust state,
- concise analysis history when useful.

### De-emphasize Or Remove

The following should not be primary side-panel experiences:

- route cards as a competing selection surface,
- "directly analyzable" buttons that duplicate chat recommendations,
- raw counts without explainable content,
- technical module names such as verification, bundle, route, or relationship without user-facing interpretation,
- long histories shown by default.

If route information remains, it should explain why the chat recommended a direction and whether the data supports it. The action should be "use this as context in chat", not a separate workflow.

## Proposed Workbench Information Architecture

Default side workbench sections should be limited to three high-signal blocks.

### 1. Current Analysis Context

Answers:

- What goal is the system currently working on?
- Which files are in scope?
- Why are these files in scope?
- Which files are available but not currently used?

Example:

> 当前目标：评估省钱卡是否值得继续运营。  
> 当前使用：订单文件、购卡文件、代金券文件。  
> 系统依据：三个文件都包含用户实体，时间范围兼容，业务主题均与省钱卡相关。  
> 未使用：游戏互推文件，主题不相关，暂不纳入。

### 2. Needs Your Confirmation

Answers:

- What is blocked?
- What assumption is uncertain?
- How will each answer change the analysis?

Every item shown here must correspond to a real resumable confirmation. If the workbench says confirmation is needed, the chat must also have a structured `ask_user_question` suspension or an equivalent Web confirmation object.

No orphaned "waiting confirmation" state is allowed.

### 3. Trust And Evidence

Answers:

- Which important claims are supported?
- Which claims were downgraded?
- Why were they downgraded?
- What evidence or data limitation caused the downgrade?

The workbench should not show only counts like "1 claim, 0 failed, 1 downgraded". It should show the claim text and reason:

> 声明：购卡后用户付费提升。  
> 状态：降级为中等可信。  
> 原因：只有购卡用户前后对比，缺少未购卡对照组，不能直接归因于省钱卡。

## Confirmation Contract

The project needs a single contract for all user-required confirmations.

If any subsystem determines that user confirmation is required, it must create a confirmation object with:

- stable id,
- confirmation type,
- user-facing question,
- answer options or expected free-text answer,
- blocking reason,
- affected scope,
- state updates to apply after answer,
- suspension id or Web-resumable equivalent,
- creation source,
- status.

The side workbench must read from the same confirmation object that chat uses. It must not infer confirmation state only from `file_relationships.requires_confirmation`, method playbooks, or route risks.

Confirmation sources include:

- file scope ambiguity,
- file relationship ambiguity,
- join logic ambiguity,
- high-risk method confirmation,
- metric definition ambiguity,
- risky cleaning decision,
- target/comparison/time-window ambiguity.

## Multi-File Analysis Model

The next implementation should replace the simple file relationship classifier with a layered analysis planner.

The goal is not to join every uploaded file. The goal is to decide, for the user's current objective, which provided files can be safely used together, which files should be excluded, which files are only supporting context, and which assumptions must be confirmed before analysis results are trustworthy.

The system should produce an analysis-scope decision before final analysis:

- use together: files are relevant to the goal and have a defensible relationship,
- use separately: files are relevant but should not be merged for this analysis,
- exclude from current goal: files are unrelated or unsupported for the stated target,
- ask user: the relationship or business role is plausible but high-impact and uncertain,
- request more data: the current files cannot support the intended analysis.

This decision should become part of the evidence behind the final answer. A final report should be able to state which files were used, why they were used, which files were excluded, and how unresolved assumptions affected confidence.

### Layer 1: File Inventory

Maintain all uploaded and loaded files in session state. For each file, store compact metadata and preview-derived facts:

- filename,
- dataset name,
- row and column counts,
- column names,
- inferred field roles,
- time fields and ranges,
- candidate entity fields,
- sample value fingerprints when safe,
- load status.

### Layer 2: Field And Entity Canonicalization

Map fields to canonical business entities before judging relationships.

Examples:

- `user_id`, `用户ID`, `主用户ID`, `产品用户ID`, `uid` may map to user entity candidates,
- `order_id`, `订单ID`, `订单号` may map to order entity,
- `pay_time`, `支付时间`, `下单时间` may map to event time,
- `amount`, `实收金额`, `付费金额` may map to monetary measure.

The mapping should carry confidence and evidence. It should not silently equate fields when aliases are plausible but uncertain.

### Layer 3: Grain Detection

Infer the likely row grain for each file:

- user-level,
- order-level,
- event-level,
- coupon-usage-level,
- product-level,
- daily aggregate,
- cohort aggregate,
- mixed or unknown.

Grain is essential because two files can share `user_id` but still be unsafe to combine without aggregation. For example, user-level labels joined to order-level events is usually safe after preserving order rows, while order-level to coupon-level can duplicate amounts if cardinality is not checked.

### Layer 4: Relationship Graph

Build candidate edges between files:

- shared entity,
- alias-based entity match,
- time compatibility,
- business theme compatibility,
- likely parent/detail relationship,
- likely supplement relationship,
- likely independent relationship.

Each edge should include:

- confidence,
- evidence,
- unresolved assumptions,
- suggested join or aggregation plan,
- risk if used incorrectly.

### Layer 5: Analysis Scope Plan

Before final recommendations, create a compact plan:

- included files,
- excluded files,
- planned relationships,
- required confirmations,
- safe analysis directions,
- blocked directions,
- context budget summary.

Only the compact plan should enter the LLM prompt by default. Detailed schema, previews, and raw relationship edges should stay in state and be loaded only when needed.

### Layer 6: Recommendation Guard

Before route recommendations are shown or sent to chat, the system should evaluate each recommendation against the active scope plan.

Each recommendation should be classified as:

- `supported`: current scoped data can support the analysis at the required grain,
- `supported_with_limits`: current data supports a descriptive or partial version, but not stronger claims,
- `needs_confirmation`: a user answer can change whether the recommendation is valid,
- `needs_more_data`: the method is relevant to the goal but cannot be run from current data,
- `out_of_scope`: the method is unrelated to the user goal or active data.

Only `supported` and `supported_with_limits` should be presented as directly analyzable. `needs_more_data` can be presented as data requirement guidance. `out_of_scope` should be hidden by default.

## Context Budget Rules

The multi-file system must not solve relationship quality by dumping all schemas into context.

Default prompt context should include:

- current goal,
- active scope plan,
- compact file summaries,
- unresolved confirmations,
- top evidence and risks.

Detailed previews should be fetched only when:

- relationship confidence is low,
- a planned analysis needs specific columns,
- the user asks about a specific file or field,
- verification needs to inspect a claim.

## Implementation Priority

### Phase A: Cleanup And Contract Repair

1. Remove or hide side-panel route-selection behavior that duplicates chat.
2. Ensure every displayed confirmation has a real resumable confirmation object.
3. Fix method confirmations that currently create pending records without question text or suspension data.
4. Stop showing orphaned relationship confirmation states.
5. Tighten route recommendations so every recommendation carries a source basis: data-supported, user-context-supported, exploratory, or data-needed.
6. Reuse and improve existing consultation and data requirement flows instead of adding a parallel system.

### Phase B: Multi-File Analysis Planner

1. Add field/entity canonicalization.
2. Add grain detection.
3. Add relationship graph scoring.
4. Add analysis scope plan.
5. Add recommendation guard classifications from the active scope plan.
6. Add regression tests from real sessions such as `a4237f2cee72`, `6ed6b0a043fb`, and `557adfd17254`.

### Phase C: Workbench Reframing

1. Rebuild the workbench around current context, confirmations, and trust/evidence.
2. Move route recommendations back into chat-first interaction.
3. Show route support in the workbench only as explanation, not as the main action.

## Acceptance Criteria

1. A user never sees "waiting confirmation" in the side workbench unless there is a corresponding answerable confirmation in chat/Web state.
2. For multi-file sessions, the system can explain why files are included, excluded, or pending confirmation.
3. Files with semantically related user identifiers can be recognized as possible user-entity links even when names differ.
4. The system distinguishes file relationship, field alias, join logic, and analysis method confirmations.
5. The side workbench no longer duplicates the chat route-selection experience as its primary value.
6. No broad schema dumps are added to normal prompts; multi-file context is represented by compact scope plans.
7. Non-file consulting remains first-class and does not trigger irrelevant data workflow UI.
8. Every recommended analysis direction is labeled by support status and grounded in current data, user context, or explicit data-needed consultation.
9. Recommendations outside the current data scope are never presented as directly executable.
10. Final analysis can cite the scope decision: which files were used, which were excluded, and what assumptions protect the conclusion.

## Out Of Scope For This Phase

- Full visual redesign of the Web UI.
- Automatic execution of multi-file joins without a planned analysis.
- General-purpose semantic layer or BI modeling system.
- Permanent deletion of historical session data.
- Domain playbook expansion beyond what is needed to support the multi-file planner.
