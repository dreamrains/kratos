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
        "required_data",
        "expected_output",
        "evidence_ids",
        "confirmation_ids",
        "result_summary",
        "limitations",
        "confidence",
        "required_capability",
        "evidence_requirements",
        "confirmation_policy",
    ):
        if key in data:
            fields[key] = data[key]
    return fields


def create_workflow_tasks_from_spec(spec: dict) -> dict:
    method_plan = spec.get("method_plan") or []
    if isinstance(method_plan, str):
        method_plan = [line.strip() for line in method_plan.splitlines() if line.strip()]
    if not isinstance(method_plan, list):
        method_plan = []

    workflow_id = spec.get("workflow_id") or f"wf_{uuid.uuid4().hex[:8]}"
    spec_id = spec.get("id", "")
    created = []
    for idx, step in enumerate(method_plan, 1):
        if isinstance(step, dict):
            subject = step.get("subject") or step.get("title") or step.get("step") or f"分析步骤 {idx}"
            description = step.get("description") or step.get("method") or json.dumps(step, ensure_ascii=False)
            node_type = step.get("node_type") or "analysis"
            expected_output = step.get("expected_output", "")
            required_data = step.get("required_data", spec.get("required_data", []))
            required_capability = step.get("required_capability", "")
            evidence_requirements = step.get("evidence_requirements", [])
            confirmation_policy = step.get("confirmation_policy", {})
        else:
            subject = str(step)
            description = str(step)
            node_type = "analysis"
            expected_output = ""
            required_data = spec.get("required_data", [])
            required_capability = ""
            evidence_requirements = []
            confirmation_policy = {}

        task = task_manager.create(
            subject=subject[:120],
            description=description,
            session_id=_session_id(),
            workflow_id=workflow_id,
            project_name=_project_name(),
            stage="execute",
            node_type=node_type,
            analysis_spec_id=spec_id,
            required_data=required_data,
            expected_output=expected_output,
            required_capability=required_capability,
            evidence_requirements=evidence_requirements,
            confirmation_policy=confirmation_policy,
        )
        created.append(task)
    return {"workflow_id": workflow_id, "created": len(created), "task_ids": [t["id"] for t in created]}


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
    if analysis_spec_json:
        try:
            spec = json.loads(analysis_spec_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "analysis_spec_json 必须是有效 JSON"}, ensure_ascii=False)
        return json.dumps(create_workflow_tasks_from_spec(spec), ensure_ascii=False, indent=2)

    current_spec = _current_analysis_spec()
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
    }

    if tasks:
        try:
            task_list_data = json.loads(tasks)
        except json.JSONDecodeError:
            return json.dumps({"error": "tasks 必须是有效的 JSON 数组"}, ensure_ascii=False)
        if not isinstance(task_list_data, list):
            return json.dumps({"error": "tasks 必须是 JSON 数组"}, ensure_ascii=False)

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
        return json.dumps({"created": len(created), "tasks": created}, ensure_ascii=False, indent=2)

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
        "更新任务状态和分析工作流字段。status 可选：pending/in_progress/completed/deleted。"
        "支持批量 updates JSON。"
    ),
    schema_overrides={
        "updates": {"description": '批量更新模式：JSON 数组 [{"task_id": 1, "status": "completed"}]'},
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
    task = task_manager.get(task_id)
    if task is None:
        return json.dumps({"error": f"Task {task_id} not found"}, ensure_ascii=False)
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_list",
    description="列出分析任务及状态。默认优先显示当前 session/project 的 workflow task。",
)
def task_list() -> str:
    return task_manager.format_list(session_id=_session_id(), project_name=_project_name())
