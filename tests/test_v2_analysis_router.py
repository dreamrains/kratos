from __future__ import annotations

import pandas as pd

from data_agent.v2.router import AnalysisKind, AnalysisRouter


def _router(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"sales": [10, 20, 30]}).to_csv(inbox / "sales.csv", index=False)
    return AnalysisRouter(tmp_path / "sessions", inbox)


def test_router_dispatches_explicit_descriptive_kind(tmp_path):
    events = list(
        _router(tmp_path).stream(
            analysis_kind=AnalysisKind.DESCRIPTIVE,
            session_id="session_router",
            turn_id="turn_router",
            payload={
                "filename": "sales.csv",
                "metric": "sales",
                "question": "平均销售额是多少？",
            },
        )
    )

    assert events[0].event == "turn_started"
    assert events[-1].event == "turn_completed"
    assert any(item.event == "final_block_delta" for item in events)


def test_router_rejects_unknown_kind_before_runtime_execution(tmp_path):
    router = _router(tmp_path)
    try:
        router.parse_kind("magic_analysis")
    except ValueError as exc:
        assert "unknown analysis_kind" in str(exc)
    else:
        raise AssertionError("unknown analysis kind was accepted")


def test_router_requires_method_specific_fields(tmp_path):
    router = _router(tmp_path)
    try:
        list(
            router.stream(
                analysis_kind=AnalysisKind.FORECAST,
                session_id="session_forecast",
                turn_id="turn_forecast",
                payload={"filename": "sales.csv", "question": "预测。"},
            )
        )
    except ValueError as exc:
        assert "time_field" in str(exc)
    else:
        raise AssertionError("forecast without method fields was accepted")


def test_router_does_not_guess_analysis_kind_from_question(tmp_path):
    router = _router(tmp_path)
    assert router.parse_kind("") is None

