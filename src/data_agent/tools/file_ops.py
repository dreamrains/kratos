from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from data_agent.utils.atomic_files import rollback_atomic_writes, write_bytes_atomic
from data_agent.config import get_config
from data_agent.tools._utils import sanitize_filename
from data_agent.tools.registry import registry, ToolResult


def _safe_path(p: str) -> Path:
    """确保路径在工作空间内，防止路径穿越。"""
    cfg = get_config()
    from data_agent.session.artifact_paths import resolve_reference
    from data_agent.tools.visualization import current_session_id
    return resolve_reference(p, project=cfg.project_resolved,
                             sessions=cfg.sessions_resolved, session_id=current_session_id() or "")


def _get_session_output_dir() -> Optional[Path]:
    """获取当前会话的 output 目录，无会话时返回 None。"""
    from data_agent.tools.visualization import current_session_id
    session_id = current_session_id()
    if not session_id:
        return None
    from data_agent.config import get_config
    d = get_config().sessions_resolved / session_id / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_file_page(fp: Path, path: str, *, limit=None, offset=0, max_chars=2000, expected_sha256="") -> dict:
    """One UTF-8 text view and one bounded page, bound to original bytes."""
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a non-negative integer character offset")
    if type(max_chars) is not int or not 1 <= max_chars <= 2000:
        raise ValueError("max_chars must be an integer from 1 to 2000")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be a positive integer or null")
    if not fp.exists(): raise FileNotFoundError(f"File not found: {path}")
    if fp.is_dir(): raise ValueError(f"{path} is a directory")
    raw = fp.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and expected_sha256 != digest:
        raise ValueError("file_changed: restart reading from offset 0")
    content = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if offset > len(content): raise ValueError("offset exceeds total_chars")
    page = content[offset:offset + max_chars]
    if limit is not None: page = "".join(page.splitlines(keepends=True)[:limit])
    end = offset + len(page)
    return {"schema_version":"file_page.v1", "path":path, "offset":offset, "end_offset":end,
            "content":page, "next_offset":end if end < len(content) else None,
            "returned_chars":len(page), "returned_lines":len(page.splitlines()),
            "total_chars":len(content), "total_bytes":len(raw), "sha256":digest,
            "limit":limit, "max_chars":max_chars,
            "text_view":"UTF-8；CRLF/CR规范化为LF；offset按Unicode字符计算，SHA绑定原始字节",
            "line_limit_basis":"从offset开始的行片段计为一行，保留行结束符；行数与字符上限先到者为准"}


@registry.register(
    name="read_file",
    capability={"capability_id":"system.read_file","category":"data_read"},
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"]},
    description="读取工作空间文件或当前会话工具产物，长短文件统一返回file_page.v1。offset为规范化文本的字符位置；max_chars为每页正文字符数（1—2000），limit可选正整数，限制每页最多行数，两者先到者为准。返回原文件SHA、实际字符范围及next_offset；使用同一path、next_offset和expected_sha256续读以核原件未变。文本保留UTF-8及换行规范化视图，SHA绑定原始字节。直接使用tool_outputs/...或sessions/<当前会话ID>/...；禁止跨会话和路径穿越。",
    schema_overrides={"limit":{"minimum":1},"offset":{"minimum":0},"max_chars":{"minimum":1,"maximum":2000}},
)
def read_file(path: str, limit: Optional[int] = None, offset: int = 0, max_chars: int = 2000,
              expected_sha256: str = "") -> str:
    fp = _safe_path(path)
    try:
        return json.dumps(_read_file_page(fp,path,limit=limit,offset=offset,max_chars=max_chars,expected_sha256=expected_sha256),ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


@registry.register(
    name="write_file",
    capability={"capability_id":"system.write_file","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="写入内容到文件。path 为相对路径。文件会保存到当前会话的 output 目录中，并自动注册到会话清单。",
)
def write_file(path: str, content: str) -> str | ToolResult:
    from data_agent.tools.visualization import current_session_id

    safe_name = sanitize_filename(path)
    session_dir = _get_session_output_dir()
    if session_dir:
        session_id = current_session_id()
        normalized = path.replace("\\", "/")
        if normalized.startswith(("output/", "sessions/")):
            fp = _safe_path(path)
            if not fp.is_relative_to(session_dir.resolve()):
                raise ValueError("write_file may only write current-session output artifacts")
        else:
            fp = session_dir / safe_name
        fp.parent.mkdir(parents=True, exist_ok=True)
        with rollback_atomic_writes():
            write_bytes_atomic(fp, content.encode("utf-8"))

            # 注册到会话 artifact 清单
            from data_agent.session.history import register_artifact
            artifact_path = f"sessions/{session_id}/output/{fp.relative_to(session_dir).as_posix()}"
            register_artifact(session_id, artifact_path, "file", path)
            return ToolResult(summary=f"Wrote {len(content.encode('utf-8'))} bytes to {artifact_path}",data={"path":artifact_path,"sha256":"sha256:"+hashlib.sha256(fp.read_bytes()).hexdigest()})
    else:
        fp = _safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with rollback_atomic_writes():
            write_bytes_atomic(fp, content.encode("utf-8"))
            return ToolResult(summary=f"Wrote {len(content.encode('utf-8'))} bytes to {path}",data={"path":path,"sha256":"sha256:"+hashlib.sha256(fp.read_bytes()).hexdigest()})


@registry.register(
    name="edit_file",
    capability={"capability_id":"system.edit_file","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="精确替换文件中的文本。old_text 必须在文件中唯一存在。",
)
def edit_file(path: str, old_text: str, new_text: str) -> str | ToolResult:
    fp = _safe_path(path)
    if not fp.exists():
        return f"Error: File not found: {path}"
    try:
        content = fp.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count == 0:
            return f"Error: Text not found in {path}"
        if count > 1:
            return f"Error: Text appears {count} times in {path}, must be unique"
        new_content = content.replace(old_text, new_text, 1)
        with rollback_atomic_writes():
            write_bytes_atomic(fp, new_content.encode("utf-8"))
            return ToolResult(summary=f"Edited {path}: replaced 1 occurrence",data={"path":path,"sha256":"sha256:"+hashlib.sha256(fp.read_bytes()).hexdigest()})
    except Exception as e:
        return f"Error: {e}"


def _file_arguments(tool, arguments):
    defaults={"path":None,"limit":None,"offset":0,"max_chars":2000,"expected_sha256":""} if tool=="read_file" else {"pattern":"**/*"}
    if tool not in {"read_file","list_files"} or set(arguments)-set(defaults):raise ValueError("Unknown file invocation")
    return dict(defaults,**arguments)


def _file_parameters(tool,args):
    base={"file_scope":"current_readable","file_output":"content" if tool=="read_file" else "entries"}
    if tool=="read_file":base.update(file_path=args["path"],file_offset=args["offset"],file_limit=args["limit"],file_max_chars=args["max_chars"])
    else:base["file_pattern"]=args["pattern"]
    return base


def _file_entry(reference):
    path=_safe_path(reference)
    path.stat()  # Observe inaccessible/disappeared entries before reading or hashing.
    if path.is_dir():return {"path":reference,"canonical_path":str(path.resolve()),"kind":"directory","bytes":None,"sha256":None}
    if not path.is_file():raise FileNotFoundError(reference)
    raw=path.read_bytes()
    return {"path":reference,"canonical_path":str(path.resolve()),"kind":"file","bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def _file_catalog(pattern):
    from pathlib import PurePosixPath
    from data_agent.tools.visualization import current_session_id
    from data_agent.session.artifact_paths import ARTIFACT_DIRS
    if not isinstance(pattern,str) or not pattern.strip() or PurePosixPath(pattern.replace("\\","/")).is_absolute() or ".." in PurePosixPath(pattern.replace("\\","/")).parts:
        raise ValueError("pattern must be a relative workspace glob without traversal")
    cfg=get_config();workspace=cfg.project_resolved;sid=current_session_id() or ""
    if not workspace.is_dir():raise FileNotFoundError("Workspace directory is not available")
    entries=[];skipped=0
    for item in sorted(workspace.glob(pattern),key=lambda item:str(item).casefold()):
        try:
            if item.resolve().is_relative_to(cfg.sessions_resolved.resolve()):continue
            entries.append(_file_entry(item.relative_to(workspace).as_posix()))
        except (OSError,ValueError):skipped+=1
    if sid:
        root=cfg.sessions_resolved/sid
        for item in sorted(root.glob(pattern)):
            rel=item.relative_to(root)
            if rel.parts and rel.parts[0] in ARTIFACT_DIRS:
                try:
                    if item.is_file():entries.append(_file_entry(f"sessions/{sid}/{rel.as_posix()}"))
                except (OSError,ValueError):skipped+=1
    return {"schema_version":"file_catalog.v1","pattern":pattern,"entries":entries,"returned_entries":len(entries),"skipped_entries":skipped,
        "scope":"授权工作目录及当前会话产物目录；按调用时枚举，不包含其他会话及不可见范围",
        "status":"partial" if skipped else "complete"}


def _file_result(tool,args):
    return _read_file_page(_safe_path(args["path"]),**args) if tool=="read_file" else _file_catalog(args["pattern"])


def _file_permissions(session_id):
    from data_agent.session.artifact_paths import ARTIFACT_DIRS
    cfg=get_config()
    return {"session_id":session_id,"project_root":str(cfg.project_resolved.resolve()),"sessions_root":str(cfg.sessions_resolved.resolve()),"artifact_dirs":sorted(ARTIFACT_DIRS)}


def _capture_file_binding(context,tool,arguments):
    """Capture the actual file range before dispatch in the existing receipt."""
    from datetime import datetime,timezone
    from data_agent.agent.publication.contracts import digest,encode
    try:
        args=_file_arguments(tool,arguments);result=_file_result(tool,args);params=_file_parameters(tool,args)
        if tool=="read_file":params["file_sha256"]=result["sha256"]
        return {"schema_version":"file_binding.v1","session_id":context.session_id,"tool":tool,"arguments":args,"parameters":params,
            "permission_scope":_file_permissions(context.session_id),"canonical_path":str(_safe_path(args["path"]).resolve()) if tool=="read_file" else str(get_config().project_resolved.resolve()),
            "captured_at":datetime.now(timezone.utc).isoformat(),"snapshot_sha256":digest(encode(result))}
    except (OSError,ValueError,TypeError):return None


def _verify_file_binding(context,receipt,result):
    """Recheck the captured scope; never infer a file proof from result shape."""
    from data_agent.agent.publication.contracts import validate_file_binding,digest,encode
    binding=receipt.get("file_binding");validate_file_binding(binding,context.session_id)
    tool=receipt["tool_name"];args=_file_arguments(tool,receipt["arguments"])
    if binding["tool"]!=tool or binding["arguments"]!=args or binding["permission_scope"]!=_file_permissions(context.session_id) or receipt.get("data_identities") or receipt.get("dataset_refs"):
        raise ValueError("File session, permission or exact invocation changed")
    params=_file_parameters(tool,args)
    if tool=="read_file":params["file_sha256"]=result.get("sha256")
    if params!=binding["parameters"] or digest(encode(result))!=binding["snapshot_sha256"]:raise ValueError("File result or actual range differs from pre-dispatch snapshot")
    if tool=="read_file":
        path=_safe_path(args["path"])
        if str(path.resolve())!=binding["canonical_path"] or encode(_file_result(tool,args))!=encode(result):raise ValueError("File source SHA, canonical path or page changed")
    else:
        if binding["canonical_path"]!=str(get_config().project_resolved.resolve()):raise ValueError("File directory permission changed")
        for entry in result["entries"]:
            if _file_entry(entry["path"])!=entry:raise ValueError("Captured file catalogue entry changed")
    return binding


@registry.register(
    name="list_files",
    capability={"capability_id":"system.list_files","category":"data_read"},
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"]},
    description="按glob列出授权工作目录及当前会话产物，返回file_catalog.v1文件目录快照：规范路径、类型、字节数及文件原SHA。真实空目录返回空entries；瞬时消失/不可访问条目明确计数并标部分完成，不将不可见范围称为空。只交付枚举时点的文件元数据，不核验文件内数据结论。",
)
def list_files(pattern: str = "**/*") -> str:
    try:return json.dumps(_file_catalog(pattern),ensure_ascii=False)
    except (OSError,ValueError,TypeError) as exc:return f"Error: Unable to enumerate workspace files: {exc}"
