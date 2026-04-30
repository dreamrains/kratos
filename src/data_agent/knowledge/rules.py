"""项目规则管理（project_rules.md），支持三层合并：全局 + 对象 + 会话。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from data_agent.config import get_config


class ProjectRules:
    """管理 project_rules.md 项目规则文件，支持全局 + 对象 + 会话三层。"""

    def __init__(self, path: Optional[Path] = None):
        cfg = get_config()
        self.path = path or cfg.knowledge_dir / "project_rules.md"
        self._content: str = ""
        self._loaded: bool = False

    def load(self) -> str:
        """加载规则文件内容。"""
        if self.path.exists():
            self._content = self.path.read_text(encoding="utf-8")
        else:
            self._content = self._default_rules()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self._content, encoding="utf-8")
        self._loaded = True
        return self._content

    @property
    def content(self) -> str:
        if not self._loaded:
            self.load()
        return self._content

    def update(self, new_content: str) -> str:
        """更新规则文件。"""
        self._content = new_content
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(new_content, encoding="utf-8")
        return f"项目规则已更新: {self.path}"

    # ── 三层合并 ──────────────────────────────────────────

    def get_rules_for_prompt(
        self,
        object_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """返回注入系统提示词的规则，支持三层合并。"""
        parts = [self.content]

        if object_name:
            obj_content = self._load_object_rules(object_name)
            if obj_content:
                parts.append(obj_content)

        if session_id:
            sess_content = self._load_session_rules(session_id)
            if sess_content:
                parts.append(sess_content)

        content = "\n---\n".join(p for p in parts if p.strip())

        if not content.strip():
            return "(无项目规则)"
        return f"<project_rules>\n{content}\n</project_rules>"

    # ── 会话层读写 ─────────────────────────────────────────

    def _session_knowledge_path(self, session_id: str) -> Path:
        from data_agent.session.history import session_knowledge_dir
        return session_knowledge_dir(session_id) / "project_rules.md"

    def _load_session_rules(self, session_id: str) -> str:
        path = self._session_knowledge_path(session_id)
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        return ""

    def update_session_rules(self, session_id: str, new_content: str) -> str:
        """更新会话级规则文件。"""
        path = self._session_knowledge_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        return f"会话 '{session_id}' 的规则已更新"

    # ── 对象层读写 ─────────────────────────────────────────

    def _object_knowledge_path(self, object_name: str) -> Path:
        cfg = get_config()
        return cfg.objects_dir / object_name / "knowledge" / "project_rules.md"

    def _load_object_rules(self, object_name: str) -> str:
        path = self._object_knowledge_path(object_name)
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        return ""

    def update_object_rules(self, object_name: str, new_content: str) -> str:
        """更新对象级规则文件。"""
        path = self._object_knowledge_path(object_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        return f"对象 '{object_name}' 的规则已更新"

    # ── 知识提升与迁移 ─────────────────────────────────────

    def promote_to_object(self, session_id: str, object_name: str) -> dict:
        """将会话层规则提升到目标对象（追加）。"""
        sess_content = self._load_session_rules(session_id)
        if not sess_content:
            return {"promoted": False, "reason": "无会话级规则"}

        obj_path = self._object_knowledge_path(object_name)
        obj_content = ""
        if obj_path.exists():
            obj_content = obj_path.read_text(encoding="utf-8").strip()

        # 追加会话规则到对象规则
        merged = obj_content
        if merged:
            merged += "\n---\n" + sess_content
        else:
            merged = sess_content

        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_text(merged, encoding="utf-8")
        return {"promoted": True}

    def migrate_between_objects(
        self, session_id: str, from_object: str, to_object: str
    ) -> dict:
        """换绑时迁移规则。规则不按会话拆分，合并旧对象规则到新对象。"""
        from_path = self._object_knowledge_path(from_object)
        if not from_path.exists():
            return {"migrated": False, "reason": "旧对象无规则"}

        from_content = from_path.read_text(encoding="utf-8").strip()
        if not from_content:
            return {"migrated": False, "reason": "旧对象规则为空"}

        to_path = self._object_knowledge_path(to_object)
        to_content = ""
        if to_path.exists():
            to_content = to_path.read_text(encoding="utf-8").strip()

        # 合并
        merged = to_content
        if merged:
            merged += "\n---\n" + from_content
        else:
            merged = from_content

        to_path.parent.mkdir(parents=True, exist_ok=True)
        to_path.write_text(merged, encoding="utf-8")
        return {"migrated": True}

    def _default_rules(self) -> str:
        return """# 项目规则

## 数据字典
<!-- 在此定义字段的业务含义、取值范围、单位、特殊值 -->

## 分析规范
- 显著性阈值: 0.05
- 相关性方法偏好: pearson
- 输出风格: 结论 + 方法说明

## 业务逻辑规则
<!-- 在此定义业务约束，如"订单状态为 REFUND 的行必须排除" -->

## 安全规则
<!-- 在此定义需脱敏的列名或模式 -->
"""


# ── 模块级单例 ────────────────────────────────────────────

_project_rules: Optional[ProjectRules] = None


def get_project_rules() -> ProjectRules:
    global _project_rules
    if _project_rules is None:
        _project_rules = ProjectRules()
    return _project_rules
