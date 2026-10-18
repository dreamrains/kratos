"""工作空间管理，存储已加载的数据集，支持项目绑定和变换血缘追踪。"""

from __future__ import annotations

import copy
from io import BytesIO
from contextlib import contextmanager
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
import weakref

import pandas as pd

from data_agent.agent.context import (
    _ensure_context_workspace_scope,
    _install_context_workspace_binding,
    _is_context_workspace_token,
    _operate_context_workspace,
    get_current_context,
)
from data_agent.utils.logging import get_logger

logger = get_logger("workspace")


def _create_workspace_context_sync(current_context_getter):
    """Capture the trusted getter used by legacy raw-storage project updates."""

    def sync(project_name):
        ctx = current_context_getter()
        if ctx is not None:
            ctx.project_name = project_name

    return sync


_sync_current_workspace_project = _create_workspace_context_sync(get_current_context)
del _create_workspace_context_sync


def _catalog_result(datasets, transform_log):
    """One metadata projection of the visible, loaded object namespace."""
    names = set(datasets)
    return {
        "scope": "current_visible_datasets",
        "datasets": {
            name: {"rows": info["rows"], "columns": info["columns"],
                   "column_names": list(info["column_names"]),
                   "derived_from": info.get("derived_from") if info.get("derived_from") in names else None}
            for name, info in sorted(datasets.items())
        },
        "transform_history": [
            {key: entry[key] for key in ("from", "op", "to")}
            for entry in transform_log
            if entry.get("from") in names and entry.get("to") in names
        ],
    }


def validate_dataset_alias(name):
    """Dataset names become persistence filenames and must remain one segment."""
    if not isinstance(name, str) or not name or len(name) > 128 or any(c in name for c in '/\\') or name in {".", ".."} or any(ord(c) < 32 for c in name):
        raise ValueError("invalid dataset alias")


def _validate_persistence_alias(name, existing_names):
    """Reject unsafe write paths without changing existing snapshot reads."""
    import os
    validate_dataset_alias(name)
    if getattr(os.path, "isreserved", lambda value: False)(name):
        raise ValueError("platform-reserved dataset persistence name")
    normalized = os.path.normcase(name)
    if any(other != name and os.path.normcase(other) == normalized for other in existing_names):
        raise ValueError("dataset persistence path conflicts with an existing object")


class Workspace:
    """管理工作空间中的数据集快照，支持分析项目绑定和变换血缘。"""

    def __init__(self):
        self._datasets: dict[str, pd.DataFrame] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._derived_lineage: dict[str, dict[str, Any]] = {}
        self._transform_log: list[dict[str, Any]] = []
        self._active_project: Optional[str] = None

    @staticmethod
    def _frame_fingerprint(df: pd.DataFrame) -> str:
        """Return a value-safe, deterministic identity for a dataframe snapshot."""
        digest = hashlib.sha256()
        digest.update(json.dumps([str(col) for col in df.columns], ensure_ascii=False).encode("utf-8"))
        digest.update(json.dumps([str(dtype) for dtype in df.dtypes], ensure_ascii=False).encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(df, index=True, categorize=True).values.tobytes())
        return f"sha256:{digest.hexdigest()}"

    def _set_identity(
        self,
        name: str,
        df: pd.DataFrame,
        *,
        role: str,
        parent_version_ids: list[str] | None = None,
        source_fingerprint: str = "",
        expression: str = "",
        source_origins: list[dict[str, Any]] | None = None,
        ancestor_version_ids: list[str] | None = None,
    ) -> None:
        fingerprint = self._frame_fingerprint(df)
        parents = list(parent_version_ids or [])
        origins = copy.deepcopy(source_origins or [{"kind":"in_memory","source_id":name}])
        ancestors = sorted(set(parents + list(ancestor_version_ids or [])))
        version_digest = hashlib.sha256(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "role": role,
                    "parents": parents,
                    "expression": expression,
                    "source_origins": origins,
                    "ancestor_version_ids": ancestors,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.set_metadata(name, "data_identity", {
            "version_id": f"dv_{version_digest[:16]}",
            "role": role,
            "fingerprint": fingerprint,
            "source_fingerprint": source_fingerprint or fingerprint,
            "parent_version_ids": parents,
            "expression": expression,
            "source_origins": origins,
            "ancestor_version_ids": ancestors,
        })

    @property
    def active_object(self) -> Optional[str]:
        """Backward-compatible alias for active_project."""
        return self._active_project

    @property
    def active_project(self) -> Optional[str]:
        return self._active_project

    def set_object(self, name: str) -> str:
        """Backward-compatible alias for set_project."""
        return self.set_project(name)

    def set_project(self, name: str) -> str:
        """绑定到分析项目。"""
        from data_agent.object_manager import get_object_manager

        mgr = get_object_manager()
        meta = mgr.get(name)
        if meta is None:
            return f"Error: 项目 '{name}' 不存在。"

        self._active_project = name
        try:
            _sync_current_workspace_project(name)
        except Exception:
            pass
        logger.info("Project activated", extra={"extra_data": {"project": name}})
        return f"已切换到项目 '{name}'"

    def clear_object(self) -> str:
        """Backward-compatible alias for clear_project."""
        return self.clear_project()

    def clear_project(self) -> str:
        """解除项目绑定，切回 inbox 模式。"""
        old = self._active_project
        self._active_project = None
        try:
            _sync_current_workspace_project(None)
        except Exception:
            pass
        if old:
            logger.info("Project deactivated", extra={"extra_data": {"project": old}})
        return "已切回到 inbox 模式"

    def add(self, name: str, df: pd.DataFrame, *, source_origin: dict[str, Any] | None = None) -> str:
        self._datasets[name] = df.copy()
        self._set_identity(name, self._datasets[name], role="raw", source_origins=[source_origin] if source_origin else None)
        return f"数据集 '{name}' 已加载: {df.shape[0]} 行 x {df.shape[1]} 列"

    def set_metadata(self, name: str, key: str, value: Any) -> None:
        if name not in self._metadata:
            self._metadata[name] = {}
        self._metadata[name][key] = value

    def get_metadata(self, name: str, key: str = "") -> Any:
        meta = self._metadata.get(name, {})
        if key:
            return meta.get(key)
        return meta

    # ── 持久化 ────────────────────────────────────────────

    def save_meta(
        self,
        session_id: str,
        dataset_names: Optional[Iterable[str]] = None,
    ) -> None:
        """Save workspace metadata to session directory for later restore."""
        from data_agent.session.history import _session_dir
        sdir = _session_dir(session_id)
        meta_path = sdir / "workspace_meta.json"

        # Saving one execution scope must not erase snapshots of other
        # datasets already persisted by this same session.
        datasets_meta = json.loads(meta_path.read_text(encoding="utf-8")) if dataset_names is not None and meta_path.exists() else {}
        names = self._datasets if dataset_names is None else dataset_names
        for name in names:
            if name not in self._datasets:
                continue
            df = self._datasets[name]
            datasets_meta[name] = {
                "shape": list(df.shape),
                "columns": list(df.columns),
                "data_identity": copy.deepcopy(
                    self._metadata.get(name, {}).get("data_identity", {})
                ),
                "source_path": self._metadata.get(name, {}).get("_source_path", ""),
                "source_fmt": self._metadata.get(name, {}).get("_source_fmt", ""),
                "context": self._metadata.get(name, {}).get("context", ""),
                "upload_binding": {key:self._metadata.get(name,{}).get(key,"")
                    for key in ("_upload_id","_original_filename","_source_sha256")},
                "version_archive": {key:self._metadata.get(name,{}).get(key,"")
                    for key in ("archived_from","archived_version_id")},
            }

        from data_agent.utils.atomic_files import write_text_atomic
        write_text_atomic(meta_path, json.dumps(datasets_meta, ensure_ascii=False, indent=2))
        logger.info("Workspace meta saved", extra={"extra_data": {"session_id": session_id, "datasets": list(datasets_meta)}})

    def persist_dataset(self, session_id: str, name: str) -> str | None:
        """Save DataFrame backup for restore.

        Parquet is preferred when an engine is installed. Pickle is a local
        fallback so session restore still works in lightweight environments.
        """
        _validate_persistence_alias(name, self._datasets)
        df = self._datasets.get(name)
        if df is None:
            return None
        from data_agent.session.history import _session_dir
        data_dir = _session_dir(session_id) / "data"
        data_dir.mkdir(exist_ok=True)
        path = data_dir / f"{name}.parquet"
        payload = BytesIO()
        try:
            df.to_parquet(payload, index=True)
        except ImportError:
            path = data_dir / f"{name}.pkl"
            payload = BytesIO()
            df.to_pickle(payload)
        from data_agent.utils.atomic_files import write_bytes_atomic
        write_bytes_atomic(path, payload.getvalue())
        logger.info("Dataset persisted", extra={"extra_data": {"session_id": session_id, "dataset": name, "path": str(path)}})
        return str(path)

    def restore_persisted_snapshot(self, session_id: str, name: str) -> bool:
        """Host rehydration: exact owned disk snapshot, never replace live data."""
        if name in self._datasets:
            return False
        snapshot = _read_persisted_snapshot(session_id, name)
        if snapshot is None:
            return False
        info, frame = snapshot
        with self._namespace_transaction():
            result = self.add(name, frame)
            if result.startswith("Error:"):
                raise ValueError(result)
            self.set_metadata(name, "data_identity", copy.deepcopy(info["data_identity"]))
            for key, value in (("context", info.get("context", "")),
                               ("_source_path", info.get("source_path", "")),
                               ("_source_fmt", info.get("source_fmt", ""))):
                self.set_metadata(name, key, value)
            for group in ("upload_binding", "version_archive"):
                for key, value in (info.get(group) or {}).items():
                    if key in {"_upload_id", "_original_filename", "_source_sha256", "archived_from", "archived_version_id"}:
                        self.set_metadata(name, key, value)
        return True

    def get(self, name: str) -> Optional[pd.DataFrame]:
        df = self._datasets.get(name)
        return df.copy(deep=True) if df is not None else None

    def get_data_identity(self, name: str) -> dict[str, Any]:
        """Return the persisted, value-safe identity for a dataset version."""
        identity = self.get_metadata(name, "data_identity")
        return copy.deepcopy(identity) if isinstance(identity, dict) else {}

    def next_analysis_name(self, source: str, label: str = "analysis") -> str:
        """Reserve a distinct logical name for a copy-on-write analysis version."""
        stem = f"{source}__{label}"
        candidate = stem
        index = 2
        while candidate in self._datasets:
            candidate = f"{stem}_{index}"
            index += 1
        return candidate

    def derive(self, source: str, name: str, df: pd.DataFrame, expression: str = "") -> str:
        """从源数据派生新数据集。"""
        source_identity = self.get_data_identity(source)
        if not source_identity:
            return f"Error: source dataset '{source}' has no registered data identity"
        if name in self._datasets:
            return f"Error: derived dataset '{name}' already exists; choose a new analysis dataset name"
        self._datasets[name] = df.copy()
        self._derived_lineage[name] = {
            "source": source,
            "expression": expression,
        }
        self._set_identity(
            name,
            self._datasets[name],
            role="analysis",
            parent_version_ids=[str(source_identity["version_id"])],
            source_fingerprint=str(source_identity["fingerprint"]),
            expression=expression,
            source_origins=source_identity.get("source_origins"),
            ancestor_version_ids=source_identity.get("ancestor_version_ids"),
        )
        self._log_transform(source, "derive", name, {"expression": expression})
        return f"派生数据集 '{name}' 已创建: {df.shape[0]} 行 x {df.shape[1]} 列"

    def derive_multi(self, sources: list[str], name: str, df: pd.DataFrame, expression: str = "") -> str:
        """Create one analysis version with explicit multi-parent lineage."""
        try:
            _validate_persistence_alias(name, self._datasets)
        except ValueError as exc:
            return "Error: " + str(exc)
        parents = [self.get_data_identity(source) for source in sources]
        if not sources or len(parents) != len(sources) or any(not item for item in parents):
            return "Error: every multi-source parent must have a registered data identity"
        if name in self._datasets:
            return f"Error: derived dataset '{name}' already exists; choose a new analysis dataset name"
        self._datasets[name] = df.copy()
        parent_ids = [str(item["version_id"]) for item in parents]
        self._derived_lineage[name] = {"sources": list(sources), "expression": expression}
        origins = {json.dumps(origin,sort_keys=True):origin for parent in parents for origin in parent.get("source_origins",[{"kind":"unregistered"}])}
        self._set_identity(name, self._datasets[name], role="analysis", parent_version_ids=parent_ids,
                           source_fingerprint="multi:" + ",".join(str(item["fingerprint"]) for item in parents), expression=expression,
                           source_origins=[origins[key] for key in sorted(origins)],
                           ancestor_version_ids=[ancestor for parent in parents for ancestor in parent.get("ancestor_version_ids",[])])
        for source in sources:
            self._log_transform(source, "derive_multi", name, {"expression": expression, "sources": list(sources)})
        return f"多父派生数据集 '{name}' 已创建: {df.shape[0]} 行 x {df.shape[1]} 列"

    def log_transform(self, source: str, operation: str, target: str, detail: str = "") -> None:
        """记录变换操作到血缘日志。供 transform_data 等工具调用。"""
        self._log_transform(source, operation, target, {"detail": detail} if detail else {})

    def _log_transform(self, source: str, operation: str, target: str, extra: dict = None) -> None:
        entry = {
            "from": source,
            "op": operation,
            "to": target,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        if extra:
            entry.update(extra)
        self._transform_log.append(entry)

    def get_transform_log(self) -> list[dict[str, Any]]:
        """返回变换血缘日志。"""
        return list(self._transform_log)

    def list_datasets(self) -> dict[str, dict]:
        result = {}
        for name, df in self._datasets.items():
            lineage = self._derived_lineage.get(name, {})
            meta = self._metadata.get(name, {})
            result[name] = {
                "rows": df.shape[0],
                "columns": df.shape[1],
                "column_names": list(df.columns),
                "derived_from": lineage.get("source"),
                "data_identity": self.get_data_identity(name),
            }
            if meta:
                result[name]["metadata"] = meta
        return result

    def remove(self, name: str) -> str:
        if name in self._datasets:
            del self._datasets[name]
            self._derived_lineage.pop(name, None)
            self._metadata.pop(name, None)
            return f"数据集 '{name}' 已删除"
        return f"数据集 '{name}' 不存在"

    def relabel_dataset(self, source: str, target: str) -> str:
        """Move a host-loaded snapshot without recomputing its identity."""
        if source not in self._datasets or target in self._datasets:
            return "Error: relabel source missing or target already exists"
        try: validate_dataset_alias(target)
        except ValueError: return "Error: invalid dataset alias"
        self._datasets[target]=self._datasets.pop(source)
        self._metadata[target]=self._metadata.pop(source,{})
        if source in self._derived_lineage:self._derived_lineage[target]=self._derived_lineage.pop(source)
        self._log_transform(source,"relabel_dataset",target,{"retained_version_id":self.get_data_identity(target).get("version_id","")})
        return target

    @contextmanager
    def _namespace_transaction(self):
        """Single owner for ingestion namespace rollback; frames are copy-on-write."""
        before = (dict(self._datasets), copy.deepcopy(self._metadata),
                  copy.deepcopy(self._derived_lineage), copy.deepcopy(self._transform_log))
        try:
            yield
        except BaseException:
            self._datasets, self._metadata, self._derived_lineage, self._transform_log = before
            raise

    def commit_ingestion(self, commit, state=None):
        """One ingestion owner for memory, participating files and trust state."""
        from data_agent.utils.atomic_files import rollback_atomic_writes
        before_state = copy.deepcopy(state.__dict__) if state is not None else None
        try:
            with self._namespace_transaction(), rollback_atomic_writes():
                return commit()
        except BaseException:
            if state is not None:
                state.__dict__.clear()
                state.__dict__.update(before_state)
            raise

    def install_loaded_data(self, name, raw_df, analysis_df, source_origin, expression, replace_existing=False):
        """Commit raw parent, active analysis and optional history together."""
        validate_dataset_alias(name)
        exists = name in self._datasets
        if replace_existing and not exists:
            raise ValueError(f"数据集 '{name}' 不存在；reload_data 只更新已有数据集。")
        if exists and not replace_existing:
            raise ValueError(f"数据集 '{name}' 已存在；请指定新的数据集名称以避免覆盖已有分析版本。")
        with self._namespace_transaction():
            archived = self.archive_version(name) if exists else ""
            if archived.startswith("Error:"): raise ValueError(archived)
            raw_name = self.next_analysis_name(name, "raw")
            raw_message = self.add(raw_name, raw_df, source_origin=source_origin)
            if raw_message.startswith("Error:"): raise ValueError(raw_message)
            derived_message = self.derive(raw_name, name, analysis_df, expression=expression)
            if derived_message.startswith("Error:"): raise ValueError(derived_message)
        return {"raw_dataset": raw_name, "archived_dataset": archived,
                "raw_message": raw_message, "derived_message": derived_message}

    def rebind_uploaded_objects(self, moves, persist) -> None:
        """Own namespace mutation and roll it back if adapter persistence fails."""
        with self._namespace_transaction():
            for source, target, replace in moves:
                if source == target:
                    continue
                if replace:
                    archived = self.archive_version(target)
                    if archived.startswith("Error:"):
                        raise ValueError(archived)
                result = self.relabel_dataset(source, target)
                if result.startswith("Error:"):
                    raise ValueError(result)
            persist()

    def archive_version(self, name: str, label: str = "history") -> str:
        """Move an active dataset to an immutable, addressable history name.

        This is intentionally a rename of the stored snapshot rather than a
        copy followed by deletion: its dataframe, data identity and lineage
        stay intact.  A caller can then create a new active version using the
        original name, while receipts bound to the prior fingerprint remain
        auditable and can be invalidated by the freshness gate.
        """
        if name not in self._datasets:
            return f"Error: dataset '{name}' does not exist"
        archived_name = self.next_analysis_name(name, label)
        identity = copy.deepcopy(self.get_data_identity(name))
        self._datasets[archived_name] = self._datasets.pop(name)
        metadata = self._metadata.pop(name, {})
        self._metadata[archived_name] = metadata
        lineage = self._derived_lineage.pop(name, None)
        if lineage is not None:
            self._derived_lineage[archived_name] = lineage
        self.set_metadata(archived_name, "archived_from", name)
        self.set_metadata(archived_name, "archived_version_id", identity.get("version_id", ""))
        self._log_transform(
            name,
            "archive_version",
            archived_name,
            {"retained_version_id": identity.get("version_id", "")},
        )
        return archived_name


def _create_workspace_registry(
    current_context_getter,
    ensure_context_scope,
    is_context_workspace_token,
    operate_context_workspace,
):
    """Return opaque bindings and policy-enforcing operations over closure-local stores."""

    class BindingToken:
        __slots__ = ("__weakref__",)

    stores = weakref.WeakKeyDictionary()
    owners = weakref.WeakKeyDictionary()
    default_bindings = weakref.WeakKeyDictionary()
    mutating_operations = frozenset({
        "add",
        "derive",
        "derive_multi",
        "archive_version",
        "relabel_dataset",
        "rebind_uploaded_objects",
        "install_loaded_data",
        "commit_ingestion",
        "remove",
        "set_metadata",
        "log_transform",
        "save_meta",
        "persist",
        "set_project",
        "clear_project",
    })

    def bind(owner, storage):
        token = BindingToken()
        stores[token] = storage if isinstance(storage, Workspace) else Workspace()
        if owner is not None:
            owners[token] = weakref.ref(owner)
        return token

    def bind_default(proxy):
        default_bindings[proxy] = bind(None, None)

    def operate_default(proxy, operation, *args):
        token = default_bindings.get(proxy)
        if token is None:
            raise RuntimeError("Default workspace binding is no longer available")
        return operate(token, operation, *args)

    def resolve(token):
        storage = stores.get(token)
        if storage is None:
            raise RuntimeError("Workspace binding is no longer available")
        owner_ref = owners.get(token)
        owner = owner_ref() if owner_ref is not None else None
        from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

        scope = WorkspaceScopeSnapshot() if owner is None else owner.workspace_scope
        if owner is not None and scope is None:
            scope = ensure_context_scope(owner)
        return storage, owner, scope

    def readable(scope, name, storage):
        if scope.phase=="legacy":return True
        if scope.phase not in {"execution","planning"}:return False
        if name in scope.allowed_datasets:return True
        if scope.phase!="execution":return False
        identities={n:storage.get_data_identity(n) for n in storage._datasets}
        authorized={identities[n].get("version_id") for n in scope.allowed_datasets if n in identities}
        roots={json.dumps(o,sort_keys=True) for n in scope.allowed_datasets for o in identities.get(n,{}).get("source_origins",[])}
        pending=list(identities.values())
        while pending:
            accepted=[i for i in pending if i.get("parent_version_ids") and set(i["parent_version_ids"]).issubset(authorized) and i.get("source_origins") and {json.dumps(o,sort_keys=True) for o in i["source_origins"]}.issubset(roots)]
            if not accepted:break
            authorized.update(i["version_id"] for i in accepted)
            pending=[i for i in pending if i not in accepted]
        return identities.get(name,{}).get("version_id") in authorized

    def visible_datasets(storage, scope):
        if scope.phase in {"synthesis", "error"}:
            return {}
        visible = storage.list_datasets()
        if scope.phase == "legacy":
            return copy.deepcopy(visible)
        result = {
            name: copy.deepcopy(info)
            for name, info in visible.items()
            if readable(scope,name,storage)
        }
        if scope.phase == "planning":
            approved = {"rows", "columns", "column_names", "derived_from"}
            result = {
                name: {key: value for key, value in info.items() if key in approved}
                for name, info in result.items()
            }
        for info in result.values():
            if info.get("derived_from") not in scope.allowed_datasets:
                info["derived_from"] = None
        return result

    def visible_history(storage, scope):
        if scope.phase in {"synthesis", "error", "planning"}:
            return []
        log = storage.get_transform_log()
        if scope.phase == "legacy":
            return copy.deepcopy(log)
        allowed = {name for name in storage._datasets if readable(scope,name,storage)}
        return copy.deepcopy([
            entry for entry in log
            if entry.get("from") in allowed and entry.get("to") in allowed
        ])

    def catalog_snapshot(storage, owner, scope):
        from dataclasses import asdict
        from data_agent.agent.publication.contracts import digest, encode
        raw=asdict(scope)
        raw["session_id"]=owner.session_id if owner is not None else scope.session_id
        raw["allowed_datasets"]=sorted(raw["allowed_datasets"])
        raw["dataset_contract_ids"]=sorted(raw["dataset_contract_ids"])
        from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
        captured=WorkspaceScopeSnapshot(**raw)
        visible=visible_datasets(storage,captured)
        result=_catalog_result(visible,visible_history(storage,captured))
        return {"binding":{"session_id":raw["session_id"],"scope":raw,"scope_fingerprint":captured.fingerprint,"snapshot_sha256":digest(encode(result))},
                "result":result,"data_identities":{n:storage.get_data_identity(n) for n in visible}}

    def write_error(scope, name, derived=False):
        if scope.phase in {"synthesis", "error"}:
            return f"Error: {scope.phase}_cannot_mutate_raw_data"
        if scope.phase == "execution" and name not in scope.allowed_datasets:
            return "Error: derived_scope_not_registered" if derived else "Error: dataset_outside_current_task_scope"
        return ""

    def operate(token, operation, *args):
        active_owner = current_context_getter()
        if (
            active_owner is not None
            and not is_context_workspace_token(active_owner, token)
        ):
            return operate_context_workspace(active_owner, operation, *args)
        storage, owner, scope = resolve(token)
        if operation in {"set_project", "clear_project"} and scope.phase == "execution":
            return "Error: execution_cannot_change_project_identity"
        if (
            operation in mutating_operations
            and scope.phase in {"planning", "synthesis", "error"}
        ):
            return f"Error: {scope.phase}_cannot_mutate_raw_data"
        if operation == "restore_persisted_snapshot":
            # Control plane only: source session comes from the bound owner,
            # no caller-supplied frame, identity, path or session is accepted.
            return owner is not None and storage.restore_persisted_snapshot(owner.session_id, args[0])
        if operation == "scope":
            return scope
        if operation == "get":
            name = args[0]
            if not readable(scope, name, storage) or scope.phase == "planning":
                return None
            frame = storage.get(name)
            return frame.copy(deep=True) if frame is not None else None
        if operation == "exists":
            name = args[0]
            return readable(scope, name, storage) and name in storage._datasets
        if operation == "list":
            return visible_datasets(storage, scope)
        if operation == "metadata":
            name, key = args
            if not readable(scope, name, storage) or scope.phase in {"synthesis", "error"}:
                return None if key else {}
            meta = copy.deepcopy(storage.get_metadata(name))
            if scope.phase == "planning":
                safe = {k: v for k, v in meta.items() if k in {"quality", "schema"}}
                return safe.get(key) if key else safe
            return meta.get(key) if key else meta
        if operation == "data_identity":
            name = args[0]
            if not readable(scope, name, storage) or scope.phase in {"synthesis", "error", "planning"}:
                return {}
            return storage.get_data_identity(name)
        if operation == "publication_measurement":
            # Rebuild only a host decision against current source bytes/schema.
            # Synthesis raw-read restrictions still apply to every model API.
            from data_agent.agent.confirmation.runtime import build_measurement_mapping_candidate
            return build_measurement_mapping_candidate(workspace=storage, **args[0])
        if operation == "bound_upload_inventory":
            # Ingestion control plane: names and original-object eligibility
            # survive a finished task's narrower scope. No frames, columns or
            # values become readable to model tools.
            return {name: bool(meta.get("_source_path") and not meta.get("archived_from")
                               and storage.get_data_identity(name).get("role") != "raw")
                    for name in storage._datasets
                    for meta in [storage.get_metadata(name)]}
        if operation == "publication_catalog_result":
            # Replay the captured visibility policy; no model raw-read grant.
            binding=args[0]
            if binding is None:
                return catalog_snapshot(storage,owner,scope)
            from data_agent.agent.publication.contracts import validate_catalog_binding
            captured=validate_catalog_binding(binding,owner.session_id if owner is not None else "")
            return catalog_snapshot(storage,owner,captured)
        if operation == "publication_identity":
            return storage.get_data_identity(args[0])
        if operation == "publication_conversion_audit":
            source_name, target_name, requests = args
            source, target = storage.get(source_name), storage.get(target_name)
            if source is None or target is None or not source.index.equals(target.index) or list(source.columns)!=list(target.columns):return None
            from data_agent.tools.data_clean import _conversion_audit
            audits=[]
            for request in requests:
                column, kind, error = request
                if column not in source.columns:return None
                if error and not source[column].equals(target[column]):return None
                audits.append(_conversion_audit(source[column],target[column],target_type=kind,error=error))
            return audits
        if operation == "publication_diagnostic_result":
            tool,arguments=args;frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.data_understand import _quick_profile_result,_readiness_result,_preview_result,_quality_result
            if tool=="interpret_dataset":
                from data_agent.tools.data_understand import _interpret_result
                peers={}
                for name in arguments.get("_bound_reads",[]):
                    if name==arguments["name"]:continue
                    other=storage.get(name)
                    if other is None:return None
                    peers[name]=other
                try:return _interpret_result(frame,arguments["name"],peers)
                except (ValueError,TypeError,OverflowError):return None
            if tool=="suggest_column_types":
                from data_agent.tools.data_clean import _type_suggestions_result
                try:return _type_suggestions_result(frame,arguments["name"])
                except (ValueError,TypeError,OverflowError):return None
            if tool=="detect_data_quality":
                try:return _quality_result(frame,arguments["name"])
                except (ValueError,TypeError,OverflowError):return None
            if tool=="preview_data":
                try:return _preview_result(frame,arguments["name"],arguments.get("n",10))
                except (ValueError,TypeError,OverflowError):return None
            try:return _quick_profile_result(frame,arguments["name"],arguments.get("compact",False)) if tool=="quick_profile" else _readiness_result(frame,arguments["name"],arguments.get("intent",""))
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_source_unit_observation":
            name,expected,metric,column,tool,result=args
            if storage.get_data_identity(name)!=expected:
                return {"reason":"源单位的原对象身份不能核定。","units":[],"valid_rows":0}
            from data_agent.agent.publication.source_units import source_unit_observation
            return source_unit_observation(storage.get(name),metric,column,tool,result)
        if operation == "publication_period_comparison_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _period_comparison_result
            try:return _period_comparison_result(frame,arguments,storage.get_metadata(arguments["name"],"_column_algebra"))
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_forecast_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.forecasting import _forecast_result
            try:return _forecast_result(frame,arguments,storage.get_data_identity(arguments["name"]))
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_time_synthesis_result":
            from data_agent.tools.multifile import _synthesis_parameters, _time_synthesis_result
            arguments=args[0]
            try:
                names,_=_synthesis_parameters(arguments)
                aligned,result=_time_synthesis_result({n:storage.get(n) for n in names},
                    {n:storage.get_data_identity(n) for n in names},arguments)
                target=arguments.get("save_as")
                if target:
                    child=storage.get(target)
                    if child is None or not child.equals(aligned):return None
                    result.update(dataset=target,derived_dataset=target,derived_identity=storage.get_data_identity(target))
                return result
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_time_series_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _time_series_result
            try:return _time_series_result(frame,arguments)
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_factor_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.factor_analysis import _attribution_result
            try:return _attribution_result(frame,arguments,storage.get_data_identity(arguments["name"]))
            except (ValueError,TypeError):return None
        if operation == "publication_curve_sensitivity":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.curve_fitting import _curve_points, _weight_sensitivity
            try:
                points,_=_curve_points(frame, **{key:arguments[key] for key in ("series_columns","x_col","y_col","zero_values","weight_col","mature_through_col","compare_weights") if key in arguments})
                return _weight_sensitivity(points)
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_contribution_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _contribution_result
            try:return _contribution_result(frame,arguments)
            except (ValueError,TypeError):return None
        if operation == "persisted_identity_matches":
            if owner is None:return False
            name,identity=args;snapshot=_read_persisted_snapshot(owner.session_id,name)
            return bool(snapshot is not None and snapshot[0].get("data_identity")==identity
                and snapshot[1].equals(storage.get(name)))
        if operation == "register_child_contract":
            if owner is None or scope.phase in {"planning","synthesis","error"}:return False
            receipt_id=args[0];receipt=next((r for r in owner.analysis_state.tool_receipts if r.get("id")==receipt_id),{})
            from data_agent.agent.artifact_refs import verified_child_contract_producer
            effect=verified_child_contract_producer(owner,None,receipt_id)
            target=effect["object"]["name"] if effect else None
            snapshot=_read_persisted_snapshot(owner.session_id,target) if effect else None
            if (snapshot is None or snapshot[0].get("data_identity")!=effect["object"]["identity"]
                    or not snapshot[1].equals(storage.get(target))):return False
            from data_agent.tools.data_io import _record_trust_workflow
            from data_agent.utils.data_features import scan_data_quality
            def register_child():
                _record_trust_workflow(session_id=owner.session_id,state=owner.analysis_state,
                    dataset=target,df=snapshot[1],applied=[],needs_confirm=[],
                    quality=scan_data_quality(snapshot[1]),interpretation_data={},
                    detail_path=receipt["detail_ref"]["path"],producer_receipt_id=receipt_id)
                return True
            return storage.commit_ingestion(register_child,owner.analysis_state)
        if operation == "publication_top_n_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _top_n_selection
            try:top,result=_top_n_selection(frame,arguments)
            except (ValueError,TypeError):return None
            target=arguments.get("save_as")
            if target:
                child=storage.get(target)
                if child is None or not child.equals(top):return None
                result.update(dataset=target,source_dataset=arguments["name"])
            return result
        if operation == "publication_segmentation_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _segmentation_result
            try:return _segmentation_result(frame,arguments)
            except (ValueError,TypeError):return None
        if operation == "publication_cohort_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _cohort_result
            try:return _cohort_result(frame,arguments)
            except (ValueError,TypeError):return None
        if operation == "publication_funnel_result":
            arguments=args[0];frame=storage.get(arguments["name"])
            if frame is None:return None
            from data_agent.tools.eda import _funnel_result
            try:return _funnel_result(frame,arguments)
            except (ValueError,TypeError,OverflowError):return None
        if operation == "publication_chart_count_matches":
            name,identity,arguments,metadata=args
            if storage.get_data_identity(name)!=identity:return False
            from data_agent.tools.visualization import _count_chart_matches
            return _count_chart_matches(storage.get(name),arguments,metadata)
        if operation == "publication_distribution_audit":
            name,columns=args;frame=storage.get(name)
            if frame is None:return None
            from data_agent.tools.eda import _distribution_columns,_distribution_observations,_distribution_quantiles
            import numpy as np
            try:selected=_distribution_columns(frame,columns)
            except ValueError:return None
            audits={}
            for column in selected:
                values,observation=_distribution_observations(frame[column])
                audits[column]={"observation":observation,"constant_sample":bool(len(values) and np.all(values==values[0])),"quantiles":_distribution_quantiles(values)}
            return audits
        if operation == "publication_resample_audit":
            name,date_col=args;frame=storage.get(name)
            if frame is None or date_col not in frame.columns:return None
            from data_agent.tools.data_transform import _resample_input
            return _resample_input(frame,date_col)[1]
        if operation == "publication_cleaning_state":
            name, columns, deduplicate = args
            frame = storage.get(name)
            if frame is None: return None
            if deduplicate: frame = frame.drop_duplicates()
            selected = columns or list(frame.columns)
            if any(c not in frame.columns for c in selected): return None
            return {"rows": len(frame), "columns": [
                {"column": c, "missing": int(frame[c].isna().sum())} for c in selected]}
        if operation == "publication_exists":
            # Host-only existence check for an exact canonical target.
            # No names, identities, columns or raw values are returned.
            return args[0] in storage._datasets
        if operation == "receipt_identity_matches":
            # Evidence validation compares an already captured host receipt
            # with current storage. A later task may have a narrower raw-data
            # scope, but that must not turn an unchanged receipt into a false
            # stale_data_binding. Return only equality, never the identity or
            # dataset content outside the current task scope.
            name, expected = args
            return bool(
                isinstance(expected, dict)
                and expected.get("version_id")
                and expected.get("fingerprint")
                and storage.get_data_identity(name) == expected
            )
        if operation == "next_analysis_name":
            source, label = args
            if not readable(scope, source, storage) or scope.phase in {"synthesis", "error", "planning"}:
                return ""
            return storage.next_analysis_name(source, label)
        if operation == "planning_schema":
            name = args[0]
            if scope.phase != "planning" or not readable(scope, name, storage):
                return []
            frame = storage.get(name)
            return list(frame.columns) if frame is not None else []
        if operation == "planning_quality":
            name = args[0]
            if scope.phase != "planning" or not readable(scope, name, storage):
                return {}
            return copy.deepcopy(storage.get_metadata(name, "quality") or {})
        if operation == "planning_preview":
            name, rows = args
            if scope.phase != "planning" or not readable(scope, name, storage):
                return []
            limit = max(0, min(int(rows), int(getattr(owner, "planning_preview_rows", 5)), 20))
            frame = storage.get(name)
            return copy.deepcopy(frame.head(limit).to_dict("records")) if frame is not None else []
        if operation == "add":
            name, frame, origin = args
            return write_error(scope, name) or storage.add(name, frame, source_origin=origin)
        if operation in {"derive","derive_multi"}:
            source_arg,name,frame,expression=args
            sources=[source_arg] if operation=="derive" else source_arg
            if scope.phase in {"synthesis","error","planning"}:return f"Error: {scope.phase}_cannot_mutate_raw_data"
            if not sources or any(not readable(scope,n,storage) for n in sources):return "Error: dataset_outside_current_task_scope"
            if name in storage._datasets and not readable(scope,name,storage):return "Error: dataset_outside_current_task_scope"
            if owner is not None and owner.session_id:
                def commit_derived():
                    message=(storage.derive(sources[0],name,frame,expression) if operation=="derive"
                             else storage.derive_multi(sources,name,frame,expression))
                    if message.startswith("Error:"):return message
                    storage.persist_dataset(owner.session_id,name)
                    storage.save_meta(owner.session_id,[name])
                    snapshot=_read_persisted_snapshot(owner.session_id,name)
                    if (snapshot is None or not snapshot[1].equals(storage.get(name))
                            or snapshot[0].get("data_identity")!=storage.get_data_identity(name)):
                        raise ValueError("派生对象的实际快照、元数据或身份读回不一致。")
                    return message
                return storage.commit_ingestion(commit_derived,getattr(owner,"analysis_state",None))
            return storage.derive(sources[0],name,frame,expression) if operation=="derive" else storage.derive_multi(sources,name,frame,expression)
        if operation == "remove":
            name = args[0]
            return write_error(scope, name) or storage.remove(name)
        if operation == "commit_ingestion":
            if scope.phase != "legacy":
                raise ValueError("file_ingestion_requires_ingestion_scope")
            return storage.commit_ingestion(args[0], getattr(owner, "analysis_state", None))
        if operation == "install_loaded_data":
            if scope.phase != "legacy":
                raise ValueError("file_ingestion_requires_ingestion_scope")
            return storage.install_loaded_data(*args)
        if operation == "rebind_uploaded_objects":
            if scope.phase != "legacy":
                raise ValueError("upload_object_binding_requires_ingestion_scope")
            return storage.rebind_uploaded_objects(*args)
        if operation == "relabel_dataset":
            source,target=args
            if scope.phase=="planning":return "Error: planning_cannot_relabel_data"
            return write_error(scope,source) or write_error(scope,target,True) or storage.relabel_dataset(source,target)
        if operation == "archive_version":
            name, label = args
            if not readable(scope, name, storage):
                return "Error: dataset_outside_current_task_scope"
            return write_error(scope, name) or storage.archive_version(name, label)
        if operation == "set_metadata":
            name, key, value = args
            return ("Error: dataset_outside_current_task_scope" if not readable(scope,name,storage) else storage.set_metadata(name, key, copy.deepcopy(value)))
        if operation == "log_transform":
            source, transform, target, detail = args
            return ("Error: dataset_outside_current_task_scope" if not readable(scope,source,storage) or not readable(scope,target,storage) else storage.log_transform(source, transform, target, detail))
        if operation == "transform_log":
            return visible_history(storage, scope)
        if operation == "save_meta":
            names = None if scope.phase == "legacy" else tuple(name for name in storage._datasets if readable(scope,name,storage))
            if scope.phase in {"synthesis", "error"}:
                names = ()
            return storage.save_meta(args[0], names)
        if operation == "persist":
            session_id, name = args
            return storage.persist_dataset(session_id, name) if readable(scope, name, storage) else None
        if operation == "set_project":
            result = storage.set_project(args[0])
            if owner is not None and not result.startswith("Error:"):
                owner.project_name = args[0]
                owner.refresh_workspace_scope()
            return result
        if operation == "clear_project":
            result = storage.clear_project()
            if owner is not None:
                owner.project_name = None
                owner.refresh_workspace_scope()
            return result
        if operation == "datasets_view":
            visible = operate(token, "list")
            return {name: operate(token, "get", name) for name in visible}
        if operation == "metadata_view":
            visible = operate(token, "list")
            return {name: operate(token, "metadata", name, "") for name in visible}
        if operation == "active_project":
            return storage.active_project
        raise ValueError(f"Unsupported workspace operation: {operation}")

    return bind, operate, bind_default, operate_default


(
    _bind_workspace_store,
    _workspace_operation,
    _bind_default_workspace,
    _default_workspace_operation,
) = _create_workspace_registry(
    get_current_context,
    _ensure_context_workspace_scope,
    _is_context_workspace_token,
    _operate_context_workspace,
)
del _create_workspace_registry


def _create_workspace_token_facades(workspace_operation):
    def get_operation(token, name):
        return workspace_operation(token, "get", name)

    def add_operation(token, name, frame):
        return workspace_operation(token, "add", name, frame)

    return get_operation, add_operation


_workspace_get_operation, _workspace_add_operation = _create_workspace_token_facades(
    _workspace_operation,
)
del _create_workspace_token_facades


def _create_workspace_proxy_operation(
    current_context_getter,
    default_workspace_operation,
    context_workspace_operation,
):
    """Capture trusted dispatch facades outside the mutable module namespace."""

    def operate(proxy, operation, *args):
        context_ref = object.__getattribute__(proxy, "_WorkspaceProxy__context_ref")
        ctx = context_ref() if context_ref is not None else current_context_getter()
        if context_ref is not None and ctx is None:
            raise RuntimeError("Agent context workspace binding is no longer available")
        if ctx is None:
            return default_workspace_operation(proxy, operation, *args)
        return context_workspace_operation(ctx, operation, *args)

    return operate


class WorkspaceProxy:
    """Context-local, scope-enforcing public workspace facade."""

    def __init__(self, context=None):
        self.__context_ref = weakref.ref(context) if context is not None else None
        if context is None:
            _bind_default_workspace(self)

    __operate = _create_workspace_proxy_operation(
        get_current_context,
        _default_workspace_operation,
        _operate_context_workspace,
    )

    def _scope(self):
        return self.__operate("scope")

    def _readable(self, name: str) -> bool:
        scope = self._scope()
        if scope.phase == "legacy":
            return True
        if scope.phase in {"execution", "planning"}:
            return name in scope.allowed_datasets
        return False

    def _write_error(self, name: str, *, derived: bool = False) -> str:
        scope = self._scope()
        if scope.phase in {"synthesis", "error"}:
            return f"Error: {scope.phase}_cannot_mutate_raw_data"
        if scope.phase == "execution" and name not in scope.allowed_datasets:
            return "Error: derived_scope_not_registered" if derived else "Error: dataset_outside_current_task_scope"
        return ""

    def get(self, name: str) -> Optional[pd.DataFrame]:
        return self.__operate("get", name)

    def exists(self, name: str) -> bool:
        return self.__operate("exists", name)

    def list_datasets(self) -> dict[str, dict]:
        return self.__operate("list")

    def get_metadata(self, name: str, key: str = "") -> Any:
        return self.__operate("metadata", name, key)

    def get_data_identity(self, name: str) -> dict[str, Any]:
        return self.__operate("data_identity", name)

    def _publication_measurement_candidate(self, **parameters):
        """Host-only current confirmation proof; never returns a raw frame."""
        return self.__operate("publication_measurement", parameters)

    def _bound_upload_inventory(self) -> dict[str, bool]:
        """Host upload transaction names; never exposes model-readable data."""
        return self.__operate("bound_upload_inventory")

    def _restore_persisted_snapshot(self, name: str) -> bool:
        """Host recovery; materialization does not change tool read permissions."""
        return self.__operate("restore_persisted_snapshot", name)

    def _publication_data_identity(self, name: str) -> dict:
        """Host control-plane metadata for declared goals; no raw data access."""
        return self.__operate("publication_identity", name)

    def _publication_conversion_audit(self, source, target, requests):
        """Host-only type effects; no frames or raw values leave storage."""
        return self.__operate("publication_conversion_audit", source, target, requests)

    def _publication_catalog_result(self, binding=None):
        """Host metadata proof for exactly the existing receipt-bound objects."""
        return self.__operate("publication_catalog_result", binding)

    def _publication_diagnostic_result(self,tool,arguments):
        return self.__operate("publication_diagnostic_result",tool,arguments)

    def _publication_source_unit_observation(self,name,identity,metric,column,tool,result):
        """Host-only bounded source units;does not grant any model frame access."""
        return self.__operate("publication_source_unit_observation",name,identity,metric,column,tool,result)

    def _publication_period_comparison_result(self, arguments):
        """Storage-owned period sums and original ratios, without frame exposure."""
        return self.__operate("publication_period_comparison_result", arguments)

    def _publication_forecast_result(self, arguments):
        """Storage-owned original ordered holdout, without raw frame exposure."""
        return self.__operate("publication_forecast_result", arguments)

    def _publication_time_synthesis_result(self, arguments):
        """Host-only original multi-parent daily result; no model raw-read grant."""
        return self.__operate("publication_time_synthesis_result", arguments)

    def _publication_time_series_result(self, arguments):
        """Storage-owned original time-series arithmetic, without frame exposure."""
        return self.__operate("publication_time_series_result", arguments)

    def _publication_factor_result(self, arguments):
        """Storage-owned original OLS association, without raw frame exposure."""
        return self.__operate("publication_factor_result", arguments)

    def _publication_curve_sensitivity(self, arguments):
        """Storage-owned comparison of the receipt-bound observations; no raw frame grant."""
        return self.__operate("publication_curve_sensitivity", arguments)

    def _publication_contribution_result(self, arguments):
        """Storage-owned original decomposition; no raw frame exposure."""
        return self.__operate("publication_contribution_result", arguments)

    def _publication_persisted_identity_matches(self, name, identity):
        """Host verifies an exact owned durable snapshot; no raw frame leaves storage."""
        return self.__operate("persisted_identity_matches", name, identity)

    def _register_child_contract(self, receipt_id):
        """Host checks the real child through its exact successful operation receipt."""
        return self.__operate("register_child_contract", receipt_id)

    def _publication_top_n_result(self, arguments):
        """Host verifies selected records and actual child without exposing a frame."""
        return self.__operate("publication_top_n_result", arguments)

    def _publication_segmentation_result(self, arguments):
        """Storage-owned cluster measurements; no frame or raw observations leave storage."""
        return self.__operate("publication_segmentation_result", arguments)

    def _publication_cohort_result(self, arguments):
        """Storage-owned monthly measurements; no frame or raw events leave storage."""
        return self.__operate("publication_cohort_result", arguments)

    def _publication_funnel_result(self, arguments):
        """Storage-owned funnel measurements; no frame or raw events leave storage."""
        return self.__operate("publication_funnel_result", arguments)

    def _publication_chart_count_matches(self,name,identity,arguments,metadata):
        """Host-only original record-count equality;no frame or read grant."""
        return self.__operate("publication_chart_count_matches",name,identity,arguments,metadata)

    def _publication_distribution_audit(self, name, columns):
        """Host-only finite observation counts; no frame or cell values."""
        return self.__operate("publication_distribution_audit", name, columns)

    def _publication_resample_audit(self, name, date_col):
        """Host-only date exclusion counts; no frame or cell values."""
        return self.__operate("publication_resample_audit", name, date_col)

    def _publication_cleaning_state(self, name, columns=(), deduplicate=False):
        """Host-only operation counts; never returns a frame or cell values."""
        return self.__operate("publication_cleaning_state", name, columns, deduplicate)

    def _publication_dataset_exists(self, name: str) -> bool:
        """Host publication checks presence without widening model reads."""
        return self.__operate("publication_exists", name)

    def _receipt_identity_matches(self, name: str, expected: dict[str, Any]) -> bool:
        """Check a host receipt against storage without exposing raw data."""
        return self.__operate("receipt_identity_matches", name, expected)

    def next_analysis_name(self, source: str, label: str = "analysis") -> str:
        return self.__operate("next_analysis_name", source, label)

    def planning_schema(self, name: str) -> list[str]:
        return self.__operate("planning_schema", name)

    def planning_quality(self, name: str) -> Any:
        return self.__operate("planning_quality", name)

    def planning_preview(self, name: str, *, rows: int = 5) -> list[dict[str, Any]]:
        return self.__operate("planning_preview", name, rows)

    def add(self, name: str, df: pd.DataFrame, *, source_origin: dict[str, Any] | None = None) -> str:
        return self.__operate("add", name, df, source_origin)

    def derive(self, source: str, name: str, df: pd.DataFrame, expression: str = "") -> str:
        return self.__operate("derive", source, name, df, expression)

    def derive_multi(self, sources: list[str], name: str, df: pd.DataFrame, expression: str = "") -> str:
        return self.__operate("derive_multi", sources, name, df, expression)

    def remove(self, name: str) -> str:
        return self.__operate("remove", name)

    def commit_ingestion(self, commit):
        return self.__operate("commit_ingestion", commit)

    def install_loaded_data(self, name, raw_df, analysis_df, source_origin, expression, replace_existing=False):
        return self.__operate("install_loaded_data", name, raw_df, analysis_df, source_origin, expression, replace_existing)

    def rebind_uploaded_objects(self, moves, persist) -> None:
        return self.__operate("rebind_uploaded_objects", moves, persist)

    def relabel_dataset(self, source: str, target: str) -> str:
        return self.__operate("relabel_dataset",source,target)

    def archive_version(self, name: str, label: str = "history") -> str:
        return self.__operate("archive_version", name, label)

    def set_metadata(self, name: str, key: str, value: Any) -> Any:
        return self.__operate("set_metadata", name, key, value)

    def log_transform(self, source: str, operation: str, target: str, detail: str = "") -> Any:
        return self.__operate("log_transform", source, operation, target, detail)

    def get_transform_log(self) -> list[dict[str, Any]]:
        return self.__operate("transform_log")

    # Persistence operates on internal storage and does not return raw data.
    def save_meta(self, session_id: str) -> None:
        return self.__operate("save_meta", session_id)

    def persist_dataset(self, session_id: str, name: str) -> str | None:
        return self.__operate("persist", session_id, name)

    def set_object(self, name: str) -> str:
        return self.set_project(name)

    def set_project(self, name: str) -> str:
        return self.__operate("set_project", name)

    def clear_object(self) -> str:
        return self.clear_project()

    def clear_project(self) -> str:
        return self.__operate("clear_project")

    def __getattr__(self, name):
        raise AttributeError(f"WorkspaceProxy does not expose '{name}'")

    @property
    def _datasets(self):
        return self.__operate("datasets_view")

    @property
    def _metadata(self):
        return self.__operate("metadata_view")

    @property
    def active_object(self) -> Optional[str]:
        return self.__operate("active_project")

    @property
    def active_project(self) -> Optional[str]:
        return self.__operate("active_project")


# 全局 facade；无 AgentContext 时使用默认工作空间，保持旧测试和 CLI 兼容。
del _create_workspace_proxy_operation
_install_context_workspace_binding(
    _bind_workspace_store,
    WorkspaceProxy,
    _workspace_operation,
)
import data_agent.agent.context as _context_module
delattr(_context_module, "_install_context_workspace_binding")
del _context_module, _install_context_workspace_binding
workspace = WorkspaceProxy()



def _read_persisted_snapshot(session_id, name):
    """One disk snapshot reader for restoration and post-restart identity checks."""
    from data_agent.config import get_config
    try:
        validate_dataset_alias(name)
        validate_dataset_alias(session_id)
        from data_agent.migration import read_session_migration_status
        if read_session_migration_status(session_id).get("mode") == "read_only_missing_original":
            return None
        sessions = get_config().sessions_resolved.resolve()
        root = (sessions / session_id).resolve()
        data = (root / "data").resolve()
        meta_path = (root / "workspace_meta.json").resolve()
        if not root.is_relative_to(sessions) or not data.is_relative_to(root) or not meta_path.is_relative_to(root):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict): return None
        info = meta.get(name)
        if not isinstance(info, dict) or not isinstance(info.get("data_identity"), dict) or not info["data_identity"]:
            return None
        path = (data / (name + ".parquet")).resolve()
        if not path.is_relative_to(data): return None
        if path.exists(): frame = pd.read_parquet(path)
        else:
            path = (data / (name + ".pkl")).resolve()
            if not path.is_relative_to(data) or not path.exists(): return None
            frame = pd.read_pickle(path)
        if Workspace._frame_fingerprint(frame) != info["data_identity"].get("fingerprint"):
            return None
        return info, frame
    except (OSError, ValueError, TypeError, KeyError):
        return None


def persisted_receipt_identity_matches(session_id, name, identity):
    """Read-only identity equality for a Workbench request after server restart."""
    snapshot = _read_persisted_snapshot(session_id, name)
    return bool(snapshot is not None and identity and snapshot[0]["data_identity"] == identity)
