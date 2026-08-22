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


def test_core_evidence_record_marks_missing_statistical_details(tmp_path):
    ctx = AgentContext(session_id="quality_stats", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="quality_stats")
    payload = {
        "claim": "购卡后付费金额下降",
        "dataset": "orders",
        "method": "before-after comparison",
        "tool_calls": ["compare_periods"],
        "result_summary": "购卡后人均实收下降 31.8%。",
        "limitations": "缺少未购卡对照组。",
        "confidence": "medium",
        "is_core": True,
    }

    with use_agent_context(ctx):
        result = json.loads(record_evidence_record(json.dumps(payload, ensure_ascii=False)))

    assert result["statistical_detail_status"] == "missing"
    record = ctx.analysis_state.evidence_records[0]
    assert record["statistical_detail_status"] == "missing"
    assert "sample_size" in record["statistical_detail_gaps"]
    assert "significance" in record["statistical_detail_gaps"]


def test_analysis_completeness_flags_missing_core_quality_fields():
    from data_agent.agent.analysis_state import analysis_completeness_summary

    state = AnalysisSessionState(session_id="complete_check", goal="evaluate feature effect")
    state.evidence_records.append({
        "id": "ev_1",
        "claim": "功能上线后付费下降",
        "dataset": "orders",
        "method": "before-after",
        "tool_calls": ["compare_periods"],
        "result_summary": "下降 31.8%",
        "limitations": "缺少对照组",
        "confidence": "medium",
        "statistical_detail_status": "missing",
        "statistical_detail_gaps": ["sample_size", "significance"],
    })

    summary = analysis_completeness_summary(state, require_charts=True)

    assert summary["status"] == "incomplete"
    assert "statistical_details" in summary["missing"]
    assert "charts" not in summary["missing"]
    # expert_synthesis is not checked by analysis_completeness_summary;
    # it would be checked by analysis_quality_summary for expert-facing output
    assert summary["status"] == "incomplete"
