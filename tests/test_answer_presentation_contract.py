from pathlib import Path

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.synthesis_policy import build_synthesis_instruction, derive_synthesis_policy


ROOT = Path(__file__).resolve().parents[1]


class _Intent:
    intent_type = "directed_analysis"
    recommended_action = "analyze"


def _state():
    state = AnalysisSessionState("presentation")
    state.evidence_records = [{"claim": "computed", "confidence": "high"}]
    return state


def test_ac30_briefness_does_not_remove_explicit_question_coverage_contract():
    policy = derive_synthesis_policy(
        intent=_Intent(), state=_state(), user_input="简短回答收入和复购率",
    )
    instruction = build_synthesis_instruction(policy)
    assert policy.answer_mode == "direct"
    assert "Preserve every supported material finding" in instruction
    assert "distinct requested questions" in instruction


def test_ac31_explicit_presentation_preferences_remain_in_prompt_source():
    prompts = (ROOT / "src/data_agent/agent/prompts.py").read_text(encoding="utf-8")
    assert "user_requirements" in prompts
    assert "不为装饰强制作图" in prompts


def test_ac33_full_width_chart_wrapper_and_cross_session_filter_are_implemented():
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    assert "_normalizeChartWrappers" in js
    assert "［［" in js and "chart\\s*：" in js
    assert "_artifactBelongsToSession(art, this.currentSessionId)" in js
    assert "Chart reference is ambiguous" in js
    assert "_chartRefsFromContent(this._normalizeChartWrappers(turn.content || ''))" in js


def test_ac34_tables_and_charts_have_desktop_keyboard_and_open_fallbacks():
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")
    assert 'tabindex="0"' in js
    assert 'title="${title}"' in js
    assert "Open chart in a new tab" in js
    assert ".markdown-table-scroll" in css


def test_ac35_data_backed_mermaid_is_not_used_as_chart_failure_fallback():
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    assert "Data-backed Mermaid charts are blocked" in js
    assert "verified numeric table" in js
