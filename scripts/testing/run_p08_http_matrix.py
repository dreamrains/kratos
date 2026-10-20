"""Control the frozen P08 real-Provider matrix through existing app HTTP APIs.

The launcher owns Provider admission and its ledger. This driver only uploads,
chats, checks SSE against durable state, and records nonvisual evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import requests


class ScenarioFailure(RuntimeError):
    """Known, owned session failure; continuation still requires a closed ledger."""
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def _record(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()


def _upload(base: str, path: Path, digest: str) -> dict[str, Any]:
    if _sha(path) != digest:
        raise RuntimeError(f"frozen fixture changed: {path.name}")
    with path.open("rb") as stream:
        ticket = _json("POST", base + "/api/upload",
                       files={"file": (path.name, stream, "text/csv")})
    if ticket.get("filename") != path.name or ticket.get("sha256") != digest:
        raise RuntimeError(f"upload ticket mismatch: {path.name}")
    return ticket


def _chat(base: str, route: str, body: dict[str, Any]) -> dict[str, Any]:
    with requests.post(base + route, json=body, stream=True,
                       timeout=(15, 190)) as response:
        response.raise_for_status()
        session_id = response.headers.get("X-Data-Agent-Session-Id") or body.get("session_id")
        if not session_id:
            raise RuntimeError("chat response omitted session id")
        names: list[str] = []
        payloads: list[tuple[str, dict[str, Any]]] = []
        event = ""
        for raw in response.iter_lines(decode_unicode=True):
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line:
                event = ""
            elif line.startswith("event:"):
                event = line[6:].strip()
                names.append(event)
            elif line.startswith("data:") and event in {"turn_start", "turn_end", "suspended", "error"}:
                payloads.append((event, json.loads(line[5:])))
    terminals = [value for name, value in payloads if name == "turn_end"]
    if names.count("turn_start") != 1 or names.count("turn_end") != 1 or len(terminals) != 1:
        raise RuntimeError(f"SSE terminal integrity failure: {session_id}")
    starts = [value for name,value in payloads if name == "turn_start"]
    if (len(starts) != 1 or not starts[0].get("turn_id")
            or terminals[0].get("turn_id") != starts[0]["turn_id"]
            or starts[0].get("session_id") != session_id or terminals[0].get("session_id") != session_id):
        raise RuntimeError(f"SSE session/turn identity mismatch: {session_id}")
    durable = _json("GET", base + f"/api/sessions/{session_id}/run-state")
    if durable.get("status") != terminals[0].get("status") or durable.get("turn_id") != terminals[0]["turn_id"]:
        raise RuntimeError(f"SSE and durable status disagree: {session_id}")
    if durable.get("session_id",session_id)!=session_id:
        raise RuntimeError(f"durable session identity mismatch: {session_id}")
    if terminals[0].get("status") not in {"completed","suspended","failed","cancelled"}:
        raise RuntimeError(f"SSE terminal status is invalid: {session_id}")
    return {
        "session_id": session_id, "events": names,
        "terminal": terminals[0].get("status"), "run_state": durable,
        "turn_id":terminals[0]["turn_id"],"terminal_payload":terminals[0],
        "suspended": next((value for name, value in payloads if name == "suspended"), None),
    }



def _snapshot(base: str, run_dir: Path, session_id: str) -> dict[str, Any]:
    """Keep app projections with their existing owned immutable answer files."""
    session = _json("GET", base + f"/api/sessions/{session_id}")
    _record(run_dir / "http-matrix.jsonl", {"action":"raw_session_response","session_id":session_id,"session":session})
    analysis = _json("GET", base + f"/api/sessions/{session_id}/analysis")
    _record(run_dir / "http-matrix.jsonl", {"action":"raw_publication_response", "session_id":session_id,
        "session":session, "analysis":analysis})
    directory = (run_dir / "sessions" / session_id).resolve()
    if (directory.parent != (run_dir / "sessions").resolve() or directory.name != session_id
            or (run_dir / "sessions" / session_id).is_symlink()):
        raise RuntimeError("session path escaped batch isolation")
    for payload in (session, analysis.get("state",{})):
        if payload.get("session_id",session_id) != session_id:
            raise RuntimeError("API response belongs to another session")
    answers, files, projection_errors = {}, {}, []
    for ref in analysis.get("state", {}).get("accepted_answers", []):
        path = (directory / ref["path"]).resolve()
        if not path.is_relative_to(directory) or _sha(path) != ref["sha256"]:
            raise RuntimeError("accepted answer file identity mismatch")
        answer = json.loads(path.read_text(encoding="utf-8"))
        body_sha = "sha256:" + hashlib.sha256(answer["body"].encode("utf-8")).hexdigest()
        if (answer.get("schema") != "answer_bindings.v2" or answer.get("session_id") != session_id
                or answer["answer_id"] != ref["answer_id"] or body_sha != ref["content_sha256"]
                or answer["content_sha256"] != body_sha or answer["snapshot_digest"] != ref["snapshot_digest"]):
            raise RuntimeError("accepted answer binding mismatch")
        matching = [m for m in session.get("messages", []) if m.get("answer_id") == answer["answer_id"]]
        if any(m.get("answer_ref",ref)!=ref for m in matching):
            raise RuntimeError("public answer reference identity conflict")
        if len(matching) != 1 or matching[0].get("content") != answer["body"] or matching[0].get("answer_sha256") != body_sha:
            projection_errors.append(answer["answer_id"])
        answers[answer["answer_id"]] = answer
        files[ref["path"]] = ref["sha256"]
        for artifact in answer["artifact_refs"]:
            target = (directory / artifact["path"]).resolve()
            if not target.is_relative_to(directory) or _sha(target) != artifact["sha256"]:
                raise RuntimeError("answer artifact identity mismatch")
            files[artifact["path"]] = artifact["sha256"]
    canonical_count = 0
    archives = []
    for name in ("conversation.json", "conversation.jsonl"):
        path = directory / name
        if path.is_file():
            files[name] = _sha(path)
            raw = path.read_text(encoding="utf-8")
            records = json.loads(raw) if name.endswith(".json") else [json.loads(line) for line in raw.splitlines() if line.strip()]
            canonical_count += len(records)
            archives.extend(m["canonical_transcript"] for m in records if m.get("canonical_transcript"))
    checked = set()
    while archives:
        ref = archives.pop()
        name = ref["filename"]
        path = (directory / "transcripts" / name).resolve()
        if Path(name).name != name or path.parent != directory / "transcripts" or _sha(path) != ref["sha256"]:
            raise RuntimeError("canonical archive identity mismatch")
        identity = (name,ref["sha256"])
        if identity in checked:continue
        if len(checked)>=32:raise RuntimeError("canonical archive budget exceeded")
        checked.add(identity)
        files["transcripts/"+name]=ref["sha256"]
        archives.extend(m["canonical_transcript"] for m in (json.loads(line) for line in path.read_text("utf-8").splitlines()) if m.get("canonical_transcript"))
    if any(m.get("answer_id") and m["answer_id"] not in answers for m in session.get("messages",[])):
        raise RuntimeError("public projection contains an unowned answer identity")
    if projection_errors:
        raise ScenarioFailure("scenario_integrity_failure", "public projection differs from accepted answer: " + ",".join(projection_errors))
    return {"session":session,"analysis":analysis,"accepted_answers":answers,
            "owned_file_digests":files,"canonical_message_count":canonical_count}


def _check_turn_publication(result: dict, snapshot: dict) -> None:
    """Assess the owned current reply; SSE and publication turn IDs differ."""
    if result["terminal"] != "completed":
        return
    terminal = result["terminal_payload"]
    reply_id = terminal.get("reply_id")
    if not isinstance(reply_id, str) or not reply_id:
        raise RuntimeError("completed SSE lacks a current reply identity")
    # Tool-call assistant messages legitimately share their reply group ID.
    messages = [m for m in snapshot["session"].get("messages", []) if m.get("reply_id") == reply_id and m.get("answer_id")]
    if len(messages) != 1:
        raise RuntimeError("current reply ownership is uncertain")
    message = messages[0]
    answer = snapshot["accepted_answers"].get(message.get("answer_id"))
    if answer is None:
        raise RuntimeError("current reply has no owned accepted answer")
    if terminal.get("reply_content") != answer["body"]:
        raise ScenarioFailure("scenario_integrity_failure", "current SSE reply differs from its owned original")
    failed = [r["id"] for r in answer["source_snapshot"]["requirements"]
              if not r["withdrawn"] and (r.get("gap") or {}).get("status") == "failed"]
    if failed:
        raise ScenarioFailure("session_execution_failure", "unrecovered host execution failure: " + ",".join(failed))


def _export_evidence(base: str, run_dir: Path, session_id: str, snapshot: dict) -> dict:
    exported = _json("GET", base + f"/api/sessions/{session_id}/export?format=markdown")
    if exported.get("status") != "exported":
        return {"response": exported, "content_verified":False}
    relative = Path(exported["artifact_path"])
    _record(run_dir / "http-matrix.jsonl", {"action":"raw_export_response","session_id":session_id,"response":exported})
    if relative.parts[:2] != ("sessions",session_id):
        raise RuntimeError("export path belongs to another session")
    own = (run_dir / relative).resolve()
    if not own.is_relative_to((run_dir / "sessions" / session_id).resolve()):
        raise RuntimeError("export path escaped isolation")
    if not own.is_file():
        raise ScenarioFailure("scenario_integrity_failure","owned export is missing")
    response = requests.get(base + "/api/files/" + relative.as_posix(), timeout=30)
    response.raise_for_status()
    if response.content != own.read_bytes():
        _record(run_dir / "http-matrix.jsonl", {"action":"export_content_failure","session_id":session_id,
            "response":exported,"download_sha256":"sha256:"+hashlib.sha256(response.content).hexdigest(),"owned_sha256":_sha(own)})
        raise ScenarioFailure("scenario_integrity_failure", "download differs from owned export bytes")
    text=response.content.decode("utf-8")
    # Compare decoded content across platform line endings; the download byte digest stays exact.
    text=text.replace("\r\n","\n")
    preserved=bool(snapshot["accepted_answers"]) and all(answer["body"].replace("\r\n","\n").strip() in text for answer in snapshot["accepted_answers"].values())
    return {"response":exported,"download_sha256":_sha(own),"download_bytes":len(response.content),
            "content_verified":preserved,"accepted_answer_ids":list(snapshot["accepted_answers"])}


def _choice(suspension: dict[str, Any], frozen_action: str | dict) -> str | None:
    """Select one frozen stable option value, without parsing visible prose."""
    if isinstance(frozen_action, dict):
        if frozen_action.get("kind") == "free_text":
            return frozen_action["response"] if (suspension.get("allow_free_text") is True
                and suspension.get("confirmation_type") in frozen_action["types"]) else None
        if frozen_action.get("kind") != "metric_scope_formula" or suspension.get("confirmation_type") != "metric_definition":
            return None
        matches = []
        for option in suspension.get("options", []):
            value = option.get("value")
            try: formula = json.loads(value)
            except (ValueError, TypeError): continue
            if (isinstance(formula, dict) and set(formula) == {"schema_version", "dataset", "effect_column", "cost_columns"}
                    and formula.get("schema_version") == "metric_scope_formula.v1"
                    and formula.get("dataset") in frozen_action["datasets"]
                    and formula.get("effect_column") == frozen_action["effect_column"]
                    and isinstance(formula.get("cost_columns"), list)
                    and all(isinstance(c,str) for c in formula["cost_columns"])
                    and len(formula["cost_columns"]) == len(set(formula["cost_columns"]))
                    and sorted(formula["cost_columns"]) == sorted(frozen_action["cost_columns"])):
                matches.append(value)
        return matches[0] if len(matches) == 1 else None
    selected = re.fullmatch(r"select_value ([A-Za-z0-9_.:-]{1,80})", frozen_action)
    options = suspension.get("options")
    if selected is None or not isinstance(options, list) or len(options) < 2:
        return None
    labels = [item.get("label") for item in options if isinstance(item, dict)]
    if len(labels) != len(options) or len(labels) != len(set(labels)):
        return None
    values = [item.get("value") or item.get("label") for item in options]
    if len(values) != len(set(values)):
        return None
    matches = [item for item in options if item.get("value") == selected.group(1)]
    if len(matches) != 1:
        return None
    return selected.group(1)


def _ledger_state(base: str, cap: int) -> dict[str, int]:
    response = requests.get(base + "/p08-ledger", timeout=30)
    response.raise_for_status()
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    started = [item.get("call_number") for item in events if item.get("event") == "started"]
    dispatched = [item.get("call_number") for item in events if item.get("event") == "dispatched"]
    failed = [item.get("call_number") for item in events if item.get("event") == "failed"]
    settled = [item.get("call_number") for item in events
               if item.get("event") in {"completed", "stream_exhausted"}]
    interrupted = [item for item in events
                   if item.get("event") in {"stream_failed", "stream_closed", "gate_fault"}]
    denied = [item for item in events if item.get("event") == "denied"]
    if (len(started) > cap or started != list(range(1, len(started) + 1))
            or sorted(dispatched) != started or sorted(settled) != started
            or failed or denied or interrupted):
        raise RuntimeError("Provider ledger has a missing, failed, denied or excess call")
    return {"started": len(started), "dispatched": len(dispatched),
            "completed": len(settled), "failed": len(failed), "denied": len(denied)}


def _preflight(root: Path, run_dir: Path, base: str) -> dict[str, Any]:
    freeze = json.loads((run_dir / "freeze.json").read_text(encoding="utf-8"))
    if freeze.get("source_commit") != subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip():
        raise RuntimeError("frozen HEAD changed")
    if freeze.get("http_driver_digest") != _sha(Path(__file__).resolve()):
        raise RuntimeError("frozen HTTP driver changed")
    if freeze.get("operator_protocol", {}).get("control_route") != "combined_http_api_browser":
        raise RuntimeError("wrong frozen control route")
    if (freeze["operator_protocol"]["control_route"]=="combined_http_api_browser"
            and freeze["operator_protocol"].get("visual_checkpoint")!="closed_ledger_stdin_v2"):
        raise RuntimeError("combined route lacks frozen visual checkpoint protocol")
    import importlib.util
    spec = importlib.util.spec_from_file_location("p08_frozen_launcher", Path(__file__).with_name("run_p08_real_matrix.py"))
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher._require_clean_source(root)
    if freeze.get("source_inventory") != launcher._source_inventory(root) or freeze.get("runtime_environment") != launcher._runtime_environment():
        raise RuntimeError("frozen source/runtime changed before HTTP controls")
    scope = freeze.get("execution_scope", freeze.get("matrix"))
    if scope != freeze.get("matrix") or scope != ["M01","M02","M03","M04","M05","M06"]:
        raise RuntimeError("invalid frozen scenario scope")
    if scope == ["M06"] and freeze.get("supplement_of", {}).get("scenario") != "M06":
        raise RuntimeError("M06-only scope lacks a bound supplement")
    if base != f"http://127.0.0.1:{freeze['operator_protocol']['service_port']}":
        raise RuntimeError("base URL differs from frozen port")
    if _json("GET", base + "/p08-freeze") != freeze:
        raise RuntimeError("served freeze differs from local freeze")
    if (run_dir / "provider-calls.jsonl").exists() or any((run_dir / "sessions").iterdir()):
        raise RuntimeError("Provider ledger or sessions already used")
    if (run_dir / "http-matrix.jsonl").exists():
        raise RuntimeError("HTTP batch evidence already exists")
    for name, digest in freeze["fixtures"].items():
        if _sha(run_dir / "fixtures" / name) != digest:
            raise RuntimeError(f"frozen fixture changed: {name}")
    return freeze


def _visual_checkpoint(base: str, freeze: dict, evidence: Path, scenario: str, session_id: str | None,
                       checkpoint: str = "scenario_end") -> None:
    protocol=freeze.get("operator_protocol",{})
    if protocol.get("control_route") != "combined_http_api_browser":return
    if protocol.get("visual_checkpoint") != "closed_ledger_stdin_v2":
        raise RuntimeError("combined route lacks frozen visual checkpoint protocol")
    ledger=_ledger_state(base,freeze["call_cap"])
    _record(evidence,{"scenario":scenario,"session_id":session_id,"checkpoint":checkpoint,"action":"visual_checkpoint_ready","provider_calls":ledger})
    print(json.dumps({"visual_checkpoint":scenario,"session_id":session_id,"checkpoint":checkpoint,"url":f"{base}/?session_id={session_id}"}),flush=True)
    # Same process and ledger; no replay, restart or Provider dispatch occurs here.
    reply=json.loads(input())
    if (set(reply)!={"scenario","session_id","checkpoint","visual_status","evidence_path","evidence_sha256"}
            or reply["scenario"]!=scenario or reply["session_id"]!=session_id
            or reply["checkpoint"]!=checkpoint
            or reply["visual_status"] not in {"passed","failed","unassessed"}):
        raise RuntimeError("visual checkpoint identity is invalid")
    path=(evidence.parent / reply["evidence_path"]).resolve()
    if not path.is_relative_to(evidence.parent.resolve()) or _sha(path)!=reply["evidence_sha256"]:
        raise RuntimeError("visual checkpoint evidence identity mismatch")
    receipt=json.loads(path.read_text("utf-8"))
    if any(receipt.get(k)!=reply[k] for k in ("scenario","session_id","checkpoint")) or receipt.get("status")!=reply["visual_status"]:
        raise RuntimeError("visual receipt differs from its checkpoint identity")
    _record(evidence,{"scenario":scenario,"session_id":session_id,"action":"visual_checkpoint_result",**reply})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run_dir = args.run_dir.resolve()
    base = args.base_url.rstrip("/")
    freeze = _preflight(root, run_dir, base)
    evidence = run_dir / "http-matrix.jsonl"
    fixture_dir = run_dir / "fixtures"
    seen_sessions: set[str] = set()

    scope = freeze.get("execution_scope", freeze["matrix"])
    def stop(index, scenario_id, session_id, exc):
        _record(evidence,{"scenario":scenario_id,"session_id":session_id,"classification":"global_stop","code":getattr(exc,"code","untrusted_batch_state"),"error":str(exc)})
        for blocked in scope[index+1:]:
            _record(evidence,{"scenario":blocked,"classification":"blocked_not_started","reason":str(exc)})

    for index, scenario_id in enumerate(scope):
        spec = freeze["scenario_inputs"][scenario_id]
        session_id: str | None = None
        errors: list[str] = []
        try:
            for number, prompt in enumerate(spec["prompts"], 1):
                stages = [stage for stage in spec.get("upload_stages", [])
                          if stage.get("before_prompt") == number]
                if len(stages) > 1:
                    raise RuntimeError("duplicate frozen upload stage")
                names = (stages[0]["fixtures"] if stages else
                         spec["fixtures"] if number == 1 and not spec.get("upload_stages") else [])
                tickets = [_upload(base, fixture_dir / name, freeze["fixtures"][name])
                           for name in names]
                body: dict[str, Any] = {"message": prompt}
                if session_id:
                    body["session_id"] = session_id
                if tickets:
                    body["uploads"] = tickets
                result = _chat(base, "/api/chat", body)
                if session_id and session_id != result["session_id"]:
                    raise RuntimeError("same-scenario session changed")
                if session_id is None and result["session_id"] in seen_sessions:
                    raise RuntimeError("cross-scenario session identity reused")
                session_id = result["session_id"]
                _record(evidence, {"scenario": scenario_id, "turn": number,
                                   "uploads": [{"filename": t["filename"], "sha256": t["sha256"]}
                                               for t in tickets], **result})
                snapshot = _snapshot(base, run_dir, session_id)
                _record(evidence, {"scenario": scenario_id, "turn": number, "action": "current_publication_snapshot", "session_id": session_id, **snapshot})
                if result["terminal"] not in {"completed", "suspended"}:
                    raise ScenarioFailure("session_execution_failure",f"turn {number}: {result['terminal']}")
                _check_turn_publication(result, snapshot)
                frozen_confirmation = spec.get("confirmations", {}).get(str(number))
                if frozen_confirmation and result["terminal"] != "suspended":
                    raise ScenarioFailure("missing_confirmation",f"turn {number}: required business confirmation absent")
                if result["terminal"] == "suspended" and frozen_confirmation is None:
                    raise ScenarioFailure("unfrozen_confirmation",f"turn {number}: unfrozen confirmation; dependent path stopped")
                if frozen_confirmation and result["terminal"] == "suspended":
                    suspended = result["suspended"]
                    if not suspended:
                        raise RuntimeError("suspended turn omitted confirmation")
                    answer = _choice(suspended, frozen_confirmation)
                    if answer is None:
                        raise ScenarioFailure("ambiguous_confirmation","frozen option identity absent or ambiguous; dependent path stopped")
                    else:
                        _visual_checkpoint(base,freeze,evidence,scenario_id,session_id,f"confirmation:{number}")
                        resumed = _chat(base, "/api/chat/resume", {
                            "session_id": session_id,
                            "confirmation_id": suspended["confirmation_id"],
                            "expected_version": suspended["version"],
                            "idempotency_key": f"p08-{scenario_id}-{session_id}-{number}",
                            "user_response": answer,
                        })
                        _record(evidence, {"scenario": scenario_id, "turn": "resume",
                                           "parent_turn":number,
                                           "frozen_action": frozen_confirmation,
                                           "selected_response": answer, **resumed})
                        resumed_snapshot = _snapshot(base, run_dir, session_id)
                        _record(evidence, {"scenario": scenario_id, "turn": f"{number}-resume", "action": "current_publication_snapshot", "session_id": session_id,
                            **resumed_snapshot})
                        if resumed["terminal"] != "completed":
                            raise ScenarioFailure("session_execution_failure",f"resume: {resumed['terminal']}")
                        _check_turn_publication(resumed, resumed_snapshot)
            if session_id:
                if "compact_context" in spec["actions"]:
                    before = _snapshot(base, run_dir, session_id)
                    compacted = _json("POST", base + "/api/compact", json={"session_id": session_id})
                    after = _snapshot(base, run_dir, session_id)
                    shortened = after["canonical_message_count"] < before["canonical_message_count"]
                    preserved = before["accepted_answers"] == after["accepted_answers"]
                    if not shortened or not preserved:
                        errors.append("actual compaction/public original preservation oracle failed")
                    _record(evidence, {"scenario": scenario_id, "action": "compact_context", "session_id":session_id,
                                       "response": compacted,"before":before,"after":after,
                                       "model_history_shortened":shortened,"public_originals_preserved":preserved})
                if "export_markdown" in spec["actions"]:
                    exported = _export_evidence(base, run_dir, session_id, _snapshot(base, run_dir, session_id))
                    _record(evidence, {"scenario": scenario_id, "action": "export_markdown", "session_id":session_id,
                                       **exported})
                    if not exported["content_verified"]:
                        raise ScenarioFailure("scenario_integrity_failure", "owned export does not retain all accepted original bodies")
                state = _json("GET", base + f"/api/sessions/{session_id}")
                _record(evidence, {"scenario": scenario_id, "action": "persisted_reload",
                                   "session_id": session_id, "run_state": state.get("run_state"),
                                   "message_count": len(state.get("messages") or []), "errors": errors})
        except ScenarioFailure as exc:
            # No unknown action is retried. A unique durable terminal was
            # already checked by _chat; ledger closure below is mandatory.
            errors.append(str(exc))
            _record(evidence,{"scenario":scenario_id,"session_id":session_id,"classification":"scenario_failure",
                "code":exc.code,"error":str(exc),"blocked_from_turn":number+1,"remaining_actions":"blocked_dependent_path"})
        except Exception as exc:
            stop(index, scenario_id, session_id, exc)
            raise
        if session_id:
            seen_sessions.add(session_id)
        try:
            ledger = _ledger_state(base, freeze["call_cap"])
        except Exception as exc:
            stop(index, scenario_id, session_id, exc)
            raise
        _record(evidence, {"scenario": scenario_id, "action": "ledger_reconciled",
                           "provider_calls": ledger})
        try:
            _visual_checkpoint(base,freeze,evidence,scenario_id,session_id)
        except Exception as exc:
            stop(index,scenario_id,session_id,exc)
            raise
        print(json.dumps({"scenario": scenario_id, "session_id": session_id,
                          "ordinary_errors": errors}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
