"""Drive a frozen P08 batch through the app's existing HTTP upload/chat APIs.

This replaces unreliable browser automation of the controls, not the app,
AgentLoop, Provider guard, or acceptance oracle. It does not validate the
upload button or visual rendering; those remain separate UI evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import requests


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def _upload(base: str, path: Path, expected_digest: str) -> dict[str, Any]:
    if _sha256(path) != expected_digest:
        raise RuntimeError(f"fixture digest mismatch: {path.name}")
    with path.open("rb") as source:
        result = _request_json(
            "POST", base + "/api/upload",
            files={"file": (path.name, source, "text/csv")},
        )
    if result.get("filename") != path.name or result.get("sha256") != expected_digest:
        raise RuntimeError(f"upload receipt mismatch: {path.name}")
    return result


def _stream(base: str, route: str, payload: dict[str, Any]) -> dict[str, Any]:
    with requests.post(base + route, json=payload, stream=True, timeout=(15, 190)) as response:
        response.raise_for_status()
        session_id = response.headers.get("X-Data-Agent-Session-Id") or payload.get("session_id")
        if not session_id:
            raise RuntimeError("chat response omitted session identity")
        event_names: list[str] = []
        event_payloads: list[dict[str, Any]] = []
        pending_name = ""
        for raw in response.iter_lines(decode_unicode=True):
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line:
                pending_name = ""
            elif line.startswith("event:"):
                pending_name = line[6:].strip()
                event_names.append(pending_name)
            elif line.startswith("data:") and pending_name in {"turn_end", "suspended"}:
                event_payloads.append({"event": pending_name, "data": json.loads(line[5:])})
    if event_names.count("turn_start") != 1:
        raise RuntimeError(f"turn_start integrity failure: {session_id}")
    if event_names.count("turn_end") != 1:
        raise RuntimeError(f"turn_end integrity failure: {session_id}")
    state = _request_json("GET", base + f"/api/sessions/{session_id}/run-state")
    terminal = next(item["data"] for item in event_payloads if item["event"] == "turn_end")
    if state.get("status") != terminal.get("status"):
        raise RuntimeError(f"SSE/persisted terminal mismatch: {session_id}")
    return {"session_id": session_id, "event_names": event_names,
            "terminal": terminal.get("status"), "run_state": state,
            "suspended": next((item["data"] for item in event_payloads
                               if item["event"] == "suspended"), None)}


def _record(path: Path, entry: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _option_value(options: list[Any], label: str) -> str | None:
    """Match the visible option, then send exactly what the Web UI sends."""
    for option in options:
        if isinstance(option, dict) and label in str(option.get("label") or ""):
            return str(option.get("value") or option["label"])
    if label == "B. 代金券成本 + 渠道成本":
        matches = [
            option for option in options
            if isinstance(option, dict)
            and ("口径B" in str(option.get("label") or "")
                 or str(option.get("label") or "").startswith("B."))
            and "代金券成本" in str(option.get("label") or "")
            and "渠道成本" in str(option.get("label") or "")
        ]
        if len(matches) == 1:
            return str(matches[0].get("value") or matches[0]["label"])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run_dir = args.run_dir.resolve()
    freeze_path = run_dir / "freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    base = args.base_url.rstrip("/")
    if base != f"http://127.0.0.1:{freeze['operator_protocol']['service_port']}":
        raise SystemExit("base URL differs from frozen localhost port")
    if freeze.get("source_commit") != subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
    ).strip():
        raise SystemExit("source HEAD differs from freeze")
    if freeze.get("http_driver_digest") != _sha256(Path(__file__)):
        raise SystemExit("HTTP driver differs from freeze")
    served = _request_json("GET", base + "/p08-freeze")
    if served != freeze:
        raise SystemExit("served freeze differs from local freeze")
    if freeze["operator_protocol"].get("control_route") != "local_http_api":
        raise SystemExit("freeze does not authorize HTTP control route")
    if (run_dir / "provider-calls.jsonl").exists() or any((run_dir / "sessions").iterdir()):
        raise SystemExit("matrix requires an unused Provider ledger and empty sessions")

    evidence = run_dir / "http-matrix.jsonl"
    if evidence.exists():
        raise SystemExit("HTTP matrix evidence already exists; no resume or retry")
    fixture_dir = run_dir / "fixtures"
    for name, digest in freeze["fixtures"].items():
        if _sha256(fixture_dir / name) != digest:
            raise SystemExit(f"frozen fixture mismatch: {name}")

    for scenario_id in freeze["matrix"]:
        spec = freeze["scenario_inputs"][scenario_id]
        session_id: str | None = None
        uploaded: dict[str, dict[str, Any]] = {}
        ordinary_errors: list[str] = []
        try:
            for turn_number, prompt in enumerate(spec["prompts"], 1):
                stage = next((stage for stage in spec.get("upload_stages", [])
                              if stage["before_prompt"] == turn_number), None)
                names = stage["fixtures"] if stage else (
                    spec["fixtures"] if turn_number == 1 and not spec.get("upload_stages") else []
                )
                attached = []
                for name in names:
                    uploaded[name] = _upload(base, fixture_dir / name, freeze["fixtures"][name])
                    attached.append(uploaded[name])
                body: dict[str, Any] = {"message": prompt}
                if session_id:
                    body["session_id"] = session_id
                if attached:
                    body["uploads"] = attached
                result = _stream(base, "/api/chat", body)
                if session_id and result["session_id"] != session_id:
                    raise RuntimeError("same-scenario session identity changed")
                session_id = result["session_id"]
                _record(evidence, {"scenario": scenario_id, "turn": turn_number,
                                   "uploaded": [{"filename": item["filename"], "sha256": item["sha256"]}
                                                for item in attached], **result})
                if result["terminal"] not in {"completed", "suspended"}:
                    ordinary_errors.append(f"turn {turn_number}: {result['terminal']}")
                if scenario_id == "M06" and turn_number == 2 and result["terminal"] == "suspended":
                    suspension = result["suspended"]
                    if not suspension:
                        raise RuntimeError("suspended state lacks confirmation event")
                    choice = "B. 代金券成本 + 渠道成本"
                    options = suspension.get("options") or []
                    user_response = _option_value(options, choice)
                    if user_response is None:
                        ordinary_errors.append("frozen confirmation option B absent")
                    else:
                        resumed = _stream(base, "/api/chat/resume", {
                            "session_id": session_id,
                            "confirmation_id": suspension["confirmation_id"],
                            "expected_version": suspension["version"],
                            "idempotency_key": f"p08-{scenario_id}-{session_id}",
                            "user_response": user_response,
                        })
                        _record(evidence, {"scenario": scenario_id, "turn": "resume", **resumed})
                        if resumed["terminal"] != "completed":
                            ordinary_errors.append(f"resume: {resumed['terminal']}")
            if session_id:
                if "compact_context" in spec["actions"]:
                    try:
                        compacted = _request_json("POST", base + "/api/compact",
                                                  json={"session_id": session_id})
                        _record(evidence, {"scenario": scenario_id, "action": "compact_context",
                                           "response": compacted})
                    except requests.HTTPError as exc:
                        ordinary_errors.append(f"compact_context: {exc}")
                if "export_markdown" in spec["actions"]:
                    exported = _request_json("GET", base + f"/api/sessions/{session_id}/export?format=markdown")
                    _record(evidence, {"scenario": scenario_id, "action": "export_markdown",
                                       "response": exported})
                persisted = _request_json("GET", base + f"/api/sessions/{session_id}")
                _record(evidence, {"scenario": scenario_id, "action": "persisted_reload",
                                   "session_id": session_id, "message_count": len(persisted.get("messages") or []),
                                   "run_state": persisted.get("run_state"), "errors": ordinary_errors})
        except requests.HTTPError as exc:
            _record(evidence, {"scenario": scenario_id, "error": str(exc),
                               "session_id": session_id, "classification": "ordinary_failure"})
        except (requests.RequestException, RuntimeError) as exc:
            _record(evidence, {"scenario": scenario_id, "error": str(exc),
                               "session_id": session_id, "classification": "global_stop"})
            raise
        print(json.dumps({"scenario": scenario_id, "session_id": session_id,
                          "ordinary_errors": ordinary_errors}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"P08 HTTP matrix stopped: {exc}", file=sys.stderr)
        raise
