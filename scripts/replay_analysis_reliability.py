#! /usr/bin/env python
"""Phase A systemic replay harness for the analysis-reliability plan (Task 12).

The harness drives the REAL ``AgentLoop`` through the Tasks 6-11 pipeline
(canonical execution envelope, exact step binding, truthful capabilities,
requirement-based completion, automatic evidence projection, tiered
publication, safe progress narration) using a scripted fake LLM. Deterministic
mode is fully offline; live mode delegates to the configured provider.

Used by both ``tests/test_analysis_reliability_replays.py`` (assertions) and
the ``replay_analysis_reliability`` CLI (acceptance JSON).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "src"
_TESTS = ROOT / "tests"
for _candidate in (_SRC, _TESTS):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import pandas as pd  # noqa: E402

from data_agent import config as _config  # noqa: E402
from data_agent.agent.loop import AgentLoop  # noqa: E402
from data_agent.agent.analysis_requirements import (  # noqa: E402
    evaluate_requirement_satisfaction,
)
from data_agent.agent.evidence_contracts import (  # noqa: E402
    analysis_plan_semantic_digest,
    analysis_step_semantic_digest,
)
from data_agent.agent.execution_control import fallback_resolution_tools  # noqa: E402
from data_agent.config import AgentConfig, get_config  # noqa: E402
from data_agent.llm.client import Response, ToolCall  # noqa: E402
from data_agent.session.task_manager import task_manager  # noqa: E402
from data_agent.tools import analysis_flow as _analysis_flow  # noqa: E402,F401
from data_agent.tools import task_tools as _task_tools  # noqa: E402,F401
from tests.fixtures.analysis_reliability import (  # noqa: E402
    build_aggregate_payment_frame,
    build_factor_relationship_frame,
    factor_relationship_prompt,
)
from acceptance.live_provider_gate_contract import (  # noqa: E402
    LIVE_PROVIDER_GATE_VERSION,
    build_live_provider_gate_receipt,
    evaluate_live_provider_run,
    validate_live_provider_gate_receipt,
)
from acceptance.release_source import release_source_digest  # noqa: E402


TERMINAL_STATES = {
    "complete",
    "complete_with_limits",
    "blocked_by_data",
    "blocked_by_tool",
    "budget_limited",
}
_REPLAY_CSV_PLACEHOLDER = "__REPLAY_CSV_PATH__"
_FACTOR_MARKER_TOKEN = "__FACTOR_MEASUREMENT_MARKER__"
LIVE_PROVIDER_PROMPT = (
    "请对上传数据进行完整分析：先检查数据质量，再分析收入和成本的总体分布、"
    "分群差异及二者关系，明确哪些结论只是描述或相关性，并给出行动建议与局限。"
)
_LIVE_REQUIREMENT_GROUPS = (
    "data_quality",
    "descriptive",
    "relationship",
    "limitations",
)
_LIVE_DATA_QUALITY_TOOLS = frozenset(
    {"quick_profile", "detect_data_quality", "assess_readiness"}
)
_LIVE_DESCRIPTIVE_TOOLS = frozenset(
    {
        "quick_profile",
        "describe_dataset",
        "distribution_analysis",
        "segmentation_analysis",
        "top_n",
    }
)
_LIVE_RELATIONSHIP_TOOLS = frozenset(
    {
        "correlation_analysis",
        "factor_relationship_analysis",
        "regression_analysis",
    }
)
_MEASUREMENT_BOOKKEEPING_CODES = frozenset(
    {
        "measurement_identity_missing",
        "measurement_marker_invalid",
        "measurement_not_found",
        "measurement_metric_mismatch",
        "measurement_claim_key_mismatch",
        "measurement_scope_mismatch",
        "measurement_dataset_version_mismatch",
        "measurement_ambiguous",
    }
)

# Canonical analysis checkpoint codes attached to substantive tool
# capabilities. Derived from ``PLAYBOOKS["factor_relationship"].method_plan``;
# each capability maps to the FIRST (primary) step it satisfies so a single
# successful call is enough to demonstrate the checkpoint was reached.
_CAPABILITY_TO_ANALYSIS_CODE: dict[str, str] = {
    "data.profile": "grain_and_missingness_checked",
    "analysis.correlation": "univariate_relationship_checked",
    "analysis.factor_relationship": "multivariable_method_attempted",
    "analysis.regression": "effect_or_contribution_estimated",
    "artifact.evidence_record": "limitations_prepared",
}


@dataclass
class ReplayResult:
    """Observer-facing summary of one replay turn.

    Field union covers every assertion in the four replay tests: the canonical
    analysis trace, terminal completion state, structured evidence, ordered
    progress events, language detection, claimed dimensions, sandbox-recovery
    counters, and the persisted vs. SSE-streamed text.
    """

    turn_completed: bool = False
    final_answer: str = ""
    final_answer_language: str = ""
    completion_state: str = ""
    trace: list[dict[str, object]] = field(default_factory=list)
    progress_events: list[Any] = field(default_factory=list)
    final_answer_sequence: int = 0
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    asserted_dimensions: list[str] = field(default_factory=list)
    serialized_trace: str = ""
    max_identical_failure_attempts: int = 0
    persisted_text: str = ""
    streamed_text: str = ""
    successful_capability_ids: list[str] = field(default_factory=list)
    requirement_statuses: dict[str, str] = field(default_factory=dict)
    published_limitations: list[str] = field(default_factory=list)
    final_audit_status: str = ""
    analysis_requirements: list[dict[str, Any]] = field(default_factory=list)
    current_plan_id: str = ""
    current_plan_digest: str = ""
    current_step_digests: dict[str, str] = field(default_factory=dict)
    current_dataset_versions: list[str] = field(default_factory=list)
    sessions_root: str = ""
    current_session_id: str = ""

    @property
    def browser_text(self) -> str:
        """Deprecated alias; SSE aggregation is not actual-browser evidence."""

        return self.streamed_text


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class _ScriptedLLM:
    """Deterministic fake LLM client used by the replay harness.

    Mirrors the ``chat``/``stream_chat_structured`` shape used by the golden
    scenario harness. When the script runs out of scripted responses, the
    fallback text is returned instead of raising — this keeps the harness
    robust to the loop's single quality-continuation round without forcing
    the test author to count calls exactly.
    """

    def __init__(
        self,
        responses: list[Response],
        *,
        fallback_text: str = "",
        csv_path: Path | None = None,
    ):
        self._responses = list(responses)
        self._fallback_text = fallback_text
        self._csv_path = Path(csv_path) if csv_path is not None else None
        self._state_provider = lambda: None
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    def bind_state_provider(self, provider) -> None:
        self._state_provider = provider

    def chat(self, messages, tools=None, system=None, **kwargs) -> Response:
        self.call_count += 1
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        if self._responses:
            response = copy.deepcopy(self._responses.pop(0))
        else:
            response = Response(text=self._fallback_text)
        for tool_call in response.tool_calls:
            if (
                self._csv_path is not None
                and tool_call.arguments.get("source") == _REPLAY_CSV_PLACEHOLDER
            ):
                tool_call.arguments["source"] = str(self._csv_path)
        if _FACTOR_MARKER_TOKEN in response.text:
            marker = _factor_measurement_marker(self._state_provider())
            response.text = response.text.replace(_FACTOR_MARKER_TOKEN, marker)
        return response

    def stream_chat_structured(self, messages, tools=None, system=None, **kwargs):
        from data_agent.llm.client import StreamComplete

        response = self.chat(messages, tools=tools, system=system)
        yield StreamComplete(response=response)


class _OfflineSemanticClient:
    """Return no semantic override so deterministic replays stay offline."""

    def chat(self, *_args, **_kwargs) -> Response:
        return Response(text="")


def _tool_call(name: str, arguments: dict[str, Any], *, call_id: str | None = None) -> ToolCall:
    payload = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    # Default id is derived from the argument hash, which collides for two
    # identical scripted calls. Callers that intentionally repeat the same
    # call (e.g. to exercise bounded identical-failure counting) must pass a
    # distinct ``call_id`` so each attempt gets its own computation ref.
    tc_id = call_id if call_id else f"tc_{name}_{abs(hash(payload)) % 100000}"
    return ToolCall(
        id=tc_id,
        name=name,
        arguments=arguments,
    )


def _tool_response(*calls: ToolCall) -> Response:
    return Response(text="", tool_calls=list(calls))


def _text_response(text: str) -> Response:
    return Response(text=text)


# ---------------------------------------------------------------------------
# Result derivation (pure helpers, no global state)
# ---------------------------------------------------------------------------


def _detect_language(text: str) -> str:
    """Return ``zh`` if any CJK character is present, else ``en``."""
    if not text:
        return ""
    for ch in text:
        if "一" <= ch <= "鿿":
            return "zh"
    return "en"


def _extract_asserted_dimensions(state) -> list[str]:
    """Return the dimension/metric keywords the agent asserted findings on.

    Pulled from successful substantive computation refs (``target_col`` plus
    feature arguments) and recorded evidence target fields. Dimensions named
    only in limitation or "missing data" text do NOT appear here — those are
    disclosures, not assertions.
    """

    asserted: list[str] = []
    seen: set[str] = set()

    def _push(value: Any) -> None:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            asserted.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _push(item)

    for ref in getattr(state, "computation_refs", []) or []:
        if not isinstance(ref, dict):
            continue
        args = ref.get("arguments") if isinstance(ref.get("arguments"), dict) else {}
        for key in ("target_col", "target", "dimension", "dimensions"):
            _push(args.get(key))
    for record in getattr(state, "evidence_records", []) or []:
        if not isinstance(record, dict):
            continue
        for key in ("dimension", "dimensions", "target", "target_col"):
            _push(record.get(key))
    return asserted


def _build_trace(state) -> tuple[list[dict[str, object]], str, int]:
    """Return ``(trace, completion_state, max_identical_failure_attempts)``.

    The trace is the canonical analysis coverage view: each successful
    substantive capability maps to its primary ``analysis_code``, repeated
    failures are counted per tool, and the terminal completion decision is
    appended last. The order is the order tools were executed.
    """

    trace: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    failure_attempts: dict[str, int] = {}
    max_identical_failures = 0

    for ref in getattr(state, "computation_refs", []) or []:
        if not isinstance(ref, dict):
            continue
        capability_id = str(ref.get("capability_id") or "")
        success = bool(ref.get("success", True))
        tool_name = str(ref.get("tool_name") or capability_id or "unknown")
        code = _CAPABILITY_TO_ANALYSIS_CODE.get(capability_id)
        if code and success and code not in seen_codes:
            trace.append({"code": code})
            seen_codes.add(code)
        if not success:
            attempts = failure_attempts.get(tool_name, 0) + 1
            failure_attempts[tool_name] = attempts
            if attempts > max_identical_failures:
                max_identical_failures = attempts
            trace.append({"same_failure_attempt": attempts})

    completion_state = ""
    for diag in reversed(getattr(state, "turn_diagnostics", []) or []):
        if isinstance(diag, dict) and diag.get("event") == "completion_decision":
            status = str(diag.get("status") or "")
            if status in TERMINAL_STATES:
                completion_state = status
                break
    # Task 8 contractually emits a terminal ``completion_decision`` whenever
    # the turn reaches the claim-tier publication pipeline (Task 10). The
    # previous silent default (``"complete"``) let a regression pass green if
    # Task 8 ever stopped emitting the event on a publication-reaching turn;
    # fail loudly there. When the turn ends under context pressure before
    # synthesis (no ``claim_tier_publication``), there is no completion event
    # to assert — leave the marker empty so the caller's completion-state
    # check surfaces it rather than masking it with a fake "complete".
    reached_publication = any(
        isinstance(d, dict) and d.get("event") == "claim_tier_publication"
        for d in (getattr(state, "turn_diagnostics", []) or [])
    )
    if reached_publication:
        assert completion_state in TERMINAL_STATES, (
            "completion_decision (Task 8) emitted no terminal state despite "
            "the turn reaching claim-tier publication"
        )
    trace.append({"completion_state": completion_state})
    return trace, completion_state, max_identical_failures


def _build_progress_events(state) -> tuple[list[Any], int]:
    """Return ``(progress_events, final_answer_sequence)``.

    ``progress_events`` is a list of ``SimpleNamespace`` objects whose
    ``sequence`` attribute is the diagnostic-list index, so callers can
    verify safe progress narration precedes the audited final publication
    (Task 11 contract). ``final_answer_sequence`` is the diagnostic index
    of the ``claim_tier_publication`` event, or ``-1`` when the turn ended
    before reaching publication (e.g. under context pressure); callers that
    contractually require publication must assert ``final_answer_sequence >= 0``.
    """

    diags = list(getattr(state, "turn_diagnostics", []) or [])
    progress_events: list[Any] = []
    final_answer_sequence = -1
    for idx, diag in enumerate(diags):
        if not isinstance(diag, dict):
            continue
        if diag.get("kind") == "analysis_progress":
            progress_events.append(SimpleNamespace(sequence=idx, **diag))
        if diag.get("event") in {"claim_tier_publication"}:
            final_answer_sequence = idx
    # Task 11 contractually emits safe progress narration for any turn that
    # runs substantive analysis tools (capability-bound computation refs).
    # Boundary-only replays (e.g. the unicode process test) intentionally
    # skip analysis tools, so no progress event is expected there. The
    # previous silent placeholder (``sequence=0``) let a regression pass green
    # if Task 11 ever stopped emitting progress for real analysis turns; fail
    # loudly instead.
    substantive_ran = any(
        isinstance(ref, dict) and ref.get("capability_id")
        for ref in (getattr(state, "computation_refs", []) or [])
    )
    if not progress_events:
        assert not substantive_ran, (
            "Task 11 safe progress narration emitted no analysis_progress event "
            "despite substantive analysis tools running"
        )
        return progress_events, max(final_answer_sequence, 0)
    # Progress events are present. When the turn also reached claim-tier
    # publication (Task 10), assert the Task 11 ordering contract: the final
    # answer must come after safe progress narration. The previous clamp
    # silently forced a compliant order; fail loudly instead. When the turn
    # ends under context pressure before synthesis (no publication event),
    # there is no final-answer sequence to order against — return the real
    # (-1) value so callers that require publication fail explicitly rather
    # than reading a clamped placeholder.
    if final_answer_sequence >= 0:
        first_progress_sequence = int(progress_events[0].sequence)
        assert final_answer_sequence > first_progress_sequence, (
            "final answer must be published after safe progress narration (Task 11)"
        )
    return progress_events, final_answer_sequence


def _serialized_trace(state, loop) -> str:
    # Include the raw tool-result message content so structured sandbox
    # errors (``error_type`` tokens like ``dataset_not_found`` /
    # ``sandbox_import_not_allowed``) are observable, not just the normalized
    # ``error_category`` recorded in ``_turn_tool_outcomes``.
    tool_results: list[dict[str, str]] = []
    for msg in getattr(loop, "messages", []) or []:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        tool_results.append({
            "tool_call_id": str(msg.get("tool_call_id") or ""),
            "content": str(msg.get("content") or ""),
        })
    payload = {
        "turn_diagnostics": list(getattr(state, "turn_diagnostics", []) or []),
        "computation_refs": list(getattr(state, "computation_refs", []) or []),
        "evidence_records": list(getattr(state, "evidence_records", []) or []),
        "tools_used": list(getattr(loop, "_turn_tools_used", []) or []),
        "tool_outcomes": list(getattr(loop, "_turn_tool_outcomes", []) or []),
        "tool_results": tool_results,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _last_assistant_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content:
            return content
    return ""


def _successful_capability_ids(state) -> list[str]:
    return list(dict.fromkeys(
        str(ref.get("capability_id") or "")
        for ref in getattr(state, "computation_refs", []) or []
        if isinstance(ref, dict)
        and bool(ref.get("success"))
        and str(ref.get("capability_id") or "")
    ))


def _latest_final_audit_status(state) -> str:
    for report in reversed(getattr(state, "verification_reports", []) or []):
        if (
            isinstance(report, dict)
            and report.get("contract_version") == "final_answer_audit.v1"
        ):
            return str(report.get("status") or "")
    return ""


def _current_requirements(state) -> list[dict[str, Any]]:
    plan = getattr(state, "analysis_plan", None)
    grouped = plan.get("analysis_requirements") if isinstance(plan, dict) else None
    if not isinstance(grouped, dict):
        return []
    return [
        requirement
        for group in grouped.values()
        if isinstance(group, list)
        for requirement in group
        if isinstance(requirement, dict)
    ]


def _extract_published_limitations(text: str) -> list[str]:
    match = re.search(
        r"(?:局限|限制|limitations?)\s*[：:]\s*(.+?)(?=(?:建议|下一步)\s*[：:]|$)",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    return [
        item.strip(" \n\t。.")
        for item in re.split(r"[、；;。]\s*", match.group(1))
        if item.strip(" \n\t。.")
    ]


def _requirement_statuses(
    state,
    *,
    evidence_records: list[dict[str, Any]],
    published_limitations: list[str],
) -> dict[str, str]:
    limitation_text = " ".join(published_limitations).casefold()

    def _has_matching_limitation(requirement: dict[str, Any]) -> bool:
        candidates = {
            token
            for value in (
                str(requirement.get("name") or "").replace("_", " "),
                str(requirement.get("reason") or ""),
            )
            for token in re.findall(r"[\w\u4e00-\u9fff]+", value.casefold())
            if len(token) >= 4
        }
        return any(token in limitation_text for token in candidates)

    requirements = _current_requirements(state)
    evaluated = evaluate_requirement_satisfaction(requirements, evidence_records)
    statuses: dict[str, str] = {}
    for requirement in evaluated:
        name = str(requirement.get("name") or "")
        if not name:
            continue
        status = str(requirement.get("status") or "unmet")
        if status == "satisfied":
            statuses[name] = "satisfied"
            continue
        if statuses.get(name) == "satisfied":
            continue
        unmet_action = str(requirement.get("unmet_action") or "")
        if (
            status == "unmet"
            and unmet_action in {"downgrade_claim", "disclose"}
            and _has_matching_limitation(requirement)
        ):
            statuses[name] = "limited"
        else:
            statuses.setdefault(name, status)
    return statuses


def _factor_measurement_marker(state) -> str:
    records = list(getattr(state, "evidence_records", []) or [])
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        for measurement in record.get("measurements") or []:
            if not isinstance(measurement, dict):
                continue
            identity = measurement.get("identity")
            if not isinstance(identity, dict):
                continue
            label = str(identity.get("metric_label") or "")
            metric_key = str(identity.get("metric_key") or "")
            if "活跃度" not in label or not metric_key.startswith(
                "coefficients.estimate"
            ):
                continue
            measurement_key = str(identity.get("measurement_key") or "")
            evidence_id = str(record.get("id") or "")
            if evidence_id and measurement_key:
                return f"[[evidence:{evidence_id}#{measurement_key}]]"
    raise AssertionError(
        "factor replay reached synthesis without a projected factor measurement"
    )


# ---------------------------------------------------------------------------
# Config / workspace isolation
# ---------------------------------------------------------------------------


@contextmanager
def _test_config(tmp_path: Path, session_id: str) -> Iterator[None]:
    """Point the global config + task_manager at isolated tmp directories."""

    from data_agent.agent import llm_intent, llm_playbook

    old_cfg = _config._config
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    old_intent_client = llm_intent._client
    old_playbook_client = llm_playbook._client

    _config._config = AgentConfig(
        PROJECT_DIR=tmp_path / session_id / "project",
        SESSIONS_DIR=tmp_path / session_id / "sessions",
    )
    task_manager._dir = tmp_path / session_id / "tasks"
    task_manager._next_id_val = 0
    llm_intent._client = _OfflineSemanticClient()
    llm_playbook._client = _OfflineSemanticClient()
    try:
        yield
    finally:
        _config._config = old_cfg
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
        llm_intent._client = old_intent_client
        llm_playbook._client = old_playbook_client


@contextmanager
def _noninteractive_stdin() -> Iterator[None]:
    """Replace stdin with an empty stream so confirmation prompts auto-cancel.

    The method_confirmation prompt the playbook creates is interactive under
    a real terminal (``prompt_toolkit`` reads from ``/dev/tty``). Under
    pytest stdin is already captured and EOFs immediately, so the prompt
    self-cancels and the loop continues. The CLI runner needs the same
    behavior: swap stdin for an empty ``StringIO`` so ``input()`` raises
    ``EOFError`` and the loop's CLI suspension handler returns ``cancelled``
    instead of blocking forever. The publication pipeline is unaffected.
    """

    saved_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO("")
        yield
    finally:
        sys.stdin = saved_stdin


@contextmanager
def _console_encoding(encoding: str) -> Iterator[None]:
    """Force the console streams to a specific encoding for the unicode replay.

    Wraps ``sys.stdout``/``sys.stderr`` in ``TextIOWrapper`` over a bytes
    buffer using the requested encoding. The unicode-safe process boundary
    (Task 4) keeps the loop turn alive even when the console cannot encode
    characters outside the codepage (e.g. ``⚠️`` under ``cp936``).
    """

    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    try:
        out_buffer = io.BytesIO()
        err_buffer = io.BytesIO()
        sys.stdout = io.TextIOWrapper(out_buffer, encoding=encoding, errors="strict")
        sys.stderr = io.TextIOWrapper(err_buffer, encoding=encoding, errors="strict")
        yield
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr


# ---------------------------------------------------------------------------
# Core replay driver
# ---------------------------------------------------------------------------


def _drive_replay(
    *,
    csv_path: Path,
    prompt: str,
    responses: list[Response],
    fallback_text: str,
    session_id: str,
    project_name: str,
    tmp_path: Path,
    streaming: bool = False,
) -> tuple[AgentLoop, str, str, str]:
    """Return ``(loop, final_text, persisted_text, streamed_text)``."""

    client = _ScriptedLLM(
        responses,
        fallback_text=fallback_text,
        csv_path=csv_path,
    )
    loop = AgentLoop(client=client, session_id=session_id, project_name=project_name)
    client.bind_state_provider(lambda: loop.context.analysis_state)
    # The replay exercises the routing/binding/completion/publication
    # pipeline, not prompt-template rendering. Empty system prompt keeps the
    # fake-LLM harness deterministic without pulling in optional heavy
    # modules that are irrelevant to the reliability contracts under test.
    loop._get_system_prompt = lambda: ""  # type: ignore[assignment]
    production_bind = loop._bind_tool_call

    def _bind_replay_step(tool_call):
        if tool_call.name != "factor_relationship_analysis":
            return production_bind(tool_call)
        from data_agent.agent.analysis_execution import bind_tool_call_to_plan_step
        from data_agent.tools.registry import registry

        state = getattr(loop.context, "analysis_state", None)
        plan = getattr(state, "analysis_plan", None)
        return bind_tool_call_to_plan_step(
            plan=plan if isinstance(plan, dict) else {},
            tool_name=tool_call.name,
            capability=registry.capability_for(tool_call.name),
            dataset_names=[str(tool_call.arguments.get("name") or "")],
            preferred_step_id="step_3",
        )

    loop._bind_tool_call = _bind_replay_step  # type: ignore[assignment]

    # Swap stdin for an empty stream so the loop's CLI confirmation handler
    # auto-cancels the method-confirmation prompt instead of blocking on a
    # real terminal. No-op under pytest where stdin is already captured.
    with _noninteractive_stdin():
        if streaming:
            events = list(loop.stream_turn(prompt))
            streamed_text = "".join(
                str(ev.get("text") or "")
                for ev in events
                if isinstance(ev, dict) and ev.get("type") == "text_delta"
            )
            final_text = streamed_text or _last_assistant_text(loop.messages)
        else:
            final_text = loop.run_turn(prompt) or ""
            streamed_text = final_text or _last_assistant_text(loop.messages)

    persisted_text = _last_assistant_text(loop.messages) or final_text
    return loop, final_text, persisted_text, streamed_text


def _finalize_result(
    *,
    loop: AgentLoop,
    final_text: str,
    persisted_text: str,
    streamed_text: str,
) -> ReplayResult:
    state = getattr(loop.context, "analysis_state", None)
    if state is None:
        return ReplayResult(
            turn_completed=bool(final_text),
            final_answer=final_text,
            final_answer_language=_detect_language(final_text),
            persisted_text=persisted_text,
            streamed_text=streamed_text,
        )
    trace, completion_state, max_identical_failures = _build_trace(state)
    progress_events, final_answer_sequence = _build_progress_events(state)
    evidence_records = list(getattr(state, "evidence_records", []) or [])
    published_limitations = _extract_published_limitations(final_text)
    plan = getattr(state, "analysis_plan", None)
    plan = plan if isinstance(plan, dict) else {}
    method_plan = plan.get("method_plan")
    method_plan = method_plan if isinstance(method_plan, list) else []
    dataset_versions = sorted({
        str(version)
        for record in evidence_records
        if isinstance(record, dict)
        for version in record.get("dataset_versions") or []
        if str(version)
    })
    artifact_paths = [
        Path(str(ref.get("artifact_path")))
        for record in evidence_records
        if isinstance(record, dict)
        for ref in record.get("computation_refs") or []
        if isinstance(ref, dict) and str(ref.get("artifact_path") or "")
    ]
    sessions_root = str(artifact_paths[0].parents[2]) if artifact_paths else ""
    return ReplayResult(
        turn_completed=bool(final_text),
        final_answer=final_text,
        final_answer_language=_detect_language(final_text),
        completion_state=completion_state,
        trace=trace,
        progress_events=progress_events,
        final_answer_sequence=final_answer_sequence,
        evidence_records=evidence_records,
        asserted_dimensions=_extract_asserted_dimensions(state),
        serialized_trace=_serialized_trace(state, loop),
        max_identical_failure_attempts=max_identical_failures,
        persisted_text=persisted_text,
        streamed_text=streamed_text,
        successful_capability_ids=_successful_capability_ids(state),
        requirement_statuses=_requirement_statuses(
            state,
            evidence_records=evidence_records,
            published_limitations=published_limitations,
        ),
        published_limitations=published_limitations,
        final_audit_status=_latest_final_audit_status(state),
        analysis_requirements=_current_requirements(state),
        current_plan_id=str(plan.get("id") or ""),
        current_plan_digest=(
            analysis_plan_semantic_digest(plan) if plan else ""
        ),
        current_step_digests={
            str(step.get("step_id") or ""): analysis_step_semantic_digest(step)
            for step in method_plan
            if isinstance(step, dict) and str(step.get("step_id") or "")
        },
        current_dataset_versions=dataset_versions,
        sessions_root=sessions_root,
        current_session_id=str(getattr(state, "session_id", "") or ""),
    )


# ---------------------------------------------------------------------------
# Public scenario builders
# ---------------------------------------------------------------------------


_FACTOR_FINAL_TEXT = (
    "活跃度 estimate 为 5.399135 "
    f"{_FACTOR_MARKER_TOKEN}。"
    "局限：样本量有限、关联不等于因果、缺失特征样本被剔除。"
)

_AGGREGATE_FINAL_TEXT = (
    "数据为按日聚合的订单数与收入指标，缺少用户级字段（例如用户ID），"
    "无法做用户画像/复购分析。需要用户级字段才能继续此类分析。"
    "当前数据仅支持按日的订单与收入分布描述。"
)

_SANDBOX_FINAL_TEXT = (
    "沙箱执行完成：预加载导入（pandas/numpy/scipy.stats）正常解析，"
    "缺失数据集返回结构化错误而非 None 级联。建议下一步记录证据。"
)

_UNICODE_FINAL_TEXT = (
    "⚠️ 数据加载与描述完成。建议进入多变量分析阶段并记录证据。"
)


def _write_factor_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "factor_frame.csv"
    build_factor_relationship_frame().to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


def _write_aggregate_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "aggregate_frame.csv"
    build_aggregate_payment_frame().to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


def _factor_responses(csv_path: Path) -> list[Response]:
    return [
        _tool_response(
            _tool_call("load_data", {"source": str(csv_path), "name": "factor_data"})
        ),
        _tool_response(_tool_call("quick_profile", {"name": "factor_data"})),
        _tool_response(
            _tool_call(
                "correlation_analysis",
                {"name": "factor_data", "columns": "目标值,活跃度,价格"},
            )
        ),
        _tool_response(
            _tool_call(
                "factor_relationship_analysis",
                {"name": "factor_data", "target_col": "目标值"},
            )
        ),
        _text_response(_FACTOR_FINAL_TEXT),
    ]


_DIMENSION_OPPORTUNITY_PROMPT = (
    "为什么目标值下降？请按渠道做贡献分解，并给出仅供验证的探索性机会候选。"
)

_DIMENSION_OPPORTUNITY_FINAL_TEXT = (
    "The channel contributions are descriptive observations. Any opportunity "
    "candidate is an exploratory hypothesis for validation, not a causal claim."
)


def _dimension_opportunity_responses(
    csv_path: Path,
    *,
    include_decomposition: bool = True,
) -> list[Response]:
    responses = [
        _tool_response(
            _tool_call(
                "load_data",
                {"source": str(csv_path), "name": "opportunity_data"},
            )
        ),
        _tool_response(
            _tool_call(
                "compare_periods",
                {
                    "name": "opportunity_data",
                    "date_col": "日期",
                    "metrics": "目标值",
                    "period_a": "2026-01-01~2026-01-16",
                    "period_b": "2026-01-17~2026-02-01",
                    "dimensions": "渠道",
                    "agg_func": "sum",
                },
            )
        ),
    ]
    if include_decomposition:
        responses.append(
            _tool_response(
                _tool_call(
                    "contribute_decomposition",
                    {
                        "name": "opportunity_data",
                        "metric": "目标值",
                        "dimension": "渠道",
                        "date_col": "日期",
                        "period_a": "2026-01-01~2026-01-16",
                        "period_b": "2026-01-17~2026-02-01",
                        "agg_func": "sum",
                    },
                )
            )
        )
    responses.append(_text_response(_DIMENSION_OPPORTUNITY_FINAL_TEXT))
    return responses


def _superficial_profile_only_responses(*, repetitions: int) -> list[Response]:
    return [
        _tool_response(
            _tool_call(
                "load_data",
                {"source": _REPLAY_CSV_PLACEHOLDER, "name": "factor_data"},
            )
        ),
        *[
            _tool_response(
                _tool_call(
                    "quick_profile",
                    {"name": "factor_data"},
                    call_id=f"tc_quick_profile_superficial_{index}",
                )
            )
            for index in range(repetitions)
        ],
    ]


def _aggregate_responses(csv_path: Path) -> list[Response]:
    return [
        _tool_response(
            _tool_call("load_data", {"source": str(csv_path), "name": "aggregate_data"})
        ),
        _tool_response(_tool_call("quick_profile", {"name": "aggregate_data"})),
        _text_response(_AGGREGATE_FINAL_TEXT),
    ]


def _sandbox_responses(csv_path: Path) -> list[Response]:
    """Script the sandbox-heavy turn so the failure path is GENUINELY exercised.

    The loop's ``pending_fallback_resolution`` contract (Task 3) requires a
    fallback-resolution tool (e.g. ``record_evidence_record``) between
    successive ``run_python`` calls; without it the 2nd/3rd ``run_python`` are
    blocked at ``execution_control.py:305`` and the cascade-prevention
    assertions become vacuously true. Interleaving evidence records keeps
    every scripted ``run_python`` inside budget so:

    * the preloaded-import call proves allowlist imports resolve (no
      ``__import__`` cascade);
    * the missing-dataset call returns a STRUCTURED ``dataset_not_found`` error
      (not an opaque ``NoneType`` cascade);
    * the IDENTICAL missing-dataset retry exercises bounded identical-failure
      counting (``max_identical_failure_attempts`` lands at 2).
    """

    exploratory_evidence = {
        "claim": "沙箱预加载导入在受限环境中可用",
        "dataset": "sandbox_data",
        "method": "受限沙箱 run_python，调用预加载的 pandas/numpy 模块",
        "tool_calls": ["run_python"],
        "result_summary": "pandas/numpy 经预加载绑定后正常执行，未触发不透明导入级联",
        "limitations": ["仅覆盖预加载冒烟路径"],
        "confidence": "high",
    }
    missing_dataset_evidence = {
        "claim": "缺失数据集返回结构化错误而非空值级联",
        "dataset": "sandbox_data",
        "method": "沙箱 get_dataset 调用不存在的数据集",
        "tool_calls": ["run_python"],
        "result_summary": "缺失数据集触发 dataset_not_found 结构化错误，错误以结构化 payload 返回",
        "limitations": ["目标数据集不存在"],
        "confidence": "high",
    }
    missing_dataset_code = (
        "df = get_dataset('nonexistent')\n"
        "result = str(df.shape)"
    )
    return [
        _tool_response(
            _tool_call("load_data", {"source": str(csv_path), "name": "sandbox_data"})
        ),
        _tool_response(
            _tool_call(
                "run_python",
                {
                    "code": (
                        "import pandas as pd\n"
                        "import numpy as np\n"
                        "result = pd.DataFrame({'x': [1, 2, 3]}).describe().to_json()"
                    )
                },
            )
        ),
        _tool_response(
            _tool_call(
                "record_evidence_record",
                {"record_json": json.dumps(exploratory_evidence, ensure_ascii=False)},
            )
        ),
        _tool_response(
            _tool_call("run_python", {"code": missing_dataset_code}, call_id="tc_run_python_missing_first")
        ),
        _tool_response(
            _tool_call(
                "record_evidence_record",
                {"record_json": json.dumps(missing_dataset_evidence, ensure_ascii=False)},
            )
        ),
        _tool_response(
            _tool_call("run_python", {"code": missing_dataset_code}, call_id="tc_run_python_missing_retry")
        ),
        _text_response(_SANDBOX_FINAL_TEXT),
    ]


def _unicode_responses(csv_path: Path) -> list[Response]:
    return [
        _tool_response(
            _tool_call("load_data", {"source": str(csv_path), "name": "unicode_data"})
        ),
        _text_response(_UNICODE_FINAL_TEXT),
    ]


# ---------------------------------------------------------------------------
# Public replay entry points (consumed by tests + CLI)
# ---------------------------------------------------------------------------


def run_deterministic_replay(
    *,
    frame: pd.DataFrame,
    prompt: str,
    root: Path,
    responses: list[Response] | None = None,
    fallback_text: str = "",
    session_id: str = "factor_replay",
    project_name: str = "factor_replay",
    dataset_name: str = "factor_data",
    streaming: bool = False,
) -> ReplayResult:
    """Drive the real AgentLoop against ``frame`` + ``prompt`` and observe it.

    When ``responses`` is omitted, a default factor-analysis script is built
    that exercises the full Tasks 6-11 pipeline (load → profile → correlation
    → factor_relationship_analysis → automatic evidence projection → synthesis).
    """

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / f"{dataset_name}.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    if responses is None:
        responses = _factor_responses(csv_path)
    if not fallback_text:
        fallback_text = _FACTOR_FINAL_TEXT

    with _test_config(root, session_id):
        loop, final_text, persisted, streamed = _drive_replay(
            csv_path=csv_path,
            prompt=prompt,
            responses=responses,
            fallback_text=fallback_text,
            session_id=session_id,
            project_name=project_name,
            tmp_path=root,
            streaming=streaming,
        )
    return _finalize_result(
        loop=loop,
        final_text=final_text,
        persisted_text=persisted,
        streamed_text=streamed,
    )


def run_sandbox_replay(root: Path) -> ReplayResult:
    """Exercise sandbox-heavy run_python calls and verify no cascade failure."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    csv_path = _write_factor_csv(root)
    responses = _sandbox_responses(csv_path)
    with _test_config(root, "sandbox_replay"):
        loop, final_text, persisted, streamed = _drive_replay(
            csv_path=csv_path,
            prompt="请用 python 检查数据基本特征并尝试稳健性诊断",
            responses=responses,
            fallback_text=_SANDBOX_FINAL_TEXT,
            session_id="sandbox_replay",
            project_name="sandbox_replay",
            tmp_path=root,
        )
    return _finalize_result(
        loop=loop,
        final_text=final_text,
        persisted_text=persisted,
        streamed_text=streamed,
    )


def run_unicode_replay(root: Path, *, console_encoding: str = "cp936") -> ReplayResult:
    """Drive a streaming replay under a constrained console encoding.

    Verifies the unicode-safe boundary (Task 4) keeps ``⚠️`` intact in both
    the persisted assistant message and SSE-streamed text, even when
    the console is captured under ``cp936``.
    """

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    csv_path = _write_factor_csv(root)
    responses = _unicode_responses(csv_path)
    with _test_config(root, "unicode_replay"), _console_encoding(console_encoding):
        loop, final_text, persisted, streamed = _drive_replay(
            csv_path=csv_path,
            prompt="请分析哪些影响因素与目标值存在显著关系，并说明方法、稳定性和局限。",
            responses=responses,
            fallback_text=_UNICODE_FINAL_TEXT,
            session_id="unicode_replay",
            project_name="unicode_replay",
            tmp_path=root,
            streaming=True,
        )
    return _finalize_result(
        loop=loop,
        final_text=final_text,
        persisted_text=persisted,
        streamed_text=streamed,
    )


# ---------------------------------------------------------------------------
# Real-provider release gate
# ---------------------------------------------------------------------------


class ProviderConfigurationUnavailable(RuntimeError):
    """The configured provider cannot be attempted without user configuration."""


class _ObservedLiveClient:
    """Record provider exceptions that ``AgentLoop`` intentionally contains."""

    def __init__(self):
        from data_agent.llm.client import LLMClient

        self._client = LLMClient()
        self.errors: list[BaseException] = []

    def chat(self, *args, **kwargs):
        try:
            return self._client.chat(*args, **kwargs)
        except BaseException as exc:
            self.errors.append(exc)
            raise

    def stream_chat_structured(self, *args, **kwargs):
        try:
            yield from self._client.stream_chat_structured(*args, **kwargs)
        except BaseException as exc:
            self.errors.append(exc)
            raise


def _current_git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _write_live_provider_csv(root: Path, run_index: int) -> Path:
    """Create a fixed, privacy-safe factor dataset with known quality defects."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    segments = ("新客", "常客", "高价值")
    channels = ("网站", "门店", "合作渠道")
    rows: list[dict[str, Any]] = []
    for index in range(120):
        segment = segments[index % len(segments)]
        channel = channels[(index // 2) % len(channels)]
        orders = 1 + index % 8
        segment_effect = {"新客": 40, "常客": 125, "高价值": 260}[segment]
        channel_effect = {"网站": 25, "门店": 70, "合作渠道": 110}[channel]
        noise = ((index * 17 + run_index * 11) % 37) - 18
        cost = 65 + orders * 31 + (index % 5) * 8
        revenue = round(cost * 1.42 + segment_effect + channel_effect + noise, 2)
        rows.append(
            {
                "customer_id": f"C{index + 1:03d}",
                "segment": segment,
                "channel": channel,
                "orders": orders,
                "revenue": revenue,
                "cost": float(cost),
                "returned": int(index % 13 == 0),
            }
        )
    for missing_index in (11, 47, 83):
        rows[missing_index]["revenue"] = None
    for missing_index in (29, 91):
        rows[missing_index]["cost"] = None
    rows.extend(copy.deepcopy(rows[index]) for index in range(5))
    path = root / "live_provider_fixture.csv"
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


@contextmanager
def _live_run_config(root: Path, session_id: str) -> Iterator[AgentConfig]:
    """Isolate persistence while preserving the exact configured provider."""

    from data_agent.agent import llm_intent, llm_playbook

    configured = get_config()
    old_cfg = _config._config
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    old_intent_client = llm_intent._client
    old_playbook_client = llm_playbook._client
    isolated = AgentConfig(
        MODEL_ID=configured.model_id,
        API_BASE=configured.api_base,
        API_KEY=configured.api_key,
        MAX_TOKENS=configured.max_tokens,
        QUALITY_JUDGE_MODEL=configured.quality_judge_model,
        PROJECT_DIR=Path(root) / "workspace",
        SESSIONS_DIR=Path(root) / "sessions",
        SIGNIFICANCE_LEVEL=configured.significance_level,
        TOKEN_THRESHOLD=configured.token_threshold,
        LOG_LEVEL=configured.log_level,
        MCP_ENABLED=False,
        SKILL_AUTO_DISCOVER=False,
        ASSURANCE_PUBLICATION_MODE=configured.assurance_publication_mode,
        MEASUREMENT_EVIDENCE_BINDING_MODE=(
            configured.measurement_evidence_binding_mode
        ),
        AUTO_EVIDENCE_PROJECTION_ENABLED=(
            configured.auto_evidence_projection_enabled
        ),
        ANALYSIS_LIVE_PROGRESS_ENABLED=configured.analysis_live_progress_enabled,
    )
    _config._config = isolated
    task_manager._dir = Path(root) / "tasks"
    task_manager._next_id_val = 0
    # These clients cache provider settings. Rebuild them inside the isolated
    # configuration rather than reusing a client from a previous test/session.
    llm_intent._client = None
    llm_playbook._client = None
    try:
        yield isolated
    finally:
        _config._config = old_cfg
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
        llm_intent._client = old_intent_client
        llm_playbook._client = old_playbook_client


def _provider_error_category(exc: BaseException) -> str:
    name = type(exc).__name__.casefold()
    message = str(exc).casefold()
    if (
        "authentication" in name
        or "permission" in name
        or any(
            token in message
            for token in (
                "api key",
                "api_key",
                "authentication",
                "credential",
                "missing key",
                "key is required",
            )
        )
    ):
        return "provider_credentials_unavailable"
    if "ratelimit" in name or "rate limit" in message or "429" in message:
        return "provider_rate_limit"
    if "timeout" in name or "timed out" in message:
        return "provider_timeout"
    if any(token in name for token in ("connection", "serviceunavailable")):
        return "provider_network_error"
    if any(token in message for token in ("connection refused", "connection error")):
        return "provider_network_error"
    return "provider_response_error"


def _latest_final_audit(state: Any) -> dict[str, Any]:
    for report in reversed(getattr(state, "verification_reports", []) or []):
        if (
            isinstance(report, dict)
            and report.get("contract_version") == "final_answer_audit.v1"
        ):
            if isinstance(report.get("claims"), list) and isinstance(
                report.get("claim_checks"), list
            ):
                return report
            from data_agent.agent.trust_workflow_runtime import (
                hydrate_final_answer_audit_ref,
            )

            hydrated = hydrate_final_answer_audit_ref(report)
            if isinstance(hydrated, dict):
                return hydrated
            return report
    return {}


def _latest_publication_actions(state: Any) -> dict[str, str]:
    for diagnostic in reversed(getattr(state, "turn_diagnostics", []) or []):
        if (
            isinstance(diagnostic, dict)
            and diagnostic.get("event") == "claim_tier_publication"
        ):
            actions = diagnostic.get("actions")
            if isinstance(actions, dict):
                return {
                    str(key): str(value)
                    for key, value in actions.items()
                    if str(key) and str(value)
                }
    return {}


def _material_publication_actions(
    audit: Any,
    publication_actions: Any,
) -> dict[str, str]:
    """Retain only actions for claims the audit declares material."""

    claims = audit.get("claims") if isinstance(audit, dict) else None
    actions = publication_actions if isinstance(publication_actions, dict) else {}
    material_claim_ids = {
        str(claim.get("id") or "")
        for claim in claims or []
        if isinstance(claim, dict)
        and claim.get("material") is True
        and str(claim.get("id") or "")
    }
    return {
        str(claim_id): str(action)
        for claim_id, action in actions.items()
        if str(claim_id) in material_claim_ids
    }


def _verified_material_claim_count(
    audit: Any,
    publication_actions: Any,
) -> int:
    """Count only audit-declared material claims published as verified."""

    return sum(
        action == "verified"
        for action in _material_publication_actions(
            audit,
            publication_actions,
        ).values()
    )


def _choose_live_confirmation_answer(event: dict[str, Any]) -> Any:
    options = event.get("options") if isinstance(event.get("options"), list) else []
    normalized: list[tuple[str, str]] = []
    for option in options:
        if isinstance(option, dict):
            value = str(option.get("value") or option.get("label") or "").strip()
            label = str(option.get("label") or value).strip()
        else:
            value = label = str(option or "").strip()
        if value:
            normalized.append((value, label))
    preferred = ("approve", "continue", "confirm", "继续", "确认", "批准", "同意")
    chosen = next(
        (
            value
            for value, label in normalized
            if any(token in f"{value} {label}".casefold() for token in preferred)
        ),
        normalized[0][0] if normalized else "继续",
    )
    return [chosen] if event.get("multi_select") else chosen


def _strip_publication_markers(text: str) -> str:
    from data_agent.agent.answer_quality import strip_internal_evidence_markers

    return strip_internal_evidence_markers(text or "").strip()


def _session_tool_outcomes(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstruct all tool outcomes across initial and resumed stream segments."""

    tool_calls: dict[str, tuple[str, str]] = {}
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            function = function if isinstance(function, dict) else {}
            call_id = str(tool_call.get("id") or "")
            if call_id:
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        canonical_arguments = json.loads(arguments)
                    except (TypeError, json.JSONDecodeError):
                        canonical_arguments = {"raw": arguments}
                elif isinstance(arguments, dict):
                    canonical_arguments = arguments
                elif arguments is None:
                    canonical_arguments = {}
                else:
                    canonical_arguments = {"raw": str(arguments or "")}
                raw = json.dumps(
                    canonical_arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                arguments_hash = hashlib.sha1(
                    raw.encode("utf-8")
                ).hexdigest()[:12]
                tool_calls[call_id] = (
                    str(function.get("name") or ""),
                    arguments_hash,
                )

    outcomes: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        content = str(message.get("content") or "")
        stripped = content.lstrip()
        payload_text = stripped.split(" [detail:", 1)[0]
        try:
            payload = json.loads(payload_text)
        except (TypeError, json.JSONDecodeError):
            payload = None
        is_error = (
            isinstance(payload, dict) and "error" in payload
        ) or stripped.casefold().startswith("error")
        error_type = (
            str(payload.get("error_type") or "tool_error")
            if isinstance(payload, dict) and is_error
            else ""
        )
        tool_name, arguments_hash = tool_calls.get(
            str(message.get("tool_call_id") or ""),
            ("", ""),
        )
        outcomes.append(
            {
                "tool_name": tool_name,
                "success": not is_error,
                "error_category": error_type,
                "arguments_hash": arguments_hash,
                "fallback_resolution_blocked": is_error and (
                    "Fallback Python result must be resolved into evidence, "
                    "limitations, task state, or user confirmation before more "
                    "exploration."
                ) in content,
            }
        )
    return outcomes


def _repeated_failure_max(outcomes: list[dict[str, Any]]) -> int:
    failures: dict[tuple[str, str, str], int] = {}
    for outcome in outcomes:
        if not isinstance(outcome, dict) or outcome.get("success"):
            continue
        key = (
            str(outcome.get("tool_name") or ""),
            str(outcome.get("error_category") or "tool_error"),
            str(outcome.get("arguments_hash") or ""),
        )
        failures[key] = failures.get(key, 0) + 1
    return max(failures.values(), default=0)


def _unresolved_fallback_blocked_calls(outcomes: list[dict[str, Any]]) -> int:
    """Count only fallback blocks that were not later resolved successfully.

    A blocked exploratory call is a recoverable control event, not itself a
    cascade.  The execution controller keeps the fallback pending until one of
    its canonical resolution actions succeeds; mirror that state transition so
    Gate F does not report a recovered block as an unresolved failure.
    """

    unresolved = 0
    resolution_tools = fallback_resolution_tools()
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        if outcome.get("fallback_resolution_blocked"):
            unresolved += 1
            continue
        if (
            outcome.get("success")
            and str(outcome.get("tool_name") or "") in resolution_tools
        ):
            unresolved = 0
    return unresolved


def _run_one_live_provider_analysis(root: Path, run_index: int) -> dict[str, Any]:
    """Run one fresh real-provider session and return bounded observables only."""

    root = Path(root)
    session_id = f"live_provider_{run_index}_{uuid.uuid4().hex[:8]}"
    csv_path = _write_live_provider_csv(root, run_index)
    client: _ObservedLiveClient | None = None
    try:
        with _live_run_config(root, session_id) as cfg:
            inbox_path = cfg.inbox_dir / csv_path.name
            shutil.copyfile(csv_path, inbox_path)
            client = _ObservedLiveClient()
            loop = AgentLoop(
                client=client,
                session_id=session_id,
                project_name=f"live_provider_gate_{run_index}",
            )
            prompt = f"{LIVE_PROVIDER_PROMPT}\n分析文件: {csv_path.name}"
            events: list[dict[str, Any]] = []
            generator = loop.stream_turn(prompt)
            for resume_index in range(4):
                batch = [event for event in generator if isinstance(event, dict)]
                events.extend(batch)
                suspended = next(
                    (event for event in reversed(batch) if event.get("type") == "suspended"),
                    None,
                )
                if suspended is None:
                    break
                answer = _choose_live_confirmation_answer(suspended)
                generator = loop.resume_turn_streaming(
                    str(
                        suspended.get("confirmation_id")
                        or suspended.get("suspension_id")
                        or ""
                    ),
                    answer,
                    expected_version=int(suspended.get("version") or 1),
                    idempotency_key=(
                        f"live-gate-{run_index}-{resume_index}-{uuid.uuid4().hex}"
                    ),
                )
            loop._auto_save()

            provider_error = client.errors[-1] if client.errors else None
            text_indexes = [
                index
                for index, event in enumerate(events)
                if event.get("type") == "text_delta" and str(event.get("text") or "")
            ]
            audit_progress_indexes = [
                index
                for index, event in enumerate(events)
                if event.get("type") == "analysis_progress"
                and event.get("code") == "audit_started"
            ]
            publication_start = audit_progress_indexes[-1] if audit_progress_indexes else -1
            final_streamed = "".join(
                str(event.get("text") or "")
                for index, event in enumerate(events)
                if index > publication_start and event.get("type") == "text_delta"
            )
            if not final_streamed and text_indexes:
                final_streamed = "".join(
                    str(events[index].get("text") or "") for index in text_indexes
                )
            persisted_memory = _last_assistant_text(loop.messages)
            from data_agent.session.history import load_session

            persisted_session = load_session(session_id) or {}
            persisted_disk = _last_assistant_text(
                list(persisted_session.get("messages") or [])
            )
            streamed_public = _strip_publication_markers(final_streamed)
            persisted_public = _strip_publication_markers(
                persisted_disk or persisted_memory
            )

            if provider_error is not None and not persisted_public:
                category = _provider_error_category(provider_error)
                if category == "provider_credentials_unavailable":
                    raise ProviderConfigurationUnavailable(category)
                return {
                    "run_id": f"live_{run_index}",
                    "status": "FAIL",
                    "reason_codes": [category],
                }

            state = getattr(loop.context, "analysis_state", None)
            outcomes = _session_tool_outcomes(loop.messages)
            successful_tools = [
                str(outcome.get("tool_name") or "")
                for outcome in outcomes
                if isinstance(outcome, dict) and outcome.get("success")
            ]
            evidence_records = list(getattr(state, "evidence_records", []) or [])
            audit = _latest_final_audit(state)
            audit_reason_codes = {
                str(code)
                for check in audit.get("claim_checks") or []
                if isinstance(check, dict)
                for code in check.get("reason_codes") or []
                if str(code)
            }
            publication_actions = _material_publication_actions(
                audit,
                _latest_publication_actions(state),
            )
            unresolved_fallback_blocked_calls = (
                _unresolved_fallback_blocked_calls(outcomes)
            )
            verified_material_claims = _verified_material_claim_count(
                audit,
                publication_actions,
            )
            first_final_index = next(
                (index for index in text_indexes if index > publication_start),
                text_indexes[0] if text_indexes else -1,
            )
            progress_before_final = first_final_index >= 0 and any(
                event.get("type") == "analysis_progress"
                for event in events[:first_final_index]
            )
            has_findings = bool(re.search(r"发现|结论|结果", persisted_public))
            has_recommendations = bool(re.search(r"建议|行动|下一步", persisted_public))
            has_limitations = bool(re.search(r"局限|限制", persisted_public))
            data_quality_count = sum(
                tool in _LIVE_DATA_QUALITY_TOOLS for tool in successful_tools
            )
            descriptive_count = sum(
                tool in _LIVE_DESCRIPTIVE_TOOLS - _LIVE_DATA_QUALITY_TOOLS
                for tool in successful_tools
            )
            relationship_count = sum(
                tool in _LIVE_RELATIONSHIP_TOOLS for tool in successful_tools
            )
            upload_contract_active = bool(
                "load_data" in successful_tools
                and getattr(state, "dataset_contracts", None)
            )
            requirements = {
                "data_quality": (
                    "satisfied"
                    if upload_contract_active and data_quality_count >= 1
                    else "missing"
                ),
                "descriptive": "satisfied" if descriptive_count >= 1 else "missing",
                "relationship": "satisfied" if relationship_count >= 1 else "missing",
                "limitations": "satisfied" if has_limitations else "missing",
            }
            return {
                "run_id": f"live_{run_index}",
                "status": "PASS" if persisted_public else "FAIL",
                "reason_codes": [] if persisted_public else ["empty_publication"],
                "upload_contract_active": upload_contract_active,
                "tool_calls": len(outcomes),
                "data_quality_computations": data_quality_count,
                "structured_computations": descriptive_count + relationship_count,
                "projected_evidence": len(evidence_records),
                "final_audit_status": str(audit.get("status") or ""),
                "publication_actions": publication_actions,
                "publication_length": len(re.sub(r"\s+", "", persisted_public)),
                "publication_language": _detect_language(persisted_public),
                "has_findings": has_findings,
                "has_recommendations": has_recommendations,
                "has_limitations": has_limitations,
                "generic_warning_present": (
                    "Some requested analysis claims" in persisted_public
                ),
                "progress_before_final": progress_before_final,
                "persisted_matches_streamed": persisted_public == streamed_public,
                "repeated_failure_max": _repeated_failure_max(outcomes),
                "unresolved_fallback_blocked_calls": (
                    unresolved_fallback_blocked_calls
                ),
                "verified_material_claims": verified_material_claims,
                "measurement_bookkeeping_scheduled_analysis": bool(
                    audit_reason_codes & _MEASUREMENT_BOOKKEEPING_CODES
                    and getattr(loop, "_turn_final_audit_analysis_retry_used", False)
                ),
                "requirements": requirements,
            }
    except ProviderConfigurationUnavailable:
        raise
    except BaseException as exc:
        category = _provider_error_category(exc)
        if category == "provider_credentials_unavailable":
            raise ProviderConfigurationUnavailable(category) from exc
        return {
            "run_id": f"live_{run_index}",
            "status": "FAIL",
            "reason_codes": [category],
        }


def _evaluate_live_run(run: dict[str, Any]) -> dict[str, Any]:
    return evaluate_live_provider_run(run)


def build_live_provider_receipt(
    *,
    source_digest: str,
    source_commit: str,
    provider_model: str,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_live_provider_gate_receipt(
        source_digest=source_digest,
        source_commit=source_commit,
        provider_model=provider_model,
        runs=runs,
    )


def _blocked_live_receipt(
    *,
    reason: str,
    source_digest: str,
    source_commit: str,
    provider_model: str,
) -> dict[str, Any]:
    return {
        "contract_version": LIVE_PROVIDER_GATE_VERSION,
        "status": "BLOCKED",
        "reason_codes": [reason],
        "accepted": False,
        "overall_status": "BLOCKED",
        "live_provider_status": "BLOCKED",
        "source_digest": source_digest,
        "source_commit": source_commit,
        "provider_model": provider_model,
        "runs": [],
    }


def run_live_provider_acceptance(
    output_dir: Path,
    *,
    runs: int = 3,
) -> dict[str, Any]:
    if runs != 3:
        raise ValueError("live provider gate requires exactly three runs")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = release_source_digest(ROOT)
    commit = _current_git_commit()
    try:
        configured = get_config()
        provider_model = str(configured.model_id)
    except BaseException:
        return _blocked_live_receipt(
            reason="provider_configuration_unavailable",
            source_digest=digest,
            source_commit=commit,
            provider_model="",
        )

    outcomes: list[dict[str, Any]] = []
    for index in range(1, 4):
        try:
            outcomes.append(
                _run_one_live_provider_analysis(output_dir / f"run_{index}", index)
            )
        except ProviderConfigurationUnavailable as exc:
            return _blocked_live_receipt(
                reason=str(exc) or "provider_credentials_unavailable",
                source_digest=digest,
                source_commit=commit,
                provider_model=provider_model,
            )
        except BaseException:
            outcomes.append(
                {
                    "run_id": f"live_{index}",
                    "status": "FAIL",
                    "reason_codes": ["live_runner_internal_error"],
                }
            )
    return build_live_provider_receipt(
        source_digest=digest,
        source_commit=commit,
        provider_model=provider_model,
        runs=outcomes,
    )


def write_live_provider_receipt(receipt: dict[str, Any], path: Path) -> Path:
    """Atomically persist a bounded receipt with no prompt or raw data rows."""

    expected_digest = str(receipt.get("source_digest") or "")
    validation = validate_live_provider_gate_receipt(
        receipt,
        expected_source_digest=expected_digest,
    )
    raw_reasons = receipt.get("reason_codes")
    expected_reasons = tuple(raw_reasons) if isinstance(raw_reasons, list) else ()
    if (
        validation.status != receipt.get("status")
        or validation.reason_codes != expected_reasons
    ):
        raise ValueError(",".join(validation.reason_codes))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


# ---------------------------------------------------------------------------
# Suite + CLI
# ---------------------------------------------------------------------------


def run_release_replay(
    output_dir: Path,
    *,
    mode: str,
    runs: int | None = None,
) -> dict[str, Any]:
    """Run the deterministic suite or the real three-run provider gate."""

    if mode not in {"deterministic", "live"}:
        raise ValueError("mode must be deterministic or live")
    if runs is None:
        runs = 3 if mode == "live" else 1
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if mode == "live":
        if runs != 3:
            raise ValueError("live mode requires --runs 3")
        return run_live_provider_acceptance(output_dir, runs=runs)

    factor_root = output_dir / "factor"
    sandbox_root = output_dir / "sandbox"
    unicode_root = output_dir / "unicode"
    aggregate_root = output_dir / "aggregate"

    factor_ok = _run_factor_scenario(factor_root)
    sandbox_ok = _run_sandbox_scenario(sandbox_root)
    unicode_ok = _run_unicode_scenario(unicode_root)
    aggregate_ok = _run_aggregate_scenario(aggregate_root)

    accepted = factor_ok and sandbox_ok and unicode_ok and aggregate_ok
    return {
        "accepted": accepted,
        "overall_status": "PASS" if accepted else "FAIL",
        "mode": "deterministic",
        "factor_relationship": factor_ok,
        "sandbox_recovery": sandbox_ok,
        "unicode_boundary": unicode_ok,
        "aggregate_profile_boundary": aggregate_ok,
    }


def replay_suite(
    *,
    mode: str,
    runs: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Compatibility wrapper for the release replay CLI."""

    return run_release_replay(output_dir, mode=mode, runs=runs)


def _run_factor_scenario(root: Path) -> bool:
    try:
        result = run_deterministic_replay(
            frame=build_factor_relationship_frame(),
            prompt=factor_relationship_prompt(),
            root=root,
        )
    except Exception:
        return False
    if not result.turn_completed or result.completion_state not in {"complete", "complete_with_limits"}:
        return False
    if not result.evidence_records or result.final_answer_language != "zh":
        return False
    if result.final_audit_status != "pass" or not result.published_limitations:
        return False
    if "Some requested analysis claims" in result.final_answer:
        return False
    if not result.progress_events:
        return False
    first_progress = int(getattr(result.progress_events[0], "sequence", 0))
    if first_progress >= result.final_answer_sequence:
        return False
    required_statuses = {
        "grain_definition",
        "target_definition",
        "missingness_assessment",
        "univariate_association",
        "multivariable_adjustment",
        "multiplicity_control",
        "collinearity_assessment",
        "effect_size_or_predictive_contribution",
        "limitations_and_alternatives",
    }
    return (
        {
            "data.profile",
            "analysis.correlation",
            "analysis.factor_relationship",
        }.issubset(result.successful_capability_ids)
        and all(
            result.requirement_statuses.get(name) == "satisfied"
            for name in required_statuses
        )
    )


def _run_aggregate_scenario(root: Path) -> bool:
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "aggregate_data.csv"
    build_aggregate_payment_frame().to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        result = run_deterministic_replay(
            frame=build_aggregate_payment_frame(),
            prompt="请分析用户画像、复购和消费分布",
            responses=_aggregate_responses(csv_path),
            fallback_text=_AGGREGATE_FINAL_TEXT,
            root=root,
            session_id="aggregate_replay",
            project_name="aggregate_replay",
            dataset_name="aggregate_data",
        )
    except Exception:
        return False
    if "年龄" in result.asserted_dimensions or "个人复购" in result.asserted_dimensions:
        return False
    if result.completion_state not in {"complete_with_limits", "blocked_by_data"}:
        return False
    return "需要用户级字段" in result.final_answer


def _run_sandbox_scenario(root: Path) -> bool:
    try:
        result = run_sandbox_replay(root)
    except Exception:
        return False
    # Negative: no opaque cascade leaked through the sandbox boundary.
    if "__import__ not found" in result.serialized_trace:
        return False
    if "NoneType" in result.serialized_trace:
        return False
    # Positive: the failing run_python ACTUALLY executed and returned a
    # structured error token (not a vacuous "absent opaque error" pass), and
    # the identical retry was bounded (1..2 attempts).
    if "dataset_not_found" not in result.serialized_trace:
        return False
    if not (1 <= result.max_identical_failure_attempts <= 2):
        return False
    return True


def _run_unicode_scenario(root: Path) -> bool:
    try:
        result = run_unicode_replay(root, console_encoding="cp936")
    except Exception:
        return False
    if not result.turn_completed:
        return False
    return "⚠️" in result.persisted_text and "⚠️" in result.streamed_text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay analysis reliability scenarios through the real agent loop."
    )
    parser.add_argument("--mode", choices=["deterministic", "live"], default="deterministic")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Live-mode receipt path (defaults inside --output-dir).",
    )
    args = parser.parse_args()
    if args.mode == "live" and args.runs != 3:
        parser.error("live mode requires --runs 3")
    summary = replay_suite(mode=args.mode, runs=args.runs, output_dir=args.output_dir)
    if args.mode == "live":
        receipt_path = args.receipt or (
            args.output_dir / "analysis_live_provider_gate.v1.json"
        )
        write_live_provider_receipt(summary, receipt_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
