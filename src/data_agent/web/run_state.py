"""Durable execution status; deliberately separate from analytical validity."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import threading

from data_agent.session.history import _session_dir
from data_agent.utils.atomic_files import replace_file


ACTIVE = {"running", "cancelling"}


class SessionBusy(RuntimeError):
    pass


class RunStates:
    def __init__(self):
        self._lock = threading.RLock()
        self._active = {}

    def _read(self, sid):
        path = _session_dir(sid) / "run_state.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _write(self, sid, state):
        path = _session_dir(sid) / "run_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {**state, "session_id": sid, "updated_at": datetime.now(timezone.utc).isoformat()}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        replace_file(temporary, path)
        return state

    def snapshot(self, sid):
        with self._lock:
            state = self._active.get(sid) or self._read(sid)
            if state.get("status") in ACTIVE and sid not in self._active:
                # Snapshot after a server restart must never claim success.
                # The owning runtime is gone: heal the stale file too, or the
                # disk keeps claiming "running" forever (the process died
                # mid-turn) and misleads any file-level reader.
                return dict(self._write(sid, {**state, "status": "unknown", "reason": "runtime_restarted"}))
            return dict(state)

    def begin(self, sid, turn_id):
        with self._lock:
            if sid in self._active:
                raise SessionBusy("该会话仍在执行或停止中，请等待执行结束。")
            state = self._write(sid, {"turn_id": turn_id, "status": "running"})
            self._active[sid] = state
            return state

    def cancelling(self, sid):
        with self._lock:
            state = self._active.get(sid)
            if state:
                self._active[sid] = self._write(sid, {**state, "status": "cancelling"})
            return self.snapshot(sid)

    def finish(self, sid, turn_id, status, **details):
        with self._lock:
            state = self._active.get(sid)
            if state and state["turn_id"] != turn_id:
                raise RuntimeError("stale turn cannot finish the current run")
            final = self._write(sid, {"turn_id": turn_id, "status": status, **details})
            self._active.pop(sid, None)
            return final
