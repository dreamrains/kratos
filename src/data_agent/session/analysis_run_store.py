"""SQLite-backed transactional authority for analysis-run state."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Sequence

from data_agent.session.analysis_run_models import (
    AnalysisRun,
    AnalysisStep,
    RunStatus,
    StepSpec,
    StepStatus,
)


class AnalysisRunError(RuntimeError):
    """Base error for invalid transactional run operations."""


class AnalysisRunOwnershipError(AnalysisRunError):
    """Raised when a session attempts to access another session's run."""


class AnalysisRunConflictError(AnalysisRunError):
    """Raised when persisted state contradicts the requested transition."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_same_or_below(candidate: Path, root: Path) -> bool:
    candidate = candidate.resolve()
    root = root.resolve()
    return candidate == root or root in candidate.parents


class AnalysisRunStore:
    """Owns run transitions and commits each state change atomically."""

    def __init__(self, path: Path, *, state_root: Path | None = None):
        self.path = Path(path).resolve()
        if state_root is not None and not _is_same_or_below(self.path, state_root):
            raise ValueError("analysis run database must be inside its assigned state root")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            self._before_commit()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _before_commit(self) -> None:
        """Hook for fault-injection tests; production behavior is a no-op."""

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('active','suspended','recovery','completed','failed','terminated')
                    ),
                    idempotency_key TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, idempotency_key)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_active_run_per_session
                ON analysis_runs(session_id)
                WHERE status IN ('active','recovery');

                CREATE TABLE IF NOT EXISTS analysis_steps (
                    step_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    capability TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (
                        status IN ('pending','in_progress','completed','failed','skipped')
                    ),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, ordinal),
                    UNIQUE(run_id, idempotency_key)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_one_in_progress_step
                ON analysis_steps(run_id)
                WHERE status = 'in_progress';

                CREATE TABLE IF NOT EXISTS analysis_run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
                    step_id TEXT REFERENCES analysis_steps(step_id) ON DELETE SET NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS analysis_tool_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
                    step_id TEXT REFERENCES analysis_steps(step_id) ON DELETE SET NULL,
                    tool_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    artifact_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS analysis_computations (
                    computation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
                    step_id TEXT REFERENCES analysis_steps(step_id) ON DELETE SET NULL,
                    capability TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS analysis_evidence_links (
                    link_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
                    step_id TEXT REFERENCES analysis_steps(step_id) ON DELETE SET NULL,
                    computation_id TEXT NOT NULL REFERENCES analysis_computations(computation_id),
                    evidence_id TEXT NOT NULL,
                    claim_key TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, evidence_id, claim_key)
                );
                """
            )
            evidence_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(analysis_evidence_links)"
                ).fetchall()
            }
            if "evidence_json" not in evidence_columns:
                connection.execute(
                    "ALTER TABLE analysis_evidence_links "
                    "ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}'"
                )

    def create_run(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        steps: Sequence[StepSpec],
    ) -> AnalysisRun:
        session_id = session_id.strip()
        idempotency_key = idempotency_key.strip()
        if not session_id or not idempotency_key:
            raise ValueError("session_id and idempotency_key are required")
        if not steps:
            raise ValueError("at least one analysis step is required")

        run_id = uuid.uuid4().hex
        now = _utc_now()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT run_id FROM analysis_runs WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return self._get_run(connection, existing["run_id"], session_id)
            try:
                connection.execute(
                    """INSERT INTO analysis_runs
                    (run_id, session_id, status, idempotency_key, created_at, updated_at)
                    VALUES (?, ?, 'active', ?, ?, ?)""",
                    (run_id, session_id, idempotency_key, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise AnalysisRunConflictError(
                    f"session {session_id!r} already has an active run"
                ) from exc

            for ordinal, spec in enumerate(steps):
                step_key = spec.idempotency_key.strip() or f"{idempotency_key}:step:{ordinal}"
                connection.execute(
                    """INSERT INTO analysis_steps
                    (step_id, run_id, ordinal, subject, capability, status,
                     payload_json, idempotency_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid.uuid4().hex,
                        run_id,
                        ordinal,
                        spec.subject,
                        spec.capability,
                        "in_progress" if ordinal == 0 else "pending",
                        json.dumps(spec.payload or {}, ensure_ascii=False, sort_keys=True),
                        step_key,
                        now,
                        now,
                    ),
                )
            connection.execute(
                """INSERT INTO analysis_run_events
                (event_id, run_id, event_type, payload_json, idempotency_key, created_at)
                VALUES (?, ?, 'run_created', ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    run_id,
                    json.dumps({"step_count": len(steps)}, sort_keys=True),
                    f"{idempotency_key}:event:created",
                    now,
                ),
            )
        return self.get_run(run_id, session_id=session_id)

    def get_run(self, run_id: str, *, session_id: str | None = None) -> AnalysisRun:
        with self._connect() as connection:
            return self._get_run(connection, run_id, session_id)

    def get_active_run(self, session_id: str) -> AnalysisRun | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT run_id FROM analysis_runs
                WHERE session_id = ? AND status IN ('active','recovery')""",
                (session_id,),
            ).fetchone()
            return (
                self._get_run(connection, row["run_id"], session_id)
                if row is not None
                else None
            )

    def get_latest_run(self, session_id: str) -> AnalysisRun | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT run_id FROM analysis_runs
                WHERE session_id = ? ORDER BY created_at DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            return (
                self._get_run(connection, row["run_id"], session_id)
                if row is not None
                else None
            )

    def terminate_active_run(
        self,
        *,
        session_id: str,
        idempotency_key: str,
    ) -> AnalysisRun | None:
        """Terminate the current run so a replacement plan can become active."""

        active = self.get_active_run(session_id)
        if active is None:
            return None
        now = _utc_now()
        with self._transaction() as connection:
            replay = connection.execute(
                "SELECT 1 FROM analysis_run_events WHERE run_id = ? AND idempotency_key = ?",
                (active.run_id, idempotency_key),
            ).fetchone()
            if replay is not None:
                return self._get_run(connection, active.run_id, session_id)
            connection.execute(
                """UPDATE analysis_runs
                SET status = 'terminated', version = version + 1, updated_at = ?
                WHERE run_id = ?""",
                (now, active.run_id),
            )
            connection.execute(
                """INSERT INTO analysis_run_events
                (event_id, run_id, event_type, payload_json,
                 idempotency_key, created_at)
                VALUES (?, ?, 'run_terminated', '{}', ?, ?)""",
                (uuid.uuid4().hex, active.run_id, idempotency_key, now),
            )
        return self.get_run(active.run_id, session_id=session_id)

    def _get_run(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        session_id: str | None = None,
    ) -> AnalysisRun:
        row = connection.execute(
            "SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise AnalysisRunError(f"analysis run {run_id!r} not found")
        if session_id is not None and row["session_id"] != session_id:
            raise AnalysisRunOwnershipError("analysis run belongs to another session")
        step_rows = connection.execute(
            "SELECT * FROM analysis_steps WHERE run_id = ? ORDER BY ordinal", (run_id,)
        ).fetchall()
        steps = tuple(
            AnalysisStep(
                step_id=step["step_id"],
                run_id=step["run_id"],
                ordinal=step["ordinal"],
                subject=step["subject"],
                capability=step["capability"],
                status=StepStatus(step["status"]),
                payload=json.loads(step["payload_json"]),
                version=step["version"],
            )
            for step in step_rows
        )
        return AnalysisRun(
            run_id=row["run_id"],
            session_id=row["session_id"],
            status=RunStatus(row["status"]),
            version=row["version"],
            steps=steps,
        )

    def complete_and_activate_next(
        self,
        *,
        run_id: str,
        step_id: str,
        session_id: str,
        idempotency_key: str,
    ) -> AnalysisRun:
        return self.finish_and_activate_next(
            run_id=run_id,
            step_id=step_id,
            session_id=session_id,
            final_status="completed",
            idempotency_key=idempotency_key,
        )

    def finish_and_activate_next(
        self,
        *,
        run_id: str,
        step_id: str,
        session_id: str,
        final_status: str,
        idempotency_key: str,
    ) -> AnalysisRun:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if final_status not in {"completed", "failed"}:
            raise ValueError("final_status must be completed or failed")
        now = _utc_now()
        with self._transaction() as connection:
            run = self._get_run(connection, run_id, session_id)
            replay = connection.execute(
                "SELECT 1 FROM analysis_run_events WHERE run_id = ? AND idempotency_key = ?",
                (run_id, idempotency_key),
            ).fetchone()
            if replay is not None:
                return run
            current = connection.execute(
                "SELECT * FROM analysis_steps WHERE step_id = ? AND run_id = ?",
                (step_id, run_id),
            ).fetchone()
            if current is None or current["status"] != StepStatus.IN_PROGRESS:
                raise AnalysisRunConflictError("step is not the current in-progress step")

            connection.execute(
                """UPDATE analysis_steps
                SET status = ?, version = version + 1, updated_at = ?
                WHERE step_id = ?""",
                (final_status, now, step_id),
            )
            next_step = connection.execute(
                """SELECT step_id FROM analysis_steps
                WHERE run_id = ? AND status = 'pending'
                ORDER BY ordinal LIMIT 1""",
                (run_id,),
            ).fetchone()
            next_step_id = next_step["step_id"] if next_step is not None else ""
            if next_step_id:
                connection.execute(
                    """UPDATE analysis_steps
                    SET status = 'in_progress', version = version + 1, updated_at = ?
                    WHERE step_id = ?""",
                    (now, next_step_id),
                )
            else:
                connection.execute(
                    """UPDATE analysis_runs
                    SET status = 'completed', version = version + 1, updated_at = ?
                    WHERE run_id = ?""",
                    (now, run_id),
                )
            connection.execute(
                """INSERT INTO analysis_run_events
                (event_id, run_id, step_id, event_type, payload_json,
                 idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    run_id,
                    step_id,
                    f"step_{final_status}",
                    json.dumps({"next_step_id": next_step_id}, sort_keys=True),
                    idempotency_key,
                    now,
                ),
            )
        return self.get_run(run_id, session_id=session_id)

    def recover_current_step(
        self,
        *,
        run_id: str,
        session_id: str,
        idempotency_key: str,
    ) -> AnalysisRun:
        """Recover a nonterminal run with no current step in one transaction."""

        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        now = _utc_now()
        with self._transaction() as connection:
            run = self._get_run(connection, run_id, session_id)
            replay = connection.execute(
                "SELECT 1 FROM analysis_run_events WHERE run_id = ? AND idempotency_key = ?",
                (run_id, idempotency_key),
            ).fetchone()
            if replay is not None or run.status not in {
                RunStatus.ACTIVE,
                RunStatus.RECOVERY,
            }:
                return run
            current = [
                step for step in run.steps if step.status == StepStatus.IN_PROGRESS
            ]
            if len(current) == 1:
                return run
            if len(current) > 1:
                raise AnalysisRunConflictError("run has multiple in-progress steps")

            next_step = next(
                (step for step in run.steps if step.status == StepStatus.PENDING),
                None,
            )
            if next_step is None:
                connection.execute(
                    """UPDATE analysis_runs
                    SET status = 'completed', version = version + 1, updated_at = ?
                    WHERE run_id = ?""",
                    (now, run_id),
                )
                event_type = "run_recovered_terminal"
                next_step_id = ""
            else:
                connection.execute(
                    """UPDATE analysis_steps
                    SET status = 'in_progress', version = version + 1, updated_at = ?
                    WHERE step_id = ?""",
                    (now, next_step.step_id),
                )
                connection.execute(
                    """UPDATE analysis_runs
                    SET status = 'active', version = version + 1, updated_at = ?
                    WHERE run_id = ?""",
                    (now, run_id),
                )
                event_type = "current_step_recovered"
                next_step_id = next_step.step_id
            connection.execute(
                """INSERT INTO analysis_run_events
                (event_id, run_id, step_id, event_type, payload_json,
                 idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    run_id,
                    next_step_id or None,
                    event_type,
                    json.dumps({"next_step_id": next_step_id}, sort_keys=True),
                    idempotency_key,
                    now,
                ),
            )
        return self.get_run(run_id, session_id=session_id)

    @staticmethod
    def _projection_receipt_from_event(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        payload = json.loads(row["payload_json"] or "{}")
        receipt = payload.get("receipt")
        return dict(receipt) if isinstance(receipt, dict) else None

    def _finish_current_step_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        step_id: str,
        now: str,
    ) -> str:
        current = connection.execute(
            "SELECT status FROM analysis_steps WHERE step_id = ? AND run_id = ?",
            (step_id, run_id),
        ).fetchone()
        if current is None or current["status"] != StepStatus.IN_PROGRESS:
            raise AnalysisRunConflictError("step is not the current in-progress step")
        connection.execute(
            """UPDATE analysis_steps
            SET status = 'completed', version = version + 1, updated_at = ?
            WHERE step_id = ?""",
            (now, step_id),
        )
        next_step = connection.execute(
            """SELECT step_id FROM analysis_steps
            WHERE run_id = ? AND status = 'pending'
            ORDER BY ordinal LIMIT 1""",
            (run_id,),
        ).fetchone()
        next_step_id = next_step["step_id"] if next_step is not None else ""
        if next_step_id:
            connection.execute(
                """UPDATE analysis_steps
                SET status = 'in_progress', version = version + 1, updated_at = ?
                WHERE step_id = ?""",
                (now, next_step_id),
            )
        else:
            connection.execute(
                """UPDATE analysis_runs
                SET status = 'completed', version = version + 1, updated_at = ?
                WHERE run_id = ?""",
                (now, run_id),
            )
        return next_step_id

    @staticmethod
    def _normalized_evidence_links(
        evidence_links: Sequence[dict] | None,
    ) -> list[tuple[str, str, dict]]:
        normalized: list[tuple[str, str, dict]] = []
        identities: set[tuple[str, str]] = set()
        for link in evidence_links or ():
            if not isinstance(link, dict):
                raise ValueError("evidence links must be objects")
            evidence_id = str(link.get("evidence_id") or "").strip()
            claim_key = str(link.get("claim_key") or "").strip()
            if not evidence_id or not claim_key:
                raise ValueError("evidence_id and claim_key are required")
            identity = (evidence_id, claim_key)
            if identity in identities:
                continue
            evidence = link.get("evidence")
            normalized.append((
                evidence_id,
                claim_key,
                dict(evidence) if isinstance(evidence, dict) else {},
            ))
            identities.add(identity)
        return normalized

    def commit_computation_projection(
        self,
        *,
        run_id: str,
        session_id: str,
        step_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_state: str,
        capability: str,
        computation: dict,
        evidence_links: Sequence[dict] | None,
        complete_step: bool,
        idempotency_key: str,
    ) -> dict:
        """Commit one computation, its evidence links, and run advancement.

        The immutable computation artifact is created before this repository
        call.  This transaction makes the artifact reference, tool outcome,
        evidence projection identities, and current-step transition visible
        together.  A computation without evidence remains replayable instead
        of becoming an orphan or forcing model-authored bookkeeping.
        """

        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if tool_state not in {
            "committed",
            "committed_with_warning",
            "rejected",
            "failed",
        }:
            raise ValueError("invalid tool outcome state")
        if not isinstance(computation, dict) or not computation:
            raise ValueError("computation is required")
        links = self._normalized_evidence_links(evidence_links)
        now = _utc_now()
        with self._transaction() as connection:
            self._get_run(connection, run_id, session_id)
            replay = connection.execute(
                """SELECT payload_json FROM analysis_run_events
                WHERE run_id = ? AND idempotency_key = ?""",
                (run_id, idempotency_key),
            ).fetchone()
            replay_receipt = self._projection_receipt_from_event(replay)
            if replay_receipt is not None:
                return replay_receipt
            owned_step = connection.execute(
                "SELECT 1 FROM analysis_steps WHERE run_id = ? AND step_id = ?",
                (run_id, step_id),
            ).fetchone()
            if owned_step is None:
                raise AnalysisRunOwnershipError(
                    "computation step belongs to another analysis run"
                )

            computation_id = uuid.uuid4().hex
            outcome_id = uuid.uuid4().hex
            projection_status = str(
                computation.get("projection_status")
                or ("projected" if links else "pending_binding")
            )
            computation_payload = dict(computation)
            computation_payload["projection_status"] = projection_status
            connection.execute(
                """INSERT INTO analysis_computations
                (computation_id, run_id, step_id, capability, payload_json,
                 idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    computation_id,
                    run_id,
                    step_id,
                    capability,
                    json.dumps(
                        computation_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    idempotency_key,
                    now,
                ),
            )
            artifact_id = str(
                computation.get("computation_ref_id")
                or computation.get("artifact_path")
                or computation_id
            )
            connection.execute(
                """INSERT INTO analysis_tool_outcomes
                (outcome_id, run_id, step_id, tool_name, state, artifact_id,
                 payload_json, idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome_id,
                    run_id,
                    step_id,
                    tool_name,
                    tool_state,
                    artifact_id,
                    json.dumps(
                        {
                            "computation_id": computation_id,
                            "computation_ref_id": computation.get(
                                "computation_ref_id", ""
                            ),
                            "tool_call_id": tool_call_id,
                            "projection_status": projection_status,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    f"{idempotency_key}:tool-outcome",
                    now,
                ),
            )
            for evidence_id, claim_key, evidence in links:
                connection.execute(
                    """INSERT INTO analysis_evidence_links
                    (link_id, run_id, step_id, computation_id, evidence_id,
                     claim_key, evidence_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid.uuid4().hex,
                        run_id,
                        step_id,
                        computation_id,
                        evidence_id,
                        claim_key,
                        json.dumps(
                            evidence,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        now,
                    ),
                )
            next_step_id = (
                self._finish_current_step_in_transaction(
                    connection,
                    run_id=run_id,
                    step_id=step_id,
                    now=now,
                )
                if complete_step
                else ""
            )
            receipt = {
                "run_id": run_id,
                "computation_id": computation_id,
                "computation_ref_id": str(
                    computation.get("computation_ref_id") or ""
                ),
                "tool_outcome_id": outcome_id,
                "completed_step_id": step_id if complete_step else "",
                "next_step_id": next_step_id,
                "evidence_ids": [item[0] for item in links],
                "projection_status": projection_status,
            }
            connection.execute(
                """INSERT INTO analysis_run_events
                (event_id, run_id, step_id, event_type, payload_json,
                 idempotency_key, created_at)
                VALUES (?, ?, ?, 'computation_projection_committed', ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    run_id,
                    step_id,
                    json.dumps(
                        {"receipt": receipt},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    idempotency_key,
                    now,
                ),
            )
        return receipt

    def reconcile_computation_projection(
        self,
        *,
        run_id: str,
        session_id: str,
        step_id: str,
        computation_id: str,
        computation: dict | None = None,
        evidence_links: Sequence[dict] | None,
        complete_step: bool,
        idempotency_key: str,
    ) -> dict:
        """Attach recovered binding/evidence to a committed computation."""

        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        links = self._normalized_evidence_links(evidence_links)
        now = _utc_now()
        with self._transaction() as connection:
            self._get_run(connection, run_id, session_id)
            replay = connection.execute(
                """SELECT payload_json FROM analysis_run_events
                WHERE run_id = ? AND idempotency_key = ?""",
                (run_id, idempotency_key),
            ).fetchone()
            replay_receipt = self._projection_receipt_from_event(replay)
            if replay_receipt is not None:
                return replay_receipt
            computation_row = connection.execute(
                """SELECT * FROM analysis_computations
                WHERE computation_id = ? AND run_id = ?""",
                (computation_id, run_id),
            ).fetchone()
            if computation_row is None:
                raise AnalysisRunOwnershipError(
                    "computation belongs to another analysis run"
                )
            owned_step = connection.execute(
                "SELECT 1 FROM analysis_steps WHERE run_id = ? AND step_id = ?",
                (run_id, step_id),
            ).fetchone()
            if owned_step is None:
                raise AnalysisRunOwnershipError(
                    "reconciliation step belongs to another analysis run"
                )
            payload = json.loads(computation_row["payload_json"] or "{}")
            if isinstance(computation, dict):
                immutable_fields = (
                    "session_id",
                    "turn_id",
                    "tool_call_id",
                    "tool_name",
                    "output_digest",
                    "dataset_versions",
                )
                for field_name in immutable_fields:
                    previous = payload.get(field_name)
                    recovered = computation.get(field_name)
                    if previous != recovered:
                        raise AnalysisRunOwnershipError(
                            "reconciliation cannot change immutable computation identity"
                        )
                if (
                    computation.get("artifact_path") != payload.get("artifact_path")
                    and computation.get("source_artifact_path")
                    != payload.get("artifact_path")
                ):
                    raise AnalysisRunOwnershipError(
                        "reconciliation artifact does not derive from the committed computation"
                    )
                payload.update(computation)
            payload["projection_status"] = "projected"
            payload["reconciled_step_id"] = step_id
            connection.execute(
                """UPDATE analysis_computations
                SET step_id = ?, payload_json = ? WHERE computation_id = ?""",
                (
                    step_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    computation_id,
                ),
            )
            for evidence_id, claim_key, evidence in links:
                connection.execute(
                    """INSERT OR IGNORE INTO analysis_evidence_links
                    (link_id, run_id, step_id, computation_id, evidence_id,
                     claim_key, evidence_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid.uuid4().hex,
                        run_id,
                        step_id,
                        computation_id,
                        evidence_id,
                        claim_key,
                        json.dumps(
                            evidence,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        now,
                    ),
                )
            next_step_id = (
                self._finish_current_step_in_transaction(
                    connection,
                    run_id=run_id,
                    step_id=step_id,
                    now=now,
                )
                if complete_step
                else ""
            )
            receipt = {
                "run_id": run_id,
                "computation_id": computation_id,
                "computation_ref_id": str(
                    payload.get("computation_ref_id") or ""
                ),
                "completed_step_id": step_id if complete_step else "",
                "next_step_id": next_step_id,
                "evidence_ids": [item[0] for item in links],
                "projection_status": "projected",
            }
            connection.execute(
                """INSERT INTO analysis_run_events
                (event_id, run_id, step_id, event_type, payload_json,
                 idempotency_key, created_at)
                VALUES (?, ?, ?, 'computation_projection_reconciled', ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    run_id,
                    step_id,
                    json.dumps(
                        {"receipt": receipt},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    idempotency_key,
                    now,
                ),
            )
        return receipt

    def list_replayable_computations(
        self,
        *,
        run_id: str,
        session_id: str,
    ) -> list[dict]:
        with self._connect() as connection:
            self._get_run(connection, run_id, session_id)
            rows = connection.execute(
                """SELECT * FROM analysis_computations
                WHERE run_id = ? ORDER BY created_at, computation_id""",
                (run_id,),
            ).fetchall()
            replayable: list[dict] = []
            for row in rows:
                payload = json.loads(row["payload_json"] or "{}")
                if payload.get("projection_status") not in {
                    "pending_binding",
                    "projection_failed",
                }:
                    continue
                item = dict(row)
                item["payload"] = payload
                replayable.append(item)
            return replayable

    def computation_count(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS count FROM analysis_computations
                WHERE run_id = ?""",
                (run_id,),
            ).fetchone()
            return int(row["count"])

    def list_computations(
        self,
        *,
        run_id: str,
        session_id: str,
    ) -> list[dict]:
        with self._connect() as connection:
            self._get_run(connection, run_id, session_id)
            rows = connection.execute(
                """SELECT computation_id, payload_json
                FROM analysis_computations
                WHERE run_id = ? ORDER BY created_at, computation_id""",
                (run_id,),
            ).fetchall()
            return [
                {
                    "computation_id": str(row["computation_id"]),
                    "payload": json.loads(row["payload_json"] or "{}"),
                }
                for row in rows
            ]

    def list_evidence_records(
        self,
        *,
        run_id: str,
        session_id: str,
    ) -> list[dict]:
        with self._connect() as connection:
            self._get_run(connection, run_id, session_id)
            rows = connection.execute(
                """SELECT evidence_id, claim_key, evidence_json
                FROM analysis_evidence_links
                WHERE run_id = ? ORDER BY created_at, evidence_id""",
                (run_id,),
            ).fetchall()
            records: list[dict] = []
            for row in rows:
                record = json.loads(row["evidence_json"] or "{}")
                if not isinstance(record, dict):
                    record = {}
                record.setdefault("id", str(row["evidence_id"] or ""))
                record.setdefault("claim_key", str(row["claim_key"] or ""))
                records.append(record)
            return records

    def evidence_link_count(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS count FROM analysis_evidence_links
                WHERE run_id = ?""",
                (run_id,),
            ).fetchone()
            return int(row["count"])

    def record_tool_outcome(
        self,
        *,
        run_id: str,
        session_id: str,
        step_id: str,
        tool_name: str,
        state: str,
        artifact_id: str = "",
        payload: dict | None = None,
        idempotency_key: str,
    ) -> dict:
        """Persist a tool outcome idempotently before downstream publication."""

        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if state not in {
            "committed",
            "committed_with_warning",
            "rejected",
            "failed",
        }:
            raise ValueError("invalid tool outcome state")
        with self._transaction() as connection:
            self._get_run(connection, run_id, session_id)
            if step_id:
                owned_step = connection.execute(
                    "SELECT 1 FROM analysis_steps WHERE run_id = ? AND step_id = ?",
                    (run_id, step_id),
                ).fetchone()
                if owned_step is None:
                    raise AnalysisRunOwnershipError(
                        "tool outcome step belongs to another analysis run"
                    )
            existing = connection.execute(
                """SELECT * FROM analysis_tool_outcomes
                WHERE run_id = ? AND idempotency_key = ?""",
                (run_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            outcome_id = uuid.uuid4().hex
            connection.execute(
                """INSERT INTO analysis_tool_outcomes
                (outcome_id, run_id, step_id, tool_name, state, artifact_id,
                 payload_json, idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome_id,
                    run_id,
                    step_id or None,
                    tool_name,
                    state,
                    artifact_id,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    idempotency_key,
                    _utc_now(),
                ),
            )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_tool_outcomes WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone()
            return dict(row)

    def tool_outcome_count(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS count FROM analysis_tool_outcomes
                WHERE run_id = ?""",
                (run_id,),
            ).fetchone()
            return int(row["count"])

    def event_count(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM analysis_run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return int(row["count"])
