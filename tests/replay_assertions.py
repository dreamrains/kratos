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
    repeated = [
        event
        for event in trace
        if int(event.get("same_failure_attempt", 0) or 0) > 2
    ]
    assert repeated == []


def assert_bound_projected_measurements(
    evidence_records: list[dict[str, object]],
) -> None:
    assert evidence_records
    for record in evidence_records:
        assert record.get("provenance_status") == "bound"
        assert record.get("computation_refs")
        for measurement in record.get("measurements") or []:
            if measurement.get("identity_status") == "metric_identity_missing":
                continue
            assert isinstance(measurement.get("identity"), dict)
