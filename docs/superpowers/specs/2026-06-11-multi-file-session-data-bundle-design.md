# Multi-File Session Data Bundle Design

## Background

The current project can upload multiple files from the Web UI, and analysis tools can load multiple datasets over time. However, the analysis workflow still behaves mostly like a single-active-dataset system. When a user uploads more than one file, or uploads new files later in the same session, the system can list files and ask in chat which file to use, but it does not consistently represent:

- all files available in the session,
- which files are currently in scope for this analysis,
- whether uploaded files are related,
- when uncertain file relationships must trigger `ask_user_question`,
- whether recommendations are based on a single dataset or a multi-file analysis bundle.

This creates risk in real analysis sessions. The system may recommend routes from stale files, mix unrelated files, or ask clarification in plain chat instead of using the structured confirmation flow.

## Goals

1. Treat a session as one continuing analysis goal by default.
2. Append newly uploaded files to the session data pool instead of replacing prior files.
3. Maintain a current analysis bundle that defines which files are actually in scope for the current turn.
4. Detect relationships between newly uploaded files and existing session files before generating final recommendations.
5. Pause and trigger `ask_user_question` when file relationships are possible but uncertain, or when unrelated files may affect the current goal.
6. Base recommendations, risk boundaries, validation prompts, and analysis plans on the current analysis bundle, not on every historical file in the session.
7. Support user override such as "only analyze the newly uploaded file" without deleting older session files.

## Non-Goals

1. Do not build a full semantic modeling layer in this phase.
2. Do not infer irreversible primary-key or foreign-key relationships without evidence or user confirmation.
3. Do not automatically join files or produce cross-file conclusions when relationship confidence is uncertain.
4. Do not remove existing single-file workflows.
5. Do not require users to manually classify every uploaded file when the relationship is clear from deterministic signals.

## Core Concepts

### Data Pool

`data_pool` is the session-level inventory of all uploaded or loaded data files that are still available for the session. It answers: "What data has this session accumulated?"

Each item should include:

- stable file id,
- filename,
- resolved path or workspace reference,
- upload/load timestamp,
- source turn id when available,
- file size and extension,
- load status,
- linked dataset name when loaded,
- lightweight profile summary.

New uploads append to `data_pool` by default.

### Active Bundle

`active_bundle` is the current analysis scope. It answers: "Which files should this analysis use now?"

It may contain one file or multiple files. It should include:

- bundle id,
- display label,
- included file ids,
- primary dataset or primary file when known,
- relationship confidence,
- relationship summary,
- user-confirmed assumptions,
- excluded file ids for this bundle,
- created and updated timestamps.

The active bundle can change across turns without deleting older data pool items.

### Dataset Bundles

`dataset_bundles` stores known or proposed file groupings. A session can have multiple bundles, for example:

- "省钱卡订单分析包": order file plus user payment flow file,
- "游戏广告分析包": banner, purchase, and retention files,
- "latest upload only": a temporary single-file bundle requested by the user.

### File Relationships

`file_relationships` records pairwise or group-level relationship candidates. It answers: "Why does the system think these files are related or not related?"

Relationship records should include:

- source file ids,
- target file ids,
- status: `linked`, `possibly_linked`, `independent`, or `insufficient_preview`,
- confidence: `high`, `medium`, or `low`,
- evidence signals,
- blocking uncertainties,
- suggested user question when confirmation is required.

### Excluded Files

`excluded_files` stores files the user explicitly says not to consider for the current analysis goal or current bundle. Exclusion is scoped to the bundle unless the user clearly asks to exclude a file for the whole session.

## File Relationship Detection

The first version should use lightweight deterministic signals before involving the LLM.

### Strong Positive Signals

Files are likely related when several of these signals agree:

- overlapping business keywords in filenames,
- overlapping ID fields such as `user_id`, `order_id`, `device_id`, or account identifiers,
- compatible time ranges,
- compatible date granularity,
- shared categorical dimensions such as product, channel, campaign, region, or platform,
- one file appears to be a detail table and another appears to be a summary or user table,
- user context names them as part of the same goal.

### Uncertainty Signals

The system must ask before proceeding when:

- multiple files match the user's phrase such as "the uploaded data" or "order file",
- fields overlap but their semantics are unclear,
- ID fields exist but coverage or granularity is unknown,
- time ranges partially overlap and comparison intent is unclear,
- one-to-many or many-to-many joins may change the conclusion,
- the new file may be a supplement to the current analysis, but the role is unclear.

### Negative Signals

Files are probably independent when:

- business themes conflict, such as ecommerce order data and unrelated game ad data,
- no key fields overlap,
- time ranges or granularity cannot support the same analysis,
- filename and schema suggest different entities or domains,
- the user says the file is for a different purpose.

Even when files look independent, the system should pause and ask if the user uploaded them in the same session without clarifying their role, because the user may know an external business relationship that the data cannot reveal.

## User Confirmation Rules

The system should use structured confirmation rather than plain chat whenever the answer can change the analysis scope, relationship model, method, or final recommendation.

### New Confirmation Types

`file_scope_confirmation`

- Triggered when more than one file could be the target of the user's request.
- Example question: "本轮要分析哪些文件？"
- Blocks direct recommendations and execution.

`file_relationship_confirmation`

- Triggered when a new file may relate to the active bundle, but the relationship is uncertain.
- Example question: "这个新文件是否与当前省钱卡分析目标有关？"
- Blocks final recommendations and cross-file execution.

`join_logic_confirmation`

- Triggered when cross-file analysis depends on join keys, join direction, or time-window alignment.
- Example question: "这些文件是否可以按 user_id 关联？是否需要限定同一时间窗口？"
- Blocks cross-file execution and report generation.

`file_exclusion_confirmation`

- Triggered when files appear unrelated but were uploaded into the same session.
- Example question: "这个文件要纳入当前分析目标，还是作为独立材料保留？"
- Blocks recommendations that would mix the unrelated file with the active bundle.

### Blocking Surfaces

For unresolved file relationship confirmations, block:

- final route recommendations,
- direct analysis execution,
- report generation,
- cross-file conclusions.

Allowed while blocked:

- show uploaded files,
- show lightweight previews,
- discuss possible analysis approaches,
- explain what information is needed.

## Flow

### Upload Flow

1. User uploads one or more files.
2. Files are appended to `data_pool`.
3. System creates lightweight profiles for new files when possible.
4. System compares new files with existing pool and active bundle.
5. Relationship detector classifies the files.
6. If relationship is clear, update or create `active_bundle`.
7. If relationship is uncertain or conflicting, create a pending confirmation and suspend the turn.
8. After confirmation, update bundle scope and generate recommendations.

### Chat Flow

When the user asks for analysis:

1. Resolve whether the user named specific files, latest files, all session files, or the current active bundle.
2. If the scope is explicit, set or update `active_bundle`.
3. If the scope is ambiguous, trigger `file_scope_confirmation`.
4. Run `decide_analysis_entry` against `active_bundle`.
5. Generate recommendations only after blocking confirmations are resolved.

### User Override Flow

If the user says "only analyze the newly uploaded file":

1. Keep all prior files in `data_pool`.
2. Create or update `active_bundle` using only the newest uploaded file or files.
3. Mark other files as excluded for this bundle.
4. Generate recommendations from that bundle only.
5. Allow later re-inclusion if the user asks to combine with previous data.

## Web Behavior

The right-side session panel should distinguish:

- Current analysis bundle: files currently used for recommendations and execution.
- Session data pool: all available uploaded or loaded files.
- Relationship status: linked, possible, independent, or needs confirmation.
- Pending confirmation: a clear prompt that recommendations are paused until the user answers.

Recommendation cards should indicate whether they are based on:

- a single file,
- a multi-file bundle,
- a tentative relationship that still requires confirmation.

When relationship confirmation is pending, hide final executable recommendations and show the confirmation prompt instead.

## CLI Behavior

CLI should mirror the same state rules:

- list current bundle separately from all available session files,
- show relationship status in concise text,
- suspend with `ask_user_question` for ambiguous file relationships,
- resume with updated bundle scope.

## Context Budget Strategy

Multi-file sessions can consume context quickly. The prompt should not include full previews for all files. Instead, the system should inject compact summaries:

- active bundle id and included files,
- top relationship evidence,
- row/column counts,
- key fields,
- time ranges,
- unresolved confirmations,
- last selected route.

Full previews should remain in tool output files or structured state and be retrieved only when needed.

The LLM should receive enough information to reason about scope and planning, but not raw tables from every session file.

## Interaction With Existing Workflow

This design extends the existing trustworthy analysis workflow:

- `dataset_contracts` remain the source of per-dataset quality and capability evidence.
- `route_proposals` should reference a bundle or dataset.
- `active_scope` should support an active bundle in addition to active dataset.
- `pending_confirmations` remains the shared mechanism for all blocking questions.
- `question_need_detector` should become aware of data pool, active bundle, and file relationships.
- `trust_view` should present bundle state without breaking existing single-file views.

## Testing Scenarios

1. Single file upload still works as before.
2. Two clearly related files are uploaded together and become one active bundle.
3. A second related file is uploaded later and is appended to the active bundle.
4. A possibly related file triggers `file_relationship_confirmation`.
5. An unrelated file triggers `file_exclusion_confirmation`.
6. "Only analyze the latest file" creates a temporary active bundle without deleting previous files.
7. Multiple matching order files trigger `file_scope_confirmation`.
8. Cross-file join with ambiguous key triggers `join_logic_confirmation`.
9. Recommendations are hidden while a blocking confirmation is pending.
10. Recommendations use only active bundle files, not all historical data pool files.
11. Web and CLI both surface the same pending confirmation state.
12. Context summary remains compact when the session contains many files.

## Acceptance Criteria

1. Uploading files never deletes or replaces prior session data pool entries unless the user explicitly removes them.
2. New files are not mixed into the active analysis bundle when their relationship is uncertain.
3. Ambiguous file scope and relationship questions use structured `ask_user_question`.
4. Final recommendations are not produced while file relationship confirmations are pending.
5. Existing single-file tests continue to pass.
6. Web trust panel clearly separates active bundle from available session files.
7. Analysis state summaries stay compact and do not include raw multi-file previews.
