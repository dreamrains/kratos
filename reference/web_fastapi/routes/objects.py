"""Object management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from data_agent.web.schemas import ObjectCreateRequest, ObjectSwitchRequest

router = APIRouter()


@router.get("/objects")
async def list_objects():
    from data_agent.config import get_config
    cfg = get_config()
    objects_dir = cfg.objects_dir
    if not objects_dir.exists():
        return {"objects": []}
    objects = []
    for d in sorted(objects_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            objects.append({"name": d.name})
    return {"objects": objects}


@router.post("/objects")
async def create_object(req: ObjectCreateRequest):
    from data_agent.config import get_config
    cfg = get_config()
    obj_dir = cfg.objects_dir / req.name
    obj_dir.mkdir(parents=True, exist_ok=True)
    # Create standard subdirs
    (obj_dir / "data").mkdir(exist_ok=True)
    (obj_dir / "knowledge").mkdir(exist_ok=True)
    return {"status": "created", "name": req.name}


@router.post("/objects/switch")
async def switch_object(req: ObjectSwitchRequest):
    from data_agent.session.workspace import workspace
    result = workspace.set_object(req.name)
    try:
        from data_agent.tools.knowledge_tools import set_active_object
        set_active_object(req.name)
    except Exception:
        pass
    return {"status": "ok", "message": result}


@router.post("/objects/clear")
async def clear_object():
    from data_agent.session.workspace import workspace
    workspace.clear_object()
    try:
        from data_agent.tools.knowledge_tools import set_active_object
        set_active_object(None)
    except Exception:
        pass
    return {"status": "ok"}
