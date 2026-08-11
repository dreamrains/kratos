"""工作空间管理，存储已加载的数据集，支持项目绑定和变换血缘追踪。"""

from __future__ import annotations

import copy
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


# M1 D7 advisory scope warnings. Out-of-scope writes are logged and allowed
# rather than aborting the operation. The symbol is retained for M2
# observability; ``consume_scope_advisory_warnings`` drains the buffer.
_SCOPE_ADVISORY_WARNINGS: list[dict[str, Any]] = []
_SCOPE_ADVISORY_SYMBOL = "dataset_outside_current_task_scope"


def record_scope_advisory_warning(dataset: str) -> None:
    """Record that an out-of-scope workspace write was allowed (advisory)."""
    if not dataset:
        return
    _SCOPE_ADVISORY_WARNINGS.append(
        {"warning": _SCOPE_ADVISORY_SYMBOL, "dataset": str(dataset)}
    )
    logger.warning(
        "%s (advisory): write to dataset '%s' allowed despite not being in the "
        "current task scope.",
        _SCOPE_ADVISORY_SYMBOL,
        dataset,
    )


def consume_scope_advisory_warnings() -> list[dict[str, Any]]:
    """Return and clear accumulated workspace scope advisory warnings."""
    drained = list(_SCOPE_ADVISORY_WARNINGS)
    _SCOPE_ADVISORY_WARNINGS.clear()
    return drained


def _create_workspace_context_sync(current_context_getter):
    """Capture the trusted getter used by legacy raw-storage project updates."""

    def sync(project_name):
        ctx = current_context_getter()
        if ctx is not None:
            ctx.project_name = project_name

    return sync


_sync_current_workspace_project = _create_workspace_context_sync(get_current_context)
del _create_workspace_context_sync


class Workspace:
    """管理工作空间中的数据集快照，支持分析项目绑定和变换血缘。"""

    def __init__(self):
        self._datasets: dict[str, pd.DataFrame] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._derived_lineage: dict[str, dict[str, Any]] = {}
        self._transform_log: list[dict[str, Any]] = []
        self._raw_snapshots: dict[str, pd.DataFrame] = {}
        self._raw_snapshot_info: dict[str, dict[str, Any]] = {}
        self._dataset_versions: dict[str, pd.DataFrame] = {}
        self._version_info: dict[str, dict[str, Any]] = {}
        self._active_version_by_name: dict[str, str] = {}
        self._active_project: Optional[str] = None

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

    def add(self, name: str, df: pd.DataFrame) -> str:
        if name in self._active_version_by_name or any(
            info.get("logical_name") == name for info in self._version_info.values()
        ):
            return "Error: versioned_dataset_requires_promotion"
        self._datasets[name] = df.copy()
        return f"数据集 '{name}' 已加载: {df.shape[0]} 行 x {df.shape[1]} 列"

    @staticmethod
    def _fingerprint_suffix(fingerprint: str) -> str:
        value = str(fingerprint or "")
        return value.split(":", 1)[-1][:12] or "unknown"

    def register_raw_snapshot(
        self,
        name: str,
        frame: pd.DataFrame,
        source_fingerprint: str,
    ) -> dict[str, Any]:
        """Register an immutable, hidden snapshot of user-provided data."""
        from data_agent.agent.data_lineage import frame_fingerprint

        actual_fingerprint = frame_fingerprint(frame)
        if str(source_fingerprint or "") != actual_fingerprint:
            raise ValueError("source_fingerprint does not match the raw frame")
        source_fingerprint = actual_fingerprint
        dataset_id = f"raw_{name}_{self._fingerprint_suffix(source_fingerprint)}"
        existing_frame = self._raw_snapshots.get(dataset_id)
        existing_info = self._raw_snapshot_info.get(dataset_id)
        if existing_frame is not None or existing_info is not None:
            if (
                existing_frame is None
                or existing_info is None
                or existing_info.get("logical_name") != name
                or existing_info.get("source_fingerprint") != source_fingerprint
                or frame_fingerprint(existing_frame) != source_fingerprint
            ):
                raise RuntimeError("raw_dataset_id_collision")
            self.set_metadata(name, "_raw_dataset_id", dataset_id)
            self.set_metadata(name, "_source_fingerprint", source_fingerprint)
            return copy.deepcopy(existing_info)

        info = {
            "dataset_id": dataset_id,
            "logical_name": name,
            "source_fingerprint": source_fingerprint,
            "role": "raw",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._raw_snapshots[dataset_id] = frame.copy(deep=True)
        self._raw_snapshot_info[dataset_id] = info
        self.set_metadata(name, "_raw_dataset_id", dataset_id)
        self.set_metadata(name, "_source_fingerprint", source_fingerprint)
        return copy.deepcopy(info)

    def _activate_analysis_version(
        self,
        name: str,
        frame: pd.DataFrame,
        info: dict[str, Any],
    ) -> dict[str, Any]:
        stored_info = copy.deepcopy(info)
        dataset_id = str(stored_info["dataset_id"])
        stored = frame.copy(deep=True)
        self._dataset_versions[dataset_id] = stored
        self._version_info[dataset_id] = stored_info
        self._datasets[name] = stored.copy(deep=True)
        self._active_version_by_name[name] = dataset_id
        self.set_metadata(name, "_raw_dataset_id", stored_info["raw_dataset_id"])
        self.set_metadata(name, "_active_dataset_id", dataset_id)
        self.set_metadata(
            name,
            "_source_fingerprint",
            stored_info.get("source_fingerprint", ""),
        )
        self.set_metadata(
            name,
            "_transformation_record",
            copy.deepcopy(stored_info["transformation_record"]),
        )
        return copy.deepcopy(stored_info)

    def promote_analysis_copy(
        self,
        name: str,
        frame: pd.DataFrame,
        raw_dataset_id: str,
        transformation_record: dict[str, Any],
    ) -> dict[str, Any]:
        """Promote a copy as the next active, versioned analysis dataset."""
        raw_info = self._raw_snapshot_info.get(raw_dataset_id)
        if raw_info is None:
            raise KeyError(f"Unknown raw dataset: {raw_dataset_id}")
        if raw_info.get("logical_name") != name:
            raise ValueError("Raw snapshot does not belong to the logical dataset")

        from data_agent.agent.data_lineage import (
            finalize_transformation_record,
            frame_fingerprint,
        )

        previous_versions = [
            int(item.get("version", 0))
            for item in self._version_info.values()
            if item.get("logical_name") == name
        ]
        version = max(previous_versions, default=0) + 1
        fingerprint = frame_fingerprint(frame)
        dataset_id = (
            f"dataset_{name}_v{version}_{self._fingerprint_suffix(fingerprint)}"
        )
        finalized_record = finalize_transformation_record(
            copy.deepcopy(transformation_record),
            derived_dataset_id=dataset_id,
            version=version,
        )
        info = {
            "dataset_id": dataset_id,
            "logical_name": name,
            "raw_dataset_id": raw_dataset_id,
            "source_fingerprint": raw_info.get("source_fingerprint", ""),
            "frame_fingerprint": fingerprint,
            "version": version,
            "role": "analysis_copy",
            "transformation_record": finalized_record,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        return self._activate_analysis_version(name, frame, info)

    def restore_analysis_version(
        self,
        name: str,
        frame: pd.DataFrame,
        raw_dataset_id: str,
        saved_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Restore one verified active version without minting a new identity."""
        raw_info = self._raw_snapshot_info.get(raw_dataset_id)
        if raw_info is None or raw_info.get("logical_name") != name:
            raise ValueError("restore raw snapshot does not belong to the dataset")
        if not isinstance(saved_info, dict):
            raise TypeError("saved version info must be a mapping")

        from data_agent.agent.data_lineage import (
            finalize_transformation_record,
            frame_fingerprint,
        )

        try:
            version = int(saved_info.get("version", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("saved version must be a positive integer") from exc
        if version <= 0:
            raise ValueError("saved version must be a positive integer")

        fingerprint = frame_fingerprint(frame)
        source_fingerprint = str(raw_info.get("source_fingerprint") or "")
        dataset_id = str(saved_info.get("dataset_id") or "")
        expected_id = (
            f"dataset_{name}_v{version}_{self._fingerprint_suffix(fingerprint)}"
        )
        if dataset_id != expected_id:
            raise ValueError("saved dataset identity does not match frame and version")
        if str(saved_info.get("logical_name") or name) != name:
            raise ValueError("saved version belongs to another logical dataset")
        if str(saved_info.get("raw_dataset_id") or "") != raw_dataset_id:
            raise ValueError("saved version raw identity does not match restored raw")
        if str(saved_info.get("source_fingerprint") or "") != source_fingerprint:
            raise ValueError("saved version source fingerprint does not match restored raw")
        if str(saved_info.get("frame_fingerprint") or "") != fingerprint:
            raise ValueError("saved version frame fingerprint does not match backup")

        record = finalize_transformation_record(
            copy.deepcopy(saved_info.get("transformation_record") or {}),
            derived_dataset_id=dataset_id,
            version=version,
        )
        info = {
            **copy.deepcopy(saved_info),
            "dataset_id": dataset_id,
            "logical_name": name,
            "raw_dataset_id": raw_dataset_id,
            "source_fingerprint": source_fingerprint,
            "frame_fingerprint": fingerprint,
            "version": version,
            "role": "analysis_copy",
            "transformation_record": record,
            "created_at": str(saved_info.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        }
        return self._activate_analysis_version(name, frame, info)

    def get_raw_snapshot(self, raw_dataset_id: str) -> Optional[pd.DataFrame]:
        frame = self._raw_snapshots.get(raw_dataset_id)
        return frame.copy(deep=True) if frame is not None else None

    def get_dataset_version(self, dataset_id: str) -> Optional[pd.DataFrame]:
        frame = self._dataset_versions.get(dataset_id)
        return frame.copy(deep=True) if frame is not None else None

    def get_active_version_info(self, name: str) -> Optional[dict[str, Any]]:
        dataset_id = self._active_version_by_name.get(name)
        info = self._version_info.get(dataset_id or "")
        return copy.deepcopy(info) if info is not None else None

    def active_dataset_version_ids(self) -> list[str]:
        """Return opaque active version identities without exposing dataset contents."""
        return sorted({
            str(dataset_id)
            for dataset_id in self._active_version_by_name.values()
            if str(dataset_id)
        })

    def list_dataset_versions(self, name: str) -> list[dict[str, Any]]:
        items = [
            copy.deepcopy(info)
            for info in self._version_info.values()
            if info.get("logical_name") == name
        ]
        return sorted(items, key=lambda item: int(item.get("version", 0)))

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

        datasets_meta = {}
        names = self._datasets if dataset_names is None else dataset_names
        for name in names:
            if name not in self._datasets:
                continue
            df = self._datasets[name]
            active_info = self.get_active_version_info(name) or {}
            raw_info = self._raw_snapshot_info.get(
                str(active_info.get("raw_dataset_id", "")), {}
            )
            datasets_meta[name] = {
                "shape": list(df.shape),
                "columns": list(df.columns),
                "source_path": self._metadata.get(name, {}).get("_source_path", ""),
                "source_fmt": self._metadata.get(name, {}).get("_source_fmt", ""),
                "context": self._metadata.get(name, {}).get("context", ""),
                "active_dataset_id": active_info.get("dataset_id", ""),
                "raw_dataset_id": active_info.get("raw_dataset_id", ""),
                "source_fingerprint": raw_info.get("source_fingerprint", ""),
                "version": active_info.get("version", 0),
                "versions": self.list_dataset_versions(name),
            }

        meta_path.write_text(
            json.dumps(datasets_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Workspace meta saved", extra={"extra_data": {"session_id": session_id, "datasets": list(datasets_meta)}})

    def persist_dataset(self, session_id: str, name: str) -> str | None:
        """Save DataFrame backup for restore.

        Parquet is preferred when an engine is installed. Pickle is a local
        fallback so session restore still works in lightweight environments.
        """
        active_frame = self._datasets.get(name)
        if active_frame is None:
            return None
        from data_agent.session.history import _session_dir
        data_dir = _session_dir(session_id) / "data"
        data_dir.mkdir(exist_ok=True)

        def persist_frame(frame: pd.DataFrame, stem: str) -> Path:
            path = data_dir / f"{stem}.parquet"
            try:
                frame.to_parquet(path, index=True)
            except ImportError:
                path = data_dir / f"{stem}.pkl"
                frame.to_pickle(path)
            return path

        path = persist_frame(active_frame, name)
        active_info = self.get_active_version_info(name) or {}
        raw_frame = self._raw_snapshots.get(str(active_info.get("raw_dataset_id", "")))
        if raw_frame is not None:
            persist_frame(raw_frame, f"{name}__raw")
        logger.info("Dataset persisted", extra={"extra_data": {"session_id": session_id, "dataset": name, "path": str(path)}})
        return str(path)

    def get(self, name: str) -> Optional[pd.DataFrame]:
        return self._datasets.get(name)

    def derive(self, source: str, name: str, df: pd.DataFrame, expression: str = "") -> str:
        """从源数据派生新数据集。"""
        self._datasets[name] = df.copy()
        self._derived_lineage[name] = {
            "source": source,
            "expression": expression,
        }
        self._log_transform(source, "derive", name, {"expression": expression})
        return f"派生数据集 '{name}' 已创建: {df.shape[0]} 行 x {df.shape[1]} 列"

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
            }
            active_info = self.get_active_version_info(name)
            if active_info:
                result[name].update({
                    "dataset_id": active_info["dataset_id"],
                    "raw_dataset_id": active_info["raw_dataset_id"],
                    "version": active_info["version"],
                    "role": "analysis_copy",
                })
            if meta:
                result[name]["metadata"] = meta
        return result

    def remove(self, name: str) -> str:
        if name in self._datasets:
            del self._datasets[name]
            self._derived_lineage.pop(name, None)
            self._metadata.pop(name, None)
            self._active_version_by_name.pop(name, None)
            version_ids = [
                dataset_id
                for dataset_id, info in self._version_info.items()
                if info.get("logical_name") == name
            ]
            for dataset_id in version_ids:
                self._dataset_versions.pop(dataset_id, None)
                self._version_info.pop(dataset_id, None)
            raw_ids = [
                dataset_id
                for dataset_id, info in self._raw_snapshot_info.items()
                if info.get("logical_name") == name
            ]
            for dataset_id in raw_ids:
                self._raw_snapshots.pop(dataset_id, None)
                self._raw_snapshot_info.pop(dataset_id, None)
            return f"数据集 '{name}' 已删除"
        return f"数据集 '{name}' 不存在"


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
        "register_raw",
        "promote_copy",
        "restore_version",
        "derive",
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

    def readable(scope, name):
        return scope.phase == "legacy" or (
            scope.phase in {"execution", "planning"}
            and name in scope.allowed_datasets
        )

    def write_error(scope, name, derived=False):
        if scope.phase in {"synthesis", "error"}:
            return f"Error: {scope.phase}_cannot_mutate_raw_data"
        if scope.phase == "execution" and name not in scope.allowed_datasets:
            # D7: execution scope is advisory for out-of-scope datasets. The
            # ``derived_scope_not_registered`` guard remains a legitimate hard
            # block (genuinely unregistered derived datasets), but an ordinary
            # out-of-scope write is logged and allowed so a normal analysis
            # turn is never truncated by the overlay.
            if derived:
                return "Error: derived_scope_not_registered"
            record_scope_advisory_warning(name)
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
        if operation == "scope":
            return scope
        if operation == "get":
            name = args[0]
            if not readable(scope, name) or scope.phase == "planning":
                return None
            frame = storage.get(name)
            return frame.copy(deep=True) if frame is not None else None
        if operation == "raw_snapshot":
            raw_dataset_id = args[0]
            info = storage._raw_snapshot_info.get(raw_dataset_id, {})
            name = str(info.get("logical_name", ""))
            if scope.phase == "planning" or not readable(scope, name):
                return None
            return storage.get_raw_snapshot(raw_dataset_id)
        if operation == "dataset_version":
            dataset_id = args[0]
            info = storage._version_info.get(dataset_id, {})
            name = str(info.get("logical_name", ""))
            if scope.phase == "planning" or not readable(scope, name):
                return None
            return storage.get_dataset_version(dataset_id)
        if operation == "active_version":
            name = args[0]
            if not readable(scope, name) or scope.phase in {"planning", "synthesis", "error"}:
                return None
            return storage.get_active_version_info(name)
        if operation == "dataset_versions":
            name = args[0]
            if not readable(scope, name) or scope.phase in {"planning", "synthesis", "error"}:
                return []
            return storage.list_dataset_versions(name)
        if operation == "active_version_ids":
            return storage.active_dataset_version_ids()
        if operation == "exists":
            name = args[0]
            return readable(scope, name) and name in storage._datasets
        if operation == "list":
            if scope.phase in {"synthesis", "error"}:
                return {}
            visible = storage.list_datasets()
            if scope.phase == "legacy":
                return copy.deepcopy(visible)
            result = {
                name: copy.deepcopy(info)
                for name, info in visible.items()
                if name in scope.allowed_datasets
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
        if operation == "metadata":
            name, key = args
            if not readable(scope, name) or scope.phase in {"synthesis", "error"}:
                return None if key else {}
            meta = copy.deepcopy(storage.get_metadata(name))
            if scope.phase == "planning":
                safe = {k: v for k, v in meta.items() if k in {"quality", "schema"}}
                return safe.get(key) if key else safe
            return meta.get(key) if key else meta
        if operation == "planning_schema":
            name = args[0]
            if scope.phase != "planning" or not readable(scope, name):
                return []
            frame = storage.get(name)
            return list(frame.columns) if frame is not None else []
        if operation == "planning_quality":
            name = args[0]
            if scope.phase != "planning" or not readable(scope, name):
                return {}
            return copy.deepcopy(storage.get_metadata(name, "quality") or {})
        if operation == "planning_preview":
            name, rows = args
            if scope.phase != "planning" or not readable(scope, name):
                return []
            limit = max(0, min(int(rows), int(getattr(owner, "planning_preview_rows", 5)), 20))
            frame = storage.get(name)
            return copy.deepcopy(frame.head(limit).to_dict("records")) if frame is not None else []
        if operation == "add":
            name, frame = args
            return write_error(scope, name) or storage.add(name, frame)
        if operation == "register_raw":
            name, frame, source_fingerprint = args
            return write_error(scope, name) or storage.register_raw_snapshot(
                name, frame, source_fingerprint
            )
        if operation == "promote_copy":
            name, frame, raw_dataset_id, transformation_record = args
            return write_error(scope, name) or storage.promote_analysis_copy(
                name,
                frame,
                raw_dataset_id,
                copy.deepcopy(transformation_record),
            )
        if operation == "restore_version":
            name, frame, raw_dataset_id, saved_info = args
            return write_error(scope, name) or storage.restore_analysis_version(
                name,
                frame,
                raw_dataset_id,
                copy.deepcopy(saved_info),
            )
        if operation == "derive":
            source, name, frame, expression = args
            if scope.phase == "execution" and name not in storage._datasets:
                return "Error: derived_scope_not_registered"
            return write_error(scope, name, True) or storage.derive(source, name, frame, expression)
        if operation == "remove":
            name = args[0]
            return write_error(scope, name) or storage.remove(name)
        if operation == "set_metadata":
            name, key, value = args
            return write_error(scope, name) or storage.set_metadata(name, key, copy.deepcopy(value))
        if operation == "log_transform":
            source, transform, target, detail = args
            return write_error(scope, target) or storage.log_transform(source, transform, target, detail)
        if operation == "transform_log":
            if scope.phase in {"synthesis", "error", "planning"}:
                return []
            log = storage.get_transform_log()
            if scope.phase == "legacy":
                return copy.deepcopy(log)
            allowed = scope.allowed_datasets
            return copy.deepcopy([
                entry for entry in log
                if entry.get("from") in allowed and entry.get("to") in allowed
            ])
        if operation == "save_meta":
            names = None if scope.phase == "legacy" else scope.allowed_datasets
            if scope.phase in {"synthesis", "error"}:
                names = ()
            return storage.save_meta(args[0], names)
        if operation == "persist":
            session_id, name = args
            return storage.persist_dataset(session_id, name) if readable(scope, name) else None
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
            # D7: advisory for ordinary out-of-scope writes; keep the
            # ``derived_scope_not_registered`` hard block for genuinely
            # unregistered derived datasets.
            if derived:
                return "Error: derived_scope_not_registered"
            record_scope_advisory_warning(name)
        return ""

    def get(self, name: str) -> Optional[pd.DataFrame]:
        return self.__operate("get", name)

    def exists(self, name: str) -> bool:
        return self.__operate("exists", name)

    def list_datasets(self) -> dict[str, dict]:
        return self.__operate("list")

    def get_metadata(self, name: str, key: str = "") -> Any:
        return self.__operate("metadata", name, key)

    def planning_schema(self, name: str) -> list[str]:
        return self.__operate("planning_schema", name)

    def planning_quality(self, name: str) -> Any:
        return self.__operate("planning_quality", name)

    def planning_preview(self, name: str, *, rows: int = 5) -> list[dict[str, Any]]:
        return self.__operate("planning_preview", name, rows)

    def add(self, name: str, df: pd.DataFrame) -> str:
        return self.__operate("add", name, df)

    def register_raw_snapshot(
        self,
        name: str,
        frame: pd.DataFrame,
        source_fingerprint: str,
    ) -> dict[str, Any] | str:
        return self.__operate("register_raw", name, frame, source_fingerprint)

    def promote_analysis_copy(
        self,
        name: str,
        frame: pd.DataFrame,
        raw_dataset_id: str,
        transformation_record: dict[str, Any],
    ) -> dict[str, Any] | str:
        return self.__operate(
            "promote_copy",
            name,
            frame,
            raw_dataset_id,
            transformation_record,
        )

    def restore_analysis_version(
        self,
        name: str,
        frame: pd.DataFrame,
        raw_dataset_id: str,
        saved_info: dict[str, Any],
    ) -> dict[str, Any] | str:
        return self.__operate(
            "restore_version",
            name,
            frame,
            raw_dataset_id,
            saved_info,
        )

    def get_raw_snapshot(self, raw_dataset_id: str) -> Optional[pd.DataFrame]:
        return self.__operate("raw_snapshot", raw_dataset_id)

    def get_dataset_version(self, dataset_id: str) -> Optional[pd.DataFrame]:
        return self.__operate("dataset_version", dataset_id)

    def get_active_version_info(self, name: str) -> Optional[dict[str, Any]]:
        return self.__operate("active_version", name)

    def active_dataset_version_ids(self) -> list[str]:
        return self.__operate("active_version_ids")

    def list_dataset_versions(self, name: str) -> list[dict[str, Any]]:
        return self.__operate("dataset_versions", name)

    def derive(self, source: str, name: str, df: pd.DataFrame, expression: str = "") -> str:
        return self.__operate("derive", source, name, df, expression)

    def remove(self, name: str) -> str:
        return self.__operate("remove", name)

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
