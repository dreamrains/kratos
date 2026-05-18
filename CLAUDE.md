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
- **Group-based activation**: Tools belong to groups (core, eda, ml, stats, report, clean, task, knowledge). Only "core" is active by default; other groups activate based on user intent keywords
- **ToolResult**: All tools return `ToolResult` (summary + optional data/artifacts). Plain strings auto-wrap via `from_str()`
- **Capability metadata**: Each tool can declare `ToolCapability` with problem_types, risk_level, evidence_fields, fallback_tools
- **Key tool modules**: `data_io.py` (load/export), `eda.py` (explore), `statistics.py`, `ml.py`, `visualization.py`, `report.py`, `analysis_flow.py`, `interaction.py`

### Knowledge System: `data_agent/knowledge/`

Three-layer merge: **Global → Object → Session** (session overrides object overrides global)

- `DomainKnowledge` (`domain.py`): Domain-specific indicators, rules, pitfalls. YAML-based. Templates for ecommerce/gaming
- `ExperienceLog` (`experience.py`): Learned patterns with draft/confirmed/deprecated lifecycle and confidence scores
- `ProjectRules` (`rules.py`): Markdown project rules injected into system prompt

Knowledge promotion: session → object (explicit action). Migration between objects on re-binding.

### Config: `data_agent/config.py`

`AgentConfig` via pydantic-settings reads `.env`. Key paths resolved as properties:
- `project_resolved` → `./project/` (data, knowledge, skills, objects subdirs)
- `sessions_resolved` → `./sessions/`
- `global_dir` → `~/.data-agent/` (cross-project skills, MCP config)

`config_resolver.py` merges global + project configs (skills dirs, MCP servers, settings).

### MCP Integration: `data_agent/mcp/`

- `MCPClientManager` manages multiple MCP server connections via a background asyncio event loop thread
- Supports stdio, SSE, and streamable-http transports
- `MCPToolBridge` discovers MCP tools and registers them into `ToolRegistry` as if native
- Config in `project/mcp_servers.yaml` and `~/.data-agent/mcp_servers.yaml`

### Skills: `data_agent/skills/`

- `SkillLoader` discovers `SKILL.md` files in `~/.data-agent/skills/` (global) and `project/skills/` (project-level, overrides global)
- Skills have YAML frontmatter (name, trigger_keywords, tools_required, task_template) + instruction body
- Loaded skills get injected into the system prompt as `<skill>` XML blocks

### Web GUI: `data_agent/web/`

Flask app with SSE-based real-time updates. `EventQueue` bridges sync AgentLoop to SSE responses. Blueprints: `chat.py`, `sessions.py`, `objects.py`, `tasks.py`, `artifacts.py`, `commands.py`, `uploads.py`.

### Lifecycle: `data_agent/lifecycle.py`

`AgentLifecycle.initialize()` → validate config → setup logging → discover native tools → register middleware hooks. MCP and skill discovery deferred to `AgentLoop.__init__()`.

## Key Patterns

- **Module-level singletons**: Config, ToolRegistry, DomainKnowledge, ExperienceLog all use `get_X()` accessor functions with lazy init
- **Decorator-based registration**: Tools use `@registry.register(name=..., description=..., capability=...)` 
- **Three-layer knowledge merge**: Global → Object → Session, with promotion/migration APIs
- **Context management**: `AgentContext` (agent/context.py) tracks per-turn state (active groups, executed tools)
- **Windows compatibility**: UTF-8 reconfiguration on win32, `ThreadPoolExecutor`-based timeouts instead of `signal`
- **LLM provider**: Uses litellm for multi-provider support. `LITELLM_LOCAL_MODEL_COST_MAP=true` avoids network calls at init

## Project Directory Structure

```
project/              # User data workspace
  data/               # Processed datasets
  inbox/              # Raw uploaded files
  knowledge/          # domain_knowledge.yaml, experience_log.yaml, project_rules.md
  skills/             # Project-level SKILL.md files
  objects/            # Per-object knowledge (object_name/knowledge/)
  mcp_servers.yaml    # Project-level MCP server configs
sessions/             # Session data (analyses, charts, knowledge per session)
tests/                # pytest test suite
reference/            # Reference code and docs (not part of runtime)
```
