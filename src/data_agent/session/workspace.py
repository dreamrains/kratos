"""工作空间管理，存储已加载的数据集，支持项目绑定和变换血缘追踪。"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
import weakref

import pandas as pd

from data_agent.agent.context import _ensure_context_workspace_scope, get_current_context
from data_agent.utils.logging import get_logger

logger = get_logger("workspace")


class Workspace:
    """管理工作空间中的数据集快照，支持分析项目绑定和变换血缘。"""

    def __init__(self):
        self._datasets: dict[str, pd.DataFrame] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._derived_lineage: dict[str, dict[str, Any]] = {}
        self._transform_log: list[dict[str, Any]] = []
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
            from data_agent.agent.context import get_current_context
            ctx = get_current_context()
            if ctx is not None:
                ctx.project_name = name
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
            from data_agent.agent.context import get_current_context
            ctx = get_current_context()
            if ctx is not None:
                ctx.project_name = None
        except Exception:
            pass
        if old:
            logger.info("Project deactivated", extra={"extra_data": {"project": old}})
        return "已切回到 inbox 模式"

    def add(self, name: str, df: pd.DataFrame) -> str:
        self._datasets[name] = df.copy()
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

        datasets_meta = {}
        names = self._datasets if dataset_names is None else dataset_names
        for name in names:
            if name not in self._datasets:
                continue
            df = self._datasets[name]
            datasets_meta[name] = {
                "shape": list(df.shape),
                "columns": list(df.columns),
                "source_path": self._metadata.get(name, {}).get("_source_path", ""),
                "source_fmt": self._metadata.get(name, {}).get("_source_fmt", ""),
                "context": self._metadata.get(name, {}).get("context", ""),
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
        df = self._datasets.get(name)
        if df is None:
            return None
        from data_agent.session.history import _session_dir
        data_dir = _session_dir(session_id) / "data"
        data_dir.mkdir(exist_ok=True)
        path = data_dir / f"{name}.parquet"
        try:
            df.to_parquet(path, index=False)
        except ImportError:
            path = data_dir / f"{name}.pkl"
            df.to_pickle(path)
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


def _create_workspace_registry():
    """Return opaque bindings and policy-enforcing operations over closure-local stores."""

    class BindingToken:
        __slots__ = ("__weakref__",)

    stores = weakref.WeakKeyDictionary()
    owners = weakref.WeakKeyDictionary()
    default_bindings = weakref.WeakKeyDictionary()
    mutating_operations = frozenset({
        "add",
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

        if owner is None:
            active_owner = get_current_context()
            active_scope = (
                _ensure_context_workspace_scope(active_owner)
                if active_owner is not None
                else None
            )
            if active_scope is not None and active_scope.phase != "legacy":
                active_token = object.__getattribute__(
                    active_owner,
                    "_AgentContext__workspace_token",
                )
                active_storage = stores.get(active_token)
                if active_storage is None:
                    raise RuntimeError("Active workspace binding is no longer available")
                return active_storage, active_owner, active_scope
            scope = WorkspaceScopeSnapshot()
        else:
            scope = owner.workspace_scope
        if owner is not None and scope is None:
            scope = _ensure_context_workspace_scope(owner)
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
            return "Error: derived_scope_not_registered" if derived else "Error: dataset_outside_current_task_scope"
        return ""

    def operate(token, operation, *args):
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
            if scope.phase == "legacy":
                return storage._datasets
            visible = operate(token, "list")
            return {name: operate(token, "get", name) for name in visible}
        if operation == "metadata_view":
            if scope.phase == "legacy":
                return storage._metadata
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
) = _create_workspace_registry()
del _create_workspace_registry


def _workspace_get_operation(token, name):
    return _workspace_operation(token, "get", name)


def _workspace_add_operation(token, name, frame):
    return _workspace_operation(token, "add", name, frame)


class WorkspaceProxy:
    """Context-local, scope-enforcing public workspace facade."""

    def __init__(self, context=None):
        self.__context = context
        if context is None:
            _bind_default_workspace(self)

    def __operate(self, operation, *args):
        ctx = self.__context or get_current_context()
        if ctx is None:
            return _default_workspace_operation(self, operation, *args)
        token = object.__getattribute__(ctx, "_AgentContext__workspace_token")
        return _workspace_operation(token, operation, *args)

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

    def planning_schema(self, name: str) -> list[str]:
        return self.__operate("planning_schema", name)

    def planning_quality(self, name: str) -> Any:
        return self.__operate("planning_quality", name)

    def planning_preview(self, name: str, *, rows: int = 5) -> list[dict[str, Any]]:
        return self.__operate("planning_preview", name, rows)

    def add(self, name: str, df: pd.DataFrame) -> str:
        return self.__operate("add", name, df)

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
workspace = WorkspaceProxy()
