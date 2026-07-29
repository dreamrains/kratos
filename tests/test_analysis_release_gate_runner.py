"""Regression tests for release-gate runner collection integrity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_analysis_release_gates as release_gates
from scripts.run_analysis_release_gates import (
    build_gate_report,
    build_product_report_for_test,
    inspect_test_harness,
    run_declared_deterministic_gates,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIGEST = "sha256:" + "a" * 64


def run_pytest_collect_only(*paths: str) -> subprocess.CompletedProcess[str]:
    """Collect the specified tests using this checkout's interpreter context."""
    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    tests_path = str(ROOT / "tests")
    environment["PYTHONPATH"] = os.pathsep.join((source_path, tests_path))
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", *paths, "-q"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_critical_web_tests_are_collected():
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert '"test_sse_reactivity.py"' not in conftest
    assert '"test_web_gui.py"' not in conftest
    assert (ROOT / "tests" / "test_web_sse_contract.py").is_file()


def test_release_critical_web_nodeids_are_in_collect_only():
    result = run_pytest_collect_only("tests/test_web_sse_contract.py")
    assert result.returncode == 0, result.stderr
    assert "test_real_chat_route_streams_progress_before_text_and_turn_end" in result.stdout


def test_deterministic_profile_does_not_claim_browser_pass():
    report = build_gate_report(
        profile="deterministic",
        gate_results={
            "A": "PASS",
            "B": "PASS",
            "C": "PASS",
            "D": "PASS",
        },
    )
    assert report["overall_status"] == "PASS"
    assert report["gates"]["E"]["status"] == "NOT_RUN"
    assert report["gates"]["F"]["status"] == "NOT_RUN"
    assert report["product_release_passed"] is False


def test_deterministic_profile_forces_external_gates_not_run():
    report = build_gate_report(
        profile="deterministic",
        gate_results={gate: "PASS" for gate in "ABCDEF"},
    )
    assert report["overall_status"] == "PASS"
    assert report["gates"]["E"]["status"] == "NOT_RUN"
    assert report["gates"]["F"]["status"] == "NOT_RUN"
    assert report["product_release_passed"] is False


def test_product_profile_fails_when_browser_or_live_gate_is_not_run():
    report = build_gate_report(
        profile="product",
        gate_results={
            "A": "PASS",
            "B": "PASS",
            "C": "PASS",
            "D": "PASS",
            "E": "NOT_RUN",
            "F": "NOT_RUN",
        },
    )
    assert report["overall_status"] == "FAIL"
    assert report["product_release_passed"] is False


def test_gate_report_rejects_unknown_profiles_and_statuses():
    with pytest.raises(ValueError, match="profile"):
        build_gate_report(profile="release", gate_results={})
    with pytest.raises(ValueError, match="invalid gate status for A"):
        build_gate_report(
            profile="deterministic",
            gate_results={"A": "SKIPPED"},
        )


def test_harness_inspection_rejects_release_critical_collect_ignore(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        'collect_ignore = ["test_web_gui.py"]\n',
        encoding="utf-8",
    )
    result = inspect_test_harness(conftest)
    assert result["status"] == "FAIL"
    assert result["release_critical_ignored"] == ["test_web_gui.py"]


def test_harness_inspection_classifies_the_direct_tool_runner(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        'collect_ignore = ["test_tools_comprehensive.py"]\n',
        encoding="utf-8",
    )
    result = inspect_test_harness(conftest)
    assert result["status"] == "PASS"
    assert result["required_direct_runners"] == [
        "tests/test_tools_comprehensive.py"
    ]


def test_harness_inspection_does_not_treat_comments_as_collect_ignore(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        '# collect_ignore = ["test_web_gui.py"]\ncollect_ignore = []\n',
        encoding="utf-8",
    )
    result = inspect_test_harness(conftest)
    assert result["status"] == "PASS"
    assert result["release_critical_ignored"] == []


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (
            'collect_ignore = []\ncollect_ignore.append("test_web_gui.py")\n',
            "dynamic_collect_ignore",
        ),
        (
            'collect_ignore = []\ncollect_ignore.extend(["test_web_gui.py"])\n',
            "dynamic_collect_ignore",
        ),
        (
            'collect_ignore_glob = ["test_web*.py"]\n',
            "collect_ignore_glob_unsupported",
        ),
        (
            "def pytest_ignore_collect(collection_path, config):\n"
            "    return True\n",
            "unsafe_collection_hook",
        ),
        (
            "def pytest_collection_modifyitems(config, items):\n"
            "    items.clear()\n",
            "unsafe_collection_hook",
        ),
    ],
)
def test_harness_inspection_rejects_dynamic_collection_controls(
    tmp_path,
    source,
    reason,
):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(source, encoding="utf-8")
    result = inspect_test_harness(conftest)
    assert result["status"] == "FAIL"
    assert reason in result["reason_codes"]


def _passing_browser_receipt() -> dict:
    return {
        "contract_version": "analysis_browser_gate.v1",
        "status": "PASS",
        "observer": "in_app_browser",
        "fixture_id": "web_sse_fixture_v1",
        "source_digest": SOURCE_DIGEST,
        "source_commit": "a" * 40,
        "url": "http://127.0.0.1:5013",
        "observations": [
            {
                "name": name,
                "observed_text": observed_text,
                "browser_ms": browser_ms,
                "server_event_ms": server_ms,
                "turn_end_browser_ms": turn_end_ms,
            }
            for name, observed_text, browser_ms, server_ms, turn_end_ms in (
                ("upload_starts_analysis", "browser_fixture.csv", 40, 0, 900),
                ("progress_before_answer", "正在检查颗粒度与缺失", 100, 80, 900),
                ("first_chunk_before_second", "第一段", 350, 300, 900),
                (
                    "complete_answer_before_turn_end",
                    "第一段第二段",
                    700,
                    650,
                    900,
                ),
                (
                    "markdown_table_and_limitation_rendered",
                    "局限",
                    750,
                    650,
                    900,
                ),
                ("persisted_after_refresh", "第一段第二段", 1200, 900, 900),
                (
                    "retained_after_session_switch",
                    "第一段第二段",
                    1400,
                    900,
                    900,
                ),
                ("suspend_resume_nonblank", "恢复后内容", 1600, 1500, 1550),
                ("interruption_nonblank", "已中断验收", 1800, 1750, 1760),
                (
                    "error_nonblank",
                    "synthetic_acceptance_error",
                    2000,
                    1950,
                    1960,
                ),
            )
        ],
    }


def _passing_live_receipt() -> dict:
    return {
        "contract_version": "analysis_live_provider_gate.v1",
        "status": "PASS",
        "source_digest": SOURCE_DIGEST,
    }


@pytest.mark.parametrize(
    ("gate", "receipt"),
    [
        ("E", None),
        ("F", None),
        ("E", {"status": "PASS", "source_digest": "stale"}),
        ("F", {"status": "PASS", "source_digest": "stale"}),
    ],
)
def test_product_gate_rejects_missing_or_stale_receipt(gate, receipt):
    report = build_product_report_for_test(
        browser_receipt=(
            receipt if gate == "E" else _passing_browser_receipt()
        ),
        live_receipt=receipt if gate == "F" else _passing_live_receipt(),
        expected_source_digest=SOURCE_DIGEST,
    )
    assert report["overall_status"] == "FAIL"
    assert report["product_release_passed"] is False
    assert report["gates"][gate]["status"] in {"FAIL", "BLOCKED"}


@pytest.mark.parametrize(
    "live_receipt",
    [
        {
            "contract_version": "analysis_live_provider_gate.v1",
            "status": "PASS",
            "source_digest": SOURCE_DIGEST,
        },
        {
            "contract_version": "analysis_live_provider_gate.v1",
            "status": "PASS",
            "source_digest": SOURCE_DIGEST,
            "provider_model": "forged-model",
            "runs": [{"status": "PASS"} for _index in range(3)],
        },
    ],
)
def test_product_gate_blocks_live_pass_until_real_validator_exists(live_receipt):
    report = build_product_report_for_test(
        browser_receipt=_passing_browser_receipt(),
        live_receipt=live_receipt,
        expected_source_digest=SOURCE_DIGEST,
    )
    assert report["overall_status"] == "FAIL"
    assert report["product_release_passed"] is False
    assert report["gates"]["F"] == {
        "status": "BLOCKED",
        "reason_codes": ["live_provider_pass_not_yet_acceptable"],
    }


def test_pure_product_status_requires_all_a_through_f_pass():
    report = build_gate_report(
        profile="product",
        gate_results={gate: "PASS" for gate in "ABCDEF"},
    )
    assert report["overall_status"] == "PASS"
    assert report["product_release_passed"] is True


def test_product_gate_preserves_source_bound_live_blocked_status():
    live = _passing_live_receipt()
    live["status"] = "BLOCKED"
    live["reason_codes"] = ["provider_credentials_unavailable"]
    report = build_product_report_for_test(
        browser_receipt=_passing_browser_receipt(),
        live_receipt=live,
        expected_source_digest=SOURCE_DIGEST,
    )
    assert report["overall_status"] == "FAIL"
    assert report["gates"]["F"] == {
        "status": "BLOCKED",
        "reason_codes": ["provider_credentials_unavailable"],
    }


def test_failed_command_records_exact_exit_code_and_machine_readable_receipt(
    tmp_path,
):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            7 if len(calls) == 2 else 0,
            stdout="bounded stdout",
            stderr="bounded stderr",
        )

    report = run_declared_deterministic_gates(
        root=tmp_path,
        command_runner=fake_run,
        harness_result={
            "status": "PASS",
            "release_critical_ignored": [],
            "required_direct_runners": ["tests/test_tools_comprehensive.py"],
        },
    )

    failed_checks = [
        check
        for gate in report["gates"].values()
        for check in gate.get("checks", [])
        if check["status"] == "FAIL"
    ]
    assert report["overall_status"] == "FAIL"
    assert len(failed_checks) == 1
    assert failed_checks[0]["exit_code"] == 7
    assert failed_checks[0]["failure_receipt"] == {
        "contract_version": "analysis_gate_failure.v1",
        "gate": "A",
        "check": failed_checks[0]["name"],
        "exit_code": 7,
    }
    json.dumps(report)


def test_declared_pytest_commands_fail_on_return_not_none_warning(tmp_path):
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    run_declared_deterministic_gates(
        root=tmp_path,
        command_runner=fake_run,
        harness_result={
            "status": "PASS",
            "release_critical_ignored": [],
            "required_direct_runners": ["tests/test_tools_comprehensive.py"],
        },
    )

    pytest_commands = [
        command
        for command in commands
        if command[:3] == [sys.executable, "-m", "pytest"]
    ]
    assert pytest_commands
    assert all(
        "-W" in command
        and "error::pytest.PytestReturnNotNoneWarning" in command
        for command in pytest_commands
    )
    assert sum(
        "tests/test_analysis_release_gate_runner.py" in command
        for command in pytest_commands
    ) == 1
    assert ["git", "diff", "--check"] in commands


def test_gate_subprocess_capture_is_utf8_safe_on_windows(tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    run_declared_deterministic_gates(
        root=tmp_path,
        command_runner=fake_run,
        harness_result={
            "status": "PASS",
            "release_critical_ignored": [],
            "required_direct_runners": ["tests/test_tools_comprehensive.py"],
        },
    )

    assert calls
    for _command, kwargs in calls:
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"


def test_machine_report_json_is_safe_for_gbk_and_ascii_consoles():
    rendered = release_gates.render_report_json(
        {
            "status": "FAIL",
            "stderr_tail": "⚠️ 中文诊断",
        }
    )
    assert json.loads(rendered) == {
        "status": "FAIL",
        "stderr_tail": "⚠️ 中文诊断",
    }
    rendered.encode("ascii")
