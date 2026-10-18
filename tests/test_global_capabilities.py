import json
from pathlib import Path


def _reset_config(monkeypatch, tmp_path):
    import data_agent.config as config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(config, "_config", None)


def test_skill_resolution_is_global_only(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.skills.loader import SkillLoader

    cfg = get_config()
    (cfg.global_skills_dir / "global_skill").mkdir(parents=True)
    (cfg.global_skills_dir / "global_skill" / "SKILL.md").write_text(
        "---\nname: global_skill\ndescription: Global skill\n---\nUse global behavior.",
        encoding="utf-8",
    )
    (cfg.skills_dir / "workspace_skill").mkdir(parents=True)
    (cfg.skills_dir / "workspace_skill" / "SKILL.md").write_text(
        "---\nname: workspace_skill\ndescription: Workspace skill\n---\nUse workspace behavior.",
        encoding="utf-8",
    )

    assert resolve_skills_dirs() == [cfg.global_skills_dir]

    loader = SkillLoader(resolve_skills_dirs())
    loader.discover()
    assert loader.get("global_skill") is not None
    assert loader.get("workspace_skill") is None


def test_disabled_skill_is_not_loaded_or_injected(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.skills.loader import SkillLoader

    cfg = get_config()
    skill_dir = cfg.global_skills_dir / "disabled_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: disabled_skill\ndescription: Disabled\nenabled: false\n---\nSecret instructions.",
        encoding="utf-8",
    )

    loader = SkillLoader(resolve_skills_dirs())
    loader.discover()

    assert loader.get("disabled_skill").enabled is False
    assert "disabled" in loader.load("disabled_skill").lower()
    assert loader.get_prompt_injections() == ""


def test_mcp_resolution_is_global_only(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.config_resolver import resolve_mcp_config

    cfg = get_config()
    cfg.global_mcp_config_path.write_text(
        "servers:\n"
        "  - name: global_server\n"
        "    transport: stdio\n"
        "    command: global-cmd\n",
        encoding="utf-8",
    )
    cfg.mcp_config_path.write_text(
        "servers:\n"
        "  - name: workspace_server\n"
        "    transport: stdio\n"
        "    command: workspace-cmd\n",
        encoding="utf-8",
    )

    resolved = resolve_mcp_config()
    assert [server.name for server in resolved.servers] == ["global_server"]


def test_mcp_management_tools_edit_global_config(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    import data_agent.tools.mcp_tools as mcp_tools
    from data_agent.config import get_config
    from data_agent.mcp.config import load_mcp_config

    cfg = get_config()
    assert "saved globally" in str(mcp_tools.add_mcp_server("fs", "stdio", command="npx"))

    config = load_mcp_config(cfg.global_mcp_config_path)
    assert config.servers[0].name == "fs"
    assert config.servers[0].enabled is True

    mcp_tools.disable_mcp_server("fs")
    config = load_mcp_config(cfg.global_mcp_config_path)
    assert config.servers[0].enabled is False

    listed = json.loads(mcp_tools.list_mcp_servers())
    assert listed["servers"][0]["name"] == "fs"

    mcp_tools.delete_mcp_server("fs")
    config = load_mcp_config(cfg.global_mcp_config_path)
    assert config.servers == []


def test_web_capability_admin_uses_global_scope(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.web.app import create_app

    cfg = get_config()
    skill_dir = cfg.global_skills_dir / "web_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: web_skill\ndescription: Web Skill\n---\nUse web skill.",
        encoding="utf-8",
    )

    app = create_app()
    client = app.test_client()

    skills = client.get("/api/skills")
    assert skills.status_code == 200
    assert skills.get_json()[0]["name"] == "web_skill"

    disabled = client.post("/api/skills/web_skill/disable")
    assert disabled.status_code == 200
    assert "disabled" in disabled.get_json()["message"].lower()

    added = client.post(
        "/api/mcp/servers",
        json={"name": "web_mcp", "transport": "stdio", "command": "npx"},
    )
    assert added.status_code == 200

    servers = client.get("/api/mcp/servers")
    assert servers.status_code == 200
    assert servers.get_json()[0]["name"] == "web_mcp"


def test_actual_agent_loops_isolate_skill_loading_and_context_dispatch(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)
    import data_agent.agent.loop as module
    from data_agent.agent.context import use_agent_context
    from data_agent.skills.loader import SkillLoader
    from data_agent.tools import skill_tools
    file=tmp_path / "skills/fixture/SKILL.md"
    file.parent.mkdir(parents=True)
    file.write_text("---\nname: fixture\nenabled: true\n---\nSESSION_PRIVATE_MARKER", encoding="utf-8")
    owner=SkillLoader(file.parent.parent);owner.discover()
    monkeypatch.setattr(module,"_skill_loader",owner)
    monkeypatch.setattr(module,"resolve_skills_dirs",lambda:[file.parent.parent],raising=False)
    import data_agent.config_resolver as resolver
    monkeypatch.setattr(resolver,"resolve_skills_dirs",lambda:[file.parent.parent])
    a=module.AgentLoop(client=object(),session_id="skills_a")
    b=module.AgentLoop(client=object(),session_id="skills_b")
    with use_agent_context(a.context):
        result=skill_tools.load_skill("fixture")
        assert result.data["state"]["loaded"] is True
        assert json.loads(skill_tools.list_skills())["skills"][0]["loaded"] is True
    assert "SESSION_PRIVATE_MARKER" in a._skill_loader.get_prompt_injections()
    assert b._skill_loader.get_prompt_injections()==""
    with use_agent_context(b.context):
        assert json.loads(skill_tools.list_skills())["skills"][0]["loaded"] is False
        skill_tools.unload_skill("fixture")
    assert a._skill_loader.list_loaded()
    with use_agent_context(b.context):skill_tools.load_skill("fixture")
    with use_agent_context(a.context):skill_tools.unload_skill("fixture")
    assert not a._skill_loader.list_loaded() and b._skill_loader.list_loaded()
    assert a._skill_loader._skills is b._skill_loader._skills


def test_global_skill_admin_invalidates_all_session_loads_without_resurrection(tmp_path, monkeypatch):
    _reset_config(monkeypatch,tmp_path)
    import data_agent.agent.loop as module
    import data_agent.config_resolver as resolver
    from data_agent.skills.loader import SkillLoader
    from data_agent.web.app import create_app
    file=tmp_path/"skills/fixture/SKILL.md";file.parent.mkdir(parents=True)
    file.write_text("---\nname: fixture\nenabled: true\n---\nPRIVATE",encoding="utf-8")
    owner=SkillLoader(file.parent.parent);owner.discover();monkeypatch.setattr(module,"_skill_loader",owner)
    monkeypatch.setattr(resolver,"resolve_skills_dirs",lambda:[file.parent.parent])
    a=module.AgentLoop(client=object(),session_id="admin_a");b=module.AgentLoop(client=object(),session_id="admin_b")
    a._skill_loader.load("fixture");b._skill_loader.load("fixture")
    with create_app().test_client() as http:
        assert http.post("/api/skills/fixture/disable").status_code==200
        assert not a._skill_loader.list_loaded() and not b._skill_loader.list_loaded()
        assert not a._skill_loader.get_prompt_injections() and not b._skill_loader.get_prompt_injections()
        http.post("/api/skills/fixture/enable")
        assert not a._skill_loader.list_loaded() and not b._skill_loader.list_loaded()
        a._skill_loader.load("fixture");b._skill_loader.load("fixture")
        assert http.delete("/api/skills/fixture").status_code==200
        assert not file.exists() and not a._skill_loader.list_loaded() and not b._skill_loader.list_loaded()
        assert a._skill_loader.get("fixture") is None and b._skill_loader.get("fixture") is None


# S3 rules: a failed durable update must never become an in-memory prompt rule.
import pytest


def _rule_write_fault(monkeypatch, path, content, fault):
    text_write,bytes_write,replace = Path.write_text,Path.write_bytes,Path.replace
    state={"fired":False}
    def candidate(p,value):
        return p.parent==path.parent and value==(content.encode("utf-8") if isinstance(value,bytes) else content)
    def write_text(p,value,*args,**kw):
        if not state["fired"] and p==path and candidate(p,value):
            state["fired"]=True
            if fault=="partial":text_write(p,value[:2],*args,**kw)
            elif fault=="after_replace":text_write(p,value,*args,**kw)
            raise OSError("injected rule write "+fault)
        return text_write(p,value,*args,**kw)
    def write_bytes(p,value,*args,**kw):
        if not state["fired"] and candidate(p,value) and fault in {"deny","partial"}:
            state["fired"]=True
            if fault=="partial":bytes_write(p,value[:2],*args,**kw)
            raise OSError("injected rule write "+fault)
        return bytes_write(p,value,*args,**kw)
    def commit(p,target,*args,**kw):
        if not state["fired"] and Path(target)==path and p.read_bytes()==content.encode("utf-8"):
            state["fired"]=True
            if fault=="after_replace":replace(p,target,*args,**kw)
            raise OSError("injected rule write "+fault)
        return replace(p,target,*args,**kw)
    monkeypatch.setattr(Path,"write_text",write_text)
    monkeypatch.setattr(Path,"write_bytes",write_bytes)
    monkeypatch.setattr(Path,"replace",commit)
    return state


@pytest.mark.parametrize("existing",[False,True])
@pytest.mark.parametrize("fault",["deny","partial","before_replace","after_replace"])
def test_rule_persistence_registry_failure_preserves_disk_cache_and_next_prompt(tmp_path,monkeypatch,existing,fault):
    from data_agent.knowledge.rules import ProjectRules
    from data_agent.tools import knowledge_tools
    from data_agent.tools.registry import registry
    from data_agent.agent.context import AgentContext,use_agent_context
    from data_agent.session.workspace import Workspace
    path=tmp_path/"knowledge/project_rules.md";path.parent.mkdir(parents=True)
    old="OLD_RULE：按真实来源回答。\n";new="NEW_RULE：不应注入失败的规则。\n"
    if existing:path.write_bytes(old.encode("utf-8"))
    rules=ProjectRules(path=path)
    if existing:assert rules.content==old
    previous=(rules._content,rules._loaded)
    monkeypatch.setattr(knowledge_tools,"_project_rules",rules)
    fault_state=_rule_write_fault(monkeypatch,path,new,fault)
    with use_agent_context(AgentContext(session_id="rules_current",workspace=Workspace())):
        result=registry.execute("update_project_rules",{"content":new})
        assert fault_state["fired"] and json.loads(result.summary).get("error"),result.summary
        assert (rules._content,rules._loaded)==previous
        assert path.exists()==existing
        if existing:
            assert path.read_bytes()==old.encode("utf-8")
            assert registry.execute("show_project_rules",{}).summary=="<project_rules>\n"+old+"\n</project_rules>"
            assert ProjectRules(path=path).content==old
    assert not list(path.parent.glob(".atomic-*.tmp"))


@pytest.mark.parametrize("content",["", "中文\n规则二", "line1\r\nline2\rfinal", "x"*10000])
def test_rule_persistence_update_matches_exact_durable_reload(tmp_path,content):
    from data_agent.knowledge.rules import ProjectRules
    path=tmp_path/"project_rules.md";rules=ProjectRules(path=path)
    result=rules.update(content)
    assert "已更新" in result
    assert rules.content==ProjectRules(path=path).content==content
    assert path.read_bytes()==content.encode("utf-8")


@pytest.mark.parametrize("fault",["deny","partial","before_replace","after_replace"])
def test_rule_persistence_default_creation_failure_has_no_ghost_file_or_cache(tmp_path,monkeypatch,fault):
    from data_agent.knowledge.rules import ProjectRules
    path=tmp_path/"project_rules.md";rules=ProjectRules(path=path)
    state=_rule_write_fault(monkeypatch,path,rules._default_rules(),fault)
    with pytest.raises(OSError):rules.load()
    assert state["fired"] and not path.exists() and rules._content=="" and not rules._loaded


def test_rule_persistence_show_merges_only_global_and_current_session(tmp_path,monkeypatch):
    from data_agent.config import get_config
    from data_agent.knowledge.rules import ProjectRules
    from data_agent.tools import knowledge_tools
    from data_agent.tools.registry import registry
    from data_agent.agent.context import AgentContext,use_agent_context
    from data_agent.session.workspace import Workspace
    cfg=get_config();monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions")
    rules=ProjectRules(path=tmp_path/"global_rules.md");rules.update("GLOBAL_RULE")
    rules.update_session_rules("rules_A","LOCAL_A")
    rules.update_session_rules("rules_B","LOCAL_B")
    monkeypatch.setattr(knowledge_tools,"_project_rules",rules)
    for sid,own,other in [("rules_A","LOCAL_A","LOCAL_B"),("rules_B","LOCAL_B","LOCAL_A")]:
        with use_agent_context(AgentContext(session_id=sid,workspace=Workspace())):
            value=registry.execute("show_project_rules",{}).summary
            assert "GLOBAL_RULE" in value and own in value and other not in value


@pytest.mark.parametrize("mode",["session","object","promote","migrate"])
@pytest.mark.parametrize("existing",[False,True])
@pytest.mark.parametrize("fault",["partial","after_replace"])
def test_rule_persistence_shared_writer_preserves_helper_destination_and_source(tmp_path,monkeypatch,mode,existing,fault):
    from data_agent.config import get_config
    from data_agent.knowledge.rules import ProjectRules
    cfg=get_config();monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions");monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    rules=ProjectRules(path=tmp_path/"global.md")
    source=rules._session_knowledge_path("source") if mode=="promote" else rules._object_knowledge_path("source")
    source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes("SOURCE\r\n规则".encode("utf-8"))
    target=rules._session_knowledge_path("target") if mode=="session" else rules._object_knowledge_path("target")
    target.parent.mkdir(parents=True,exist_ok=True)
    old="OLD\r\n规则";new="NEW\r\n规则"
    if existing:target.write_bytes(old.encode("utf-8"))
    expected=((old+"\n---\n") if existing else "")+"SOURCE\r\n规则" if mode in {"promote","migrate"} else new
    state=_rule_write_fault(monkeypatch,target,expected,fault)
    with pytest.raises(OSError):
        if mode=="session":rules.update_session_rules("target",new)
        elif mode=="object":rules.update_object_rules("target",new)
        elif mode=="promote":rules.promote_to_object("source","target")
        else:rules.migrate_between_objects("source","source","target")
    assert state["fired"] and target.exists()==existing
    if existing:assert target.read_bytes()==old.encode("utf-8")
    assert source.read_bytes()=="SOURCE\r\n规则".encode("utf-8")
    assert not list(target.parent.glob(".atomic-*.tmp"))


@pytest.mark.parametrize("mode",["session","object","promote","migrate"])
def test_rule_persistence_shared_writer_exact_merge_and_reload(tmp_path,monkeypatch,mode):
    from data_agent.config import get_config
    from data_agent.knowledge.rules import ProjectRules
    cfg=get_config();monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions");monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    rules=ProjectRules(path=tmp_path/"global.md");text="中文\r\n第二行"
    if mode=="session":
        rules.update_session_rules("target",text);path=rules._session_knowledge_path("target");loaded=rules._load_session_rules("target")
    elif mode=="object":
        rules.update_object_rules("target",text);path=rules._object_knowledge_path("target");loaded=rules._load_object_rules("target")
    else:
        rules.update_object_rules("target","OLD")
        if mode=="promote":rules.update_session_rules("source",text);assert rules.promote_to_object("source","target")=={"promoted":True}
        else:rules.update_object_rules("source",text);assert rules.migrate_between_objects("source","source","target")=={"migrated":True}
        text="OLD\n---\n"+text;path=rules._object_knowledge_path("target");loaded=rules._load_object_rules("target")
    assert path.read_bytes()==text.encode("utf-8") and loaded==text
