"""Skill management tools."""

from __future__ import annotations

import json

from data_agent.tools.registry import registry, ToolResult


def _loader():
    from data_agent.agent.loop import get_skill_loader

    return get_skill_loader()


def _operate(name,action):
    from data_agent.agent.publication.native import _skill_state
    loader=_loader()
    if loader.get(name) is None:return json.dumps({"error":"Unknown skill: "+name})
    if action=="load_skill":summary=loader.load(name)
    elif action=="unload_skill":summary=loader.unload(name)
    elif action=="enable_skill":summary=loader.set_enabled(name,True)
    elif action=="disable_skill":summary=loader.set_enabled(name,False)
    else:summary=loader.uninstall(name)
    state=_skill_state(name)
    key,value={"load_skill":("loaded",True),"unload_skill":("loaded",False),"enable_skill":("enabled",True),"disable_skill":("enabled",False),"delete_skill":("exists",False)}[action]
    if state[key]!=value:return json.dumps({"error":summary})
    return ToolResult(summary=summary,data={"skill":name,"state":state})

@registry.register(
    name="load_skill",
    capability={"capability_id":"system.load_skill","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Load an enabled global skill into the current agent context.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def load_skill(name: str) -> str:
    return _operate(name,"load_skill")


@registry.register(
    name="unload_skill",
    capability={"capability_id":"system.unload_skill","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Unload a skill from the current agent context without deleting it.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def unload_skill(name: str) -> str:
    return _operate(name,"unload_skill")


def _list_skills_result(loader):
    return {"skills": [
        {"name": skill.name, "description": skill.description,
         "enabled": skill.enabled, "loaded": skill.name in loader._loaded,
         "scope": skill.scope}
        for skill in loader.list_available()
    ]}


def _skills_catalog_snapshot(context):
    """Read the configured source and the current session's existing catalogue."""
    import hashlib
    from pathlib import Path
    from dataclasses import asdict
    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.agent.context import get_current_context
    from data_agent.agent.publication.contracts import encode, digest
    if context is None or get_current_context() is not context:
        raise ValueError("Skills catalogue requires the current session")
    loader = _loader()
    if loader.session_id != context.session_id:
        raise ValueError("Skills loading state belongs to another session")
    configured = resolve_skills_dirs()
    if [str(p.resolve()) for p in loader._dirs] != [str(p.resolve()) for p in configured]:
        raise ValueError("Skills directory configuration changed")
    directories=[]; files=[]; discovered={}
    def record(skill):
        row=asdict(skill); row["path"]=str(skill.path.resolve()); return row
    def fail(error):
        raise error
    for root in configured:
        canonical=root.resolve()
        try: root.stat()
        except FileNotFoundError:
            directories.append({"path":str(canonical),"exists":False}); continue
        if not root.is_dir(): raise ValueError("Configured Skills source is not a directory")
        directories.append({"path":str(canonical),"exists":True})
        paths=[]
        for parent,dirs,names in root.walk(on_error=fail,follow_symlinks=False):
            paths.extend(parent/n for n in names if Path(n).match("SKILL.md"))
        for path in sorted(paths):
            resolved=path.resolve()
            if not resolved.is_relative_to(canonical):
                raise ValueError("Skill source leaves its configured directory")
            raw=path.read_bytes(); parsed=loader._parse_skill(path)
            if parsed is None: raise ValueError("Skill source could not be parsed")
            if path.read_bytes()!=raw: raise ValueError("Skill source changed during read")
            discovered[parsed.name]=record(parsed)
            files.append({"path":str(resolved),"sha256":"sha256:"+hashlib.sha256(raw).hexdigest()})
    cached={skill.name:record(skill) for skill in loader.list_available()}
    if encode(list(cached.values())) != encode(list(discovered.values())):
        # Both owners enumerate configured roots and sorted files in the same order.
        raise ValueError("Discovered Skills catalogue does not match its current files")
    result=_list_skills_result(loader)
    binding={"schema_version":"skills_catalog_binding.v1","session_id":context.session_id,
             "permission_scope":"global_catalog_current_session_loading",
             "directories":directories,"files":files,"snapshot_sha256":digest(encode(result))}
    return result,binding


def _capture_skills_binding(context):
    try: return _skills_catalog_snapshot(context)[1]
    except (OSError,ValueError,TypeError): return None


def _verify_skills_binding(context,receipt,result):
    from data_agent.agent.publication.contracts import validate_skills_binding,encode
    binding=receipt.get("skills_binding");validate_skills_binding(binding,context.session_id)
    if receipt["tool_name"]!="list_skills" or receipt["arguments"] or receipt.get("data_identities") or receipt.get("dataset_refs"):
        raise ValueError("Skills catalogue invocation or source scope changed")
    actual,current=_skills_catalog_snapshot(context)
    if current!=binding or encode(result)!=encode(actual):
        raise ValueError("Skills directories, source files, catalogue or session loading changed")
    return binding


@registry.register(
    name="list_skills",
    description="List installed global skills and the current session's enabled/loaded state. The verified catalogue may be empty; it is metadata, not dataset evidence.",
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"]},
    parameters={"type": "object", "properties": {}},
)
def list_skills() -> str:
    from data_agent.agent.context import get_current_context
    context=get_current_context()
    result=_skills_catalog_snapshot(context)[0] if context is not None else _list_skills_result(_loader())
    return json.dumps(result,ensure_ascii=False,indent=2)


@registry.register(
    name="enable_skill",
    capability={"capability_id":"system.enable_skill","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Enable an installed global skill.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def enable_skill(name: str) -> str:
    return _operate(name,"enable_skill")


@registry.register(
    name="disable_skill",
    capability={"capability_id":"system.disable_skill","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Disable an installed global skill and unload it if active.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def disable_skill(name: str) -> str:
    return _operate(name,"disable_skill")


@registry.register(
    name="delete_skill",
    capability={"capability_id":"system.delete_skill","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Delete an installed global skill.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def delete_skill(name: str) -> str:
    return _operate(name,"delete_skill")
