"""File upload staging, session binding, and deterministic ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import uuid

from flask import Blueprint, jsonify, request

from data_agent.config import get_config
from data_agent.file_formats import SUPPORTED_DATA_EXTENSIONS

uploads_bp = Blueprint("uploads", __name__)

ALLOWED_EXTENSIONS = SUPPORTED_DATA_EXTENSIONS
_UPLOAD_ID_RE = re.compile(r"[0-9a-f]{32}")
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
_UPLOAD_BIND_LOCK = threading.RLock()


class UploadBindingError(ValueError):
    """A structured upload reference is invalid or no longer claimable."""


class UploadIngestionError(ValueError):
    """A claimed upload could not be loaded into its owning session."""


@dataclass(frozen=True)
class BoundUpload:
    upload_id: str
    session_id: str
    filename: str
    path: Path
    size: int
    sha256: str
    record_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pending_uploads_dir() -> Path:
    root = get_config().sessions_resolved / ".pending_uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalise_filename(value: str) -> str:
    raw = str(value or "").strip()
    portable = raw.replace("\\", "/")
    name = PurePosixPath(portable).name
    if not name or name in {".", ".."} or name != portable:
        raise UploadBindingError("Invalid upload filename")
    if any(ord(char) < 32 for char in name):
        raise UploadBindingError("Invalid upload filename")
    return name


def _validate_upload_id(value: object) -> str:
    upload_id = str(value or "").strip().lower()
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        raise UploadBindingError("Invalid upload_id")
    return upload_id


def _validate_session_id(value: object) -> str:
    session_id = str(value or "").strip()
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise UploadBindingError("Invalid session_id for upload binding")
    return session_id


def _write_json_atomic(path: Path, payload: dict) -> None:
    from data_agent.utils.atomic_files import write_text_atomic
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_upload_record(directory: Path, upload_id: str) -> dict:
    record_path = directory / "upload.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UploadBindingError(f"Upload {upload_id} is not available") from exc
    if record.get("upload_id") != upload_id:
        raise UploadBindingError(f"Upload {upload_id} has invalid metadata")
    filename = _normalise_filename(record.get("filename", ""))
    file_path = directory / filename
    if not file_path.is_file():
        raise UploadBindingError(f"Upload {upload_id} is not available")
    return record


def _bound_upload(directory: Path, session_id: str, record: dict) -> BoundUpload:
    filename = _normalise_filename(record.get("filename", ""))
    return BoundUpload(
        upload_id=str(record["upload_id"]),
        session_id=session_id,
        filename=filename,
        path=directory / filename,
        size=int(record.get("size") or 0),
        sha256=str(record.get("sha256") or ""),
        record_path=directory / "upload.json",
    )


def _verify_upload_payload(directory: Path, record: dict) -> None:
    filename = _normalise_filename(record.get("filename", ""))
    path = directory / filename
    expected_size = int(record.get("size") or -1)
    expected_hash = str(record.get("sha256") or "")
    try:
        actual_size = path.stat().st_size
        actual_hash = _sha256_file(path)
    except OSError as exc:
        raise UploadBindingError(f"Upload {record.get('upload_id')} is not available") from exc
    if actual_size != expected_size or actual_hash != expected_hash:
        raise UploadBindingError(f"Upload {record.get('upload_id')} failed integrity verification")


def bind_uploads_to_session(session_id: str, references: object) -> list[BoundUpload]:
    """Atomically claim opaque upload tickets for exactly one session."""

    if references in (None, []):
        return []
    if not isinstance(references, list) or len(references) > 20:
        raise UploadBindingError("uploads must be a list containing at most 20 items")
    safe_session_id = _validate_session_id(session_id)

    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise UploadBindingError("Each upload reference must be an object")
        upload_id = _validate_upload_id(reference.get("upload_id"))
        filename = _normalise_filename(reference.get("filename", ""))
        if upload_id in seen:
            raise UploadBindingError(f"Duplicate upload_id: {upload_id}")
        seen.add(upload_id)
        parsed.append((upload_id, filename))

    pending_root = _pending_uploads_dir()
    session_uploads = get_config().sessions_resolved / safe_session_id / "uploads"

    with _UPLOAD_BIND_LOCK:
        prepared: list[tuple[str, str, Path, dict, bool]] = []
        for upload_id, expected_filename in parsed:
            pending_dir = pending_root / upload_id
            bound_dir = session_uploads / upload_id
            if bound_dir.is_dir():
                record = _read_upload_record(bound_dir, upload_id)
                if record.get("session_id") != safe_session_id:
                    raise UploadBindingError(f"Upload {upload_id} is not available")
                from_pending = False
            elif pending_dir.is_dir():
                record = _read_upload_record(pending_dir, upload_id)
                from_pending = True
            else:
                raise UploadBindingError(f"Upload {upload_id} is not available")
            if record.get("filename") != expected_filename:
                raise UploadBindingError(f"Upload {upload_id} filename does not match its ticket")
            _verify_upload_payload(bound_dir if not from_pending else pending_dir, record)
            prepared.append((upload_id, expected_filename, bound_dir, record, from_pending))

        session_uploads.mkdir(parents=True, exist_ok=True)
        bound: list[BoundUpload] = []
        for upload_id, _filename, bound_dir, record, from_pending in prepared:
            if from_pending:
                (pending_root / upload_id).replace(bound_dir)
            record.update({
                "status": record.get("status") if record.get("status") == "loaded" else "claimed",
                "session_id": safe_session_id,
                "claimed_at": record.get("claimed_at") or _now(),
            })
            _write_json_atomic(bound_dir / "upload.json", record)
            bound.append(_bound_upload(bound_dir, safe_session_id, record))
        return bound


def _dataset_name_for_upload(filename: str, existing: set[str]) -> str:
    stem = Path(filename).stem.strip() or "data"
    candidate = stem
    index = 2
    while candidate in existing or f"{candidate}__raw" in existing:
        candidate = f"{stem}_{index}"
        index += 1
    return candidate


def _update_ingestion_record(upload: BoundUpload, **updates) -> dict:
    record = _read_upload_record(upload.record_path.parent, upload.upload_id)
    record.update(updates)
    record["updated_at"] = _now()
    _write_json_atomic(upload.record_path, record)
    return record


def ingest_bound_uploads(agent_loop, uploads: list[BoundUpload]) -> str:
    """Load claimed files before analysis planning and return trusted turn context."""

    if not uploads:
        return ""

    from data_agent.agent.context import use_agent_context
    from data_agent.session.history import _session_dir
    from data_agent.session.workspace import workspace
    from data_agent.tools.data_io import load_data
    from data_agent.utils.atomic_files import write_text_atomic

    loaded: list[tuple[BoundUpload, str, str]] = []
    record_snapshots: dict[str, dict] = {}
    # A retry of an upload that is already present must not retire a newer
    # plan.  Inspect only ticket metadata plus the currently readable names;
    # perform the authoritative scope transition only when bytes still need
    # to enter this workspace.
    with use_agent_context(agent_loop.context):
        inventory = workspace._bound_upload_inventory()
        readable = set(inventory)
        needs_ingestion = False
        for upload in uploads:
            record = _read_upload_record(upload.record_path.parent, upload.upload_id)
            _verify_upload_payload(upload.record_path.parent, record)
            record_snapshots[upload.upload_id] = dict(record)
            if (
                record.get("status") != "loaded"
                or str(record.get("dataset_name") or "") not in readable
            ):
                needs_ingestion = True
        baseline_datasets = set(readable)
        prior_objects = [name for name, eligible in inventory.items() if eligible]
        workspace_meta_path = _session_dir(agent_loop.session_id) / "workspace_meta.json"
        workspace_meta_before = (
            workspace_meta_path.read_text(encoding="utf-8")
            if workspace_meta_path.exists()
            else None
        )
    retirement = {"retired": False}
    if needs_ingestion:
        # A new bound upload changes the data basis for the session. Retire
        # the old execution plan so the authoritative scope can accept the
        # new immutable raw snapshot and its analysis copy.
        retirement = agent_loop.prepare_for_bound_upload()
    try:
        with use_agent_context(agent_loop.context):
            existing = set(workspace.list_datasets())
            for upload in uploads:
                record = _read_upload_record(upload.record_path.parent, upload.upload_id)
                recorded_dataset = str(record.get("dataset_name") or "")
                if record.get("status") == "loaded" and recorded_dataset in existing:
                    loaded.append((upload, recorded_dataset, "already loaded from an earlier retry"))
                    continue

                dataset_name = _dataset_name_for_upload(upload.filename, existing)
                from data_agent.tools.registry import ToolResult
                loaded_result = load_data(str(upload.path), name=dataset_name)
                loaded_result = loaded_result if isinstance(loaded_result, ToolResult) else ToolResult.from_str(str(loaded_result))
                result = loaded_result.summary
                if (loaded_result.data or {}).get("error"):
                    raise UploadIngestionError(
                        f"Uploaded file {upload.filename} could not be loaded: {result}"
                    )

                existing = set(workspace.list_datasets())
                for name, info in workspace.list_datasets().items():
                    metadata = info.get("metadata") if isinstance(info, dict) else {}
                    if str((metadata or {}).get("_source_path") or "") == str(upload.path):
                        workspace.set_metadata(name, "_upload_id", upload.upload_id)
                        workspace.set_metadata(name, "_original_filename", upload.filename)
                        workspace.set_metadata(name, "_source_sha256", upload.sha256)
                workspace.save_meta(upload.session_id)
                _update_ingestion_record(
                    upload,
                    status="loaded",
                    dataset_name=dataset_name,
                    loaded_at=_now(),
                    error="",
                )
                loaded.append((upload, dataset_name, result))
    except Exception as exc:
        # Loading and metadata publication form one transaction from the
        # caller's perspective.  Remove all datasets created by this batch,
        # restore ticket records, then reactivate the exact prior plan/scope.
        compensation_errors: list[str] = []
        try:
            with use_agent_context(agent_loop.context):
                for name in set(workspace.list_datasets()) - baseline_datasets:
                    workspace.remove(name)
            if workspace_meta_before is None:
                workspace_meta_path.unlink(missing_ok=True)
            else:
                write_text_atomic(workspace_meta_path, workspace_meta_before)
        except Exception as cleanup_exc:
            compensation_errors.append(f"workspace:{cleanup_exc}")
        for upload in uploads:
            try:
                original = dict(record_snapshots[upload.upload_id])
                if original.get("status") != "loaded":
                    original.update({
                        "status": "failed",
                        "error": str(exc)[:2000],
                        "updated_at": _now(),
                    })
                _write_json_atomic(upload.record_path, original)
            except Exception as record_exc:
                compensation_errors.append(f"ticket:{upload.upload_id}:{record_exc}")
        try:
            rollback = agent_loop.rollback_bound_upload(retirement)
            if retirement.get("retired") and not (
                rollback.get("restored") or rollback.get("reason") == "already_restored"
            ):
                compensation_errors.append(f"plan:{rollback.get('reason')}")
        except Exception as rollback_exc:
            compensation_errors.append(f"plan:{rollback_exc}")
        detail = f"Upload ingestion failed: {exc}"
        if compensation_errors:
            detail += "; compensation incomplete: " + " | ".join(compensation_errors)
        raise UploadIngestionError(detail) from exc

    invalidate = getattr(agent_loop, "invalidate_prompt_cache", None)
    if callable(invalidate):
        invalidate()

    agent_loop._current_uploads={"uploads":[{"upload_id":u.upload_id,"filename":u.filename,"sha256":u.sha256,"dataset":name}
        for u,name,_ in loaded],"prior_objects":prior_objects}
    configure_upload_confirmation(agent_loop)
    agent_loop._bind_current_uploads=lambda user,bindings,intent=None: prepare_upload_bindings(agent_loop,loaded,user,bindings,intent)

    lines = [
        "<uploaded_data_context>",
        "The server verified these attachment tickets and they are already loaded into this session before analysis planning.",
        "Use the listed dataset names directly. Do not ask the user for file paths and do not reload the same attachments.",
    ]
    for upload, dataset_name, result in loaded:
        compact_result = result[:3500]
        lines.append(
            f"- {upload.filename} -> dataset `{dataset_name}` "
            f"(upload_id={upload.upload_id}, sha256={upload.sha256})\n{compact_result}"
        )
    lines.append("</uploaded_data_context>")
    return "\n".join(lines)


def _explicit_upload_object(row, user_input):
    """Validate the semantic proposal's exact original object reference."""
    from data_agent.agent.publication.contracts import ContractError, fields, text
    fields(row, {"upload_id", "dataset", "relation", "exact_span"}, {"object_span"})
    if "object_span" not in row:
        return False
    reference = text(row["object_span"], limit=128)
    span = text(row["exact_span"], limit=4000)
    if reference != row["dataset"] or reference not in span or user_input.count(span) != 1 or user_input.count(reference) != 1:
        raise ContractError("upload_object_ref", "对象引用必须是本轮唯一原文中的精确业务别名。")
    return True


def _upload_relation_unresolved(row, loaded, prior, user_input):
    explicit = _explicit_upload_object(row, user_input)
    return row["relation"] == "replace" and not explicit and (len(loaded) != 1 or prior != [row["dataset"]])


def prepare_upload_bindings(loop,loaded,user_input,bindings,intent):
    """An uncertain object relation is one existing file-scope decision."""
    prior=loop._current_uploads["prior_objects"]
    ambiguous=any(_upload_relation_unresolved(row,loaded,prior,user_input) for row in bindings)
    if not ambiguous or intent is None:
        apply_upload_bindings(loop,loaded,user_input,bindings)
        return None
    from itertools import product
    from data_agent.agent.confirmation.models import AnswerMode,ConfirmationOption,QuestionCandidate
    from data_agent.session.workspace import workspace
    if not prior:
        raise UploadBindingError("没有可替换的先前业务对象，请明确附件对象。")
    choices=[]
    for row in bindings:
        if not isinstance(row,dict) or row.get("upload_id") not in {u.upload_id for u,_,_ in loaded} or user_input.count(str(row.get("exact_span") or ""))!=1:
            raise UploadBindingError("对象候选没有唯一当前票据与原文。")
        choices.append([dict(row,dataset=name) for name in prior] if _upload_relation_unresolved(row,loaded,prior,user_input) else [row])
    count=1
    for rows in choices:count*=len(rows)
    if count>128: raise UploadBindingError("对象映射组合超过128项，请分批明确对应对象。")
    options=tuple(ConfirmationOption("；".join(r["upload_id"][:8]+" → "+r["dataset"] for r in rows),
        json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(",",":")))
        for rows in product(*choices) if len({r["dataset"] for r in rows})==len(rows))
    if not options:raise UploadBindingError("没有互不冲突的对象映射，请明确附件对象。")
    identities={name:workspace.get_data_identity(name) for name in prior+[source for _,source,_ in loaded]}
    seed=json.dumps([bindings,identities],ensure_ascii=False,sort_keys=True)
    identity=hashlib.sha256(seed.encode()).hexdigest()
    return QuestionCandidate(confirmation_id="upload_object_"+identity[:24],session_id=loop.session_id,
        turn_id=loop._publication_turn_id,decision_key="upload_object:"+identity,
        source="host_upload_object.v1",operation="bind_uploaded_objects",
        question="请确认本轮附件分别替换哪个已有业务对象。",decision_impact="对象映射决定哪些旧版本退出当前计算范围。",
        answer_mode=AnswerMode.SINGLE_SELECT,options=options,blocking_surfaces=("upload_object_binding",),skippable=False,
        resolution_action="bind_uploaded_objects",data_version=identity,
        resolution_params={"confirmation_type":"file_scope","decision_kind":"file_scope",
            "missing_value":"attachment_object_relation","affected_operations":["bind_uploaded_objects"],
            "business_scope":identity,"uploads":[u.upload_id for u,_,_ in loaded],"prior_objects":prior,
            "data_identities":identities,"user_input":user_input,"proposed_bindings":bindings,"intent":vars(intent)})


def configure_upload_confirmation(loop):
    """Install the HTTP adapter action on both new and restored loops."""
    service=loop._confirmation_runtime()
    if getattr(loop,"_upload_confirmation_service",None) is service:return
    def apply(context,answer):
        from data_agent.agent.context import use_agent_context
        from data_agent.session.workspace import workspace
        params=context.parameters
        directory=get_config().sessions_resolved/_validate_session_id(context.session_id)/"uploads"
        loaded=[]
        with use_agent_context(loop.context):
            for upload_id in params["uploads"]:
                upload_id=_validate_upload_id(upload_id)
                record=_read_upload_record(directory/upload_id,upload_id)
                if record.get("session_id")!=context.session_id or record.get("status")!="loaded":
                    raise UploadBindingError("对象确认的上传票据不属于当前会话。")
                loaded.append((_bound_upload(directory/upload_id,context.session_id,record),record["dataset_name"],""))
            if any(workspace.get_data_identity(name)!=identity for name,identity in params["data_identities"].items()):
                raise UploadBindingError("对象确认期间数据版本已变化，请重新确认。")
            selected=json.loads(answer)
            loop._current_uploads={"prior_objects":list(params["prior_objects"])}
            apply_upload_bindings(loop,loaded,params["user_input"],selected,confirmed=True)
        return {"confirmation_id":context.confirmation_id,"bindings":selected}
    def after_resolution(record):
        from copy import deepcopy
        from data_agent.agent.context import use_agent_context
        from data_agent.agent.intent import TurnIntent
        if record.resolution_action!="bind_uploaded_objects":return True
        if record.status.value!="resolved":return False
        params=record.resolution_params
        selected=json.loads(record.response)
        with use_agent_context(loop.context):
            intent=TurnIntent(**deepcopy(params["intent"]))
            changes={}
            for old,new in zip(params["proposed_bindings"],selected):
                changes.setdefault(old["dataset"],set()).add(new["dataset"])
            for row in intent.requested_outputs:
                scope=row.get("business_scope",{})
                names=scope.get("datasets",[])
                # A unique confirmed alias substitutes the original placeholder.
                # An ambiguous placeholder remains unresolved; no formula authority.
                scope["datasets"]=[next(iter(changes[n])) if n in changes and len(changes[n])==1 else n for n in names]
            mappings=[]
            for row in intent.measurement_mappings:
                targets=changes.get(row.get("dataset"))
                if targets is not None:
                    if len(targets)!=1:continue
                    row["dataset"]=next(iter(targets))
                mappings.append(row)
            intent.measurement_mappings=mappings
            intent.upload_bindings=selected
            loop._current_uploads={}
            loop._complete_analysis_turn(params["user_input"],intent)
        loop._bind_current_uploads=None
        return True
    loop._after_confirmation_resolution=after_resolution
    service.action_registry.register("bind_uploaded_objects",apply)
    loop._upload_confirmation_service=service


def apply_upload_bindings(loop, loaded, user_input, bindings, *, confirmed=False):
    """Apply semantic object proposals to verified tickets with atomic compensation."""
    from data_agent.session.workspace import workspace
    from data_agent.agent.publication.contracts import ContractError, fields, text
    moves=[];seen=set();prior=loop._current_uploads["prior_objects"]
    for row in bindings:
        fields(row,{"upload_id","dataset","relation","exact_span"},{"object_span"})
        target=text(row["dataset"],limit=128);span=text(row["exact_span"],limit=4000)
        _explicit_upload_object(row,user_input)
        upload_id=text(row["upload_id"],limit=128)
        if target in {".",".."} or any(c in target for c in '<>:"/\\|?*'):
            raise ContractError("upload_binding","业务别名不能作为安全数据路径。")
        if user_input.count(span)!=1 or not isinstance(row["relation"],str) or row["relation"] not in {"new","replace"}:
            raise ContractError("upload_binding","对象映射缺少唯一原文或关系。")
        found=[item for item in loaded if item[0].upload_id==upload_id]
        if len(found)!=1 or upload_id in seen or target in {m[2] for m in moves}:
            raise ContractError("upload_binding","对象映射没有唯一当前票据和目标。")
        upload,source,_=found[0];seen.add(upload.upload_id)
        _verify_upload_payload(upload.record_path.parent,_read_upload_record(upload.record_path.parent,upload.upload_id))
        if workspace.get_metadata(source,"_upload_id")!=upload.upload_id or workspace.get_metadata(source,"_source_sha256")!=upload.sha256:
            raise ContractError("upload_binding","对象映射的当前加载来源已变化。")
        replace=row["relation"]=="replace"
        if (replace and ((not confirmed and _upload_relation_unresolved(row,loaded,prior,user_input)) or target not in prior)) or (not replace and target not in span):
            raise ContractError("upload_binding","新版对象不唯一或别名不来自明确命名。请明确附件对应的业务对象。")
        if source!=target and workspace.exists(target) and not replace:
            raise ContractError("upload_binding","业务别名已存在，需要明确版本替换关系。")
        moves.append((upload,source,target,replace))
    from data_agent.session.history import _session_dir
    from data_agent.utils.atomic_files import write_bytes_atomic
    meta_path = _session_dir(loop.session_id) / "workspace_meta.json"
    meta_before = meta_path.read_bytes() if meta_path.exists() else None
    ticket_bytes = {u.upload_id: u.record_path.read_bytes() for u,_,_,_ in moves}
    from copy import deepcopy
    state=loop.context.analysis_state
    projections_before=deepcopy((state.dataset_contracts,state.route_proposals,state.cleaning_logs,state.active_scope))
    state_path=_session_dir(loop.session_id)/"analysis_state.json"
    state_bytes=state_path.read_bytes() if state_path.exists() else None
    def persist():
        for upload,_,target,_ in moves:
            _update_ingestion_record(upload,dataset_name=target)
        workspace.save_meta(loop.session_id)
        # An explicit host rebind preserves the original understanding artifact.
        # The alias is usable only while this exact source identity is current.
        for _,source,target,_ in moves:
            if source==target: continue
            identity=workspace._publication_data_identity(target)
            for refs in (state.dataset_contracts,state.route_proposals,state.cleaning_logs):
                for ref in refs:
                    if ref.get("dataset")==source:
                        aliases=ref.setdefault("host_aliases",{})
                        aliases[target]=deepcopy(identity)
            if state.active_scope.get("active_dataset")==source:
                state.active_scope["active_dataset"]=target
        state.save()
    try:
        workspace.rebind_uploaded_objects([(source,target,replace) for _,source,target,replace in moves],persist)
    except Exception as exc:
        errors=[]
        state.dataset_contracts,state.route_proposals,state.cleaning_logs,state.active_scope=projections_before
        try:
            if state_bytes is None: state_path.unlink(missing_ok=True)
            else: write_bytes_atomic(state_path,state_bytes)
        except OSError as error: errors.append(str(error))
        for upload,_,_,_ in moves:
            try: write_bytes_atomic(upload.record_path,ticket_bytes[upload.upload_id])
            except OSError as error: errors.append(str(error))
        try:
            if meta_before is None: meta_path.unlink(missing_ok=True)
            else: write_bytes_atomic(meta_path,meta_before)
        except OSError as error: errors.append(str(error))
        if errors: raise UploadIngestionError("Object binding rollback incomplete: "+" | ".join(errors)) from exc
        raise
    if moves:
        loop.messages.append({"role":"system","content":"宿主已按本轮明确对象关系绑定验票附件："+json.dumps([
            {"upload_id":u.upload_id,"dataset":target,"relation":"replace" if replace else "new"} for u,_,target,replace in moves],ensure_ascii=False)})
        loop.invalidate_prompt_cache()
    return bool(moves)


@uploads_bp.post("/upload")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file_storage = request.files["file"]
    if not file_storage.filename:
        return jsonify({"error": "Empty filename"}), 400

    try:
        filename = _normalise_filename(file_storage.filename)
    except UploadBindingError as exc:
        return jsonify({"error": str(exc)}), 400

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    upload_id = uuid.uuid4().hex
    root = _pending_uploads_dir()
    temporary_dir = root / f".{upload_id}.tmp"
    ticket_dir = root / upload_id
    temporary_dir.mkdir(parents=False, exist_ok=False)
    try:
        destination = temporary_dir / filename
        file_storage.save(str(destination))
        record = {
            "schema_version": 1,
            "upload_id": upload_id,
            "filename": filename,
            "size": destination.stat().st_size,
            "sha256": _sha256_file(destination),
            "status": "pending",
            "session_id": "",
            "created_at": _now(),
        }
        _write_json_atomic(temporary_dir / "upload.json", record)
        temporary_dir.replace(ticket_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    return jsonify({
        "upload_id": upload_id,
        "filename": filename,
        "size": record["size"],
        "sha256": record["sha256"],
    })


@uploads_bp.delete("/upload/<upload_id>")
def cancel_upload(upload_id: str):
    """Discard an unclaimed upload ticket when the user removes an attachment."""

    try:
        safe_upload_id = _validate_upload_id(upload_id)
    except UploadBindingError as exc:
        return jsonify({"error": str(exc)}), 400

    with _UPLOAD_BIND_LOCK:
        pending_dir = _pending_uploads_dir() / safe_upload_id
        if pending_dir.is_dir():
            shutil.rmtree(pending_dir)

    # Cancellation is intentionally idempotent. A ticket that has already
    # been claimed is session-owned and is never removed by this endpoint.
    return jsonify({"upload_id": safe_upload_id, "status": "cancelled"})
