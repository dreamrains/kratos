"""Data Agent V2 Slice 1 semantic SSE and refresh endpoints."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict

from flask import Blueprint, Response, jsonify, request

from data_agent.config import get_config
from data_agent.v2.slice1 import Slice1DescriptiveRuntime
from data_agent.v2.slice2 import Slice2FactorRuntime
from data_agent.v2.slice3 import Slice3TransformationRuntime
from data_agent.v2.slice4a import Slice4AGroupComparisonRuntime
from data_agent.v2.slice4b import Slice4BTimeSeriesRuntime
from data_agent.v2.slice4c import Slice4CForecastRuntime
from data_agent.v2.slice4d import Slice4DMultiFindingRuntime
from data_agent.v2.slice4e import Slice4EExploratoryRuntime
from data_agent.v2.models import EventType
from data_agent.v2.store import V2FactStore
from data_agent.v2.time_series import TimeAggregation, TimeFrequency
from data_agent.v2.transformation import TransformationStore
from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.router import AnalysisRouter
from data_agent.v2.execution_control import (
    ActiveRunRegistry,
    StopRequestConflict,
)
from data_agent.v2.steer import SteerConflict, SteerStatus, SteerStore
from data_agent.web.event_bus import EventQueue, SSEEvent

v2_bp = Blueprint("v2", __name__)
ACTIVE_V2_RUNS = ActiveRunRegistry()


def _request_context(payload: dict, analysis_kind: str) -> dict[str, str]:
    allowed = {
        "filename",
        "metric",
        "target",
        "features",
        "analysis_unit",
        "time_field",
        "question",
        "date_column",
        "group",
        "recommendation_intent",
        "action_risk",
        "reversible",
        "frequency",
        "aggregation",
        "horizon",
        "purpose",
    }
    context = {"analysis_kind": analysis_kind}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            normalized = ",".join(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, bool):
            normalized = str(value).lower()
        else:
            normalized = str(value or "").strip()
        if normalized:
            context[key] = normalized
    return context


def _resume_payload(payload: dict, analysis_kind: str) -> dict:
    """Freeze method inputs without carrying request routing identities forward."""

    frozen = dict(payload)
    for key in ("session_id", "turn_id", "steer_id", "client_request_id"):
        frozen.pop(key, None)
    frozen["analysis_kind"] = analysis_kind
    return frozen


def _sse_response(queue: EventQueue) -> Response:
    return Response(
        queue.iter(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@v2_bp.post("/v2/analyze")
def analyze_v2() -> Response:
    """Run one explicitly selected V2 method through the unified envelope."""

    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    cfg = get_config()
    router = AnalysisRouter(cfg.sessions_resolved, cfg.inbox_dir)
    steer_store = None
    queued_steer = None
    try:
        requested_steer_id = str(payload.get("steer_id") or "").strip()
        if requested_steer_id:
            session_id = str(payload.get("session_id") or "").strip()
            if not session_id:
                return jsonify({"error": "session_id is required with steer_id"}), 400
            steer_store = SteerStore(cfg.sessions_resolved, session_id)
            queued_steer = steer_store.get(requested_steer_id)
            if queued_steer.status is not SteerStatus.QUEUED:
                return jsonify(
                    {
                        "error": f"steer is already {queued_steer.status.value}",
                        "steer": queued_steer.to_dict(),
                    }
                ), 409
            effective_payload = dict(queued_steer.resume_payload)
            effective_payload["question"] = queued_steer.message
        else:
            effective_payload = payload
            session_id = str(
                payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}"
            ).strip()
        kind = router.parse_kind(effective_payload.get("analysis_kind", ""))
        if kind is None:
            return jsonify({"error": "analysis_kind is required"}), 400
        turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
        prepared = router.prepare(
            analysis_kind=kind,
            session_id=session_id,
            turn_id=turn_id,
            payload=effective_payload,
        )
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    store = V2FactStore(cfg.sessions_resolved, session_id)
    steer_store = steer_store or SteerStore(cfg.sessions_resolved, session_id)
    resume_payload = _resume_payload(effective_payload, kind.value)
    try:
        active = ACTIVE_V2_RUNS.register(
            store=store,
            steer_store=steer_store,
            session_id=session_id,
            turn_id=turn_id,
            request_context=_request_context(effective_payload, kind.value),
            resume_payload=resume_payload,
        )
    except StopRequestConflict as exc:
        return jsonify({"error": str(exc)}), 409
    if queued_steer is not None:
        try:
            steer_store.consume(queued_steer.steer_id, target_turn_id=turn_id)
        except SteerConflict as exc:
            ACTIVE_V2_RUNS.unregister(active)
            return jsonify({"error": str(exc)}), 409
    queue = EventQueue()

    def run() -> None:
        try:
            for event in active.stream(prepared.stream()):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {"session_id": session_id, "turn_id": turn_id, "status": "failed",
                     "error_code": type(exc).__name__, "message": str(exc)},
                )
            )
        finally:
            ACTIVE_V2_RUNS.unregister(active)
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/runs/steer")
def steer_v2_run() -> Response:
    """Persist a message for the next turn without mutating the active run."""

    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    session_id = str(payload.get("session_id") or "").strip()
    turn_id = str(payload.get("turn_id") or "").strip()
    expected_run_id = str(payload.get("expected_run_id") or "").strip()
    client_request_id = str(payload.get("client_request_id") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not all((session_id, turn_id, expected_run_id, client_request_id, message)):
        return jsonify(
            {
                "error": (
                    "session_id, turn_id, expected_run_id, client_request_id, "
                    "and message are required"
                )
            }
        ), 400
    try:
        store = SteerStore(get_config().sessions_resolved, session_id)
        existing_steers = store.list_for_turn(turn_id)
        receipt = ACTIVE_V2_RUNS.request_steer(
            session_id,
            turn_id,
            expected_run_id=expected_run_id,
            client_request_id=client_request_id,
            message=message,
        )
    except StopRequestConflict as exc:
        matching = next(
            (
                item
                for item in existing_steers
                if item.client_request_id == client_request_id
            ),
            None,
        )
        if (
            matching is not None
            and matching.source_run_id == expected_run_id
            and matching.message == message
        ):
            return jsonify(matching.to_dict()), 202
        return jsonify({"error": str(exc)}), 409
    except SteerConflict as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(receipt.to_dict()), 202


@v2_bp.post("/v2/runs/stop")
def stop_v2_run() -> Response:
    """Persist interruption facts, then signal cooperative generator shutdown."""

    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    session_id = str(payload.get("session_id") or "").strip()
    turn_id = str(payload.get("turn_id") or "").strip()
    if not session_id or not turn_id:
        return jsonify({"error": "session_id and turn_id are required"}), 400
    try:
        receipt = ACTIVE_V2_RUNS.request_stop(session_id, turn_id)
    except StopRequestConflict as exc:
        store = V2FactStore(get_config().sessions_resolved, session_id)
        try:
            turn = store.read_turn_blocks(turn_id)
        except KeyError:
            return jsonify({"error": str(exc)}), 409
        if turn.get("status") == "interrupted":
            control = store.read_turn_control(turn_id)
            run_id = str(control.get("run_id") or "")
            commitment_ids = tuple(
                dict.fromkeys(
                    item.commitment_id
                    for item in store.read_events()
                    if item.run_id == run_id
                    and item.event_type is EventType.USER_INTERRUPTED
                )
            )
            return jsonify(
                {
                    "status": "interrupted",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "run_id": run_id,
                    "commitment_ids": list(commitment_ids),
                }
            ), 202
        if turn.get("status") == "finalized":
            return jsonify({"error": "run is already completed"}), 409
        return jsonify({"error": str(exc)}), 409
    return jsonify(asdict(receipt)), 202


@v2_bp.post("/v2/describe")
def describe_v2() -> Response:
    """Run the Slice 1 explicit single-metric descriptive journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    cfg = get_config()
    runtime = Slice1DescriptiveRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                metric=str(payload.get("metric") or ""),
                question=str(payload.get("question") or ""),
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/factors")
def factors_v2() -> Response:
    """Run the Slice 2 explicit continuous factor-relationship journey."""

    payload = request.get_json(force=True)
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        return jsonify({"error": "features must be a JSON array"}), 400
    features = tuple(str(item or "").strip() for item in raw_features if str(item or "").strip())
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    cfg = get_config()
    runtime = Slice2FactorRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                target=str(payload.get("target") or ""),
                features=features,
                analysis_unit=str(payload.get("analysis_unit") or ""),
                time_field=str(payload.get("time_field") or ""),
                question=str(payload.get("question") or ""),
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/transform-dates")
def transform_dates_v2() -> Response:
    """Start the Slice 3 safe date-transformation journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    cfg = get_config()
    runtime = Slice3TransformationRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.start(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                date_column=str(payload.get("date_column") or ""),
                question=str(payload.get("question") or ""),
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/transform-dates/resolve")
def resolve_transform_dates_v2() -> Response:
    """Append a bound semantic decision and resume the Slice 3 turn."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or "").strip()
    turn_id = str(payload.get("turn_id") or "").strip()
    if not session_id or not turn_id:
        return jsonify({"error": "session_id and turn_id are required"}), 400
    cfg = get_config()
    runtime = Slice3TransformationRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.resolve(
                session_id=session_id,
                turn_id=turn_id,
                proposal_id=str(payload.get("proposal_id") or ""),
                option_key=str(payload.get("option_key") or ""),
                expected_parent_version_id=str(
                    payload.get("expected_parent_version_id") or ""
                ),
                expected_parent_content_fingerprint=str(
                    payload.get("expected_parent_content_fingerprint") or ""
                ),
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/group-comparison")
def group_comparison_v2() -> Response:
    """Run the Slice 4A explicit two-group comparison journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    try:
        intent = RecommendationIntent(str(payload.get("recommendation_intent") or "none"))
        risk = ActionRisk(str(payload.get("action_risk") or "low"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    raw_reversible = payload.get("reversible", True)
    if not isinstance(raw_reversible, bool):
        return jsonify({"error": "reversible must be a boolean"}), 400
    cfg = get_config()
    runtime = Slice4AGroupComparisonRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                metric=str(payload.get("metric") or ""),
                group=str(payload.get("group") or ""),
                analysis_unit=str(payload.get("analysis_unit") or ""),
                question=str(payload.get("question") or ""),
                recommendation_intent=intent,
                action_risk=risk,
                reversible=raw_reversible,
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/time-trend")
def time_trend_v2() -> Response:
    """Run the Slice 4B explicit historical-trend journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    try:
        frequency = TimeFrequency(str(payload.get("frequency") or "daily"))
        aggregation = TimeAggregation(str(payload.get("aggregation") or "sum"))
        intent = RecommendationIntent(str(payload.get("recommendation_intent") or "none"))
        risk = ActionRisk(str(payload.get("action_risk") or "low"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    raw_reversible = payload.get("reversible", True)
    if not isinstance(raw_reversible, bool):
        return jsonify({"error": "reversible must be a boolean"}), 400
    cfg = get_config()
    runtime = Slice4BTimeSeriesRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                time_field=str(payload.get("time_field") or ""),
                metric=str(payload.get("metric") or ""),
                frequency=frequency,
                aggregation=aggregation,
                question=str(payload.get("question") or ""),
                recommendation_intent=intent,
                action_risk=risk,
                reversible=raw_reversible,
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/forecast")
def forecast_v2() -> Response:
    """Run the Slice 4C explicit backtested baseline forecast journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    raw_horizon = payload.get("horizon", 7)
    if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int):
        return jsonify({"error": "horizon must be an integer"}), 400
    if raw_horizon <= 0 or raw_horizon > 30:
        return jsonify({"error": "horizon must be between 1 and 30"}), 400
    try:
        frequency = TimeFrequency(str(payload.get("frequency") or "daily"))
        aggregation = TimeAggregation(str(payload.get("aggregation") or "sum"))
        intent = RecommendationIntent(str(payload.get("recommendation_intent") or "none"))
        risk = ActionRisk(str(payload.get("action_risk") or "low"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    raw_reversible = payload.get("reversible", True)
    if not isinstance(raw_reversible, bool):
        return jsonify({"error": "reversible must be a boolean"}), 400
    cfg = get_config()
    runtime = Slice4CForecastRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                time_field=str(payload.get("time_field") or ""),
                metric=str(payload.get("metric") or ""),
                frequency=frequency,
                aggregation=aggregation,
                horizon=raw_horizon,
                question=str(payload.get("question") or ""),
                recommendation_intent=intent,
                action_risk=risk,
                reversible=raw_reversible,
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/multi-finding")
def multi_finding_v2() -> Response:
    """Run the Slice 4D trend-plus-group synthesis journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    try:
        frequency = TimeFrequency(str(payload.get("frequency") or "daily"))
        aggregation = TimeAggregation(str(payload.get("aggregation") or "mean"))
        intent = RecommendationIntent(str(payload.get("recommendation_intent") or "none"))
        risk = ActionRisk(str(payload.get("action_risk") or "low"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    raw_reversible = payload.get("reversible", True)
    if not isinstance(raw_reversible, bool):
        return jsonify({"error": "reversible must be a boolean"}), 400
    cfg = get_config()
    runtime = Slice4DMultiFindingRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                time_field=str(payload.get("time_field") or ""),
                metric=str(payload.get("metric") or ""),
                frequency=frequency,
                aggregation=aggregation,
                group=str(payload.get("group") or ""),
                analysis_unit=str(payload.get("analysis_unit") or ""),
                question=str(payload.get("question") or ""),
                recommendation_intent=intent,
                action_risk=risk,
                reversible=raw_reversible,
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id, "turn_id": turn_id,
                        "status": "failed", "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.post("/v2/exploratory-python")
def exploratory_python_v2() -> Response:
    """Run a structured core answer plus non-promotable Python exploration."""

    payload = request.get_json(force=True)
    purpose = str(payload.get("purpose") or "").strip()
    code = str(payload.get("code") or "").strip()
    if not purpose or not code:
        return jsonify({"error": "purpose and code are required"}), 400
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    cfg = get_config()
    runtime = Slice4EExploratoryRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id, turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                metric=str(payload.get("metric") or ""),
                question=str(payload.get("question") or ""),
                purpose=purpose, code=code,
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {"session_id": session_id, "turn_id": turn_id, "status": "failed",
                     "error_code": type(exc).__name__, "message": str(exc)},
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.get("/v2/sessions/<session_id>/turns/<turn_id>")
def get_v2_turn(session_id: str, turn_id: str):
    sessions_root = get_config().sessions_resolved
    store = V2FactStore(sessions_root, session_id)
    try:
        turn = store.read_turn_blocks(turn_id)
    except KeyError:
        return jsonify({"error": "V2 turn not found"}), 404
    proposal_id = turn.get("request_context", {}).get("proposal_id", "")
    if proposal_id:
        try:
            state = TransformationStore(
                get_config().sessions_resolved, session_id
            ).project(proposal_id)
            turn["transformation"] = {
                "status": state.status,
                "proposal": asdict(state.proposal),
                "decision": asdict(state.decision) if state.decision else None,
            }
        except KeyError:
            turn["transformation"] = None
    turn["steers"] = [
        item.to_dict()
        for item in SteerStore(sessions_root, session_id).list_for_turn(turn_id)
    ]
    return jsonify(turn)


@v2_bp.get("/v2/sessions/<session_id>/artifacts/<chart_id>")
def get_v2_chart(session_id: str, chart_id: str) -> Response:
    try:
        html = V2FactStore(get_config().sessions_resolved, session_id).read_chart_html(chart_id)
    except ValueError:
        return jsonify({"error": "Invalid V2 artifact identity"}), 400
    except KeyError:
        return jsonify({"error": "V2 chart not found"}), 404
    return Response(
        html,
        mimetype="text/html",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
