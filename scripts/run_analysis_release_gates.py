#! /usr/bin/env python
"""Run fail-closed deterministic or product analysis release gates.

The deterministic profile proves only Gates A-D. Gates E and F require
source-bound external receipts and are never inferred from scripted replay.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
for _candidate in (ROOT, ROOT / "src", ROOT / "tests"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from scripts.acceptance.browser_gate_contract import (  # noqa: E402
    validate_browser_user_journey_receipt,
)
from scripts.acceptance.live_provider_gate_contract import (  # noqa: E402
    validate_live_user_journey_receipt,
)
from scripts.acceptance.release_source import release_source_digest  # noqa: E402


RELEASE_CONTRACT_VERSION = "analysis_reliability_release.v1"
FAILURE_CONTRACT_VERSION = "analysis_gate_failure.v1"
VALID_GATE_STATUSES = {"PASS", "FAIL", "NOT_RUN", "BLOCKED"}
DETERMINISTIC_REQUIRED = ("A", "B", "C", "D")
PRODUCT_REQUIRED = ("A", "B", "C", "D", "E", "F")
_RELEASE_CRITICAL_IGNORED = frozenset(
    {"test_sse_reactivity.py", "test_web_gui.py"}
)
_DIRECT_RUNNERS = {
    "test_tools_comprehensive.py": "tests/test_tools_comprehensive.py",
}
_COLLECTION_HOOKS = frozenset(
    {
        "pytest_ignore_collect",
        "pytest_collect_directory",
        "pytest_collect_file",
        "pytest_pycollect_makemodule",
        "pytest_pycollect_makeitem",
        "pytest_make_collect_report",
        "pytest_collection",
        "pytest_collection_modifyitems",
        "pytest_collection_finish",
        "pytest_deselected",
    }
)
_MAX_RECEIPT_BYTES = 1024 * 1024
_MAX_CAPTURE_CHARS = 4000

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _same_or_descendant(candidate: Path, protected: Path) -> bool:
    candidate = Path(candidate).resolve()
    protected = Path(protected).resolve()
    return candidate == protected or protected in candidate.parents


def build_isolated_runtime_environment(
    *,
    repository_root: Path,
    state_root: Path,
    base_environment: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build child-process state roots that cannot touch interactive runtime.

    Release subprocesses import module-level state managers.  Their paths must
    therefore be fixed in the environment before Python imports application
    modules; changing a singleton after startup is too late.
    """

    repository_root = Path(repository_root).resolve()
    state_root = Path(state_root).resolve()
    workspace_root = state_root / "workspace"
    sessions_root = state_root / "sessions"
    protected_roots = (
        repository_root / "workspace",
        repository_root / "sessions",
    )
    candidates = (state_root, workspace_root, sessions_root)
    if any(
        _same_or_descendant(candidate, protected)
        for candidate in candidates
        for protected in protected_roots
    ):
        raise ValueError("interactive_runtime_state roots are forbidden")

    workspace_root.mkdir(parents=True, exist_ok=True)
    sessions_root.mkdir(parents=True, exist_ok=True)
    environment = dict(base_environment or {})
    environment["DATA_AGENT_TEST_STATE_ROOT"] = str(state_root)
    environment["WORKSPACE_DIR"] = str(workspace_root)
    environment["SESSIONS_DIR"] = str(sessions_root)
    source_paths = (
        str(repository_root / "src"),
        str(repository_root / "tests"),
        str(repository_root),
    )
    inherited_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        (*source_paths, *([inherited_pythonpath] if inherited_pythonpath else []))
    )
    return environment, {
        "name": "runtime_state_isolation",
        "status": "PASS",
        "state_isolated": True,
        "source_import_isolated": True,
        "source_root": str(repository_root / "src"),
    }


def build_gate_report(
    *,
    profile: str,
    gate_results: dict[str, str],
) -> dict[str, Any]:
    """Build public status without upgrading any absent gate."""

    if profile not in {"deterministic", "product"}:
        raise ValueError("profile must be deterministic or product")
    required = (
        DETERMINISTIC_REQUIRED
        if profile == "deterministic"
        else PRODUCT_REQUIRED
    )
    gates: dict[str, dict[str, Any]] = {}
    for gate in PRODUCT_REQUIRED:
        status = (
            "NOT_RUN"
            if profile == "deterministic" and gate in {"E", "F"}
            else gate_results.get(gate, "NOT_RUN")
        )
        if status not in VALID_GATE_STATUSES:
            raise ValueError(f"invalid gate status for {gate}: {status}")
        gates[gate] = {"status": status}
    passed = all(gates[gate]["status"] == "PASS" for gate in required)
    product_passed = (
        profile == "product"
        and all(gates[gate]["status"] == "PASS" for gate in PRODUCT_REQUIRED)
    )
    return {
        "contract_version": RELEASE_CONTRACT_VERSION,
        "profile": profile,
        "overall_status": "PASS" if passed else "FAIL",
        "product_release_passed": product_passed,
        "gates": gates,
    }


def _collect_ignore_values(tree: ast.AST) -> tuple[list[str], list[str]]:
    values: list[str] = []
    reasons: list[str] = []
    for node in ast.walk(tree):
        value_node: ast.AST | None = None
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Name) and target.id == "collect_ignore"
                for target in targets
            ):
                value_node = node.value
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "collect_ignore"
        ):
            value_node = node.value
        if value_node is None:
            continue
        try:
            raw = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            reasons.append("collect_ignore_not_static")
            continue
        if not isinstance(raw, (list, tuple)):
            reasons.append("collect_ignore_not_sequence")
            continue
        if not all(isinstance(item, str) for item in raw):
            reasons.append("collect_ignore_contains_non_string")
            continue
        values.extend(raw)
    return values, reasons


def _contains_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(item, ast.Name) and item.id == name
        for item in ast.walk(node)
    )


def _collection_control_reasons(tree: ast.AST) -> list[str]:
    reasons: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id == "collect_ignore_glob"
        ):
            reasons.append("collect_ignore_glob_unsupported")
        if isinstance(node, ast.Call) and _contains_name(node, "collect_ignore"):
            reasons.append("dynamic_collect_ignore")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if (
                    not isinstance(target, ast.Name)
                    and _contains_name(target, "collect_ignore")
                ):
                    reasons.append("dynamic_collect_ignore")
                if (
                    isinstance(target, ast.Name)
                    and target.id in _COLLECTION_HOOKS
                ):
                    reasons.append("unsafe_collection_hook")
        if isinstance(node, ast.Delete) and any(
            _contains_name(target, "collect_ignore")
            for target in node.targets
        ):
            reasons.append("dynamic_collect_ignore")
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in _COLLECTION_HOOKS
        ):
            reasons.append("unsafe_collection_hook")
    return list(dict.fromkeys(reasons))


def inspect_test_harness(conftest: Path) -> dict[str, Any]:
    """Classify ignored tests and reject hidden release-critical Web tests."""

    reasons: list[str] = []
    ignored: list[str] = []
    try:
        source = Path(conftest).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(conftest))
        ignored, parse_reasons = _collect_ignore_values(tree)
        reasons.extend(parse_reasons)
        reasons.extend(_collection_control_reasons(tree))
    except (OSError, UnicodeError, SyntaxError):
        reasons.append("test_harness_unreadable")
    ignored_names = {Path(item).name for item in ignored}
    release_critical = sorted(ignored_names & _RELEASE_CRITICAL_IGNORED)
    if release_critical:
        reasons.append("release_critical_collect_ignore")
    unowned_ignored = sorted(
        name for name in ignored_names if name not in _DIRECT_RUNNERS
    )
    if unowned_ignored:
        reasons.append("unowned_collect_ignore")
    direct_runners = sorted(
        path
        for name, path in _DIRECT_RUNNERS.items()
        if name in ignored_names
    )
    return {
        "status": "PASS" if not reasons else "FAIL",
        "release_critical_ignored": release_critical,
        "unowned_ignored": unowned_ignored,
        "required_direct_runners": direct_runners,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def _pytest_command(*paths: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-W",
        "error::pytest.PytestReturnNotNoneWarning",
        *paths,
        "-q",
    ]


def _declared_commands(replay_root: Path) -> dict[str, list[tuple[str, list[str]]]]:
    return {
        "A": [
            (
                "collected_web_contracts",
                _pytest_command(
                    "tests/test_web_sse_contract.py",
                    "tests/test_web_sse_reactivity_contract.py",
                    "tests/test_web_resume_ownership.py",
                    "tests/test_analysis_progress_streaming.py",
                    "tests/test_analysis_release_gate_runner.py",
                ),
            ),
            (
                "direct_tool_runner",
                [sys.executable, "tests/test_tools_comprehensive.py"],
            ),
            (
                "python_compile",
                [sys.executable, "-m", "compileall", "-q", "src/data_agent"],
            ),
            (
                "web_javascript_syntax",
                ["node", "--check", "src/data_agent/web/static/js/app.js"],
            ),
            ("working_tree_diff_check", ["git", "diff", "--check"]),
        ],
        "B": [
            (
                "measurement_contract_and_mutations",
                _pytest_command(
                    "tests/test_automatic_evidence_projection.py",
                    "tests/test_final_answer_claim_audit.py",
                    "tests/test_verification_layer.py",
                    "tests/test_final_answer_publish_gate.py",
                    "tests/test_tiered_analysis_publication.py",
                ),
            )
        ],
        "C": [
            (
                "real_projection_to_publication",
                _pytest_command("tests/test_measurement_identity_pipeline.py"),
            )
        ],
        "D": [
            (
                "analysis_quality_replay_tests",
                _pytest_command("tests/test_analysis_reliability_replays.py"),
            ),
            (
                "deterministic_replay_cli",
                [
                    sys.executable,
                    "scripts/replay_analysis_reliability.py",
                    "--mode",
                    "deterministic",
                    "--output-dir",
                    str(replay_root),
                ],
            ),
        ],
    }


def _bounded_capture(value: Any) -> str:
    return str(value or "")[-_MAX_CAPTURE_CHARS:]


def _command_check(
    *,
    gate: str,
    name: str,
    command: list[str],
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    status = "PASS" if completed.returncode == 0 else "FAIL"
    result: dict[str, Any] = {
        "name": name,
        "status": status,
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": _bounded_capture(completed.stdout),
        "stderr_tail": _bounded_capture(completed.stderr),
    }
    if status == "FAIL":
        result["failure_receipt"] = {
            "contract_version": FAILURE_CONTRACT_VERSION,
            "gate": gate,
            "check": name,
            "exit_code": completed.returncode,
        }
    return result


def run_declared_deterministic_gates(
    *,
    root: Path = ROOT,
    command_runner: CommandRunner = subprocess.run,
    harness_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run A-D and retain exact per-command exit codes in the JSON report."""

    root = Path(root).resolve()
    harness = harness_result or inspect_test_harness(root / "tests" / "conftest.py")
    gate_checks: dict[str, list[dict[str, Any]]] = {
        gate: [] for gate in DETERMINISTIC_REQUIRED
    }
    harness_check: dict[str, Any] = {
        "name": "test_harness_inspection",
        "status": harness["status"],
        "release_critical_ignored": harness.get("release_critical_ignored", []),
        "unowned_ignored": harness.get("unowned_ignored", []),
        "required_direct_runners": harness.get("required_direct_runners", []),
        "reason_codes": harness.get("reason_codes", []),
    }
    if harness_check["status"] != "PASS":
        harness_check["failure_receipt"] = {
            "contract_version": FAILURE_CONTRACT_VERSION,
            "gate": "A",
            "check": "test_harness_inspection",
            "exit_code": None,
    }
    gate_checks["A"].append(harness_check)

    with tempfile.TemporaryDirectory(prefix="data-agent-release-gates-") as tmp:
        gate_root = Path(tmp)
        environment, isolation_check = build_isolated_runtime_environment(
            repository_root=root,
            state_root=gate_root / "runtime-state",
            base_environment=os.environ.copy(),
        )
        environment["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        gate_checks["A"].append(isolation_check)
        commands = _declared_commands(gate_root / "deterministic-replay")
        for gate in DETERMINISTIC_REQUIRED:
            for name, command in commands[gate]:
                try:
                    completed = command_runner(
                        command,
                        cwd=root,
                        env=environment,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        capture_output=True,
                        check=False,
                    )
                except OSError as exc:
                    completed = subprocess.CompletedProcess(
                        command,
                        127,
                        stdout="",
                        stderr=type(exc).__name__,
                    )
                gate_checks[gate].append(
                    _command_check(
                        gate=gate,
                        name=name,
                        command=command,
                        completed=completed,
                    )
                )

    statuses = {
        gate: (
            "PASS"
            if all(check["status"] == "PASS" for check in gate_checks[gate])
            else "FAIL"
        )
        for gate in DETERMINISTIC_REQUIRED
    }
    report = build_gate_report(
        profile="deterministic",
        gate_results=statuses,
    )
    for gate in DETERMINISTIC_REQUIRED:
        report["gates"][gate]["checks"] = gate_checks[gate]
    return report


def _validate_receipt(
    receipt: Any,
    *,
    gate: str,
    expected_source_digest: str,
) -> dict[str, Any]:
    if receipt is None:
        return {
            "status": "BLOCKED",
            "reason_codes": [
                "browser_receipt_missing"
                if gate == "E"
                else "live_provider_receipt_missing"
            ],
        }
    if not isinstance(receipt, dict):
        return {"status": "FAIL", "reason_codes": ["invalid_receipt"]}
    if gate == "E":
        validation = validate_browser_user_journey_receipt(
            receipt,
            expected_source_digest=expected_source_digest,
        )
        return {
            "status": validation.status,
            "reason_codes": list(validation.reason_codes),
        }
    validation = validate_live_user_journey_receipt(
        receipt,
        expected_source_digest=expected_source_digest,
    )
    return {
        "status": validation.status,
        "reason_codes": list(validation.reason_codes),
    }


def _read_receipt(path: Path | None, *, gate: str) -> tuple[Any, list[str]]:
    if path is None:
        return None, []
    try:
        path = Path(path)
        if path.stat().st_size > _MAX_RECEIPT_BYTES:
            return None, ["receipt_too_large"]
        return json.loads(path.read_text(encoding="utf-8")), []
    except FileNotFoundError:
        return None, []
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, [
            "invalid_browser_receipt_file"
            if gate == "E"
            else "invalid_live_provider_receipt_file"
        ]


def _build_product_report(
    *,
    deterministic_report: dict[str, Any],
    browser_receipt: Any,
    live_receipt: Any,
    expected_source_digest: str,
    browser_file_reasons: list[str] | None = None,
    live_file_reasons: list[str] | None = None,
) -> dict[str, Any]:
    e_result = _validate_receipt(
        browser_receipt,
        gate="E",
        expected_source_digest=expected_source_digest,
    )
    f_result = _validate_receipt(
        live_receipt,
        gate="F",
        expected_source_digest=expected_source_digest,
    )
    if browser_file_reasons:
        e_result = {"status": "FAIL", "reason_codes": browser_file_reasons}
    if live_file_reasons:
        f_result = {"status": "FAIL", "reason_codes": live_file_reasons}
    gate_results = {
        gate: deterministic_report["gates"][gate]["status"]
        for gate in DETERMINISTIC_REQUIRED
    }
    gate_results.update({"E": e_result["status"], "F": f_result["status"]})
    report = build_gate_report(profile="product", gate_results=gate_results)
    for gate in DETERMINISTIC_REQUIRED:
        report["gates"][gate].update(
            {
                key: value
                for key, value in deterministic_report["gates"][gate].items()
                if key != "status"
            }
        )
    report["gates"]["E"]["reason_codes"] = e_result["reason_codes"]
    report["gates"]["F"]["reason_codes"] = f_result["reason_codes"]
    report["source_digest"] = expected_source_digest
    return report


def build_product_report_for_test(
    *,
    browser_receipt: Any,
    live_receipt: Any,
    expected_source_digest: str,
) -> dict[str, Any]:
    """Exercise receipt validation without executing A-D subprocesses."""

    deterministic = build_gate_report(
        profile="deterministic",
        gate_results={gate: "PASS" for gate in DETERMINISTIC_REQUIRED},
    )
    return _build_product_report(
        deterministic_report=deterministic,
        browser_receipt=browser_receipt,
        live_receipt=live_receipt,
        expected_source_digest=expected_source_digest,
    )


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def render_report_json(report: dict[str, Any]) -> str:
    """Serialize report safely even when the console encoding is ASCII/GBK."""

    return json.dumps(report, ensure_ascii=True, indent=2)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run truthful analysis reliability release gates."
    )
    parser.add_argument(
        "--profile",
        choices=("deterministic", "product"),
        required=True,
    )
    parser.add_argument("--browser-receipt", type=Path)
    parser.add_argument("--live-provider-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    deterministic = run_declared_deterministic_gates(root=ROOT)
    if args.profile == "deterministic":
        report = deterministic
    else:
        expected_digest = release_source_digest(ROOT)
        browser, browser_file_reasons = _read_receipt(
            args.browser_receipt,
            gate="E",
        )
        live, live_file_reasons = _read_receipt(
            args.live_provider_receipt,
            gate="F",
        )
        report = _build_product_report(
            deterministic_report=deterministic,
            browser_receipt=browser,
            live_receipt=live,
            expected_source_digest=expected_digest,
            browser_file_reasons=browser_file_reasons,
            live_file_reasons=live_file_reasons,
        )
    if args.output:
        _write_report(args.output, report)
    print(render_report_json(report))
    return 0 if report["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
