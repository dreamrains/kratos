"""P0-3 objective scenario auditor: deterministic five-dimension verdicts.

Reads only persisted artifacts (session dirs, provider ledger, reports).
Blocking checks are closed-class (protocol states, artifact presence, receipt
arithmetic); unverified answer numbers remain unassessed.
Every mechanical oracle cites the plan principle it enforces so oracle drift
from the approved principles is detectable (``oracle_contract_is_consistent``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Scenario prompt prefixes (mirrors scripts/testing/p08_real_matrix_contract.json;
# the contract file is authoritative when present, these are the offline default).
SCENARIO_PROMPT_PREFIXES = {
    "M01": "请分析当前上传的销售订单数据",
    "M02": "请计算并解释 D1 至 D7 留存",
    "M03": "请分别比较当前六个来源",
    "M04": "请基于当前 v1 数据提出并检验",
    "M05": "请先基于当前订单给出一份证据受限的事实摘要",
    "M06": "请分析名为 missing_orders 的数据集",
}

DEFAULT_ACTIONS = {
    "M01": ["refresh"],
    "M02": ["export_markdown", "refresh"],
    "M03": ["compact_context", "export_markdown", "refresh"],
    "M04": ["inspect_workbench", "refresh"],
    "M05": ["export_markdown", "refresh"],
    "M06": ["export_markdown", "refresh"],
}

# Only M06 is authorized to suspend on a real business-scope confirmation
# (frozen operator protocol; IC principle 2: business ambiguity is specific).
AUTHORIZED_CONFIRMATION_TYPES = {
    "M01": set(),
    "M02": set(),
    "M03": set(),
    "M04": set(),
    "M05": set(),
    "M06": {"metric_definition", "business_scope", "cost_scope", "decision"},
}

HOST_DEADLINE_SECONDS = 120.0
DEADLINE_SLACK_SECONDS = 5.0

# ---------------------------------------------------------------------------
# Mechanical oracle registry: each entry cites the plan principle it enforces.
#   principle ids: VP=2026-09-06 value-preservation plan (§4.1 principles / G-goals),
#   IC=2026-09-07 intent-clarification plan (§3 principles),
#   CP=2026-09-08 answer-content plan (CR-goals / §5-§6).
# ---------------------------------------------------------------------------
MECHANICAL_ORACLES: list[dict] = [
    {"id": "scenario_matrix_coverage", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "VP-P8(完整 M01-M06 批次)/CP-CR03(逐项交付)", "type": "matrix"},
    {"id": "run_state_terminal_unique", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "VP-G6(能力不回退)/P08验收§15(终态唯一)", "type": "run_state"},
    {"id": "run_state_completed", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "VP-P8-四维契约(执行与生命周期:product_failed)/VP-G6", "type": "run_state"},
    {"id": "tool_pairing_closed", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "VP-G6(工具协议完整)/IC-§7(事件完整性)", "type": "pairing"},
    {"id": "confirmations_authorized", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "IC-3.1(方法不是确认理由)/IC-3.8(技术字段不进入用户负担)", "type": "confirmations"},
    {"id": "ledger_closed", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "VP-P8-12.1(调用核算完整性)", "type": "ledger"},
    {"id": "ledger_max_duration", "scenario": "*", "dim": "execution", "blocking": True,
     "principle": "VP-G6(宿主 deadline 生效)", "type": "ledger"},
    {"id": "answer_numeric_oracles", "scenario": "*", "dim": "evidence", "blocking": False,
     "principle": "CP-CR02/CR04(绑定数字一致)/CP-§5(未知不得伪装为已检查)", "type": "numeric"},
    {"id": "export_dual_artifacts", "scenario": "*", "dim": "transfer", "blocking": True,
     "principle": "CP-CR06(图文对应、导出一致)/VP-P8-12.1(生命周期一致性)", "type": "export"},
    {"id": "tasks_terminal", "scenario": "*", "dim": "declaration", "blocking": True,
     "principle": "VP-G5(假设生命周期闭合)/CP-CR03(覆盖或具体缺口)", "type": "tasks"},
    {"id": "extrapolated_value_receipt_bound", "scenario": "*", "dim": "evidence", "blocking": False,
     "principle": "VP-4.1(允许标注的待验证解释,禁止无依据外推)/CP-§5(未知待评)", "type": "extrapolation"},
    {"id": "yoy_requires_crossyear_receipt", "scenario": "*", "dim": "evidence", "blocking": False,
     "principle": "VP-4.1(口径正确)/CP-CR04/CP-§5(开放语义待评)", "type": "yoy"},
    # Open-class semantics: advisory only (CP-§5: 规则不能可靠判定的语义不伪精确).
    {"id": "unit_drift_advisory", "scenario": "*", "dim": "value", "blocking": False,
     "principle": "CP-§5(unknown 不得写成已知)/CP-§6(避免过度保守)", "type": "advisory_unit"},
    {"id": "origin_lean_advisory", "scenario": "*", "dim": "value", "blocking": False,
     "principle": "VP-4.1(来源断言需依据)/CP-§6(区分 invalid 与 unassessed)", "type": "advisory_origin"},
    {"id": "single_next_step_advisory", "scenario": "*", "dim": "value", "blocking": False,
     "principle": "CP-§5(条件式建议而非排他式单一路径)", "type": "advisory_next_step"},
]

_KNOWN_CHECK_TYPES = {
    "matrix", "run_state", "pairing", "confirmations", "ledger", "numeric", "export",
    "tasks", "extrapolation", "yoy", "advisory_unit", "advisory_origin",
    "advisory_next_step",
}
_KNOWN_DIMS = {"execution", "evidence", "value", "transfer", "declaration"}


def oracle_contract_is_consistent() -> list[str]:
    """Validate that every mechanical oracle cites a principle and known fields."""
    problems: list[str] = []
    ids: set[str] = set()
    for entry in MECHANICAL_ORACLES:
        eid = entry.get("id")
        if not eid:
            problems.append("oracle without id")
            continue
        if eid in ids:
            problems.append(f"duplicate oracle id {eid}")
        ids.add(eid)
        if not str(entry.get("principle") or "").strip():
            problems.append(f"{eid}: principle citation missing")
        if entry.get("dim") not in _KNOWN_DIMS:
            problems.append(f"{eid}: unknown dimension {entry.get('dim')!r}")
        if entry.get("type") not in _KNOWN_CHECK_TYPES:
            problems.append(f"{eid}: unknown check type {entry.get('type')!r}")
        if not isinstance(entry.get("blocking"), bool):
            problems.append(f"{eid}: blocking must be boolean")
    return problems


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _final_assistant_text(messages: list) -> str:
    texts = [
        str(m.get("content") or "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "assistant" and str(m.get("content") or "").strip()
    ]
    return texts[-1] if texts else ""


def _all_assistant_text(messages: list) -> str:
    return "\n".join(
        str(m.get("content") or "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "assistant"
    )


def _detect_scenario(summary: str) -> str | None:
    text = str(summary or "")
    for scenario, prefix in SCENARIO_PROMPT_PREFIXES.items():
        if text.startswith(prefix[:12]):
            return scenario
    return None


def _detect_scenario_from(sdir: Path) -> str | None:
    """Map a session to its scenario, surviving context compression.

    After mid-session compaction the meta summary AND the original user prompt
    are replaced by a structured digest.  Fall back to the closed-class anchor
    that compaction cannot rewrite: the uploaded fixture filenames recorded in
    the session's upload tickets.  Only fixture prefixes that map to exactly
    one scenario are authoritative (M01-sales is shared by M01/M05/M06 and
    therefore never decides alone).
    """
    meta = _read_json(sdir / "meta.json") or {}
    scenario = _detect_scenario(meta.get("summary") or "")
    if scenario is not None:
        return scenario
    messages = _read_json(sdir / "conversation.json") or []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            scenario = _detect_scenario(str(m.get("content") or ""))
            if scenario is not None:
                return scenario
    fixture_scenarios: set[str] = set()
    uploads = sdir / "uploads"
    if uploads.exists():
        for ticket in sorted(uploads.iterdir()):
            record = _read_json(ticket / "upload.json") or {}
            filename = str(record.get("filename") or "")
            for candidate, prefix in {
                "M02": "M02-retention", "M03": "M03-source", "M04": "M04-hyp",
            }.items():
                if filename.startswith(prefix):
                    fixture_scenarios.add(candidate)
    if len(fixture_scenarios) == 1:
        return fixture_scenarios.pop()
    return None


def _confirmation_is_authorized(record: dict, scenario: str) -> bool:
    """Closed-class authorization: only M06's frozen cost-scope question may suspend.

    Real records carry no ``confirmation_type`` field; the discriminator is the
    frozen operator protocol itself: M06's authorized question is the cost-scope
    single-select defined in the frozen prompt (成本口径). Any other question in
    any scenario is an unauthorized suspension (IC principle 1/2).
    """
    if scenario == "M06" and "成本口径" in str(record.get("question") or ""):
        return True
    ctype = str(record.get("confirmation_type") or "")
    return ctype in AUTHORIZED_CONFIRMATION_TYPES.get(scenario, set())


def _check(passed: bool, check_id: str, detail: str, blocking: bool, dim: str, principle: str) -> dict:
    return {
        "check": check_id,
        "passed": bool(passed),
        "blocking": blocking,
        "dim": dim,
        "principle": principle,
        "detail": detail,
    }


def _oracle_meta(check_id: str) -> dict:
    for entry in MECHANICAL_ORACLES:
        if entry["id"] == check_id:
            return entry
    raise KeyError(check_id)


# ---------------------------------------------------------------------------
# per-session checks
# ---------------------------------------------------------------------------

_ADVISORY_UNIT = re.compile(r"\d\s*(?:块钱|块)|(?:升级|换算)成?\s*(?:元|块)")
_ADVISORY_ORIGIN = re.compile(
    r"(?:像是|更像|疑似|极可能|大概率|更可能)[^。；;\n]{0,16}(?:样例|占位|模板|测试数据|构造|合成)", re.I
)
_SINGLE_NEXT_STEP = re.compile(
    r"唯一(?:的)?(?:下一步|选项|路径|办法|出路|行动|动作)|"
    r"下一步[（(]单一动作[）)]|"
    r"只有(?:一条|一个)(?:路|途径|选项|下一步|办法)",
    re.I,
)
_D_TOKEN = re.compile(r"(?<![A-Za-z0-9])D(\d+)")
_PCT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%")


def audit_session(sdir: Path, scenario: str, actions: list[str] | None = None) -> dict:
    actions = list(actions if actions is not None else DEFAULT_ACTIONS.get(scenario, []))
    checks: list[dict] = []

    run_state = _read_json(sdir / "run_state.json") or {}
    meta = _read_json(sdir / "meta.json") or {}
    messages = _read_json(sdir / "conversation.json") or []
    final_text = _final_assistant_text(messages)
    all_text = _all_assistant_text(messages)

    # 1. run_state terminal & unique (blocking)
    o = _oracle_meta("run_state_terminal_unique")
    status = str(run_state.get("status") or "")
    terminal_ok = status in {"completed", "failed"} and bool(run_state.get("turn_id"))
    checks.append(_check(terminal_ok, o["id"], f"status={status!r}", o["blocking"], o["dim"], o["principle"]))

    # 1b. a failed terminal is itself a scenario failure (blocking) — the
    # four-dimension contract records execution=product_failed for it; the
    # auditor reports the reason so external causes stay re-classifiable.
    o = _oracle_meta("run_state_completed")
    completed_ok = status == "completed"
    reason = str(run_state.get("reason") or "")
    notice = str(run_state.get("notice") or "")[:120]
    checks.append(_check(
        completed_ok, o["id"],
        f"status={status!r} reason={reason!r} notice={notice!r}" if not completed_ok else "completed",
        o["blocking"], o["dim"], o["principle"],
    ))

    # 2. tool pairing closed (blocking)
    o = _oracle_meta("tool_pairing_closed")
    declared: list[str] = []
    answered: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                tc_id = str((tc or {}).get("id") or "")
                if tc_id:
                    declared.append(tc_id)
        elif m.get("role") == "tool":
            tid = str(m.get("tool_call_id") or "")
            if tid:
                answered.append(tid)
    pairing_ok = sorted(declared) == sorted(answered)
    checks.append(_check(
        pairing_ok, o["id"],
        f"declared={len(declared)} answered={len(answered)}",
        o["blocking"], o["dim"], o["principle"],
    ))

    # 3. authorized confirmation questions only (blocking)
    o = _oracle_meta("confirmations_authorized")
    snapshot = _read_json(sdir / "confirmations" / "snapshot.json") or {}
    records = snapshot.get("records") if isinstance(snapshot.get("records"), dict) else {}
    unauthorized = [
        str(rec.get("confirmation_id") or rec.get("question") or "unknown")[:60]
        for rec in (records or {}).values()
        if isinstance(rec, dict) and not _confirmation_is_authorized(rec, scenario)
    ]
    checks.append(_check(
        not unauthorized, o["id"],
        f"unauthorized_types={unauthorized}" if unauthorized else "no unauthorized confirmations",
        o["blocking"], o["dim"], o["principle"],
    ))

    # 4. Answer text cannot certify numeric correctness or completeness.
    # Keep this obligation explicitly unassessed until a current receipt,
    # binding and rendered span can be checked together.
    o = _oracle_meta("answer_numeric_oracles")
    detail = (
        "unassessed: review raw-scale D1-D7, unit evidence, and receipt-bound D30"
        if scenario == "M02" else
        "unassessed: answer numbers require current receipt, binding, and rendered-span review"
    )
    numeric_check = _check(False, o["id"], detail, o["blocking"], o["dim"], o["principle"])
    numeric_check["assessment"] = "unassessed"
    checks.append(numeric_check)

    # 5. export dual artifacts (blocking when the scenario exports)
    o = _oracle_meta("export_dual_artifacts")
    if "export_markdown" in actions:
        reports = list((sdir / "reports").glob("*.md")) if (sdir / "reports").exists() else []
        has_conversation = any(p.name.startswith("conversation_") for p in reports)
        has_publication = any(p.name.startswith("publication_") for p in reports)
        export_ok = has_conversation and has_publication
        detail = f"conversation={has_conversation} publication={has_publication} files={len(reports)}"
    else:
        export_ok = True
        detail = "export action not in frozen actions"
    checks.append(_check(export_ok, o["id"], detail, o["blocking"], o["dim"], o["principle"]))

    # 6. tasks terminal at completed run state (blocking) — declaration dimension
    o = _oracle_meta("tasks_terminal")
    if status == "completed":
        residue: list[str] = []
        workspace_tasks = sdir.parent.parent / "workspace" / "tasks"
        if workspace_tasks.exists():
            for tf in sorted(workspace_tasks.glob("task_*.json")):
                task = _read_json(tf) or {}
                if str(task.get("session_id") or "") != str(meta.get("session_id") or sdir.name):
                    continue
                if task.get("status") in {"pending", "blocked", "in_progress"}:
                    residue.append(str(tf.name))
            active = _read_json(workspace_tasks / "active_plans.json")
            if isinstance(active, dict) and str(meta.get("session_id") or sdir.name) in {
                key.split("::")[0] for key in active
            }:
                residue.append("active_plan_registered")
        tasks_ok = not residue
        detail = f"residue={residue}" if residue else "no non-terminal tasks or active plans"
    else:
        tasks_ok = True
        detail = f"run_state={status!r}; declaration check applies to completed runs"
    checks.append(_check(tasks_ok, o["id"], detail, o["blocking"], o["dim"], o["principle"]))

    # 7. Text/curve-value coincidence does not prove a scenario binding, and
    # wording-based uncertainty escapes do not establish whether a claim is safe.
    o = _oracle_meta("extrapolated_value_receipt_bound")
    d_point_rate = any(
        _PCT.search(clause) and _D_TOKEN.search(clause)
        for clause in re.split(r"[。；;\n]", final_text)
    )
    extrapolation_check = _check(
        not d_point_rate, o["id"],
        "unassessed: D-point rate needs a current claim-bound receipt and host-rendered span"
        if d_point_rate else "no D-point rate expression found",
        o["blocking"], o["dim"], o["principle"],
    )
    if d_point_rate:
        extrapolation_check["assessment"] = "unassessed"
    checks.append(extrapolation_check)

    # 8. A lexical label is a review lead, not a verified claim. An unrelated
    # cross-year receipt cannot authorize the sentence that used the label.
    o = _oracle_meta("yoy_requires_crossyear_receipt")
    yoy_labelled = any(
        "同比" in clause and "同比例" not in clause
        for clause in re.split(r"[。；;\n]", final_text)
    )
    yoy_check = _check(
        not yoy_labelled, o["id"],
        "unassessed: 同比 wording needs a claim-bound same-period cross-year receipt"
        if yoy_labelled else "no 同比 label found",
        o["blocking"], o["dim"], o["principle"],
    )
    if yoy_labelled:
        yoy_check["assessment"] = "unassessed"
    checks.append(yoy_check)

    # 9-10. advisory open-class semantics (never blocking)
    o = _oracle_meta("unit_drift_advisory")
    unit_hits = _ADVISORY_UNIT.findall(final_text)
    checks.append(_check(
        not unit_hits, o["id"],
        f"unit_drift_candidates={len(unit_hits)}", o["blocking"], o["dim"], o["principle"],
    ))
    o = _oracle_meta("origin_lean_advisory")
    origin_hits = _ADVISORY_ORIGIN.findall(final_text)
    checks.append(_check(
        not origin_hits, o["id"],
        f"origin_lean_candidates={len(origin_hits)}", o["blocking"], o["dim"], o["principle"],
    ))

    # 11. P2-2 排他式"唯一下一步"框架（价值维软检查，永不阻断）：
    # 把单一路径写成唯一选项（真实 r1 M06"下一步（单一动作）"）压缩了
    # 用户的决策空间；条件式指引（触发/停止条件）不计。
    o = _oracle_meta("single_next_step_advisory")
    next_step_hits = _SINGLE_NEXT_STEP.findall(final_text)
    checks.append(_check(
        not next_step_hits, o["id"],
        f"exclusive_next_step_candidates={len(next_step_hits)}" if next_step_hits
        else "no exclusive next-step framing",
        o["blocking"], o["dim"], o["principle"],
    ))

    return {"session": sdir.name, "scenario": scenario, "checks": checks}


# ---------------------------------------------------------------------------
# run-level checks
# ---------------------------------------------------------------------------

def audit_run_dir(run_dir: Path) -> dict:
    run_checks: list[dict] = []

    o = _oracle_meta("ledger_closed")
    ledger_path = run_dir / "provider-calls.jsonl"
    started = dispatched = failed = 0
    max_duration = 0.0
    pairs: dict[int, dict] = {}
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            pairs.setdefault(int(entry.get("call_number") or 0), {})[str(entry.get("event"))] = float(entry.get("at") or 0)
            if entry.get("event") == "started":
                started += 1
            elif entry.get("event") == "dispatched":
                dispatched += 1
            elif entry.get("event") == "failed":
                failed += 1
        for events in pairs.values():
            if "started" in events and "dispatched" in events:
                max_duration = max(max_duration, events["dispatched"] - events["started"])
    ledger_ok = (started == dispatched + failed) and started > 0
    run_checks.append(_check(
        ledger_ok, o["id"],
        f"started={started} dispatched={dispatched} failed={failed}",
        o["blocking"], o["dim"], o["principle"],
    ))

    o = _oracle_meta("ledger_max_duration")
    deadline_limit = HOST_DEADLINE_SECONDS + DEADLINE_SLACK_SECONDS
    run_checks.append(_check(
        max_duration <= deadline_limit, o["id"],
        f"max_duration={max_duration:.1f}s limit={deadline_limit:.0f}s",
        o["blocking"], o["dim"], o["principle"],
    ))

    sessions: dict[str, dict] = {}
    sessions_root = run_dir / "sessions"
    if sessions_root.exists():
        for sdir in sorted(sessions_root.iterdir()):
            if not (sdir / "run_state.json").exists():
                continue
            scenario = _detect_scenario_from(sdir)
            if scenario is None:
                continue
            sessions[sdir.name] = audit_session(sdir, scenario=scenario)

    o = _oracle_meta("scenario_matrix_coverage")
    observed_scenarios = {item["scenario"] for item in sessions.values()}
    missing_scenarios = sorted(set(SCENARIO_PROMPT_PREFIXES) - observed_scenarios)
    run_checks.append(_check(
        not missing_scenarios, o["id"],
        f"observed={sorted(observed_scenarios)} missing={missing_scenarios}",
        o["blocking"], o["dim"], o["principle"],
    ))

    any_blocking = any(
        (not c["passed"]) and c["blocking"]
        for c in run_checks
    ) or any(
        (not c["passed"]) and c["blocking"]
        for verdict in sessions.values()
        for c in verdict["checks"]
    )
    needs_review = any(
        check.get("assessment") == "unassessed"
        for verdict in sessions.values() for check in verdict["checks"]
    )
    return {
        "run_dir": str(run_dir),
        "run_checks": run_checks,
        "sessions": sessions,
        "verdict": "failed" if any_blocking else "needs_review" if needs_review else "passed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic P08 scenario auditor")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    problems = oracle_contract_is_consistent()
    if problems:
        print(json.dumps({"oracle_contract_problems": problems}, ensure_ascii=False))
        return 2

    report = audit_run_dir(Path(args.run_dir))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return {"passed": 0, "failed": 1, "needs_review": 2}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
