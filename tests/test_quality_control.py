import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.analysis_flow import record_evidence_record


def test_evidence_record_accepts_speculative_confidence(tmp_path):
    ctx = AgentContext(session_id="quality_speculative", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="quality_speculative")
    payload = {
        "claim": "收入下降可能与付费用户数减少有关",
        "dataset": "pay",
        "method": "limited descriptive check",
        "tool_calls": ["preview_data"],
        "result_summary": "只看到样例数据，尚未完成完整拆解。",
        "limitations": "缺少完整时间范围和维度拆解。",
        "confidence": "speculative",
    }

    with use_agent_context(ctx):
        result = json.loads(record_evidence_record(json.dumps(payload, ensure_ascii=False)))

    assert "evidence_id" in result
    assert ctx.analysis_state.evidence_records[0]["confidence"] == "speculative"


def test_evidence_record_rejects_unknown_confidence_level():
    payload = {
        "claim": "收入一定下降",
        "dataset": "pay",
        "method": "guess",
        "tool_calls": [],
        "result_summary": "没有证据。",
        "limitations": "证据不足。",
        "confidence": "certain",
    }

    result = json.loads(record_evidence_record(json.dumps(payload, ensure_ascii=False)))

    assert result["error_type"] == "invalid_confidence"
    assert "speculative" in result["allowed"]
