"""Golden final-answer quality measurement harness.

Measurement-only layer. Not imported by agent runtime synthesis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLDEN_MANIFEST_SCHEMA = "golden_answer_scenarios.v1"
ALLOWED_SOFT_DIMENSIONS = {
    "rigor",
    "insight_depth",
    "guidance",
    "data_explanation",
    "direction_expansion",
    "synthesis",
}


class GoldenManifestError(ValueError):
    pass


def load_golden_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoldenManifestError(f"malformed golden manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise GoldenManifestError("golden manifest root must be an object")
    if manifest.get("schema_version") != GOLDEN_MANIFEST_SCHEMA:
        raise GoldenManifestError(
            f"golden manifest schema_version must be {GOLDEN_MANIFEST_SCHEMA}"
        )
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise GoldenManifestError("golden manifest scenarios must be a non-empty list")
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            raise GoldenManifestError(f"scenario {index} requires a string id")
        required_files = scenario.get("required_files")
        if (
            not isinstance(required_files, list)
            or not required_files
            or not all(isinstance(name, str) and name for name in required_files)
        ):
            raise GoldenManifestError(
                f"scenario {scenario['id']} has invalid required_files"
            )
        if not isinstance(scenario.get("business_question"), str) or not scenario["business_question"]:
            raise GoldenManifestError(
                f"scenario {scenario['id']} requires a business_question"
            )
        focus = scenario.get("soft_dimension_focus", [])
        if not isinstance(focus, list) or not set(focus).issubset(ALLOWED_SOFT_DIMENSIONS):
            raise GoldenManifestError(
                f"scenario {scenario['id']} has invalid soft_dimension_focus"
            )
    return manifest


import uuid
from datetime import datetime, timezone

from data_agent.agent.answer_quality import evaluate_fatal, build_judge_context
from data_agent.agent.quality_judge import judge_absolute, judge_pairwise


def evaluate_answer(
    answer_text: str,
    state,
    question: str,
    dimensions: list[str],
    *,
    baseline_answer: str | None = None,
    judge_client=None,
) -> dict[str, Any]:
    fatal = evaluate_fatal(answer_text, state)
    context = build_judge_context(state, question)
    data_brief = context["data_brief"]
    soft: dict[str, Any] = {
        "absolute": judge_absolute(answer_text, question, data_brief, dimensions, client=judge_client),
        "pairwise": None,
    }
    if baseline_answer is not None:
        soft["pairwise"] = judge_pairwise(
            baseline_answer, answer_text, question, data_brief, dimensions, client=judge_client
        )
    return {"fatal": fatal, "soft": soft}


def read_baseline(baseline_dir: Path, scenario_id: str) -> str | None:
    path = baseline_dir / f"{scenario_id}.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def write_baseline(baseline_dir: Path, scenario_id: str, answer_text: str) -> None:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / f"{scenario_id}.txt").write_text(answer_text, encoding="utf-8")


def drive_agent_for_scenario(scenario: dict[str, Any], data_dir: Path, *, client=None) -> tuple[str, Any, str | None]:
    from data_agent.tools import discover_tools  # ensure tools registered
    from data_agent.agent.loop import AgentLoop, FinalResponse, SuspendedForConfirmation
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.tools.data_io import load_data

    discover_tools()
    # Force sequential tool execution for the measurement run. The runtime's
    # parallel read-only path (_execute_tools_parallel) has an intermittent
    # contextvars race ("cannot enter context: already entered") under this
    # driver's context setup, triggered when the agent issues multiple read-only
    # tool calls (common for rich multi-file scenarios). Neutralising
    # get_read_only_tools makes the loop take the sequential branch and avoids
    # the race entirely; measurement needs no parallel speedup. The runtime
    # race itself is tracked as a separate follow-up.
    from data_agent.tools import registry as _tool_registry

    _tool_registry.get_read_only_tools = lambda reg: set()
    project_name = f"golden_{scenario['id']}"
    session_id = uuid.uuid4().hex[:12]
    loop = AgentLoop(client=client, session_id=session_id, project_name=project_name)
    # loop.client is the effective client used (passed-in or a default LLMClient),
    # so read the model id from it for traceability.
    agent_model_id = getattr(loop.client, "model_id", None)
    resume_answer = "按你的最佳判断继续分析"
    max_resumes = 5
    with use_agent_context(loop.context):
        for index, name in enumerate(scenario["required_files"]):
            load_data(str((data_dir / name).resolve()), name=f"{project_name}_ds{index}")
        # Drive fully non-interactively: never touch stdin. Use the web-mode
        # structured + resume path instead of run_turn (CLI path), which blocks
        # reading stdin via _handle_cli_suspension -> _ask_single/_ask_multiple.
        result = loop.run_turn_structured(scenario["business_question"])
        resumes = 0
        while isinstance(result, SuspendedForConfirmation):
            if resumes >= max_resumes:
                raise GoldenManifestError(
                    f"scenario {scenario['id']}: agent did not produce a final answer "
                    f"after {max_resumes} confirmation resumptions "
                    f"(last question: {result.question!r})"
                )
            resumes += 1
            # Structured state-driving selects (allow_free_text=False) reject
            # free text via _validate_answer; answer with the first option's
            # value so resume resolves cleanly instead of surfacing an
            # "Error: ..." FinalResponse as the scenario's answer.
            if not getattr(result, "allow_free_text", True) and getattr(result, "options", None):
                first = result.options[0]
                if isinstance(first, str):
                    answer = first
                else:
                    answer = first.get("value") or first.get("label") or str(first)
            else:
                answer = resume_answer
            result = loop.resume_turn(
                result.suspension_id,
                answer,
                idempotency_key=f"{session_id}:resume:{resumes}",
            )
        if isinstance(result, FinalResponse):
            final_text = result.content
        else:
            # result is None: _loop exhausted max rounds without a final answer
            final_text = "达到最大轮次限制。"
    state = load_analysis_state(session_id, project_name)
    return final_text, state, agent_model_id


def run_golden_manifest(
    manifest_path: Path,
    data_dir: Path,
    output_root: Path,
    *,
    mode: str = "generate",
    baseline_dir: Path | None = None,
    judge_client=None,
    agent_client=None,
) -> Path:
    manifest = load_golden_manifest(manifest_path)
    generated_at = datetime.now(timezone.utc)
    scenario_results: list[dict[str, Any]] = []
    agent_model_id: str | None = None
    for scenario in manifest["scenarios"]:
        missing = [n for n in scenario["required_files"] if not (data_dir / n).is_file()]
        if missing:
            scenario_results.append({"id": scenario["id"], "status": "missing_required_files", "missing_files": missing})
            continue
        if mode == "generate":
            answer_text, state, agent_model_id = drive_agent_for_scenario(scenario, data_dir, client=agent_client)
        else:
            raise GoldenManifestError("evaluate mode requires stored answers; use the CLI evaluator")
        baseline = read_baseline(baseline_dir, scenario["id"]) if baseline_dir else None
        evaluation = evaluate_answer(
            answer_text,
            state,
            scenario["business_question"],
            scenario.get("soft_dimension_focus", []),
            baseline_answer=baseline,
            judge_client=judge_client,
        )
        scenario_results.append(
            {
                "id": scenario["id"],
                "status": "evaluated",
                "question": scenario["business_question"],
                "answer_text": answer_text,
                "evaluation": evaluation,
            }
        )
    if judge_client is not None:
        judge_model_id = getattr(judge_client, "model_id", None)
    else:
        # Lazy import keeps the measurement-only boundary; resolves the same
        # default judge client used downstream by evaluate_answer/_judge.
        from data_agent.agent.quality_judge import _get_judge_client

        judge_model_id = getattr(_get_judge_client(), "model_id", None)
    result = {
        "schema_version": "golden_quality_results.v1",
        "generated_at": generated_at.isoformat(),
        "mode": mode,
        "manifest": str(manifest_path.resolve()),
        "data_dir": str(data_dir.resolve()),
        "run": {
            "mode": mode,
            "model": agent_model_id,
            "judge_model": judge_model_id,
            "baseline_ref": str(baseline_dir.resolve()) if baseline_dir else None,
        },
        "scenarios": scenario_results,
    }
    result_dir = output_root / generated_at.strftime("%Y%m%dT%H%M%S.%fZ")
    result_dir.mkdir(parents=True, exist_ok=False)
    result_path = result_dir / "results.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result_path
