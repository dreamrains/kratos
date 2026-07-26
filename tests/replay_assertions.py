TERMINAL_STATES = {
    "complete",
    "complete_with_limits",
    "blocked_by_data",
    "blocked_by_tool",
    "budget_limited",
}


def assert_reliable_analysis_trace(
    trace: list[dict[str, object]],
    *,
    require_inferential_attempt: bool,
) -> None:
    codes = [str(event.get("code") or "") for event in trace]
    terminal = [
        event
        for event in trace
        if event.get("completion_state") in TERMINAL_STATES
    ]
    assert len(terminal) == 1
    assert "grain_and_missingness_checked" in codes
    assert "univariate_relationship_checked" in codes
    if require_inferential_attempt:
        assert "multivariable_method_attempted" in codes
    assert "limitations_prepared" in codes
    repeated = [
        event
        for event in trace
        if int(event.get("same_failure_attempt", 0) or 0) > 2
    ]
    assert repeated == []
