"""P0-3 objective scenario auditor: deterministic five-dimension verdicts.

Reads only persisted artifacts (session dirs, provider ledger, reports).
Blocking checks are closed-class (protocol states, numeric oracles, artifact
presence, receipt arithmetic); open-class semantics are advisory only.
Every mechanical oracle cites the plan principle it enforces so oracle drift
from the approved principles is detectable (``oracle_contract_is_consistent``).
"""

from __future__ import annotations

import argparse
import json
import math
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

NUMERIC_ORACLES = {
    "M01": ["12", "120"],
    "M02": ["55", "10"],
    "M03": ["210", "231"],
    "M04": [],
    "M05": ["12", "120"],
    "M06": ["120"],
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
    {"id": "answer_numeric_oracles", "scenario": "*", "dim": "evidence", "blocking": True,
     "principle": "CP-CR02/CR04(绑定数字一致)", "type": "numeric"},
    {"id": "export_dual_artifacts", "scenario": "*", "dim": "transfer", "blocking": True,
     "principle": "CP-CR06(图文对应、导出一致)/VP-P8-12.1(生命周期一致性)", "type": "export"},
    {"id": "tasks_terminal", "scenario": "*", "dim": "declaration", "blocking": True,
     "principle": "VP-G5(假设生命周期闭合)/CP-CR03(覆盖或具体缺口)", "type": "tasks"},
    {"id": "extrapolated_value_receipt_bound", "scenario": "*", "dim": "evidence", "blocking": True,
     "principle": "VP-4.1(允许标注的待验证解释,禁止无依据外推)", "type": "extrapolation"},
    {"id": "yoy_requires_crossyear_receipt", "scenario": "*", "dim": "evidence", "blocking": True,
     "principle": "VP-4.1(口径正确)/CP-CR04", "type": "yoy"},
    # Open-class semantics: advisory only (CP-§5: 规则不能可靠判定的语义不伪精确).
    {"id": "unit_drift_advisory", "scenario": "*", "dim": "value", "blocking": False,
     "principle": "CP-§5(unknown 不得写成已知)/CP-§6(避免过度保守)", "type": "advisory_unit"},
    {"id": "origin_lean_advisory", "scenario": "*", "dim": "value", "blocking": False,
     "principle": "VP-4.1(来源断言需依据)/CP-§6(区分 invalid 与 unassessed)", "type": "advisory_origin"},
]

_KNOWN_CHECK_TYPES = {
    "run_state", "pairing", "confirmations", "ledger", "numeric", "export",
    "tasks", "extrapolation", "yoy", "advisory_unit", "advisory_origin",
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
_UNCERTAINTY_ESCAPE = re.compile(
    r"未知|不能|无法|非观测|未观测|情景|假设|待确认|未验证|不是预测", re.I
)
_D_TOKEN = re.compile(r"(?<![A-Za-z0-9])D(\d+)")
_PCT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%")


def _find_curve_receipt(tool_outputs_dir: Path) -> dict | None:
    if not tool_outputs_dir.exists():
        return None
    for path in sorted(tool_outputs_dir.glob("*.json")):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue

        def walk(node):
            if isinstance(node, dict):
                if isinstance(node.get("fits"), list) and isinstance(node.get("points"), list):
                    return node
                for value in node.values():
                    found = walk(value)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = walk(value)
                    if found is not None:
                        return found
            return None

        found = walk(data)
        if found is not None:
            return found
    return None


def _find_compare_periods_receipts(tool_outputs_dir: Path) -> list[dict]:
    """All compare_periods receipts (period_a/period_b carrying date ranges)."""
    receipts: list[dict] = []
    if not tool_outputs_dir.exists():
        return receipts
    for path in sorted(tool_outputs_dir.glob("*.json")):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue

        def walk(node):
            if isinstance(node, dict):
                pa, pb = node.get("period_a"), node.get("period_b")
                if (
                    isinstance(pa, dict) and isinstance(pb, dict)
                    and isinstance(pa.get("range"), list) and isinstance(pb.get("range"), list)
                ):
                    receipts.append(node)
                    return
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(data)
    return receipts


def _receipt_is_cross_year(receipt: dict) -> bool:
    """P1-6：跨年判定只认回执里的结构化日期范围，不挖散文年份。"""
    from datetime import date as _date

    starts = []
    for key in ("period_a", "period_b"):
        raw = (receipt.get(key) or {}).get("range") or []
        if len(raw) < 2:
            return False
        try:
            starts.append(_date.fromisoformat(str(raw[0])[:10]))
        except ValueError:
            return False
    left, right = starts
    return left.month == right.month and left.day == right.day and left.year != right.year


def _family_value(fit: dict, x: float) -> float | None:
    params = fit.get("parameters") or {}
    try:
        family = fit.get("family")
        if family == "power":
            return float(params["a"]) * x ** float(params["b"])
        if family == "exponential":
            return float(params["a"]) * math.exp(float(params["b"]) * x)
        if family == "logarithmic":
            return float(params["a"]) + float(params["b"]) * math.log(x)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return None


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

    # 4. numeric oracles present in the final answer (blocking)
    o = _oracle_meta("answer_numeric_oracles")
    missing = [tok for tok in NUMERIC_ORACLES.get(scenario, []) if tok not in final_text]
    checks.append(_check(
        not missing, o["id"],
        f"missing_tokens={missing}" if missing else "numeric oracles present",
        o["blocking"], o["dim"], o["principle"],
    ))

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

    # 7. extrapolated % values must be receipt-bound or uncertainty-marked (blocking)
    o = _oracle_meta("extrapolated_value_receipt_bound")
    receipt = _find_curve_receipt(sdir / "tool_outputs")
    offenders: list[str] = []
    if receipt:
        xs = [float(p.get("x")) for p in receipt.get("points", []) if isinstance(p, dict) and p.get("x") is not None]
        max_x = max(xs) if xs else None
        fits = [f for f in receipt.get("fits", []) if isinstance(f, dict)]
        if max_x is not None:
            for clause in re.split(r"[。；;\n]", final_text):
                for dm in _D_TOKEN.finditer(clause):
                    day = float(dm.group(1))
                    if day <= max_x:
                        continue
                    window = clause[max(0, dm.start() - 40): dm.end() + 60]
                    for pm in _PCT.finditer(clause[dm.end():dm.end() + 80]):
                        reported = float(pm.group(1)) / 100
                        matches = [
                            abs(reported - v) <= 0.0005
                            for v in (_family_value(f, day) for f in fits)
                            if v is not None
                        ]
                        if any(matches):
                            continue
                        if _UNCERTAINTY_ESCAPE.search(window):
                            continue
                        offenders.append(window.strip()[:60])
    checks.append(_check(
        not offenders, o["id"],
        f"unbound_extrapolated_values={len(offenders)}" if offenders else "no unbound extrapolated values",
        o["blocking"], o["dim"], o["principle"],
    ))

    # 8. 同比 label requires a cross-year period receipt (blocking)
    o = _oracle_meta("yoy_requires_crossyear_receipt")
    yoy_labelled = any(
        "同比" in clause and "同比例" not in clause
        for clause in re.split(r"[。；;\n]", final_text)
    )
    period_receipts = _find_compare_periods_receipts(sdir / "tool_outputs")
    crossyear_count = sum(1 for receipt in period_receipts if _receipt_is_cross_year(receipt))
    yoy_ok = not yoy_labelled or crossyear_count > 0
    checks.append(_check(
        yoy_ok, o["id"],
        f"yoy_labelled={yoy_labelled} crossyear_receipts={crossyear_count}",
        o["blocking"], o["dim"], o["principle"],
    ))

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

    any_blocking = any(
        (not c["passed"]) and c["blocking"]
        for c in run_checks
    ) or any(
        (not c["passed"]) and c["blocking"]
        for verdict in sessions.values()
        for c in verdict["checks"]
    )
    return {
        "run_dir": str(run_dir),
        "run_checks": run_checks,
        "sessions": sessions,
        "verdict": "passed" if not any_blocking else "failed",
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
    return 0 if report["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
