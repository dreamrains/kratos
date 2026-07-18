import json

from data_agent.agent.analysis_state import AnalysisSessionState, load_analysis_state
from data_agent.agent.loop import SuspendedForConfirmation, SuspensionManager
from data_agent.session.task_manager import TaskManager


def test_analysis_state_utf8_roundtrip(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig

    old_cfg = config._config
    config._config = AgentConfig(PROJECT_DIR=tmp_path / "project", SESSIONS_DIR=tmp_path / "sessions")
    try:
        state = AnalysisSessionState(session_id="utf8_state", project_name="省钱卡项目")
        state.set_analysis_plan({"goal": "分析收入、留存、成本", "limitations": ["不能直接推断因果"]})
        state.goal = "评估省钱卡是否值得长期运营"
        state.evidence_records.append({"claim": "省钱卡用户消费更高", "confidence": "medium"})
        state.save()

        loaded = load_analysis_state("utf8_state")
        assert loaded.project_name == "省钱卡项目"
        assert loaded.goal == "评估省钱卡是否值得长期运营"
        assert loaded.analysis_plan["limitations"][0] == "不能直接推断因果"
        assert loaded.evidence_records[0]["claim"] == "省钱卡用户消费更高"
    finally:
        config._config = old_cfg


def test_task_json_utf8_roundtrip(tmp_path):
    manager = TaskManager(tmp_path / "tasks")
    task = manager.create(
        subject="确认 ROI 口径",
        description="需要用户确认成本定义",
        session_id="utf8_task",
        project_name="省钱卡项目",
        limitations="缺少成本数据，不能输出强 ROI 结论",
    )

    loaded = manager.get(task["id"])
    assert loaded["subject"] == "确认 ROI 口径"
    assert loaded["description"] == "需要用户确认成本定义"
    assert loaded["project_name"] == "省钱卡项目"
    assert loaded["limitations"] == "缺少成本数据，不能输出强 ROI 结论"


def test_suspension_utf8_roundtrip(tmp_path):
    manager = SuspensionManager(tmp_path / "sessions")
    suspension = SuspendedForConfirmation(
        suspension_id="utf8_confirm",
        question="请选择 ROI 口径",
        options=[{"label": "收入/成本", "description": "投入产出比"}],
        context=json.dumps({"原因": "缺少成本数据"}, ensure_ascii=False),
        snapshot={"messages": [{"role": "user", "content": "预测下月收入和 ROI"}]},
        confirmation_type="method_confirmation",
        blocking_reason="预测和 ROI 需要确认口径",
        state_updates=json.dumps({"goal": "预测下月收入和 ROI"}, ensure_ascii=False),
    )

    manager.save(suspension)
    loaded = manager.load("utf8_confirm")

    assert loaded.question == "请选择 ROI 口径"
    assert loaded.options[0]["description"] == "投入产出比"
    assert "缺少成本数据" in loaded.context
    assert loaded.blocking_reason == "预测和 ROI 需要确认口径"
