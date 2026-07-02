"""工作空间管理，存储已加载的数据集，支持项目绑定和变换血缘追踪。"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from data_agent.agent.context import get_current_context
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


class WorkspaceProxy:
    """Context-local, scope-enforcing public workspace facade."""

    def __init__(self):
        self.__default = Workspace()

    def _scope(self):
        from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

        ctx = get_current_context()
        if ctx is None:
            return WorkspaceScopeSnapshot()
        if ctx.workspace is None:
            ctx.workspace = Workspace()
        if ctx.workspace_scope is None:
            return ctx.refresh_workspace_scope()
        return ctx.workspace_scope

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
        if not self._readable(name) or self._scope().phase == "planning":
            return None
        ctx = get_current_context()
        frame = (ctx.workspace if ctx is not None else self.__default).get(name)
        return frame.copy(deep=True) if frame is not None else None

    def exists(self, name: str) -> bool:
        if not self._readable(name):
            return False
        ctx = get_current_context()
        return name in (ctx.workspace if ctx is not None else self.__default)._datasets

    def list_datasets(self) -> dict[str, dict]:
        scope = self._scope()
        if scope.phase in {"synthesis", "error"}:
            return {}
        ctx = get_current_context()
        visible = (ctx.workspace if ctx is not None else self.__default).list_datasets()
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

    def get_metadata(self, name: str, key: str = "") -> Any:
        scope = self._scope()
        if not self._readable(name) or scope.phase in {"synthesis", "error"}:
            return None if key else {}
        ctx = get_current_context()
        meta = copy.deepcopy((ctx.workspace if ctx is not None else self.__default).get_metadata(name))
        if scope.phase == "planning":
            safe = {k: v for k, v in meta.items() if k in {"quality", "schema", "context"}}
            return safe.get(key) if key else safe
        return meta.get(key) if key else meta

    def planning_schema(self, name: str) -> list[str]:
        if self._scope().phase != "planning" or not self._readable(name):
            return []
        ctx = get_current_context()
        frame = (ctx.workspace if ctx is not None else self.__default).get(name)
        return list(frame.columns) if frame is not None else []

    def planning_quality(self, name: str) -> Any:
        if self._scope().phase != "planning" or not self._readable(name):
            return {}
        ctx = get_current_context()
        return copy.deepcopy((ctx.workspace if ctx is not None else self.__default).get_metadata(name, "quality") or {})

    def planning_preview(self, name: str, *, rows: int = 5) -> list[dict[str, Any]]:
        if self._scope().phase != "planning" or not self._readable(name):
            return []
        ctx = get_current_context()
        bound = getattr(ctx, "planning_preview_rows", 5)
        limit = max(0, min(int(rows), int(bound), 20))
        frame = (ctx.workspace if ctx is not None else self.__default).get(name)
        return copy.deepcopy(frame.head(limit).to_dict("records")) if frame is not None else []

    def add(self, name: str, df: pd.DataFrame) -> str:
        error = self._write_error(name)
        ctx = get_current_context()
        return error or (ctx.workspace if ctx is not None else self.__default).add(name, df)

    def derive(self, source: str, name: str, df: pd.DataFrame, expression: str = "") -> str:
        scope = self._scope()
        ctx = get_current_context()
        storage = ctx.workspace if ctx is not None else self.__default
        if scope.phase == "execution" and name not in storage._datasets:
            return "Error: derived_scope_not_registered"
        error = self._write_error(name, derived=True)
        return error or storage.derive(source, name, df, expression)

    def remove(self, name: str) -> str:
        error = self._write_error(name)
        ctx = get_current_context()
        return error or (ctx.workspace if ctx is not None else self.__default).remove(name)

    def set_metadata(self, name: str, key: str, value: Any) -> Any:
        error = self._write_error(name)
        if error:
            return error
        ctx = get_current_context()
        return (ctx.workspace if ctx is not None else self.__default).set_metadata(name, key, copy.deepcopy(value))

    def log_transform(self, source: str, operation: str, target: str, detail: str = "") -> Any:
        error = self._write_error(target)
        if error:
            return error
        ctx = get_current_context()
        return (ctx.workspace if ctx is not None else self.__default).log_transform(source, operation, target, detail)

    def get_transform_log(self) -> list[dict[str, Any]]:
        scope = self._scope()
        if scope.phase in {"synthesis", "error", "planning"}:
            return []
        ctx = get_current_context()
        log = (ctx.workspace if ctx is not None else self.__default).get_transform_log()
        if scope.phase == "legacy":
            return copy.deepcopy(log)
        allowed = scope.allowed_datasets
        return copy.deepcopy([
            entry for entry in log
            if entry.get("from") in allowed and entry.get("to") in allowed
        ])

    # Persistence operates on internal storage and does not return raw data.
    def save_meta(self, session_id: str) -> None:
        scope = self._scope()
        dataset_names = None if scope.phase == "legacy" else scope.allowed_datasets
        if scope.phase in {"synthesis", "error"}:
            dataset_names = ()
        ctx = get_current_context()
        return (ctx.workspace if ctx is not None else self.__default).save_meta(session_id, dataset_names)

    def persist_dataset(self, session_id: str, name: str) -> str | None:
        if not self._readable(name):
            return None
        ctx = get_current_context()
        return (ctx.workspace if ctx is not None else self.__default).persist_dataset(session_id, name)

    def set_object(self, name: str) -> str:
        return self.set_project(name)

    def set_project(self, name: str) -> str:
        self._scope()
        ctx = get_current_context()
        result = (ctx.workspace if ctx is not None else self.__default).set_project(name)
        if ctx is not None:
            ctx.refresh_workspace_scope()
        return result

    def clear_object(self) -> str:
        return self.clear_project()

    def clear_project(self) -> str:
        self._scope()
        ctx = get_current_context()
        result = (ctx.workspace if ctx is not None else self.__default).clear_project()
        if ctx is not None:
            ctx.refresh_workspace_scope()
        return result

    def __getattr__(self, name):
        raise AttributeError(f"WorkspaceProxy does not expose '{name}'")

    @property
    def _datasets(self):
        if self._scope().phase == "legacy":
            ctx = get_current_context()
            return (ctx.workspace if ctx is not None else self.__default)._datasets
        return {name: self.get(name) for name in self.list_datasets()}

    @property
    def _metadata(self):
        if self._scope().phase == "legacy":
            ctx = get_current_context()
            return (ctx.workspace if ctx is not None else self.__default)._metadata
        return {name: self.get_metadata(name) for name in self.list_datasets()}

    @property
    def active_object(self) -> Optional[str]:
        self._scope()
        ctx = get_current_context()
        return (ctx.workspace if ctx is not None else self.__default).active_object

    @property
    def active_project(self) -> Optional[str]:
        self._scope()
        ctx = get_current_context()
        return (ctx.workspace if ctx is not None else self.__default).active_project


# 全局 facade；无 AgentContext 时使用默认工作空间，保持旧测试和 CLI 兼容。
workspace = WorkspaceProxy()
