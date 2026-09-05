"""Collect every independent case without retrying a failed journey.

This coordinator does not grant Provider authority or dispatch requests. A
separately frozen driver supplies steps, guarded clients, receipt accounting
and process isolation. Unknown driver errors halt a case, not the matrix;
failure to prove teardown/accounting safety halts the remaining matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class MatrixStep:
    id: str
    requires: tuple[str, ...] = ()
    # Only read_only steps may run after scenario termination. Uploads and
    # other local mutations must not masquerade as existing-state inspection.
    mode: Literal["provider_action", "local_action", "read_only"] = "provider_action"


@dataclass(frozen=True)
class MatrixCase:
    id: str
    steps: tuple[MatrixStep, ...]


@dataclass(frozen=True)
class StepObservation:
    passed: bool
    state_available: bool = True
    code: str = ""
    stop_scope: Literal["none", "case", "batch"] = "none"


class BrowserMatrix:
    """Single-use ordered collector with explicit case/batch stop scopes."""

    def __init__(self, cases: tuple[MatrixCase, ...]):
        if not cases or len({case.id for case in cases}) != len(cases):
            raise ValueError("matrix requires unique case ids")
        for case in cases:
            seen = set()
            for step in case.steps:
                if step.mode not in {"provider_action", "local_action", "read_only"}:
                    raise ValueError("invalid step mode")
                if step.id in seen or not set(step.requires) <= seen:
                    raise ValueError("steps must have unique ids and earlier dependencies")
                seen.add(step.id)
            if not seen:
                raise ValueError("case requires steps")
        self._cases = cases
        self._started = False

    def run(
        self,
        *,
        observe: Callable[[MatrixCase, MatrixStep], StepObservation],
        close_case: Callable[[MatrixCase], bool],
        batch_block_reason: Callable[[], str],
    ) -> dict:
        """Visit each case once, even after scenario-local exceptions.

        ``close_case`` must prove all case processes/requests stopped, final
        counts known and writes isolated. ``batch_block_reason`` checks the
        shared authorization, source/data integrity and remaining total cap.
        Both fail closed; neither is inferred from a failed oracle.
        """
        if self._started:
            raise RuntimeError("matrix already consumed; no implicit rerun")
        self._started = True
        results = []
        batch_stop = ""
        for case in self._cases:
            if not batch_stop:
                batch_stop = self._check_batch(batch_block_reason)
            if batch_stop:
                results.append({"id": case.id, "status": "not_run", "reason": batch_stop, "steps": []})
                continue
            steps = []
            available = set()
            case_stop = ""
            try:
                for step in case.steps:
                    if not batch_stop:
                        batch_stop = self._check_batch(batch_block_reason)
                    missing = sorted(set(step.requires) - available)
                    blocked = batch_stop or (
                        "dependency_unavailable:" + ",".join(missing) if missing else ""
                    ) or (case_stop if step.mode != "read_only" else "")
                    if blocked:
                        steps.append({"id": step.id, "status": "blocked", "reason": blocked})
                        continue
                    try:
                        result = observe(case, step)
                        if not isinstance(result, StepObservation) or result.stop_scope not in {"none", "case", "batch"}:
                            raise ValueError("invalid step observation")
                        if result.stop_scope != "none" and result.passed:
                            raise ValueError("terminal observation cannot pass")
                    except Exception as exc:
                        # Do not put exception text (possibly credentials or
                        # raw rows) into aggregate reports. Driver evidence is
                        # retained in its authorized case-specific location.
                        result = StepObservation(False, False, f"driver_exception:{type(exc).__name__}", "case")
                    if result.state_available:
                        available.add(step.id)
                    steps.append({
                        "id": step.id,
                        "status": "passed" if result.passed else "failed",
                        "reason": result.code,
                    })
                    if result.stop_scope == "case":
                        case_stop = result.code or "case_terminated"
                    if result.stop_scope == "batch":
                        batch_stop = result.code or "batch_terminated"
            finally:
                try:
                    contained = close_case(case) is True
                except Exception:
                    contained = False
                if not contained:
                    batch_stop = "case_containment_or_accounting_unproven"
            results.append({
                "id": case.id,
                "status": "passed" if contained and all(s["status"] == "passed" for s in steps) else "failed",
                "reason": case_stop or (batch_stop if not contained else ""),
                "steps": steps,
            })
        return {
            "schema_version": "browser_matrix_collection.v1",
            "status": "passed" if all(c["status"] == "passed" for c in results) else "failed",
            "batch_stop_reason": batch_stop,
            "cases": results,
            "cases_attempted": sum(c["status"] != "not_run" for c in results),
            "cases_not_run": sum(c["status"] == "not_run" for c in results),
        }

    @staticmethod
    def _check_batch(check):
        try:
            reason = check()
            return reason if isinstance(reason, str) else "batch_safety_check_invalid"
        except Exception:
            return "batch_safety_check_failed"
