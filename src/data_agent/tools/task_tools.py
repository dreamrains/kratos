"""Task management tools.

Tasks remain backward-compatible todos, with optional analysis-workflow fields
used by the consulting analysis flow.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from data_agent.session.task_manager import task_manager
from data_agent.tools.registry import registry

_current_session_id: str = ""


def set_task_session(session_id: str):
    global _current_session_id
    _current_session_id = session_id


def _context():
    try:
        from data_agent.agent.context import get_current_context
        return get_current_context()
    except Exception:
        return None


def _session_id() -> str:
    ctx = _context()
    if ctx is not None:
        return ctx.session_id
    return _current_session_id


def _project_name() -> str:
    ctx = _context()
    if ctx is not None and ctx.project_name:
        return ctx.project_name
    return ""


def _scoped_task(task_id):
    return task_manager.get_for_scope(task_id, _session_id(), _project_name())


def _scope_error() -> str:
    # Do not reveal whether a foreign task exists, its content, or its owner.
    return json.dumps({"error": "Task not found in current scope", "error_type": "task_scope_not_found"})


def _foreign_creation_scope(fields: dict) -> bool:
    return bool(
        (_session_id() and fields.get("session_id", _session_id()) != _session_id())
        or (_context() is not None and fields.get("project_name", _project_name()) != _project_name())
    )


def _update_scope_error(update: dict) -> str | None:
    current = _scoped_task(update.get("task_id", 0))
    if current is None:
        return _scope_error()
    if any(key in update and update[key] != current.get(key, "") for key in ("session_id", "project_name")):
        return _scope_error()
    for key in ("addBlocks", "addBlockedBy"):
        value = _json_or_value(update.get(key))
        if value is None:
            continue
        if not isinstance(value, list) or any(type(tid) is not int or tid <= 0 for tid in value):
            return json.dumps({"error": key + " must be a JSON array of positive task IDs"})
        if any(_scoped_task(tid) is None for tid in value):
            return _scope_error()
    return None


def _current_analysis_spec() -> dict:
    ctx = _context()
    state = getattr(ctx, "analysis_state", None) if ctx is not None else None
    spec = getattr(state, "analysis_spec", None)
    return spec if isinstance(spec, dict) else {}


def _json_or_value(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _workflow_fields_from_dict(data: dict) -> dict:
    fields = {}
    for key in (
        "workflow_id",
        "project_name",
        "stage",
        "node_type",
        "analysis_spec_id",
        "analysis_plan_id",
        "step_id",
        "dataset_inputs",
        "dataset_contract_ids",
        "combination_mode",
        "required_evidence_step_ids",
        "required_data",
        "expected_output",
        "evidence_ids",
        "confirmation_ids",
        "result_summary",
        "limitations",
        "confidence",
        "required_capability",
        "evidence_requirements",
        "satisfied_evidence_requirements",
        "confirmation_policy",
        "plan_id",
        "plan_version",
        "plan_status",
        "task_kind",
        "source",
        "superseded_by",
        "archived_at",
        "completed_by",
        "completed_at",
    ):
        if key in data:
            fields[key] = data[key]
    return fields


def _step_subject(step, idx: int) -> str:
    if isinstance(step, dict):
        return (
            step.get("task")
            or step.get("subject")
            or step.get("title")
            or step.get("step")
            or step.get("name")
            or f"分析步骤 {idx}"
        )
    return str(step)


def _step_description(step) -> str:
    if isinstance(step, dict):
        return (
            step.get("description")
            or step.get("detail")
            or step.get("method")
            or json.dumps(step, ensure_ascii=False)
        )
    return str(step)


def _ensure_active_plan_for_spec(spec: dict) -> dict:
    workflow_id = spec.get("workflow_id") or f"wf_{uuid.uuid4().hex[:8]}"
    spec["workflow_id"] = workflow_id
    spec_id = spec.get("id", "")
    session_id = _session_id()
    project_name = _project_name()
    active_plan_id = task_manager.get_active_plan_id(session_id, project_name)
    if active_plan_id:
        active_tasks = task_manager.list_active_for_scope(
            session_id=session_id,
            project_name=project_name,
        )
        if any(
            t.get("analysis_spec_id") == spec_id or t.get("workflow_id") == workflow_id
            for t in active_tasks
        ):
            return {
                "id": active_plan_id,
                "version": max([int(t.get("plan_version") or 1) for t in active_tasks], default=1),
                "workflow_id": workflow_id,
                "analysis_spec_id": spec_id,
            }
    return task_manager.create_plan(
        session_id=session_id,
        project_name=project_name,
        goal=spec.get("goal", ""),
        source="analysis_spec",
        analysis_spec_id=spec_id,
        workflow_id=workflow_id,
    )


def _incoming_has_explicit_plan(task_list_data: list) -> bool:
    return any(
        isinstance(t, dict)
        and any(key in t for key in ("plan_id", "plan_version", "plan_status"))
        for t in task_list_data
    )


def _ensure_llm_plan_for_batch(task_list_data: list, current_spec: dict, active_plan_id: str, active_tasks: list[dict]) -> dict:
    """Keep LLM-authored execution plans separate from system candidate plans."""
    if _incoming_has_explicit_plan(task_list_data):
        return {
            "id": active_plan_id,
            "version": max([int(t.get("plan_version") or 1) for t in active_tasks], default=1),
        }

    has_llm_plan = any(t.get("source") == "llm_plan" for t in active_tasks)
    if active_plan_id and has_llm_plan:
        return {
            "id": active_plan_id,
            "version": max([int(t.get("plan_version") or 1) for t in active_tasks], default=1),
        }

    first_subject = ""
    for task_data in task_list_data:
        if isinstance(task_data, dict) and task_data.get("subject"):
            first_subject = task_data["subject"]
            break
    return task_manager.create_plan(
        session_id=_session_id(),
        project_name=_project_name(),
        goal=current_spec.get("goal") or first_subject or "LLM analysis plan",
        source="llm_plan",
        analysis_spec_id=current_spec.get("id", ""),
        workflow_id=current_spec.get("workflow_id", ""),
    )


def create_workflow_tasks_from_spec(spec: dict) -> dict:
    from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks
    ctx=_context()
    if spec.get("contract_version")=="stage3c0b.v2":
        current=getattr(getattr(ctx,"analysis_state",None),"analysis_plan",{}) or {}
        if not current.get("plan_sha256") or spec!=current:
            return {"created":0,"task_ids":[],"error":"validated_analysis_plan_required"}

    return project_plan_to_workflow_tasks(
        task_manager,
        spec,
        session_id=_session_id(),
        project_name=_project_name(),
        source="analysis_plan",
    )


@registry.register(
    name="task_create",
    description=(
        "创建分析任务。支持单个任务、批量 tasks JSON，以及从 AnalysisSpec 创建 workflow task。"
        "复杂分析应先形成 AnalysisSpec，再用任务节点执行 method_plan。"
    ),
    schema_overrides={
        "tasks": {"description": '批量创建模式：JSON 数组 [{"subject": "...", "description": "..."}]'},
        "analysis_spec_json": {"description": "可选：AnalysisSpec JSON，用于从 method_plan 批量创建 workflow task"},
    },
)
def task_create(
    subject: str = "",
    description: str = "",
    tasks: str = "",
    analysis_spec_json: str = "",
    workflow_id: str = "",
    project_name: str = "",
    stage: str = "",
    node_type: str = "",
    analysis_spec_id: str = "",
    required_data: str = "",
    expected_output: str = "",
    evidence_ids: str = "",
    confirmation_ids: str = "",
    required_capability: str = "",
    evidence_requirements: str = "",
    confirmation_policy: str = "",
) -> str:
    if project_name and _foreign_creation_scope({"project_name": project_name}):
        return _scope_error()

    if analysis_spec_json:
        try:
            spec = json.loads(analysis_spec_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "analysis_spec_json 必须是有效 JSON"}, ensure_ascii=False)
        return json.dumps(create_workflow_tasks_from_spec(spec), ensure_ascii=False, indent=2)

    current_spec = _current_analysis_spec()
    active_plan_id = task_manager.get_active_plan_id(_session_id(), _project_name())
    active_tasks = (
        task_manager.list_active_for_scope(session_id=_session_id(), project_name=_project_name())
        if active_plan_id else []
    )
    if active_plan_id and task_manager.active_plan_has_live_stage_tasks(
        _session_id(), _project_name()
    ):
        # The projected plan already owns the task authority for this analysis.
        # Manual task creation used to silently supersede it, which the scope
        # resolver then read as "tasks without stage tasks" (legacy) and the
        # transition guard turned into a permanent error phase.
        return json.dumps({
            "error": (
                "当前存在未完成的结构化分析计划（record_analysis_plan 已投影任务）。"
                "请勿手动创建重复任务：按步骤执行工具形成真实回执，"
                "或重新提交修订后的 record_analysis_plan。"
            ),
            "error_type": "active_stage_plan_task_create_refused",
            "active_plan_id": active_plan_id,
        }, ensure_ascii=False)
    active_plan_version = max([int(t.get("plan_version") or 1) for t in active_tasks], default=1)
    common_fields = {
        "workflow_id": workflow_id or current_spec.get("workflow_id", ""),
        "project_name": project_name or _project_name(),
        "stage": stage or ("execute" if current_spec else ""),
        "node_type": node_type,
        "analysis_spec_id": analysis_spec_id or current_spec.get("id", ""),
        "required_data": _json_or_value(required_data, []),
        "expected_output": expected_output,
        "evidence_ids": _json_or_value(evidence_ids, []),
        "confirmation_ids": _json_or_value(confirmation_ids, []),
        "required_capability": required_capability,
        "evidence_requirements": _json_or_value(evidence_requirements, []),
        "confirmation_policy": _json_or_value(confirmation_policy, current_spec.get("confirmation_policy", {})),
        "plan_id": active_plan_id,
        "plan_version": active_plan_version,
        "plan_status": "active" if active_plan_id else "",
        "task_kind": "plan_task",
        "source": "llm_plan" if active_plan_id else "",
    }

    if tasks:
        try:
            task_list_data = json.loads(tasks)
        except json.JSONDecodeError:
            return json.dumps({"error": "tasks 必须是有效的 JSON 数组"}, ensure_ascii=False)
        if not isinstance(task_list_data, list):
            return json.dumps({"error": "tasks 必须是 JSON 数组"}, ensure_ascii=False)

        # Check the entire batch before plan supersession or the first write.
        if any(isinstance(t, dict) and _foreign_creation_scope(t) for t in task_list_data):
            return _scope_error()

        owned={"analysis_plan_id","step_id","plan_sha256","requirement_ids","required_delivery_ids","dataset_inputs","dataset_contract_ids","combination_mode","required_evidence_step_ids"}
        if any(isinstance(t,dict) and owned.intersection(t) for t in task_list_data):
            return json.dumps({"error":"Analysis bindings require record_analysis_plan"})
        llm_plan = _ensure_llm_plan_for_batch(task_list_data, current_spec, active_plan_id, active_tasks)
        if llm_plan.get("id"):
            common_fields["plan_id"] = llm_plan["id"]
            common_fields["plan_version"] = llm_plan.get("version", 1)
            common_fields["plan_status"] = "active"
            common_fields["source"] = "llm_plan"

        created = []
        for t in task_list_data:
            if not isinstance(t, dict):
                continue
            fields = {**common_fields, **_workflow_fields_from_dict(t)}
            task = task_manager.create(
                subject=t.get("subject", ""),
                description=t.get("description", ""),
                session_id=t.get("session_id") or _session_id(),
                **fields,
            )
            created.append(task)
        return json.dumps({
            "created": len(created),
            "plan_id": common_fields.get("plan_id", ""),
            "tasks": created,
        }, ensure_ascii=False, indent=2)

    if not subject:
        return json.dumps({"error": "subject 不能为空"}, ensure_ascii=False)
    task = task_manager.create(
        subject=subject,
        description=description,
        session_id=_session_id(),
        **common_fields,
    )
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_update",
    description=(
        "更新任务状态和分析工作流字段。status 可选：pending/blocked/in_progress/completed/failed/superseded/archived/deleted。"
        "支持批量 updates JSON。"
    ),
    schema_overrides={
        "status": {"description": "可选状态：pending/blocked/in_progress/completed/failed/superseded/archived/deleted"},
        "updates": {"description": '批量更新模式：JSON 数组 [{"task_id": 1, "status": "completed"}]；status 可用 pending/blocked/in_progress/completed/failed/superseded/archived/deleted'},
    },
)
def task_update(
    task_id: int = 0,
    status: str = "",
    owner: str = "",
    addBlocks: Optional[str] = None,
    addBlockedBy: Optional[str] = None,
    updates: str = "",
    result_summary: str = "",
    evidence_ids: str = "",
    confirmation_ids: str = "",
    limitations: str = "",
    confidence: str = "",
    stage: str = "",
    node_type: str = "",
    expected_output: str = "",
    required_capability: str = "",
    evidence_requirements: str = "",
    confirmation_policy: str = "",
) -> str:
    if updates:
        try:
            update_list = json.loads(updates)
        except json.JSONDecodeError:
            return json.dumps({"error": "updates 必须是有效的 JSON 数组"}, ensure_ascii=False)
        if not isinstance(update_list, list):
            return json.dumps({"error": "updates 必须是 JSON 数组"}, ensure_ascii=False)

        # Foreign IDs and dependency endpoints must fail before any batch write.
        for update in update_list:
            if isinstance(update, dict):
                error = _update_scope_error(update)
                if error:
                    return error

        # A model may annotate or explicitly fail a scoped step. The plan's
        # identity, dataset bindings and dependencies are host-owned.
        protected = {"analysis_plan_id","plan_id","plan_sha256","step_id","requirement_ids","required_delivery_ids","dataset_inputs","dataset_contract_ids","combination_mode","required_evidence_step_ids","addBlocks","addBlockedBy"}
        for u in update_list:
            current=_scoped_task(u.get("task_id",0)) if isinstance(u,dict) else None
            if current and (task_manager._is_stage3c0b_scoped_task(current) and protected.intersection(u) or {"analysis_plan_id","step_id","plan_sha256","requirement_ids","required_delivery_ids","dataset_inputs","dataset_contract_ids","combination_mode","required_evidence_step_ids"}.intersection(u)):
                return json.dumps({"error":"Scoped task bindings are owned by the validated analysis plan"})
        results = []
        for u in update_list:
            if not isinstance(u, dict):
                continue
            tid = u.get("task_id")
            if not tid:
                continue
            task = task_manager.update(
                tid,
                status=u.get("status"),
                owner=u.get("owner"),
                addBlocks=_json_or_value(u.get("addBlocks")),
                addBlockedBy=_json_or_value(u.get("addBlockedBy")),
                **_workflow_fields_from_dict(u),
            )
            if task:
                results.append(task)
        return json.dumps({"updated": len(results), "tasks": results}, ensure_ascii=False, indent=2)

    if not task_id:
        return json.dumps({"error": "task_id 不能为空"}, ensure_ascii=False)

    error = _update_scope_error({"task_id": task_id, "addBlocks": addBlocks, "addBlockedBy": addBlockedBy})
    if error:
        return error
    current = _scoped_task(task_id)
    if current and task_manager._is_stage3c0b_scoped_task(current) and (addBlocks or addBlockedBy):
        return json.dumps({"error":"Scoped dependencies are owned by the validated analysis plan"})
    fields = {
        "result_summary": result_summary or None,
        "evidence_ids": _json_or_value(evidence_ids) if evidence_ids else None,
        "confirmation_ids": _json_or_value(confirmation_ids) if confirmation_ids else None,
        "limitations": limitations or None,
        "confidence": confidence or None,
        "stage": stage or None,
        "node_type": node_type or None,
        "expected_output": expected_output or None,
        "required_capability": required_capability or None,
        "evidence_requirements": _json_or_value(evidence_requirements) if evidence_requirements else None,
        "confirmation_policy": _json_or_value(confirmation_policy) if confirmation_policy else None,
    }
    task = task_manager.update(
        task_id,
        status=status or None,
        owner=owner or None,
        addBlocks=_json_or_value(addBlocks),
        addBlockedBy=_json_or_value(addBlockedBy),
        **fields,
    )
    if task is None:
        return json.dumps({"error": f"Task {task_id} not found"}, ensure_ascii=False)
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_get",
    description="获取指定任务的详情。",
)
def task_get(task_id: int) -> str:
    task = _scoped_task(task_id)
    if task is None:
        return _scope_error()
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_list",
    description="列出分析任务及状态。默认优先显示当前 session/project 的 workflow task。",
)
def task_list() -> str:
    return task_manager.format_list(session_id=_session_id(), project_name=_project_name())
