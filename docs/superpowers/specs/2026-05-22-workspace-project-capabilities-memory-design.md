# Workspace, Project, Capabilities, and Memory Redesign

## Background

The current system uses `project/` as the local workspace directory while also moving the user-facing "object" concept toward "project". This creates a naming collision:

- `project/` means local data/config workspace.
- `object` means a ChatGPT/Codex-like project container.
- `project_name` is already becoming the canonical session binding field.

Because the product has not been released publicly, this redesign can prefer a clean model over long compatibility windows.

## Goals

1. Rename the local filesystem concept from project to workspace.
2. Make `project` the user-facing analysis container.
3. Remove `object` as an active product concept.
4. Make skills and MCP servers global capabilities, not project-scoped.
5. Establish the boundary for knowledge as global plus session only.
6. Leave the full knowledge and memory product as a follow-up project, with only foundational hooks in this redesign.

## Terminology

### Workspace

The workspace is the local filesystem and runtime root. It contains user data, sessions, artifacts, projects, and migration state.

Preferred environment variable:

```text
WORKSPACE_DIR=./workspace
```

`PROJECT_DIR` may remain as a temporary development alias, but new code and docs should use `WORKSPACE_DIR`.

### Project

A project is a user-facing organization container for related analysis work. It stores:

- metadata: name, description, tags, status, timestamps
- associated sessions
- data references or imported files
- task references

A project does not store auto-injected long-term knowledge. Project descriptions may be injected as current context, but they are not part of the memory or knowledge layer.

### Session

A session is the active conversation and analysis execution context. It owns temporary analysis context, current datasets, tool traces, evidence, charts, and session-level notes.

### Global Knowledge

Global knowledge is the only long-term knowledge layer. It stores stable user preferences, analysis conventions, domain files, reusable experience, and accepted memory or skill candidates.

### Object

`object` is removed as a product concept. Because the project is pre-release, compatibility should be minimal:

- old code names can be renamed directly where practical
- old `/api/objects` routes can be removed or kept briefly only if tests still depend on them
- old `object_name` metadata should migrate to `project_name`
- old `workspace/objects` or `project/objects` directories should migrate to `workspace/projects`

## Filesystem Layout

Target layout:

```text
workspace/
  data/
  inbox/
  projects/
    <project_name>/
      meta.yaml
      data/
      tasks/
  sessions/
    <session_id>/
      meta.json
      conversation.json
      conversation.jsonl
      knowledge/
      analyses/
      charts/
      reports/
```

Global user config:

```text
~/.data-agent/
  settings.yaml
  skills/
    <skill_name>/
      SKILL.md
      skill.yaml
  mcp_servers.yaml
  knowledge/
    memory.md
    user.md
    domains/
      ecommerce.md
      statistics.md
      ab_testing.md
    memories/
      atoms.jsonl
      scenarios/
      candidates/
```

## Project Redesign

Replace `ObjectManager` with `ProjectManager`.

Core operations:

- create project
- list projects
- get project
- rename project
- archive/reactivate project
- delete project
- bind/unbind session
- attach/detach data file reference

Project binding is an organization relationship only. Binding a session to a project must not promote knowledge.

## Skill Design

Skills become global capabilities.

Source of truth:

```text
~/.data-agent/skills/
```

Remove project-level skill scanning and override behavior. Existing `project/skills` should be migrated once into the global skills directory.

Each skill should have lifecycle metadata:

```yaml
name: full_report
enabled: true
source: local
created_at: "2026-05-22"
updated_at: "2026-05-22"
```

Required operations:

- list skills
- view skill
- create skill
- install skill from local path
- enable skill
- disable skill
- delete skill
- load skill for current session
- unload skill for current session

Web and CLI should expose the same operations.

## MCP Design

MCP servers become global capabilities.

Source of truth:

```text
~/.data-agent/mcp_servers.yaml
```

Remove project-level MCP config and merging. Existing `project/mcp_servers.yaml` should be migrated once into the global file.

Required operations:

- list servers
- view server
- add server
- edit server
- enable server
- disable server
- delete server
- test connection
- reload servers
- show tools per server

Agent initialization must read the global MCP config. The current implementation already has a resolver but the loop reads the project config directly; this should be corrected as part of the redesign.

## Knowledge Redesign

Remove the project/object knowledge layer.

Prompt knowledge sources become:

- global relevant knowledge
- current session context
- current project metadata or description

Project metadata is context, not knowledge. It is not auto-updated, promoted, merged, or migrated.

This redesign should only implement the foundation needed to remove project-level knowledge safely. The full knowledge and memory product should be split into a dedicated follow-up spec and plan.

### Global Knowledge Types

1. `user.md`: stable user profile and preferences.
2. `memory.md`: compact agent notes, environment facts, workflow conventions, and durable lessons.
3. `domains/*.md`: domain knowledge files, one domain per file.
4. `memories/atoms.jsonl`: atomic facts extracted from sessions.
5. `memories/scenarios/*.md`: repeated workflow patterns or scenario summaries.
6. `memories/candidates/*.md`: proposed memories or skills awaiting user confirmation.

### User-Managed Knowledge

Knowledge must be user-manageable. The system should not treat long-term knowledge as an internal-only cache.

Users should be able to:

- create a domain knowledge file
- edit a domain knowledge file
- correct an existing memory or knowledge entry
- deprecate stale knowledge
- delete sensitive or incorrect knowledge
- review memory candidates
- accept or reject memory candidates
- promote a scenario candidate into a skill candidate

The system should preserve traceability when users edit or correct knowledge:

```yaml
id: mem_abc123
status: accepted
content: "Use daily averages when comparing periods with unequal lengths."
corrections:
  - corrected_at: "2026-05-22"
    reason: "Clarified that this applies to additive metrics only."
    previous_content: "Use daily averages when comparing periods with unequal lengths."
```

Physical deletion should be reserved for privacy, sensitive data, or clearly erroneous entries that should not remain in local history.

### Domain Knowledge

Domains should be file-based instead of a single YAML blob.

The agent should select relevant domain files dynamically using:

- user query
- current datasets and column names
- active analysis intent
- recent session context
- keyword or semantic retrieval

Selected domain content should be injected within a bounded token budget.

### Memory Pipeline

Borrowing from TencentDB-Agent-Memory's layered model:

- L0 Conversation: raw session messages and tool traces.
- L1 Atoms: small facts, preferences, or lessons with source references.
- L2 Scenarios: repeated procedures and context-specific workflows.
- L3 Profile/Memory: compact global files and accepted durable knowledge.

Every generated memory must preserve evidence:

```yaml
id: mem_abc123
type: preference | convention | domain_fact | workflow | correction
content: "Use daily averages when comparing periods with unequal lengths."
source_session_id: "..."
source_message_refs: [...]
confidence: 0.72
status: candidate
created_at: "2026-05-22"
```

### Self-Update Policy

Automatic extraction may create candidates. It should not silently write durable global knowledge unless the user explicitly asks to remember something.

Write policy:

- explicit "remember this" requests can write directly
- repeated patterns create candidates
- conflicting memories create review candidates
- stale or contradicted memories are deprecated, not deleted
- accepted scenario candidates can become skill candidates

## Cross-Session Recall

Add cross-session read capability backed by local indexes.

Initial implementation can use SQLite FTS over:

- session summaries
- user messages
- assistant conclusions
- tool names
- evidence records
- accepted memories

Later implementation can add embeddings and reciprocal rank fusion.

Recall should return traceable snippets and source links, not opaque summaries.

## UI Scope

Add a capabilities/settings area with three tabs:

- Skills
- MCP Servers
- Knowledge

Skills tab:

- table of installed skills
- enabled toggle
- load/unload current session action
- create/install/delete
- view SKILL.md

MCP tab:

- table of servers
- enabled toggle
- status/test/reload
- tool list
- add/edit/delete form

Knowledge tab:

- global memory files
- domain files
- candidates requiring review
- cross-session search

For this redesign, the Knowledge tab can be a placeholder or minimal read-only foundation if implementation scope needs to stay focused. Full CRUD, candidate review, correction history, and cross-session search belong to the follow-up knowledge and memory project.

## CLI Scope

Commands should match web operations:

```text
/skill list
/skill view <name>
/skill create <name>
/skill install <path>
/skill enable <name>
/skill disable <name>
/skill delete <name>
/skill load <name>
/skill unload <name>

/mcp list
/mcp view <name>
/mcp add
/mcp enable <name>
/mcp disable <name>
/mcp delete <name>
/mcp test <name>
/mcp reload

/memory search <query>
/memory candidates
/memory accept <id>
/memory reject <id>
/domain list
/domain view <name>
/domain create <name>
/domain delete <name>
```

For this redesign, CLI commands for knowledge may be limited to the minimum needed for migration and inspection. Full user-managed knowledge commands should be implemented in the dedicated knowledge and memory follow-up.

## Migration

Because the product is pre-release, migration can be direct and opinionated.

1. Add `WORKSPACE_DIR` config and prefer it over `PROJECT_DIR`.
2. Move local root from `project/` to `workspace/` when safe.
3. Move `objects/` to `projects/`.
4. Rewrite metadata from `object_name` to `project_name`.
5. Move `project/skills` to `~/.data-agent/skills`.
6. Move `project/mcp_servers.yaml` into `~/.data-agent/mcp_servers.yaml`.
7. Convert project/object knowledge into global candidates rather than preserving a project knowledge layer.

If conversion would require substantial memory-pipeline work, store migrated project/object knowledge under a clearly marked review directory:

```text
~/.data-agent/knowledge/migration-review/
```

These files should not be injected automatically until the user accepts or rewrites them.

## Implementation Phasing

### Phase 1: Foundation

This spec covers the foundation:

- rename local root concept to workspace
- make project the user-facing organization container
- remove object as an active product concept
- globalize skills and MCP
- remove project-level knowledge from prompt injection
- create migration-review output for old project/object knowledge

### Phase 2: Knowledge and Memory Product

Create a separate spec and plan for:

- user-managed knowledge CRUD in CLI and Web
- domain file creation, editing, review, and deletion
- memory candidate extraction and review
- accepted/deprecated/deleted memory lifecycle
- cross-session search
- scenario memory
- skill candidate generation
- traceable memory evidence UI

## Testing

Tests should cover:

- `WORKSPACE_DIR` preferred over `PROJECT_DIR`
- project CRUD under `workspace/projects`
- session project binding without knowledge promotion
- skill discovery only from global directory
- MCP initialization only from global config
- old sample data migration where needed
- knowledge prompt injection excludes project knowledge layer
- migrated project/object knowledge is not auto-injected
- Web and CLI capability parity

## Open Decisions

The knowledge and memory product details are intentionally deferred to a dedicated follow-up design. The accepted product decision here is that project is an organization container only, not a knowledge layer.
