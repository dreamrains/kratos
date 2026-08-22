from __future__ import annotations

import pandas as pd

from data_agent.v2.exploratory import execute_exploratory_python


def test_exploratory_python_returns_bounded_traceable_output_without_mutating_input():
    frame = pd.DataFrame({"sales": [10, 20, 30]})
    result = execute_exploratory_python(
        frame,
        code='print("rows", len(data)); result = data["sales"].median()',
        purpose="检查中位数作为异常值敏感性补充",
    )

    assert result.status == "succeeded"
    assert result.output == "rows 3\n"
    assert result.result == "20.0"
    assert result.code_fingerprint.startswith("sha256:")
    assert result.verification_level == "exploratory_only"
    assert frame["sales"].tolist() == [10, 20, 30]


def test_exploratory_python_rejects_import_and_file_access():
    frame = pd.DataFrame({"sales": [10]})

    imported = execute_exploratory_python(
        frame, code="import os\nresult = os.getcwd()", purpose="读取环境"
    )
    opened = execute_exploratory_python(
        frame, code='result = open("secret.txt").read()', purpose="读取文件"
    )
    written = execute_exploratory_python(
        frame, code='data.to_csv("leak.csv")', purpose="写出文件"
    )

    assert imported.status == "rejected"
    assert imported.error_code == "import_not_allowed"
    assert opened.status == "rejected"
    assert opened.error_code == "unsafe_code"
    assert written.status == "rejected"
    assert written.error_code == "io_not_allowed"


def test_exploratory_python_hard_timeout_terminates_execution():
    result = execute_exploratory_python(
        pd.DataFrame({"sales": [10]}),
        code="while True:\n    pass",
        purpose="测试执行预算",
        timeout_seconds=0.2,
    )

    assert result.status == "timed_out"
    assert result.error_code == "execution_timeout"


def test_exploratory_python_truncates_large_output():
    result = execute_exploratory_python(
        pd.DataFrame({"sales": [10]}),
        code='print("x" * 1000)',
        purpose="检查输出边界",
        max_output_chars=80,
    )

    assert result.status == "succeeded"
    assert len(result.output) <= 80
    assert result.output_truncated is True
