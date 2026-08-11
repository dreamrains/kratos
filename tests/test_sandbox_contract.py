"""Sandbox execution contract tests: bounded imports, dataset lookup, recovery.

These tests target Task 3 of the analysis-reliability plan: the sandbox must
(a) resolve allowlisted imports from preloaded modules without invoking the
runtime importer, (b) surface missing datasets as structured errors instead of
cascading through ``None``, and (c) expose enough failure metadata for the
turn-execution state to block identical retries.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from data_agent.agent.execution_control import (
    ToolExecutionBudget,
    TurnExecutionState,
)
from data_agent.session.workspace import Workspace
from data_agent.tools.sandbox import run_python


@pytest.fixture
def workspace(monkeypatch):
    """Bind a fresh in-memory workspace exposing only the ``orders`` dataset."""

    import data_agent.tools.sandbox as sandbox

    ws = Workspace()
    ws.add("orders", pd.DataFrame({"x": [1, 2, 3]}))
    monkeypatch.setattr(sandbox, "workspace", ws)
    return ws


@pytest.fixture
def turn_state():
    return TurnExecutionState(ToolExecutionBudget())


@pytest.mark.parametrize(
    "code",
    [
        "import pandas\nresult = pandas.DataFrame({'x': [1]}).shape",
        "import pandas as frame_lib\nresult = frame_lib.DataFrame({'x': [1]}).shape",
        "from pandas import DataFrame\nresult = DataFrame({'x': [1]}).shape",
        "import numpy\nresult = numpy.mean([1, 2, 3])",
        "from scipy import stats\nresult = stats.pearsonr([1, 2, 3], [1, 2, 4]).statistic",
    ],
)
def test_preloaded_import_forms_do_not_call_runtime_import(code):
    payload = json.loads(run_python(code))
    assert payload["success"] is True
    assert "__import__ not found" not in json.dumps(payload)


@pytest.mark.parametrize(
    "code",
    [
        "import requests",
        "import scipy.optimize",
        "from pandas import *",
        "from pandas import __dict__",
        # Dotted paths whose ROOT is allowlisted but whose full path is not
        # an approved module must be rejected — the previous normalizer only
        # checked the root and silently bound the root module instead.
        "import pandas.core",
        "from pandas.core import DataFrame",
        "import pandas._testing",
        "import numpy.linalg",
        # ``scipy`` is not an approved root and only ``scipy.stats`` is
        # dotted-approved; mixing stats with another submodule must reject
        # the whole statement.
        "from scipy import stats, optimize",
    ],
)
def test_unapproved_imports_fail_before_execution(code):
    payload = json.loads(run_python(code))
    assert payload["error_type"] == "sandbox_import_not_allowed"
    assert payload["success"] is False
    # Every failure payload advertises the structured recovery fields.
    for required in (
        "message",
        "dataset_reads",
        "failed_operation",
        "allowed_datasets",
        "safe_alternatives",
    ):
        assert required in payload


@pytest.mark.parametrize(
    "code",
    [
        # ``numpy`` is an allowed root and ``linalg`` is a public attribute of
        # the preloaded numpy module — same rule as ``from pandas import
        # DataFrame``. Must NOT regress when rejecting ``import numpy.linalg``.
        "from numpy import linalg\nresult = linalg.norm([1, 2, 3])",
        # ``scipy.stats`` is the single dotted-approved module; binding from
        # it must keep working.
        "from scipy.stats import pearsonr\nresult = pearsonr([1, 2, 3], [1, 2, 4]).statistic",
    ],
)
def test_public_attribute_imports_from_allowed_roots_still_succeed(code):
    payload = json.loads(run_python(code))
    assert payload["success"] is True


@pytest.mark.parametrize(
    "handler",
    ["Exception", "ValueError", "ImportError"],
)
def test_common_exception_handlers_are_available_in_sandbox(handler):
    if handler == "ImportError":
        code = (
            "try:\n"
            "    raise ImportError('optional dependency unavailable')\n"
            "except ImportError:\n"
            "    result = 'handled'"
        )
    else:
        code = (
            "try:\n"
            "    int('not-a-number')\n"
            f"except {handler}:\n"
            "    result = 'handled'"
        )

    payload = json.loads(run_python(code))

    assert payload["success"] is True
    assert payload["result"] == "handled"


def test_get_dataset_missing_name_is_structured_and_never_none(workspace):
    payload = json.loads(
        run_python("df = get_dataset('missing')\nresult = df['x'].sum()")
    )
    assert payload["error_type"] == "dataset_not_found"
    assert payload["dataset_reads"] == ["missing"]
    assert payload["allowed_datasets"] == ["orders"]
    assert "NoneType" not in json.dumps(payload)
    assert payload["success"] is False
    assert payload["failed_operation"] == "get_dataset"
    assert isinstance(payload["safe_alternatives"], list)
    assert payload["safe_alternatives"]


def test_numeric_dtype_introspection_does_not_require_user_runtime_import(workspace):
    """NumPy may resolve an already-loaded private formatter internally.

    The sandbox must support that library-internal lookup without exposing a
    general importer to user code. This exact operation failed in the real
    savings-card journey before any substantive analysis could run.
    """

    payload = json.loads(
        run_python("df = get_dataset('orders')\nresult = str(df['x'].dtype)")
    )

    assert payload["success"] is True
    assert payload["result"] == "int64"
    assert "__import__" not in json.dumps(payload)


def test_user_code_cannot_call_runtime_importer():
    payload = json.loads(run_python("result = __import__('os')"))

    assert payload["success"] is False
    assert payload["error_type"] == "sandbox_violation"


def test_identical_sandbox_failure_is_blocked_after_first_corrected_retry(turn_state):
    fingerprint = turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    # First failure permits one corrected retry; second identical call must block.
    assert turn_state.can_retry_failure(fingerprint) is False


def test_distinct_sandbox_failures_remain_retryable(turn_state):
    first = turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    second = turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import os"},
        error_type="sandbox_import_not_allowed",
    )
    assert first != second
    assert turn_state.can_retry_failure(first) is True
    assert turn_state.can_retry_failure(second) is True


def test_failure_fingerprint_is_deterministic(turn_state):
    first = turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    # Reset attempts by mutating the stored entry to simulate a fresh run.
    turn_state.requirement_failures.clear()
    second = turn_state.record_requirement_failure(
        requirement_id="req_step_python",
        tool_name="run_python",
        arguments={"code": "import requests"},
        error_type="sandbox_import_not_allowed",
    )
    assert first == second
