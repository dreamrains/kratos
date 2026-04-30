"""经验日志管理（experience_log.yaml），支持三层合并：全局 + 对象 + 会话。"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from data_agent.config import get_config


class ExperienceLog:
    """管理 experience_log.yaml 经验日志，支持全局 + 对象 + 会话三层。"""

    def __init__(self, path: Optional[Path] = None):
        cfg = get_config()
        self.path = path or cfg.knowledge_dir / "experience_log.yaml"
        self._entries: list[dict] = []
        self._loaded: bool = False

    def load(self) -> list[dict]:
        if self.path.exists():
            content = self.path.read_text(encoding="utf-8")
            self._entries = yaml.safe_load(content) or []
        else:
            self._entries = []
            self._save()
        self._loaded = True
        return self._entries

    @property
    def entries(self) -> list[dict]:
        if not self._loaded:
            self.load()
        return self._entries

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.dump(self._entries, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def _save_to_path(self, path: Path, entries: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(entries, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def _load_from_path(self, path: Path) -> list[dict]:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            entries = yaml.safe_load(content)
            if isinstance(entries, list):
                return entries
        return []

    def add_draft(
        self,
        pattern: str,
        domain: str = "general",
        evidence: Optional[dict] = None,
        confidence: float = 0.6,
        object_name: Optional[str] = None,
        session_id: Optional[str] = None,
        effect_size: Optional[float] = None,
        is_key_metric: bool = False,
        user_requested: bool = False,
    ) -> Optional[dict]:
        """添加新经验（draft 状态）。带过滤条件，不满足条件时不写入。

        知识先落会话层（sessions/{id}/knowledge/），如果同时绑定了对象则同步到对象层。

        过滤规则（满足任一才写入）：
        - effect_size 超过阈值（>0.5 表示 Cohen's d 或相关系数 >0.6）
        - 与已有 confirmed 经验矛盾
        - 用户明确要求（user_requested=True）
        - 涉及关键指标（is_key_metric=True）
        """
        should_write = (
            user_requested
            or is_key_metric
            or (effect_size is not None and effect_size > 0.5)
            or len(self.check_conflict(pattern, domain)) > 0
        )
        if not should_write:
            return None

        entry = {
            "id": f"exp_{uuid.uuid4().hex[:6]}",
            "created": datetime.now().strftime("%Y-%m-%d"),
            "domain": domain,
            "pattern": pattern,
            "evidence": evidence or {},
            "confidence": round(confidence, 2),
            "status": "draft",
            "confirmed_by": None,
            "corrections": [],
            "source_session_id": session_id or "",
        }

        # 先落会话层
        if session_id:
            self._save_to_session(session_id, entry)

        # 如果同时绑定了对象，同步到对象层
        if object_name:
            self._save_to_object(object_name, entry)

        # 如果两者都没有，写到全局层
        if not session_id and not object_name:
            self.entries.append(entry)
            self._save()

        return entry

    def confirm(self, entry_id: str, confirmed_by: str = "user") -> Optional[dict]:
        """确认经验。在全局层查找并更新。"""
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry["status"] = "confirmed"
                entry["confirmed_by"] = confirmed_by
                entry["confidence"] = min(0.95, entry["confidence"] + 0.2)
                self._save()
                return entry
        return None

    def deprecate(self, entry_id: str, reason: str = "") -> Optional[dict]:
        """废弃经验。"""
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry["status"] = "deprecated"
                entry["corrections"].append({
                    "reason": reason,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                })
                self._save()
                return entry
        return None

    def reinforce(self, entry_id: str) -> Optional[dict]:
        """验证已有经验（提高置信度）。"""
        for entry in self.entries:
            if entry["id"] == entry_id and entry["status"] == "confirmed":
                entry["confidence"] = min(0.9, entry["confidence"] + 0.1)
                self._save()
                return entry
        return None

    def get_confirmed(self, min_confidence: float = 0.5, domain: str = "") -> list[dict]:
        """获取可用于分析的经验。"""
        results = []
        for entry in self.entries:
            if entry["status"] != "confirmed":
                continue
            if entry["confidence"] < min_confidence:
                continue
            if domain and entry.get("domain") not in (domain, "general"):
                continue
            results.append(entry)
        return results

    def check_conflict(self, new_pattern: str, domain: str = "") -> list[dict]:
        """检查新经验是否与已有确认经验冲突。"""
        conflicts = []
        for entry in self.get_confirmed(domain=domain):
            new_words = set(new_pattern.lower().split())
            old_words = set(entry["pattern"].lower().split())
            overlap = new_words & old_words
            if len(overlap) > 3:
                conflicts.append(entry)
        return conflicts

    # ── 三层合并 ──────────────────────────────────────────

    def get_merged_entries(
        self,
        object_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """获取三层合并后的经验列表：全局 ∪ 对象 ∪ 会话。"""
        merged_ids = set()

        # 全局层
        global_entries = list(self.entries)
        for e in global_entries:
            if "id" in e:
                merged_ids.add(e["id"])

        # 对象层
        obj_entries = []
        if object_name:
            obj_entries = self._load_object_entries(object_name)

        # 会话层
        session_entries = []
        if session_id:
            session_entries = self._load_session_entries(session_id)

        # 合并：全局 + 对象 + 会话，同 id 优先会话 > 对象 > 全局
        merged = list(global_entries)
        for entry in obj_entries:
            eid = entry.get("id")
            if eid and eid not in merged_ids:
                merged.append(entry)
                merged_ids.add(eid)
        for entry in session_entries:
            eid = entry.get("id")
            if eid and eid not in merged_ids:
                merged.append(entry)
                merged_ids.add(eid)

        merged.sort(key=lambda e: e.get("confidence", 0), reverse=True)
        return merged

    def get_for_prompt(
        self,
        object_name: Optional[str] = None,
        session_id: Optional[str] = None,
        domain: str = "",
        max_entries: int = 5,
    ) -> str:
        """返回注入系统提示词的经验摘要，支持三层合并。"""
        all_entries = self.get_merged_entries(object_name=object_name, session_id=session_id)

        confirmed = []
        for entry in all_entries:
            if entry.get("status") != "confirmed":
                continue
            if entry.get("confidence", 0) < 0.6:
                continue
            if domain and entry.get("domain") not in (domain, "general"):
                continue
            confirmed.append(entry)

        if not confirmed:
            return "(无已确认经验)"

        lines = ["<experience_log>"]
        for entry in confirmed[:max_entries]:
            lines.append(
                f"  [{entry['id']}] ({entry['confidence']}) {entry['pattern']}"
            )
        lines.append("</experience_log>")
        return "\n".join(lines)

    # ── 会话层读写 ─────────────────────────────────────────

    def _session_knowledge_path(self, session_id: str) -> Path:
        """获取会话级经验日志路径。"""
        from data_agent.session.history import session_knowledge_dir
        return session_knowledge_dir(session_id) / "experience_log.yaml"

    def _load_session_entries(self, session_id: str) -> list[dict]:
        return self._load_from_path(self._session_knowledge_path(session_id))

    def _save_to_session(self, session_id: str, entry: dict) -> None:
        path = self._session_knowledge_path(session_id)
        existing = self._load_from_path(path)
        existing.append(entry)
        self._save_to_path(path, existing)

    # ── 对象层读写 ─────────────────────────────────────────

    def _object_knowledge_path(self, object_name: str) -> Path:
        cfg = get_config()
        return cfg.objects_dir / object_name / "knowledge" / "experience_log.yaml"

    def _load_object_entries(self, object_name: str) -> list[dict]:
        return self._load_from_path(self._object_knowledge_path(object_name))

    def _save_to_object(self, object_name: str, entry: dict) -> None:
        path = self._object_knowledge_path(object_name)
        existing = self._load_from_path(path)
        existing.append(entry)
        self._save_to_path(path, existing)

    # ── 知识提升与迁移 ─────────────────────────────────────

    def promote_to_object(self, session_id: str, object_name: str) -> dict:
        """将会话层知识提升（合并）到目标对象。"""
        session_entries = self._load_session_entries(session_id)
        if not session_entries:
            return {"promoted": 0}

        obj_path = self._object_knowledge_path(object_name)
        obj_entries = self._load_from_path(obj_path)
        obj_ids = {e.get("id") for e in obj_entries if "id" in e}

        promoted = 0
        for entry in session_entries:
            eid = entry.get("id")
            if eid and eid not in obj_ids:
                obj_entries.append(entry)
                obj_ids.add(eid)
                promoted += 1

        self._save_to_path(obj_path, obj_entries)
        return {"promoted": promoted}

    def migrate_between_objects(
        self, session_id: str, from_object: str, to_object: str
    ) -> dict:
        """换绑时：从旧对象提取该会话产生的条目，迁移到新对象。"""
        from_path = self._object_knowledge_path(from_object)
        from_entries = self._load_from_path(from_path)

        # 筛选该会话产生的条目
        to_migrate = [e for e in from_entries if e.get("source_session_id") == session_id]
        remain = [e for e in from_entries if e.get("source_session_id") != session_id]

        if to_migrate:
            # 从旧对象移除
            self._save_to_path(from_path, remain)

            # 合并到新对象
            to_path = self._object_knowledge_path(to_object)
            to_entries = self._load_from_path(to_path)
            to_ids = {e.get("id") for e in to_entries if "id" in e}
            migrated = 0
            for entry in to_migrate:
                eid = entry.get("id")
                if eid and eid not in to_ids:
                    to_entries.append(entry)
                    to_ids.add(eid)
                    migrated += 1
            self._save_to_path(to_path, to_entries)
        else:
            migrated = 0

        return {"migrated": migrated, "removed_from_source": len(to_migrate)}


# ── 模块级单例 ────────────────────────────────────────────

_experience_log: Optional[ExperienceLog] = None


def get_experience_log() -> ExperienceLog:
    global _experience_log
    if _experience_log is None:
        _experience_log = ExperienceLog()
    return _experience_log
