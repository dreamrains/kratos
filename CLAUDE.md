# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Data Agent is a Chinese-language expert AI agent for professional data analysis via natural language. It runs as a CLI (REPL) or Flask web GUI, connects to LLMs via litellm, and provides 40+ analysis tools for data loading, EDA, statistics, ML, visualization, and reporting.

## Commands

```bash
# Install (uv)
uv sync

# CLI REPL
python main.py

# Web GUI (Flask, port 5001)
python -m data_agent.web.entry

# Run all tests
uv run pytest tests/ -v

# Run a single test
uv run pytest tests/test_web_gui.py -v
uv run pytest tests/test_interaction.py::test_function_name -v
```

## Architecture

### Entry Points

- `main.py` → `data_agent.main:main` → CLI REPL via `AgentLifecycle` + `run_repl()`
- `data_agent.web.entry:main` → Flask web GUI on port 5001
- Entry point `kratos` maps to CLI; `data-agent-web` maps to web GUI

### Core Loop: `data_agent/agent/loop.py`

`AgentLoop` is the central orchestrator. Each user turn:
1. Builds system prompt (injects domain knowledge, experience log, project rules, loaded skills)
2. Sends to LLM via litellm with active tool schemas
3. Executes tool calls through `ToolRegistry`, handling suspension for user confirmations
4. Manages context compaction (`agent/compact.py`) when token usage approaches threshold
5. Returns `FinalResponse` or `SuspendedForConfirmation`

`AgentRunner` (agent/runner.py) wraps loop turns in a background thread with cooperative interrupt support.

### Tool System: `data_agent/tools/`

- **Auto-discovery**: `discover_tools()` scans all modules in `data_agent/tools/`, each uses `@registry.register()` decorator to register into the global `ToolRegistry` singleton
- **Group-based activation**: Tools belong to groups (core, eda, ml, stats, report, clean, task, knowledge). Only "core" is active by default; other groups activate based on user intent keywords. Deprecated tools are in `deprecated_report_artifacts` group and filtered from search
- **ToolResult**: All tools return `ToolResult` (summary + optional data/artifacts). Plain strings auto-wrap via `from_str()`
- **Capability metadata**: Each tool can declare `ToolCapability` with problem_types, risk_level, evidence_fields, fallback_tools
- **Report strategy**: Report artifact tools (`generate_report`, `generate_analysis_brief`, `generate_formal_report`) are **deprecated**. Analysis conclusions are synthesized directly in conversation. `/export` remains for saving conversation to HTML/Markdown
- **Key tool modules**: `data_io.py` (load/export), `eda.py` (explore), `statistics.py`, `ml.py`, `visualization.py`, `report.py` (conversation export only), `analysis_flow.py`, `interaction.py`

### Knowledge & Memory System: `data_agent/knowledge/`

**Primary system** (SQLite-backed, no layer merging):
- `KnowledgeLibrary` (`library.py`): Versioned knowledge items stored as Markdown files with SQLite metadata. Lifecycle: ACTIVE → DEPRECATED → ARCHIVED. Global scope, no per-project layering
- `MemoryStore` (`memory.py`): Ephemeral memory candidates with lifecycle CANDIDATE → CONFIRMED/REJECTED/DEPRECATED. Types: PREFERENCE, DOMAIN_FACT, WORKFLOW_PATTERN, CORRECTION, TOOL_USAGE. Auto-deduplication via `dedup_key`
- `EvidenceStore` (`evidence.py`): Session-indexed evidence records (MESSAGE, TOOL_CALL, ANALYSIS_RESULT, USER_CORRECTION, REPORT). Links analysis claims to source data
- `MemoryCandidateExtractor` (`candidates.py`): Auto-extracts memory candidates from tool outputs by detecting markers (preferences, corrections, metric definitions, workflow patterns)
- `RetrievalEngine` (`retrieval.py`): Unified retrieval across KnowledgeLibrary + MemoryStore + EvidenceStore with conflict detection and token budget management
- `KnowledgeDatabase` (`sqlite_store.py`): SQLite storage layer for knowledge/memory/evidence
- `models.py`: Pydantic models (KnowledgeItem, MemoryItem, EvidenceRecord, RetrievedContext, etc.)

**Legacy YAML-based components** (still in use, pending migration to the primary system):
- `DomainKnowledge` (`domain.py`): Domain-specific indicators, rules, pitfalls with templates for ecommerce/gaming. Still uses three-layer merge (global → project → session)
- `ExperienceLog` (`experience.py`): Learned patterns with draft/confirmed/deprecated lifecycle and confidence scores. Still uses three-layer union (global ∪ project ∪ session)
- `ProjectRules` (`rules.py`): Markdown project rules injected into system prompt. Still uses three-layer append (global → project → session)

### Config: `data_agent/config.py`

`AgentConfig` via pydantic-settings reads `.env`. Key paths resolved as properties:
- `workspace_resolved` → `./workspace/` (data, knowledge, projects, inbox subdirs). Legacy alias: `project_resolved`
- `sessions_resolved` → `./sessions/`
- `global_dir` → `~/.data-agent/` (cross-project skills, MCP config)
- `projects_dir` → `<workspace>/projects/`
- `objects_dir` → `<workspace>/objects/` (legacy, kept for migration only)

`config_resolver.py` merges global + workspace configs (skills dirs, MCP servers, settings).

### MCP Integration: `data_agent/mcp/`

- `MCPClientManager` manages multiple MCP server connections via a background asyncio event loop thread
- Supports stdio, SSE, and streamable-http transports
- `MCPToolBridge` discovers MCP tools and registers them into `ToolRegistry` as if native
- Config in `workspace/mcp_servers.yaml` and `~/.data-agent/mcp_servers.yaml`

### Skills: `data_agent/skills/`

- `SkillLoader` discovers `SKILL.md` files in `~/.data-agent/skills/` (global) and `workspace/skills/` (workspace-level, overrides global)
- Skills have YAML frontmatter (name, trigger_keywords, tools_required, task_template) + instruction body
- Loaded skills get injected into the system prompt as `<skill>` XML blocks

### Project Management: `data_agent/project_manager.py`

- `ProjectManager` manages projects within `workspace/projects/{name}/`
- Each project has `meta.yaml` (name, description, status, tags), `data/`, and `tasks/`
- Sessions can be bound to projects via `bind_session_to_project()` (session/history.py)
- `list_objects()` exists as a backward-compatible alias for `list_projects()`

### Web GUI: `data_agent/web/`

Flask app with SSE-based real-time updates. `EventQueue` bridges sync AgentLoop to SSE responses. Blueprints: `chat.py`, `sessions.py`, `objects.py` (handles `/api/projects` endpoints), `tasks.py`, `artifacts.py`, `commands.py`, `uploads.py`, `capabilities.py`, `management.py` (knowledge/memory/evidence admin panel).

### Lifecycle: `data_agent/lifecycle.py`

`AgentLifecycle.initialize()` → validate config → setup logging → discover native tools → register middleware hooks. MCP and skill discovery deferred to `AgentLoop.__init__()`.

## Key Patterns

- **Module-level singletons**: Config, ToolRegistry, DomainKnowledge, ExperienceLog all use `get_X()` accessor functions with lazy init
- **Decorator-based registration**: Tools use `@registry.register(name=..., description=..., capability=...)`
- **Unified retrieval with conflict detection**: RetrievalEngine composes context from KnowledgeLibrary + MemoryStore + EvidenceStore, auto-detecting conflicts between knowledge and memory
- **Context management**: `AgentContext` (agent/context.py) tracks per-turn state (active groups, executed tools). `project_name` is primary field; `object_name` is a backward-compatible alias
- **Canonical analysis planning**: Analysis planning has one writable `AnalysisPlan` contract. Legacy `AnalysisSpec` payloads are normalized only at tool/session boundaries and remain read-only compatibility inputs.
- **Non-destructive data preparation**: `load_data` retains an immutable raw snapshot and exposes a versioned analysis-ready copy under the user's logical dataset name. Safe parsing runs only on the copy.
- **Material cleaning confirmation**: Destructive or meaning-changing cleaning creates a candidate and requires confirmation before promotion. Raw data and prior analysis-copy versions remain available for audit.
- **Windows compatibility**: UTF-8 reconfiguration on win32, `ThreadPoolExecutor`-based timeouts instead of `signal`
- **LLM provider**: Uses litellm for multi-provider support. `LITELLM_LOCAL_MODEL_COST_MAP=true` avoids network calls at init

## Directory Structure

### Source Code

```
src/data_agent/
  agent/                # Core agent logic (loop, intent, synthesis_policy, analysis_state)
  knowledge/            # Knowledge & memory system (library, memory, evidence, retrieval)
  tools/                # Tool registry and native tools
  skills/               # Skill loader
  mcp/                  # MCP protocol integration
  session/              # Session persistence (history, workspace, task_manager)
  web/                  # Flask web GUI (blueprints, static, templates)
  plugins/              # Plugin system
  llm/                  # LLM client integration
  utils/                # Utility functions
```

### Runtime Data

```
workspace/              # User data workspace (default ./workspace)
  data/                 # Processed datasets
  inbox/                # Raw uploaded files
  knowledge/            # Knowledge library (library/{domain}/*.md + SQLite)
  projects/             # Per-project data and tasks
    {name}/
      meta.yaml         # Project metadata
      data/             # Project-specific data
      tasks/            # Project-specific tasks
  mcp_servers.yaml      # Workspace-level MCP server configs (legacy)
  skills/               # Workspace-level SKILL.md files (legacy)

sessions/               # Session data (default ./sessions)
  {session_id}/
    meta.json           # Session metadata
    conversation.jsonl  # Active conversation (rotates to .json)
    analysis_state.json # Analysis state persistence
    artifacts.json      # Artifact registry
    analyses/           # Analysis results (report + charts)
    knowledge/          # Session-level knowledge
    data/               # Session-level data
    tool_outputs/       # Tool execution outputs

~/.data-agent/          # Global config
  skills/               # Global SKILL.md files
  mcp_servers.yaml      # Global MCP server configs
  settings.yaml         # Global settings

tests/                  # pytest test suite
reference/              # Reference code and docs (not part of runtime)
```
