"""Regression tests for release-gate runner collection integrity."""

from __future__ import annotations

import copy
import hashlib
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
from scripts.acceptance.real_user_journey_oracles import (
    scenario_oracle_names,
    scenario_prompt_digest,
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


def test_gate_a_executes_background_session_ownership_regressions(tmp_path):
    commands = dict(release_gates._declared_commands(tmp_path)["A"])
    assert "tests/test_web_resume_ownership.py" in commands["collected_web_contracts"]


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


def test_harness_inspection_rejects_unowned_ignored_test(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        'collect_ignore = ["test_old_system.py"]\n',
        encoding="utf-8",
    )

    result = inspect_test_harness(conftest)

    assert result["status"] == "FAIL"
    assert result["unowned_ignored"] == ["test_old_system.py"]
    assert "unowned_collect_ignore" in result["reason_codes"]


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


def _legacy_browser_receipt() -> dict:
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


def _passing_live_run(index: int) -> dict:
    return {
        "run_id": f"live_{index}",
        "status": "PASS",
        "reason_codes": [],
        "upload_contract_active": True,
        "tool_calls": 8,
        "data_quality_computations": 1,
        "structured_computations": 3,
        "projected_evidence": 2,
        "final_audit_status": "pass",
        "publication_actions": {"claim_1": "verified"},
        "publication_length": 1200,
        "publication_language": "zh",
        "has_findings": True,
        "has_recommendations": True,
        "has_limitations": True,
        "generic_warning_present": False,
        "progress_before_final": True,
        "persisted_matches_streamed": True,
        "repeated_failure_max": 1,
        "unresolved_fallback_blocked_calls": 0,
        "verified_material_claims": 1,
        "measurement_bookkeeping_scheduled_analysis": False,
        "requirements": {
            "data_quality": "satisfied",
            "descriptive": "satisfied",
            "relationship": "satisfied",
            "limitations": "satisfied",
        },
    }


def _legacy_live_receipt() -> dict:
    return {
        "contract_version": "analysis_live_provider_gate.v1",
        "status": "PASS",
        "reason_codes": [],
        "accepted": True,
        "overall_status": "PASS",
        "live_provider_status": "PASS",
        "source_digest": SOURCE_DIGEST,
        "source_commit": "a" * 40,
        "provider_model": "configured-model",
        "runs": [_passing_live_run(index) for index in range(1, 4)],
    }


def _passing_live_receipt() -> dict:
    scenarios = ["cross_promo_funnel_v1", "card_multifile_paired_v1"]
    runs = []
    for index, scenario_id in enumerate(scenarios, start=1):
        journey = copy.deepcopy(_passing_browser_receipt())
        session_id = f"live-session-{index}"
        journey["scenario_id"] = scenario_id
        journey["fixture_digest"] = "sha256:" + hashlib.sha256(
            f"fixture:{scenario_id}".encode()
        ).hexdigest()
        journey["prompt_digest"] = scenario_prompt_digest(scenario_id)
        journey["oracle_digest"] = "sha256:" + hashlib.sha256(
            f"oracle:{scenario_id}".encode()
        ).hexdigest()
        journey["oracle_assertions"] = [
            {"name": name, "passed": True}
            for name in scenario_oracle_names(scenario_id)
        ]
        journey["session_id"] = session_id
        journey["refresh"]["session_id"] = session_id
        runs.append({
            "scenario_id": scenario_id,
            "status": "PASS",
            "provider_session_index": index,
            "browser_journey": journey,
            "human_review": {
                "question_understood": True,
                "method_appropriate": True,
                "claim_strength_appropriate": True,
                "limitations_material": True,
            },
        })
    return {
        "contract_version": "analysis_live_user_journey.v2",
        "status": "PASS",
        "reason_codes": [],
        "accepted": True,
        "source_digest": SOURCE_DIGEST,
        "source_commit": "a" * 40,
        "provider_model": "configured-model",
        "selection": {
            "risk_class": "task_evidence_recovery",
            "required_scenario_ids": scenarios,
        },
        "authorization": {
            "max_sessions": 2,
            "used_sessions": 2,
            "policy": "fail_fast",
        },
        "runs": runs,
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


def test_product_gate_accepts_complete_source_bound_live_pass():
    report = build_product_report_for_test(
        browser_receipt=_passing_browser_receipt(),
        live_receipt=_passing_live_receipt(),
        expected_source_digest=SOURCE_DIGEST,
    )
    assert report["overall_status"] == "PASS"
    assert report["product_release_passed"] is True
    assert report["gates"]["F"] == {
        "status": "PASS",
        "reason_codes": [],
    }


def _passing_browser_receipt() -> dict:
    return {
        "contract_version": "analysis_browser_user_journey.v2",
        "status": "PASS",
        "observer": "in_app_browser",
        "entrypoint": "web",
        "scenario_id": "lifecycle_canary_v1",
        "source_digest": SOURCE_DIGEST,
        "source_commit": "a" * 40,
        "fixture_digest": "sha256:" + "b" * 64,
        "prompt_digest": "sha256:" + "c" * 64,
        "oracle_digest": "sha256:" + "d" * 64,
        "url": "http://127.0.0.1:5013",
        "session_id": "session-canary",
        "tasks": {
            "total": 2,
            "completed": 2,
            "terminal": 2,
            "max_in_progress": 1,
            "monotonic": True,
        },
        "computations": {"bound": 1, "orphan": 0},
        "evidence": {"bound": 1, "orphan": 0, "legacy_unbound": 0},
        "oracle_assertions": [
            {"name": "row_count", "passed": True},
            {"name": "amount_sum", "passed": True},
        ],
        "answer": {
            "useful": True,
            "complete_before_turn_end": True,
            "forbidden_markers": [],
            "empty_structures": 0,
            "progress_visible": True,
            "content_digest": "sha256:" + "e" * 64,
        },
        "refresh": {
            "session_id": "session-canary",
            "task_total": 2,
            "task_completed": 2,
            "evidence_bound": 1,
            "answer_restored": True,
            "answer_digest": "sha256:" + "e" * 64,
        },
        "session_isolation": {"passed": True},
        "elapsed_ms": 4200,
        "first_failure_stage": "",
    }


def test_product_gate_rejects_legacy_transport_only_browser_receipt():
    legacy = _legacy_browser_receipt()
    assert legacy["contract_version"] == "analysis_browser_gate.v1"

    report = build_product_report_for_test(
        browser_receipt=legacy,
        live_receipt=_passing_live_receipt(),
        expected_source_digest=SOURCE_DIGEST,
    )

    assert report["gates"]["E"]["status"] == "FAIL"
    assert "invalid_user_journey_contract_version" in report["gates"]["E"]["reason_codes"]


def test_product_gate_rejects_incomplete_or_inconsistent_live_pass():
    cases = []
    missing_runs = _passing_live_receipt()
    missing_runs["runs"] = missing_runs["runs"][:1]
    missing_runs["authorization"]["used_sessions"] = 1
    cases.append((missing_runs, "required_live_user_journey_scenarios_missing"))

    duplicate_ids = _passing_live_receipt()
    duplicate_ids["runs"][1]["scenario_id"] = "cross_promo_funnel_v1"
    duplicate_ids["runs"][1]["browser_journey"]["scenario_id"] = "cross_promo_funnel_v1"
    cases.append((duplicate_ids, "duplicate_live_user_journey_scenarios"))

    shallow_run = _passing_live_receipt()
    shallow_run["runs"][1]["browser_journey"]["evidence"]["bound"] = 0
    shallow_run["runs"][1]["browser_journey"]["refresh"]["evidence_bound"] = 0
    cases.append((shallow_run, "missing_bound_user_journey_evidence"))

    inconsistent = _passing_live_receipt()
    inconsistent["accepted"] = False
    cases.append((inconsistent, "inconsistent_live_user_journey_status"))

    missing_provider = _passing_live_receipt()
    missing_provider["provider_model"] = ""
    cases.append((missing_provider, "invalid_live_user_journey_model"))

    for receipt, expected_reason in cases:
        report = build_product_report_for_test(
            browser_receipt=_passing_browser_receipt(),
            live_receipt=copy.deepcopy(receipt),
            expected_source_digest=SOURCE_DIGEST,
        )
        assert report["overall_status"] == "FAIL"
        assert report["product_release_passed"] is False
        assert report["gates"]["F"]["status"] == "FAIL"
        assert expected_reason in report["gates"]["F"]["reason_codes"]


def test_product_gate_rejects_legacy_three_run_provider_receipt():
    report = build_product_report_for_test(
        browser_receipt=_passing_browser_receipt(),
        live_receipt=_legacy_live_receipt(),
        expected_source_digest=SOURCE_DIGEST,
    )

    assert report["gates"]["F"]["status"] == "FAIL"
    assert "invalid_live_user_journey_contract_version" in report["gates"]["F"]["reason_codes"]


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
    live["accepted"] = False
    live["authorization"]["used_sessions"] = 0
    live["runs"] = []
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
