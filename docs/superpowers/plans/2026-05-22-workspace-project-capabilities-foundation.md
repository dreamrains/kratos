# Workspace Project Capabilities Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pre-release object/project ambiguity with a clean workspace/project model, globalize skills and MCP, and remove project-level knowledge injection while deferring the full knowledge and memory product.

**Architecture:** Introduce `workspace` as the local filesystem root and `project` as the user-facing organization container. Replace active object APIs and code paths with project equivalents, make skills and MCP read only from global config, and migrate old project/object knowledge into a non-injected review area.

**Tech Stack:** Python, Flask blueprints, Alpine.js frontend, YAML/JSON file persistence, pytest.

---

## File Structure

- Modify `src/data_agent/config.py`: add `workspace_dir`, prefer `WORKSPACE_DIR`, keep `PROJECT_DIR` as a development fallback.
- Modify `src/data_agent/config_resolver.py`: remove project-level skill and MCP merging.
- Rename or replace `src/data_agent/object_manager.py` with `src/data_agent/project_manager.py`: make project storage primary.
- Modify `src/data_agent/session/history.py`: make `project_name` canonical and remove active object promotion paths.
- Modify `src/data_agent/session/workspace.py`: rename object-facing methods and fields to project-facing names.
- Modify `src/data_agent/agent/loop.py`: use workspace/project terminology, read global MCP config, remove object knowledge assumptions.
- Modify `src/data_agent/tools/knowledge_tools.py`: remove project/object knowledge layer from prompt sources.
- Modify `src/data_agent/knowledge/rules.py`, `domain.py`, `experience.py`: remove project/object merge and promotion APIs from active use.
- Modify `src/data_agent/skills/loader.py` and `installer.py`: use global skill directory only and add enabled metadata support.
- Modify `src/data_agent/mcp/config.py`: support global server CRUD persistence.
- Modify `src/data_agent/tools/skill_tools.py` and `mcp_tools.py`: expose management operations.
- Modify `src/data_agent/web/blueprints/objects.py`: replace with project routes or keep file name temporarily with project-only implementation.
- Add or modify Web routes for skills/MCP capability management.
- Modify `src/data_agent/web/static/js/app.js`, `templates/index.html`, and `static/css/app.css`: align UI with project terminology and add settings/capabilities surfaces as needed.
- Modify tests under `tests/`: update terminology, storage paths, and add regression coverage.
- Modify `README.md`, `docs/user_guide.md`, and `CLAUDE.md`: update architecture docs.

---

### Task 1: Configuration Boundary

**Files:**
- Modify: `src/data_agent/config.py`
- Test: `tests/test_workspace_config.py`

- [ ] **Step 1: Write failing tests for workspace config**

Create `tests/test_workspace_config.py`:

```python
from pathlib import Path

from data_agent.config import AgentConfig


def test_workspace_dir_defaults_to_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AgentConfig(_env_file=None)
    assert cfg.workspace_resolved == tmp_path / "workspace"


def test_workspace_dir_prefers_workspace_env(tmp_path, monkeypatch):
    target = tmp_path / "custom_workspace"
    monkeypatch.setenv("WORKSPACE_DIR", str(target))
    cfg = AgentConfig(_env_file=None)
    assert cfg.workspace_resolved == target


def test_project_dir_is_development_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy_project"
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("PROJECT_DIR", str(legacy))
    cfg = AgentConfig(_env_file=None)
    assert cfg.workspace_resolved == legacy
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_workspace_config.py -v`

Expected: fails because `workspace_dir` does not exist and default root is still `project`.

- [ ] **Step 3: Implement workspace config**

In `AgentConfig`, add:

```python
workspace_dir: Path = Field(alias="WORKSPACE_DIR", default=Path("./workspace"))
project_dir: Optional[Path] = Field(alias="PROJECT_DIR", default=None)
```

Update `project_resolved` to become a compatibility alias for `workspace_resolved`:

```python
@property
def workspace_resolved(self) -> Path:
    p = self.workspace_dir
    if self.project_dir is not None and self.workspace_dir == Path("./workspace"):
        p = self.project_dir
    if not p.is_absolute():
        p = Path.cwd() / p
    p.mkdir(parents=True, exist_ok=True)
    return p

@property
def project_resolved(self) -> Path:
    return self.workspace_resolved
```

Update all root subdirectory properties to use `workspace_resolved`.

- [ ] **Step 4: Run config tests**

Run: `pytest tests/test_workspace_config.py -v`

Expected: all tests pass.

---

### Task 2: Project Manager Replacement

**Files:**
- Create: `src/data_agent/project_manager.py`
- Modify: `src/data_agent/object_manager.py`
- Test: `tests/test_project_manager.py`

- [ ] **Step 1: Write failing project manager tests**

Create `tests/test_project_manager.py`:

```python
from data_agent.config import AgentConfig
import data_agent.config as config
from data_agent.project_manager import ProjectManager


def test_project_manager_uses_projects_dir(tmp_path):
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", _env_file=None)
    mgr = ProjectManager()
    created = mgr.create("revenue", description="Revenue analysis")
    assert created["name"] == "revenue"
    assert (tmp_path / "workspace" / "projects" / "revenue" / "meta.yaml").exists()


def test_project_bind_unbind_session(tmp_path):
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions", _env_file=None)
    mgr = ProjectManager()
    mgr.create("revenue")
    mgr.bind_session("revenue", "s1")
    assert "s1" in mgr.get("revenue")["sessions"]
    mgr.unbind_session("revenue", "s1")
    assert "s1" not in mgr.get("revenue")["sessions"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_project_manager.py -v`

Expected: fails because `project_manager.py` does not exist.

- [ ] **Step 3: Create `ProjectManager`**

Move the active implementation from `ObjectManager` into `ProjectManager` and update names:

```python
class ProjectManager:
    def __init__(self, projects_dir: Optional[Path] = None):
        cfg = get_config()
        self._projects_dir = projects_dir or cfg.projects_dir
```

Use `projects_dir / name`, project-oriented messages, and no knowledge initialization inside project creation.

- [ ] **Step 4: Turn `ObjectManager` into a thin deprecated alias**

Keep `object_manager.py` only if imports still require it:

```python
from data_agent.project_manager import ProjectManager, get_project_manager

ObjectManager = ProjectManager


def get_object_manager() -> ProjectManager:
    return get_project_manager()
```

- [ ] **Step 5: Run project manager tests**

Run: `pytest tests/test_project_manager.py -v`

Expected: all tests pass.

---

### Task 3: Session Project Binding

**Files:**
- Modify: `src/data_agent/session/history.py`
- Test: `tests/test_project_intent_context.py`

- [ ] **Step 1: Update tests to expect project-only metadata**

Change tests that assert both `project_name` and `object_name` to assert only `project_name`. Add:

```python
def test_session_meta_uses_project_name_only(tmp_path):
    import data_agent.config as config
    from data_agent.config import AgentConfig
    from data_agent.session.history import save_session, load_session

    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions", _env_file=None)
    save_session([{"role": "user", "content": "hello"}], "s1", extra_meta={"project_name": "revenue"})
    loaded = load_session("s1")
    assert loaded["project_name"] == "revenue"
    assert "object_name" not in loaded
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_project_intent_context.py -v`

Expected: fails where old object alias is still expected.

- [ ] **Step 3: Remove object metadata as active output**

In `save_session`, write `project_name` only. In `load_session`, read legacy `object_name` as fallback but return `project_name` only:

```python
project_name = meta.get("project_name") or meta.get("object_name")
```

Remove knowledge promotion from bind behavior. Keep `promote_session_knowledge_to_project` out of active command flow.

- [ ] **Step 4: Run session tests**

Run: `pytest tests/test_project_intent_context.py tests/test_task_manager_scope.py -v`

Expected: all updated tests pass.

---

### Task 4: Project API and UI Terminology

**Files:**
- Modify: `src/data_agent/web/blueprints/objects.py`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/templates/index.html`
- Test: `tests/test_web_overhaul.py`, `tests/test_web_workbench_parity.py`

- [ ] **Step 1: Update API tests**

Update tests to use `/api/projects` only. Remove `/api/objects` expectations unless a short development alias remains.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_web_overhaul.py tests/test_web_workbench_parity.py -v`

Expected: failures around old route names or object fields.

- [ ] **Step 3: Make project routes primary**

Update the blueprint to import `get_project_manager` and expose:

```text
GET /api/projects
POST /api/projects
POST /api/projects/bind
POST /api/projects/unbind
POST /api/projects/<name>/rename
DELETE /api/projects/<name>
```

- [ ] **Step 4: Rename frontend state**

In `app.js`, rename active state:

```javascript
projects: []
activeProjectName: ''
expandedProjects: {}
projectGroups: {}
```

Update fetch calls to `/api/projects`.

- [ ] **Step 5: Run web tests**

Run: `pytest tests/test_web_overhaul.py tests/test_web_workbench_parity.py -v`

Expected: all updated tests pass.

---

### Task 5: Global Skills Only

**Files:**
- Modify: `src/data_agent/config_resolver.py`
- Modify: `src/data_agent/skills/loader.py`
- Modify: `src/data_agent/skills/installer.py`
- Modify: `src/data_agent/tools/skill_tools.py`
- Test: `tests/test_skills_global.py`

- [ ] **Step 1: Write failing skill scope tests**

Create `tests/test_skills_global.py`:

```python
from pathlib import Path

import data_agent.config as config
from data_agent.config import AgentConfig
from data_agent.config_resolver import resolve_skills_dirs
from data_agent.skills.loader import SkillLoader


def test_resolve_skills_dirs_global_only(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", _env_file=None)
    dirs = resolve_skills_dirs()
    assert dirs == [tmp_path / ".data-agent" / "skills"]


def test_disabled_skill_is_not_available(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo\n---\nBody", encoding="utf-8")
    (skill_dir / "skill.yaml").write_text("enabled: false\n", encoding="utf-8")
    loader = SkillLoader([tmp_path / "skills"])
    loader.discover()
    assert [s.name for s in loader.list_available()] == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_skills_global.py -v`

Expected: fails because resolver still returns global plus project and loader ignores metadata.

- [ ] **Step 3: Resolve global skills only**

Change `resolve_skills_dirs()` to:

```python
return [get_config().global_skills_dir]
```

- [ ] **Step 4: Add skill enabled metadata**

In `SkillLoader.discover`, skip a skill when `skill.yaml` exists and contains `enabled: false`.

- [ ] **Step 5: Add management tools**

Add registry tools:

- `enable_skill`
- `disable_skill`
- `delete_skill`
- `view_skill`

Each updates or reads global skill files only.

- [ ] **Step 6: Run skill tests**

Run: `pytest tests/test_skills_global.py -v`

Expected: all tests pass.

---

### Task 6: Global MCP Only

**Files:**
- Modify: `src/data_agent/config_resolver.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/tools/mcp_tools.py`
- Test: `tests/test_mcp_global.py`

- [ ] **Step 1: Write failing MCP global tests**

Create `tests/test_mcp_global.py`:

```python
import data_agent.config as config
from data_agent.config import AgentConfig
from data_agent.config_resolver import resolve_mcp_config
from data_agent.mcp.config import MCPConfig, MCPServerConfig, save_mcp_config


def test_resolve_mcp_config_global_only(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", _env_file=None)
    cfg = config.get_config()
    save_mcp_config(
        MCPConfig(servers=[MCPServerConfig(name="global", transport="stdio", command="python")]),
        cfg.global_mcp_config_path,
    )
    save_mcp_config(
        MCPConfig(servers=[MCPServerConfig(name="project", transport="stdio", command="python")]),
        cfg.mcp_config_path,
    )
    resolved = resolve_mcp_config()
    assert [s.name for s in resolved.servers] == ["global"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_mcp_global.py -v`

Expected: fails because project MCP config is merged.

- [ ] **Step 3: Resolve global MCP only**

Change `resolve_mcp_config()` to load only `cfg.global_mcp_config_path`.

- [ ] **Step 4: Update AgentLoop MCP initialization**

In `_ensure_mcp_initialized`, replace direct `cfg.mcp_config_path` loading with:

```python
from data_agent.config_resolver import resolve_mcp_config
mcp_config = resolve_mcp_config()
```

Do not require `cfg.mcp_config_path.exists()`.

- [ ] **Step 5: Add MCP management tools**

Add registry tools:

- `enable_mcp_server`
- `disable_mcp_server`
- `delete_mcp_server`
- `view_mcp_server`
- `reload_mcp_servers`

Use `cfg.global_mcp_config_path`.

- [ ] **Step 6: Run MCP tests**

Run: `pytest tests/test_mcp_global.py -v`

Expected: all tests pass.

---

### Task 7: Remove Project Knowledge Injection

**Files:**
- Modify: `src/data_agent/tools/knowledge_tools.py`
- Modify: `src/data_agent/knowledge/rules.py`
- Modify: `src/data_agent/knowledge/domain.py`
- Modify: `src/data_agent/knowledge/experience.py`
- Modify: `src/data_agent/agent/loop.py`
- Test: `tests/test_knowledge_scope.py`

- [ ] **Step 1: Write failing knowledge scope tests**

Create `tests/test_knowledge_scope.py`:

```python
import data_agent.config as config
from data_agent.config import AgentConfig
from data_agent.knowledge.rules import ProjectRules


def test_project_rules_prompt_excludes_project_layer(tmp_path):
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions", _env_file=None)
    cfg = config.get_config()
    (cfg.knowledge_dir / "project_rules.md").write_text("global rule", encoding="utf-8")
    project_rules_path = cfg.projects_dir / "revenue" / "knowledge" / "project_rules.md"
    project_rules_path.parent.mkdir(parents=True)
    project_rules_path.write_text("project rule should not inject", encoding="utf-8")

    prompt = ProjectRules().get_rules_for_prompt(object_name="revenue", session_id=None)
    assert "global rule" in prompt
    assert "project rule should not inject" not in prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_knowledge_scope.py -v`

Expected: fails because object/project layer is still loaded.

- [ ] **Step 3: Remove active object/project knowledge loading**

Update `get_rules_for_prompt`, `DomainKnowledge.get_merged`, and `ExperienceLog.get_merged_entries` to use global plus session only. Leave legacy helper methods only if tests still import them, but remove them from active prompt-building.

- [ ] **Step 4: Ensure project metadata is context only**

In `AgentLoop._build_system_prompt`, include project name/description as session context if useful, but do not call project knowledge paths.

- [ ] **Step 5: Run knowledge tests**

Run: `pytest tests/test_knowledge_scope.py tests/test_prompt_system.py -v`

Expected: all updated tests pass.

---

### Task 8: Migration Review Command

**Files:**
- Create: `src/data_agent/migration.py`
- Modify: `src/data_agent/main.py` or CLI entry where startup commands are registered
- Test: `tests/test_workspace_migration.py`

- [ ] **Step 1: Write failing migration tests**

Create `tests/test_workspace_migration.py`:

```python
import data_agent.config as config
from data_agent.config import AgentConfig
from data_agent.migration import migrate_legacy_workspace


def test_legacy_object_knowledge_moves_to_review(tmp_path):
    legacy = tmp_path / "project"
    old_knowledge = legacy / "objects" / "revenue" / "knowledge"
    old_knowledge.mkdir(parents=True)
    (old_knowledge / "project_rules.md").write_text("old project rule", encoding="utf-8")

    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", PROJECT_DIR=legacy, _env_file=None)
    result = migrate_legacy_workspace()

    review = tmp_path / ".data-agent" / "knowledge" / "migration-review"
    assert result["knowledge_review_files"] >= 1
    assert any("old project rule" in p.read_text(encoding="utf-8") for p in review.glob("*.md"))
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_workspace_migration.py -v`

Expected: fails because migration module does not exist.

- [ ] **Step 3: Implement migration helper**

Create `migrate_legacy_workspace()` that:

- moves or copies `project/objects/*` to `workspace/projects/*`
- writes legacy knowledge into `~/.data-agent/knowledge/migration-review/*.md`
- does not add migrated knowledge to prompt injection
- returns counts for migrated projects, skills, MCP servers, and review files

- [ ] **Step 4: Run migration tests**

Run: `pytest tests/test_workspace_migration.py -v`

Expected: all tests pass.

---

### Task 9: Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/user_guide.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture language**

Replace active references to:

- `project/` local root with `workspace/`
- object management with project management
- project-level skills with global skills
- project-level MCP with global MCP
- three-layer knowledge with global plus session knowledge

- [ ] **Step 2: Add migration note**

Document that the app is pre-release and migration is direct:

```text
If you have local development data under ./project, run the migration helper before continuing. Project-level knowledge is moved to migration-review and is not injected automatically.
```

- [ ] **Step 3: Verify docs mention no active object concept**

Run: `rg -n "object|Object|objects|PROJECT_DIR|project/skills|project/mcp_servers|three-layer|三层" README.md docs CLAUDE.md`

Expected: remaining hits are either historical migration notes or deliberate code terms.

---

### Task 10: Full Verification

**Files:**
- No direct edits unless verification finds failures.

- [ ] **Step 1: Run focused suite**

Run:

```bash
pytest tests/test_workspace_config.py tests/test_project_manager.py tests/test_project_intent_context.py tests/test_skills_global.py tests/test_mcp_global.py tests/test_knowledge_scope.py tests/test_workspace_migration.py -v
```

Expected: all pass.

- [ ] **Step 2: Run web and prompt regression tests**

Run:

```bash
pytest tests/test_web_overhaul.py tests/test_web_workbench_parity.py tests/test_prompt_system.py -v
```

Expected: all pass.

- [ ] **Step 3: Run full test suite**

Run:

```bash
pytest
```

Expected: all pass or unrelated existing failures documented.

- [ ] **Step 4: Manual smoke test**

Run the app, create a project, bind a session, list skills, list MCP servers, and confirm no project-level knowledge is injected.

Expected: project organization works, skills/MCP are global, and old object terminology is absent from visible UI.
