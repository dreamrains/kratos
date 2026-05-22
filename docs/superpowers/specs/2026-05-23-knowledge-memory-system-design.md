# Knowledge and Memory System Design

## Context

The project is a data analysis agent. It already has a workspace/project concept, global Skills and MCP servers, chat sessions, and a basic knowledge mechanism. The next step is to redesign knowledge and memory so the agent can reuse domain knowledge and past work without overloading context or silently changing trusted facts.

The current direction is:

- Keep project as an organization and filtering concept, not a knowledge storage layer.
- Keep Skills and MCP servers global.
- Separate formal knowledge from memory.
- Load knowledge dynamically and only when useful.
- Let users manage official knowledge directly.
- Let the agent create candidates, evidence, and suggestions, but not silently overwrite trusted knowledge.

This design borrows selectively from:

- Hermes Agent: lightweight persistent memory, session search, and skill-generation feedback loops.
- TencentDB-Agent-Memory: layered memory, traceability, short-term compression, hybrid retrieval, and source-linked memory evolution.

It does not copy either architecture wholesale. The first version should stay small enough to implement and verify inside this project.

## Goals

1. Provide a user-managed formal knowledge library for domain rules, metric definitions, business terms, data analysis methods, and reusable project conventions.
2. Provide a memory inbox where the agent can propose candidate memories extracted from conversations and work traces.
3. Provide cross-session search so the agent and user can retrieve prior evidence without promoting everything into long-term memory.
4. Dynamically load only relevant knowledge and memory hints for each task.
5. Detect meaningful conflicts and ask the user before using conflicting high-impact knowledge.
6. Keep prompt boundaries clear so knowledge and memory cannot override system or developer instructions.
7. Prepare a unified Web management center for Skills, MCP, Knowledge, and Memory.

## Non-Goals for the First Version

- No automatic writing to formal knowledge without user confirmation.
- No full TencentDB-style L0-L3 pipeline in the first version.
- No autonomous skill creation. The system may create skill candidates, but the user must review and act on them.
- No project-level knowledge layer. Project may appear as metadata or a retrieval filter only.
- No attempt to solve all personalization, preference, and long-term agent identity problems.

## Core Concepts

### Formal Knowledge

Formal knowledge is trusted, user-managed, and stable enough to be reused across sessions. It should be stored as domain-oriented files plus metadata.

Examples:

- Metric definitions.
- SQL conventions.
- Business rules.
- Report style rules that are stable and explicit.
- Data source notes.
- Domain glossary.
- Analysis playbooks that are not yet Skills.

Formal knowledge can be created, edited, deprecated, restored, searched, and deleted by the user through CLI and Web.

The agent may propose changes, but those changes go through review before becoming official knowledge.

### Memory

Memory is extracted from work history. It is weaker than formal knowledge and must preserve evidence.

Examples:

- "The user often asks for same-period comparison before month-over-month comparison."
- "In recent sales analyses, the `net_revenue` field was preferred over `gross_revenue`."
- "A repeated troubleshooting path for connection failures is to inspect MCP config first."

Memory is not automatically authoritative. It can become:

- A confirmed memory.
- A formal knowledge update.
- A Skill candidate.
- Deprecated or rejected evidence.

### Session Evidence

Session evidence is the raw or compressed source material behind memories and knowledge proposals.

Examples:

- Chat messages.
- Tool calls.
- Analysis steps.
- Generated reports.
- User corrections.
- Accepted or rejected suggestions.

Cross-session search reads evidence directly. This prevents the system from over-promoting noisy facts into memory.

## Layering

The first version should use three practical layers:

1. Formal Knowledge Library
2. Memory Inbox and Confirmed Memories
3. Session Evidence Search

Project is not a fourth layer. Instead, project appears as metadata:

- `project_id`
- `session_id`
- `source_type`
- `domain`
- `tags`
- `created_at`
- `updated_at`

This avoids the confusion of global/project/session knowledge while still allowing users to filter by project when useful.

## Data Model

### Knowledge Item

Recommended fields:

- `id`
- `title`
- `domain`
- `path`
- `summary`
- `status`: `active`, `deprecated`, `archived`
- `tags`
- `source`: `user`, `memory_promotion`, `import`
- `version`
- `created_at`
- `updated_at`
- `deprecated_at`
- `supersedes`
- `superseded_by`

Storage recommendation:

- Content as Markdown files under a knowledge directory.
- Metadata in SQLite for search, status, and lifecycle management.

### Memory Item

Recommended fields:

- `id`
- `type`: `preference`, `domain_fact`, `workflow_pattern`, `correction`, `tool_usage`, `skill_candidate`
- `text`
- `summary`
- `status`: `observed`, `candidate`, `confirmed`, `promoted`, `rejected`, `deprecated`
- `confidence`
- `source_session_id`
- `source_message_ids`
- `source_tool_call_ids`
- `project_id`
- `domain`
- `tags`
- `last_used_at`
- `hit_count`
- `created_at`
- `updated_at`
- `promotion_target`: `knowledge`, `skill`, `none`

### Evidence Record

Recommended fields:

- `id`
- `session_id`
- `project_id`
- `kind`: `message`, `tool_call`, `analysis_result`, `user_correction`, `report`
- `content_ref`
- `summary`
- `embedding_ref`
- `created_at`
- `tags`

Evidence records are optimized for retrieval and traceability, not for direct prompt injection.

## Retrieval and Loading Flow

The agent should not load all knowledge by default.

Recommended flow:

1. Task understanding identifies domain, intent, data source, and risk level.
2. Knowledge router creates a retrieval query and optional filters.
3. Retrieval searches formal knowledge, confirmed memory, and session evidence separately.
4. Results are ranked with source priority:
   - active formal knowledge
   - confirmed memory
   - candidate memory
   - raw session evidence
5. Conflict resolver checks contradictions among high-impact results.
6. Context composer injects only selected snippets into the model context.

Formal knowledge should be concise in context. Long documents should be summarized or chunked before injection.

## Conflict Handling

Conflict handling should be risk-based.

Ask the user when:

- Two active knowledge items disagree on a metric, rule, or calculation.
- A confirmed memory conflicts with formal knowledge and the conflict affects analysis output.
- A user correction contradicts existing active knowledge.
- The agent is about to generate a report or make a recommendation based on conflicting facts.

Do not interrupt the user when:

- The conflict is low impact.
- One item is deprecated.
- The memory is only a weak preference hint.
- The conflict can be resolved by source priority without changing output.

When asking the user, show:

- The conflicting claims.
- Their sources.
- The likely impact.
- The proposed resolution options.

## Prompt Safety

Knowledge and memory must not become system instructions.

Recommended prompt structure:

1. System and developer instructions.
2. Task instruction.
3. Session context.
4. Retrieved formal knowledge in a read-only block.
5. Memory hints in a lower-priority block.
6. Evidence summaries with citations when needed.

The retrieved knowledge block should state:

- It is reference material.
- It cannot override system, developer, or user instructions.
- It may be incomplete or stale.
- Source, status, and updated time are available for each item.

Memory hints should be clearly weaker than formal knowledge.

## Self-Update Flow

The self-update system should be review-first.

After meaningful sessions, the agent may produce:

- Memory candidates.
- Knowledge update candidates.
- Deprecation candidates.
- Skill candidates.

Candidate generation triggers:

- Explicit user correction.
- Repeated workflow across sessions.
- Repeated data source usage.
- Repeated analysis operation.
- New domain definition provided by the user.
- Conflict resolution outcome.

Candidate review outcomes:

- Confirm memory.
- Promote to formal knowledge.
- Merge into an existing knowledge item.
- Reject.
- Deprecate older knowledge.
- Mark as skill candidate.

For the first version, candidate generation can be manual or session-end triggered. Fully autonomous background learning can come later.

## Web Management Center

Skills, MCP, Knowledge, and Memory should be managed through a unified Web management center.

Layout:

- Left menu: Skills, MCP, Knowledge, Memory.
- Right content area: searchable and filterable management views.
- Right-to-left drawer: details, preview, edit forms, configuration.
- Modal dialogs: destructive actions, conflict resolution, merge review, and complex setup.

Knowledge UI:

- List by domain, tag, status, updated time.
- Create domain knowledge.
- Edit Markdown content.
- View versions and source metadata.
- Deprecate, restore, delete.
- Search across knowledge.

Memory UI:

- Inbox for candidate memories.
- Confirm, reject, merge, promote to knowledge.
- View source evidence.
- Filter by type, confidence, project, session, status.
- Show usage history.

Session Search UI:

- Search past sessions and evidence.
- Open source conversations or summaries.
- Promote selected evidence into a memory candidate.

This management center can first host existing Skill and MCP management, then add Knowledge and Memory as the system matures.

## CLI Management

The CLI should mirror the Web operations.

Knowledge commands:

- list knowledge by domain/status/tag.
- create knowledge item.
- edit knowledge item.
- deprecate or restore knowledge.
- delete knowledge.
- search knowledge.

Memory commands:

- list candidates.
- confirm or reject candidate.
- promote candidate to knowledge.
- deprecate memory.
- search memories.
- show evidence for memory.

Session search commands:

- search sessions.
- show evidence.
- create memory candidate from evidence.

The CLI should be suitable for power users and automated workflows, while the Web UI should be suitable for review and curation.

## Architecture Components

### Knowledge Store

Owns formal knowledge files and metadata. Provides CRUD, search indexing, status updates, and version metadata.

### Memory Store

Owns candidate and confirmed memories. Provides lifecycle transitions, source tracking, and retrieval.

### Evidence Store

Indexes session traces and summaries. Supports cross-session search and source lookup.

### Retrieval Router

Given a task, decides what to search and how much to return.

### Conflict Resolver

Detects contradictions among retrieved items and decides whether user confirmation is required.

### Context Composer

Formats selected knowledge and memory into safe prompt sections.

### Review Service

Creates and manages memory, knowledge, deprecation, and skill candidates.

## Testing Strategy

Unit tests:

- Knowledge CRUD and status transitions.
- Memory lifecycle transitions.
- Evidence source linking.
- Retrieval ranking and filtering.
- Conflict detection.
- Context composer safety formatting.

Integration tests:

- User correction creates a candidate memory.
- Candidate memory promotes to knowledge.
- Deprecated knowledge is not injected.
- Formal knowledge beats memory hints.
- Conflict asks for user confirmation before analysis.
- Cross-session search returns source-linked evidence.

Web tests:

- Management center navigation.
- Knowledge list, create, edit, deprecate.
- Memory inbox confirm, reject, promote.
- Drawer and modal behavior.

CLI tests:

- Knowledge and memory management commands.
- Search commands.
- Promotion and deprecation flows.

## Implementation Phases

### Phase 1: Foundation

- Add Knowledge Store metadata and Markdown-backed formal knowledge.
- Add Memory Store with candidate and confirmed states.
- Add Evidence Store search over session summaries or existing session records.
- Add dynamic retrieval and context composer.
- Add CLI management basics.
- Add Web management center shell and Knowledge/Memory tabs.

### Phase 2: Review and Learning

- Add session-end candidate generation.
- Add conflict review UI.
- Add memory-to-knowledge promotion.
- Add better source visualization.
- Add repeated workflow detection.

### Phase 3: Advanced Reuse

- Add skill candidate generation.
- Add hybrid retrieval improvements.
- Add richer scenario memory.
- Add scheduled memory maintenance.
- Add knowledge version diff and merge workflows.

## Open Decisions

The following can be deferred until implementation planning:

- Whether embeddings are required in Phase 1 or whether keyword/BM25-like retrieval is enough initially.
- Exact storage paths and table names.
- Whether Web editing uses a simple textarea first or a richer Markdown editor.
- Whether candidate generation is manual-only in Phase 1 or triggered automatically after selected sessions.

## Recommendation

Build Phase 1 around three concrete capabilities:

1. Knowledge Library
2. Memory Inbox
3. Session Search / Evidence Store

This gives the project a strong foundation without overbuilding. It keeps the user in control of official knowledge, lets the agent learn from repeated work, and avoids context explosion through dynamic retrieval.
