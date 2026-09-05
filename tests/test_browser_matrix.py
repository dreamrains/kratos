import pytest

from scripts.acceptance.browser_matrix import BrowserMatrix, MatrixCase, MatrixStep, StepObservation


def _matrix():
    return BrowserMatrix(tuple(MatrixCase(f"M{i:02d}", (
        MatrixStep("upload", mode="local_action"),
        MatrixStep("analysis", ("upload",)),
        MatrixStep("chart", ("analysis",), "read_only"),
        MatrixStep("followup", ("analysis",)),
        MatrixStep("existing_page", ("upload",), "read_only"),
    )) for i in range(1, 7)))


def test_all_six_cases_attempted_even_if_every_analysis_raises():
    calls, closed = [], []

    def observe(case, step):
        calls.append((case.id, step.id))
        if step.id == "analysis":
            raise RuntimeError("case-local abnormal termination")
        return StepObservation(True)

    report = _matrix().run(
        observe=observe, close_case=lambda c: closed.append(c.id) or True, batch_block_reason=lambda: "",
    )
    assert report["cases_attempted"] == 6
    assert report["cases_not_run"] == 0
    assert report["status"] == "failed"
    assert closed == [f"M{i:02d}" for i in range(1, 7)]
    assert len([s for _, s in calls if s == "analysis"]) == 6
    assert len([s for _, s in calls if s == "existing_page"]) == 6
    assert not any(s in ("chart", "followup") for _, s in calls)
    assert all(c["steps"][2]["status"] == "blocked" for c in report["cases"])


def test_nonblocking_oracle_failure_does_not_block_later_states_or_cases():
    calls = []

    def observe(case, step):
        calls.append((case.id, step.id))
        return StepObservation(step.id != "chart", code="single_series" if step.id == "chart" else "")

    report = _matrix().run(observe=observe, close_case=lambda _: True, batch_block_reason=lambda: "")
    assert len(calls) == 30
    assert report["cases_attempted"] == 6
    assert all(c["status"] == "failed" for c in report["cases"])


def test_terminal_case_keeps_read_only_observations_but_never_submits_again():
    calls = []

    def observe(case, step):
        calls.append((case.id, step.id))
        return StepObservation(False, True, "provider_request_failed", "case") if step.id == "analysis" else StepObservation(True)

    report = _matrix().run(observe=observe, close_case=lambda _: True, batch_block_reason=lambda: "")
    assert report["cases_attempted"] == 6
    assert len([s for _, s in calls if s == "chart"]) == 6
    assert not any(s == "followup" for _, s in calls)


@pytest.mark.parametrize("close", [lambda _: False, lambda _: (_ for _ in ()).throw(RuntimeError())])
def test_unproven_process_isolation_or_receipt_counts_blocks_remaining_matrix(close):
    report = _matrix().run(observe=lambda *_: StepObservation(True), close_case=close, batch_block_reason=lambda: "")
    assert report["cases_attempted"] == 1
    assert report["cases_not_run"] == 5
    assert report["cases"][0]["status"] == "failed"
    assert report["batch_stop_reason"] == "case_containment_or_accounting_unproven"


@pytest.mark.parametrize("reason", ["source_mismatch", "shared_upload_integrity_failed", "batch_call_cap_reached", "not_authorized"])
def test_batch_hard_stop_is_zero_dispatch(reason):
    calls = []
    report = _matrix().run(observe=lambda *args: calls.append(args), close_case=lambda _: True, batch_block_reason=lambda: reason)
    assert calls == []
    assert report["cases_not_run"] == 6
    assert report["status"] == "failed"


def test_batch_can_exhaust_budget_mid_case_and_is_never_rerun():
    matrix = _matrix()
    calls = []

    def observe(case, step):
        calls.append(step.id)
        return StepObservation(True)

    report = matrix.run(observe=observe, close_case=lambda _: True, batch_block_reason=lambda: "cap_reached" if "analysis" in calls else "")
    assert calls == ["upload", "analysis"]
    assert report["cases_not_run"] == 5
    with pytest.raises(RuntimeError, match="already consumed"):
        matrix.run(observe=observe, close_case=lambda _: True, batch_block_reason=lambda: "")


def test_batch_safety_failure_is_not_treated_as_a_case_failure():
    def failed_check():
        raise OSError("shared receipt unreadable")

    report = _matrix().run(observe=lambda *_: pytest.fail("must not dispatch"), close_case=lambda _: True, batch_block_reason=failed_check)
    assert report["cases_not_run"] == 6
    assert report["batch_stop_reason"] == "batch_safety_check_failed"


def test_step_dependencies_cannot_be_forward_missing_or_duplicate():
    with pytest.raises(ValueError):
        BrowserMatrix((MatrixCase("M01", (MatrixStep("analysis", ("missing",)),)),))
    with pytest.raises(ValueError):
        BrowserMatrix((MatrixCase("M01", (MatrixStep("upload"), MatrixStep("upload"))),))
