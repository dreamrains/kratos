"""领域知识管理（domain_knowledge.yaml），支持三层合并：全局 + 对象 + 会话。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from data_agent.config import get_config


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 优先。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class DomainKnowledge:
    """管理 domain_knowledge.yaml 领域知识文件，支持全局 + 对象 + 会话三层。"""

    def __init__(self, path: Optional[Path] = None):
        cfg = get_config()
        self.path = path or cfg.knowledge_dir / "domain_knowledge.yaml"
        self._data: dict = {}
        self._loaded: bool = False

    def load(self) -> dict:
        if self.path.exists():
            content = self.path.read_text(encoding="utf-8")
            self._data = yaml.safe_load(content) or {}
        else:
            self._data = self._default_domain("general")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(yaml.dump(self._data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        self._loaded = True
        return self._data

    @property
    def data(self) -> dict:
        if not self._loaded:
            self.load()
        return self._data

    @property
    def domain_name(self) -> str:
        return self.data.get("domain", "general")

    @property
    def is_active(self) -> bool:
        return self.domain_name != "general"

    def update(self, new_data: dict) -> str:
        self._data = new_data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.dump(new_data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        return f"领域知识已更新: {self.path}"

    def set_domain(self, domain_name: str, object_name: Optional[str] = None) -> str:
        """切换或创建领域知识包。可指定写入对象级或全局。"""
        templates = {
            "ecommerce": self._ecommerce_template,
            "gaming": self._gaming_template,
            "general": lambda: {"domain": "general"},
        }
        builder = templates.get(domain_name, lambda: {"domain": domain_name})
        new_data = builder()

        if object_name:
            cfg = get_config()
            obj_path = cfg.objects_dir / object_name / "knowledge" / "domain_knowledge.yaml"
            obj_path.parent.mkdir(parents=True, exist_ok=True)
            obj_path.write_text(
                yaml.dump(new_data, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
            return f"对象 '{object_name}' 已切换到领域: {domain_name}"

        self._data = new_data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.dump(self._data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        self._loaded = True
        return f"已切换到领域: {domain_name}"

    # ── 三层合并 ──────────────────────────────────────────

    def get_merged(
        self,
        object_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict:
        """获取三层合并后的领域知识：全局 → 对象 → 会话。"""
        result = dict(self.data)

        if object_name:
            obj_data = self._load_object_domain(object_name)
            if obj_data:
                result = _deep_merge(result, obj_data)

        if session_id:
            sess_data = self._load_session_domain(session_id)
            if sess_data:
                result = _deep_merge(result, sess_data)

        return result

    def get_for_prompt(
        self,
        object_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """返回注入系统提示词的领域知识，支持三层合并。"""
        data = self.get_merged(object_name=object_name, session_id=session_id)
        if not data or data.get("domain") == "general":
            return "(无特定领域知识)"
        return f"<domain_knowledge>\n{yaml.dump(data, allow_unicode=True, default_flow_style=False)}\n</domain_knowledge>"

    # ── 会话层读写 ─────────────────────────────────────────

    def _session_knowledge_path(self, session_id: str) -> Path:
        from data_agent.session.history import session_knowledge_dir
        return session_knowledge_dir(session_id) / "domain_knowledge.yaml"

    def _load_session_domain(self, session_id: str) -> Optional[dict]:
        path = self._session_knowledge_path(session_id)
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if data and data.get("domain", "general") != "general":
                return data
        return None

    def _save_to_session(self, session_id: str, data: dict) -> None:
        path = self._session_knowledge_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    # ── 对象层读写 ─────────────────────────────────────────

    def _load_object_domain(self, object_name: str) -> Optional[dict]:
        cfg = get_config()
        obj_path = cfg.objects_dir / object_name / "knowledge" / "domain_knowledge.yaml"
        if obj_path.exists():
            data = yaml.safe_load(obj_path.read_text(encoding="utf-8"))
            if data and data.get("domain", "general") != "general":
                return data
        return None

    def _object_knowledge_path(self, object_name: str) -> Path:
        cfg = get_config()
        return cfg.objects_dir / object_name / "knowledge" / "domain_knowledge.yaml"

    # ── 知识提升与迁移 ─────────────────────────────────────

    def promote_to_object(self, session_id: str, object_name: str) -> dict:
        """将会话层领域知识提升到目标对象。"""
        sess_data = self._load_session_domain(session_id)
        if not sess_data:
            return {"promoted": False, "reason": "无会话级领域知识"}

        obj_path = self._object_knowledge_path(object_name)
        obj_data = {}
        if obj_path.exists():
            obj_data = yaml.safe_load(obj_path.read_text(encoding="utf-8")) or {}

        merged = _deep_merge(obj_data, sess_data)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_text(
            yaml.dump(merged, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        return {"promoted": True}

    def migrate_between_objects(
        self, session_id: str, from_object: str, to_object: str
    ) -> dict:
        """换绑时迁移领域知识。领域知识通常不按会话拆分，直接从旧对象合并到新对象。"""
        from_path = self._object_knowledge_path(from_object)
        if not from_path.exists():
            return {"migrated": False, "reason": "旧对象无领域知识"}

        from_data = yaml.safe_load(from_path.read_text(encoding="utf-8")) or {}
        if not from_data or from_data.get("domain") == "general":
            return {"migrated": False, "reason": "旧对象无特定领域知识"}

        to_path = self._object_knowledge_path(to_object)
        to_data = {}
        if to_path.exists():
            to_data = yaml.safe_load(to_path.read_text(encoding="utf-8")) or {}

        merged = _deep_merge(to_data, from_data)
        to_path.parent.mkdir(parents=True, exist_ok=True)
        to_path.write_text(
            yaml.dump(merged, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        return {"migrated": True}

    def _default_domain(self, name: str) -> dict:
        return {"domain": name}

    def _ecommerce_template(self) -> dict:
        return {
            "domain": "ecommerce",
            "indicators": {
                "GMV": {
                    "description": "总交易额",
                    "formula": "商品数量 * 单价",
                    "exclude_conditions": "order_status = 'CANCEL'",
                },
                "conversion_rate": {
                    "description": "购买转化率",
                    "formula": "下单用户数 / 访问用户数",
                },
                "ARPU": {
                    "description": "每用户平均收入",
                    "formula": "revenue / active_users",
                },
            },
            "analysis_rules": [
                "归因分析优先使用 SHAP 值",
                "时间序列预测默认周期 7 天",
            ],
            "common_pitfalls": [
                "测试渠道数据需排除（channel 前缀为 'test_'）",
                "退款订单需单独分析",
            ],
            "learned_patterns": [],
            "suggested_analyses": [
                "GMV 趋势分析与异常检测",
                "转化率漏斗分析（访问→加购→下单→支付）",
                "用户分层 RFM 分析",
                "渠道 ROI 对比分析",
                "退款率异常归因",
            ],
        }

    def _gaming_template(self) -> dict:
        return {
            "domain": "gaming",
            "indicators": {
                "DAU": {"description": "日活跃用户数", "formula": "当日登录用户去重计数"},
                "retention_d7": {"description": "7日留存率", "formula": "7日后仍活跃用户 / 新增用户"},
                "ARPU": {"description": "每用户平均收入", "formula": "revenue / DAU"},
            },
            "analysis_rules": [
                "留存分析优先使用 cohort 分析",
                "关注新手引导完成率与留存的关系",
            ],
            "common_pitfalls": [
                "测试账号需排除",
            ],
            "learned_patterns": [],
            "suggested_analyses": [
                "DAU/MAU 趋势与周周期性检测",
                "新手引导完成率与 D7 留存相关性",
                "付费 vs 非付费用户行为对比",
                "ARPU 波动归因（价格 vs 活跃度拆解）",
                "用户生命周期价值 (LTV) 预测",
            ],
        }


# ── 模块级单例 ────────────────────────────────────────────

_domain_knowledge: Optional[DomainKnowledge] = None


def get_domain_knowledge() -> DomainKnowledge:
    global _domain_knowledge
    if _domain_knowledge is None:
        _domain_knowledge = DomainKnowledge()
    return _domain_knowledge
