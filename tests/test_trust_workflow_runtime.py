from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.agent.hypotheses import hydrate_hypothesis_refs
from data_agent.agent.intent import TurnIntent
from data_agent.agent.trust_workflow_runtime import (
    maybe_create_hypothesis_set,
    refine_turn_intent_with_state,
)


def _intent(intent_type="intent_negotiation", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "vague",
        "data_state": "data_loaded",
        "analysis_stage": "discover",
        "recommended_action": "guide_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


def test_runtime_refines_vague_intent_with_state_routes():
    state = AnalysisSessionState(session_id="runtime_refine_routes")
    state.route_proposals = [
        {"id": "route_trend", "label": "Revenue trend", "direction": "trend"},
        {"id": "route_compare", "label": "Period compare", "direction": "period_compare"},
    ]

    refined = refine_turn_intent_with_state("help me explore this dataset", _intent(), state)

    assert refined.recommended_action == "guide_analysis"
    assert refined.ambiguities[-1]["field"] == "analysis_route"
    assert refined.ambiguities[-1]["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
        {"label": "Period compare", "direction": "period_compare"},
    ]


def test_runtime_marks_unsupported_retention_request_as_insufficient_data():
    state = AnalysisSessionState(session_id="runtime_refine_retention")
    state.dataset_contracts = [{
        "id": "contract_orders",
        "unsupported_analyses": [
            {"type": "user_level_retention", "reason": "missing user id"},
        ],
    }]
    base = _intent(
        "directed_analysis",
        clarity="clear",
        analysis_stage="execute",
        recommended_action="run_analysis",
    )

    refined = refine_turn_intent_with_state("analyze cohort retention", base, state)

    assert refined.clarity == "clarification_needed"
    assert refined.recommended_action == "request_data"
    assert refined.execution_readiness == "insufficient_data"
    assert refined.ambiguities[-1]["field"] == "unsupported_analysis"


def test_runtime_refinement_falls_back_when_state_refs_are_malformed():
    class MalformedState:
        dataset_contracts = {"not": "a list"}
        route_proposals = {"not": "a list"}

    base = _intent()

    refined = refine_turn_intent_with_state("help me explore", base, MalformedState())

    assert refined is base






def _stage3c0b_runtime_measurement(**overrides):
    measurement = {
        "metric": "conversion_rate",
        "definition": "Orders divided by visitors.",
        "value": 0.18,
        "unit": "ratio",
        "grain": "day",
        "time_scope": "2026-06",
        "population_scope": "all visitors",
        "method": "aggregate ratio",
        "denominator": "visitors",
        "limitations": ["descriptive only"],
    }
    measurement.update(overrides)
    return measurement


def _stage3c0b_runtime_evidence(evidence_id, claim, *, plan_id="plan_current", **overrides):
    record = {
        "id": evidence_id,
        "plan_id": plan_id,
        "step_id": "step_conversion",
        "claim_key": evidence_id,
        "claim": claim,
        "dataset": "orders",
        "dataset_contract_id": "contract_orders",
        "method": "grouped aggregation",
        "tool_calls": [{"name": "run_python"}],
        "result_summary": claim,
        "sample_size": 1000,
        "time_scope": "2026-06",
        "calculation_method": "orders divided by visitors",
        "method_detail": "aggregated daily visitors and orders",
        "limitations": ["descriptive only"],
        "confidence": "high",
        "evidence_requirement": "conversion_rate",
        "measurements": [_stage3c0b_runtime_measurement()],
    }
    record.update(overrides)
    return record






















def test_runtime_creates_hypothesis_set_from_direct_entry_decision(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_create", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "evidence_requirements": ["date", "metric"],
        }]

        ref = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)

        assert ref is not None
        assert state.hypothesis_sets == [ref]
        hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)
        assert hydrated[0]["route"] == "trend"
        assert len(hydrated[0]["hypotheses"]) >= 2
    finally:
        cfg.sessions_dir = old_sessions


def test_explicit_hypothesis_set_waits_for_current_plan(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_plan_first", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales", "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{"dataset": "sales", "direction": "trend"}]
        request = "请提出并检验至少两种竞争性假设"

        assert maybe_create_hypothesis_set(request, _intent("directed_analysis"), state) is None
        assert state.hypothesis_sets == []
        state.set_analysis_spec({"id": "spec_preliminary", "goal": request})
        preliminary = maybe_create_hypothesis_set(request, _intent("directed_analysis"), state)
        assert preliminary is None
        assert state.analysis_plan is None
        state.analysis_plan = {"id": "plan_current", "goal": request,
                               "contract_version": "stage3c0b.v1"}
        ref = maybe_create_hypothesis_set(request, _intent("directed_analysis"), state)
        assert ref is not None
        assert ref["plan_id"] == "plan_current"
        assert all(h["plan_id"] != "spec_preliminary" for h in state.hypothesis_sets)
        current = next(item for item in hydrate_hypothesis_refs(state.hypothesis_sets)
                       if item["id"] == ref["id"])
        assert all(item["id"].startswith(ref["id"])
                   for item in current["hypotheses"])
    finally:
        cfg.sessions_dir = old_sessions


def test_runtime_skips_duplicate_hypothesis_set_for_same_route(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_dup", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{"dataset": "sales", "direction": "trend"}]

        first = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)
        second = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)

        assert first is not None
        assert second is None
        assert len(state.hypothesis_sets) == 1
    finally:
        cfg.sessions_dir = old_sessions


def test_runtime_refreshes_existing_hypothesis_set_from_evidence(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_refresh", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{"dataset": "sales", "direction": "trend"}]

        first = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)
        hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)
        claim = hydrated[0]["hypotheses"][0]["claim"]
        state.evidence_records = [{"id": "ev_support", "claim": claim, "dataset": "sales"}]

        refreshed = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)
        refreshed_hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)

        # Contract update (P1 / D08 / H04): refreshing with matching evidence
        # text yields a candidate relation, not "supported". The original
        # requirement promoted the hypothesis via token overlap; the confirmed
        # principle keeps it undetermined pending a structured relation.
        assert first is not None
        assert refreshed is not None
        assert len(state.hypothesis_sets) == 1
        hypothesis = refreshed_hydrated[0]["hypotheses"][0]
        assert hypothesis["status"] == "inconclusive"
        assert hypothesis["related_evidence_ids"] == ["ev_support"]
        assert hypothesis["supporting_evidence_ids"] == []
        assert refreshed_hydrated[0]["status_summary"].get("supported") is None
    finally:
        cfg.sessions_dir = old_sessions


# ── P1 (D08 / H10): plan-scoped hypothesis identity ──


def test_runtime_h10_new_plan_creates_fresh_set_and_keeps_old_as_history(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_plan_isolation", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{"dataset": "sales", "direction": "trend"}]
        state.analysis_plan = {"id": "plan_a", "goal": "Trend under plan A"}
        state.evidence_records = [{
            "id": "ev_plan_a",
            "plan_id": "plan_a",
            "claim": "revenue has a directional trend over time in sales.",
            "dataset": "sales",
        }]

        first = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)
        assert first is not None
        assert first["plan_id"] == "plan_a"

        # A new analysis plan on the same dataset/route must not reuse the old
        # set's statuses: identity is plan-scoped, the old ref stays as history.
        state.analysis_plan = {"id": "plan_b", "goal": "Trend under plan B"}
        second = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)

        assert second is not None
        assert second["plan_id"] == "plan_b"
        assert second["id"] != first["id"]
        assert {ref["id"] for ref in state.hypothesis_sets} == {first["id"], second["id"]}

        hydrated = {item["id"]: item for item in hydrate_hypothesis_refs(state.hypothesis_sets)}
        fresh = hydrated[second["id"]]
        for hypothesis in fresh["hypotheses"]:
            assert hypothesis["status"] in {"proposed", "inconclusive"}
            assert hypothesis["supporting_evidence_ids"] == []
        # plan_a evidence must not even appear as related to the plan_b set.
        for hypothesis in fresh["hypotheses"]:
            assert "ev_plan_a" not in hypothesis.get("related_evidence_ids", [])
    finally:
        cfg.sessions_dir = old_sessions


def test_runtime_h10_same_plan_refresh_reuses_existing_set(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState(session_id="runtime_hyp_same_plan", data_state="data_loaded")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{"dataset": "sales", "direction": "trend"}]
        state.analysis_plan = {"id": "plan_a", "goal": "Trend under plan A"}

        first = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)
        second = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis"), state)

        assert first is not None
        assert second is None
        assert len(state.hypothesis_sets) == 1
    finally:
        cfg.sessions_dir = old_sessions


# ── P5 (D09 / H11): runtime refresh of hypothesis state ──


def _relation_state(state_session: str) -> AnalysisSessionState:
    state = AnalysisSessionState(session_id=state_session, data_state="data_loaded")
    state.dataset_contracts = [{
        "dataset": "sales",
        "quality": {"status": "ready"},
        "field_roles": {"date": ["date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [{
        "dataset": "sales",
        "direction": "trend",
        "evidence_requirements": ["date", "metric"],
    }]
    return state


def _structured_evidence(evidence_id, hypothesis_id, relation, observed, delta, claim):
    return {
        "id": evidence_id,
        "claim": claim,
        "result_summary": claim,
        "dataset": "sales",
        "method": "trend analysis",
        "measurements": [{
            "metric": "revenue",
            "definition": "revenue aggregated per period",
            "value": max(abs(delta), 1),
            "unit": "currency",
            "grain": "period",
            "population_scope": "all records",
            "time_scope": "2026-08",
            "method": "period compare",
            "denominator": "period days",
            "limitations": [],
            "delta": delta,
        }],
        "competing_hypotheses": [{
            "hypothesis_id": hypothesis_id,
            "relation": relation,
            "metric": "revenue",
            "observed": observed,
        }],
    }


def _verified_measurements_for_lifecycle(_state, records):
    """Isolate hypothesis refresh/stale tests from the separately tested receipt loader."""
    return {
        record["id"]: {
            measurement["metric"]: {
                "value": measurement["delta"],
                "direction": "increased" if measurement["delta"] > 0 else "decreased" if measurement["delta"] < 0 else "flat",
                "receipt_id": "tr_host_verified_lifecycle_fixture",
            }
            for measurement in record["measurements"]
        }
        for record in records
    }


def test_h11_new_evidence_changes_hypothesis_state_on_refresh(tmp_path, monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(
        "data_agent.agent.hypotheses.receipt_verified_hypothesis_measurements",
        _verified_measurements_for_lifecycle,
    )
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = _relation_state("runtime_h11")
        first = maybe_create_hypothesis_set(
            "show revenue trend", _intent("directed_analysis"), state,
        )
        assert first is not None
        hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)
        primary_id = hydrated[0]["hypotheses"][0]["id"]

        state.evidence_records = [
            _structured_evidence(
                "ev_h11_up", primary_id, "supports", "increased", 112,
                "Revenue increased between the compared periods.",
            ),
        ]
        refreshed = maybe_create_hypothesis_set(
            "show revenue trend", _intent("directed_analysis"), state,
        )
        assert refreshed is not None
        after_support = hydrate_hypothesis_refs(state.hypothesis_sets)[0]
        assert after_support["hypotheses"][0]["status"] == "supported"

        # 新的反证证据进入后，状态按最新快照重算为 contested，旧状态不粘滞
        state.evidence_records.append(
            _structured_evidence(
                "ev_h11_flat", primary_id, "refutes", "flat", 0,
                "Revenue was flat in the matched window.",
            ),
        )
        maybe_create_hypothesis_set(
            "show revenue trend", _intent("directed_analysis"), state,
        )
        after_conflict = hydrate_hypothesis_refs(state.hypothesis_sets)[0]
        assert after_conflict["hypotheses"][0]["status"] == "contested"
        assert len(state.hypothesis_sets) == 1
    finally:
        cfg.sessions_dir = old_sessions


def test_h11_supported_hypothesis_becomes_stale_when_its_evidence_disappears(tmp_path, monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(
        "data_agent.agent.hypotheses.receipt_verified_hypothesis_measurements",
        _verified_measurements_for_lifecycle,
    )
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = _relation_state("runtime_h11_stale")
        first = maybe_create_hypothesis_set(
            "show revenue trend", _intent("directed_analysis"), state,
        )
        hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)
        primary_id = hydrated[0]["hypotheses"][0]["id"]
        state.evidence_records = [
            _structured_evidence(
                "ev_stale", primary_id, "supports", "increased", 112,
                "Revenue increased between the compared periods.",
            ),
        ]
        maybe_create_hypothesis_set(
            "show revenue trend", _intent("directed_analysis"), state,
        )
        supported = hydrate_hypothesis_refs(state.hypothesis_sets)[0]
        assert supported["hypotheses"][0]["status"] == "supported"

        # 依赖证据消失：已判定的假设转为 stale（历史保留），不退回 proposed 静默丢失
        state.evidence_records = []
        maybe_create_hypothesis_set(
            "show revenue trend", _intent("directed_analysis"), state,
        )
        after = hydrate_hypothesis_refs(state.hypothesis_sets)[0]
        assert after["hypotheses"][0]["status"] == "stale"
        assert after["hypotheses"][0]["supporting_evidence_ids"] == []
    finally:
        cfg.sessions_dir = old_sessions


# ── P7-L3/B04: data-version change invalidates evidence, hypotheses go stale ──


def _binding_evidence(evidence_id, hypothesis_id, fingerprint, delta=10, dataset="sales"):
    return {
        "id": evidence_id,
        "claim": "Revenue shows a rising trend over time.",
        "result_summary": "revenue rising",
        "dataset": dataset,
        "method": "trend analysis",
        "measurements": [{"metric": "revenue", "delta": delta, "value": 100 + delta}],
        "competing_hypotheses": [{
            "hypothesis_id": hypothesis_id, "relation": "supports",
            "metric": "revenue", "observed": "increased" if delta else "flat",
        }],
        "result_bindings": [{
            "receipt_id": "tr_v1", "tool_call_id": "", "result_sha256": "",
            "data_identities": {dataset: {"fingerprint": fingerprint}},
        }],
    }


def test_b04_freshness_gate_is_pure_and_conservative():
    from data_agent.agent.trust_workflow_runtime import _split_evidence_by_data_freshness

    mismatch = _binding_evidence("ev_mismatch", "h1", "fp_v1")
    # 绑定到当前工作区不存在的数据集：无法判定 → 保守保留
    absent_dataset = _binding_evidence("ev_absent", "h1", "fp_x", dataset="archive")
    current = {
        "sales": {"fingerprint": "fp_v2"},
        "orders": {"fingerprint": "fp_o"},
    }

    fresh, exclusions = _split_evidence_by_data_freshness(
        [mismatch, absent_dataset], current,
    )

    assert [record["id"] for record in fresh] == ["ev_absent"], "仅版本确实变化的证据被排除"
    assert exclusions == [{
        "evidence_id": "ev_mismatch",
        "reason": "data_version_changed",
        "dataset": "sales",
        "bound_fingerprint": "fp_v1",
        "current_fingerprint": "fp_v2",
    }]


def _produce_b04_current_relation_metadata(context, state, local_workspace):
    from contextlib import nullcontext
    from data_agent.tools.data_io import _record_trust_workflow
    context.analysis_state = state
    first = not any(r.get("artifact_path") for r in state.dataset_contracts)
    if first:
        state.dataset_contracts = []
        state.route_proposals = []
        state.cleaning_logs = []
    state.set_active_dataset("sales")
    state.active_scope["active_mode"] = "data_loaded"
    frame = local_workspace.get("sales")
    # Fresh production reads get their own grant; the previous version's
    # planning grant never becomes raw-frame permission on the new turn.
    with context.planning_workspace_scope(["sales"]) if first else nullcontext():
        _record_trust_workflow(session_id=state.session_id, state=state, dataset="sales",
            df=frame, applied=[], needs_confirm=[], quality={},
            interpretation_data={"columns_classified":{"time_columns":["date"], "key_metrics":["revenue"]}}, detail_path="")


def test_b04_version_change_turns_supported_hypothesis_stale(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace

    monkeypatch.setattr(
        "data_agent.agent.hypotheses.receipt_verified_hypothesis_measurements",
        _verified_measurements_for_lifecycle,
    )
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        local_workspace = Workspace()
        context = AgentContext(session_id="runtime_b04", workspace=local_workspace)
        with use_agent_context(context):
            local_workspace.add("sales__raw", __import__("pandas").DataFrame({"date": __import__("pandas").date_range("2026-01-01", periods=2), "revenue": [10, 20]}))
            local_workspace.derive(
                "sales__raw", "sales", local_workspace.get("sales__raw"), "initial analysis version",
            )
            first_identity = local_workspace.get_data_identity("sales")
            state = _relation_state("runtime_b04")
            _produce_b04_current_relation_metadata(context, state, local_workspace)
            first = maybe_create_hypothesis_set(
                "show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state,
            )
            assert first is not None
            hydrated = hydrate_hypothesis_refs(state.hypothesis_sets)
            primary_id = hydrated[0]["hypotheses"][0]["id"]

            state.evidence_records = [_binding_evidence(
                "ev_b04_v1", primary_id, first_identity["fingerprint"],
            )]
            maybe_create_hypothesis_set(
                "show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state,
            )
            before = hydrate_hypothesis_refs(state.hypothesis_sets)[0]
            assert before["hypotheses"][0]["status"] == "supported"

            # 真实的同名版本替换：归档 v1，再创建 v2；不篡改旧证据。
            assert local_workspace.archive_version("sales") == "sales__history"
            local_workspace.add("sales__raw_2", __import__("pandas").DataFrame({"date": __import__("pandas").date_range("2026-01-01", periods=2), "revenue": [10, 10]}))
            local_workspace.derive(
                "sales__raw_2", "sales", local_workspace.get("sales__raw_2"), "reloaded analysis version",
            )
            assert local_workspace.get_data_identity("sales__history") == first_identity
            _produce_b04_current_relation_metadata(context, state, local_workspace)

            refreshed = maybe_create_hypothesis_set(
                "show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state,
            )
            assert refreshed is not None
            after = hydrate_hypothesis_refs(state.hypothesis_sets)[0]
            assert after["hypotheses"][0]["status"] == "stale"
            assert after["hypotheses"][0]["supporting_evidence_ids"] == []
            assert after.get("evidence_exclusions") and after["evidence_exclusions"][0]["reason"] == "data_version_changed"
            # 假设集保留（历史），证据记录本身不删除。
            assert len(state.hypothesis_sets) == 1
            assert state.evidence_records
    finally:
        cfg.sessions_dir = old_sessions


def test_b04_new_plan_does_not_leave_old_version_verdict_current(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace
    import pandas as pd

    monkeypatch.setattr(
        "data_agent.agent.hypotheses.receipt_verified_hypothesis_measurements",
        _verified_measurements_for_lifecycle,
    )
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        local_workspace = Workspace()
        context = AgentContext(session_id="runtime_b04_new_plan", workspace=local_workspace)
        with use_agent_context(context):
            local_workspace.add("sales__raw", pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "revenue": [10, 20]}))
            local_workspace.derive(
                "sales__raw", "sales", local_workspace.get("sales__raw"), "initial version",
            )
            v1 = local_workspace.get_data_identity("sales")
            state = _relation_state("runtime_b04_new_plan")
            _produce_b04_current_relation_metadata(context, state, local_workspace)
            state.analysis_plan = {"id": "plan_v1"}
            first = maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            old_id = hydrate_hypothesis_refs([first])[0]["hypotheses"][0]["id"]
            record = _binding_evidence("ev_old", old_id, v1["fingerprint"])
            record["plan_id"] = "plan_v1"
            state.evidence_records = [record]
            maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            assert hydrate_hypothesis_refs([state.hypothesis_sets[0]])[0]["hypotheses"][0]["status"] == "supported"

            assert local_workspace.archive_version("sales") == "sales__history"
            local_workspace.add("sales__raw_2", pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "revenue": [10, 10]}))
            local_workspace.derive(
                "sales__raw_2", "sales", local_workspace.get("sales__raw_2"), "new version",
            )
            _produce_b04_current_relation_metadata(context, state, local_workspace)
            state.analysis_plan = {"id": "plan_v2"}
            maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            assert len(state.hypothesis_sets) == 2
            old = hydrate_hypothesis_refs([state.hypothesis_sets[0]])[0]
            assert old["hypotheses"][0]["status"] == "stale"
            assert old["hypotheses"][0]["evidence_relations"] == []
            assert old["evidence_exclusions"][0]["evidence_id"] == "ev_old"
            new = hydrate_hypothesis_refs([state.hypothesis_sets[1]])[0]
            assert new["hypotheses"][0]["status"] != "supported"
            maybe_create_hypothesis_set("show revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            old_again = hydrate_hypothesis_refs([state.hypothesis_sets[0]])[0]
            assert old_again["hypotheses"][0]["status"] == "stale"
            assert old_again["hypotheses"][0]["evidence_relations"] == []
            assert state.evidence_records == [record]
    finally:
        cfg.sessions_dir = old_sessions


def test_b04_same_plan_other_route_also_loses_old_version_verdict(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace
    import pandas as pd

    monkeypatch.setattr(
        "data_agent.agent.hypotheses.receipt_verified_hypothesis_measurements",
        _verified_measurements_for_lifecycle,
    )
    route = {"value": "trend"}
    monkeypatch.setattr(
        "data_agent.agent.analysis_entry.decide_analysis_entry",
        lambda *_args: {"decision": "direct_analysis", "dataset": "sales", "route": route["value"]},
    )
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        local_workspace = Workspace()
        context = AgentContext(session_id="runtime_b04_other_route", workspace=local_workspace)
        with use_agent_context(context):
            local_workspace.add("sales__raw", pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "revenue": [10, 20]}))
            local_workspace.derive("sales__raw", "sales", local_workspace.get("sales__raw"), "v1")
            v1 = local_workspace.get_data_identity("sales")
            state = _relation_state("runtime_b04_other_route")
            state.analysis_plan = {"id": "same_plan"}
            first = maybe_create_hypothesis_set("revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            primary_id = hydrate_hypothesis_refs([first])[0]["hypotheses"][0]["id"]
            record = _binding_evidence("ev_same_plan_old", primary_id, v1["fingerprint"])
            record["plan_id"] = "same_plan"
            state.evidence_records = [record]
            maybe_create_hypothesis_set("revenue trend", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            assert hydrate_hypothesis_refs([state.hypothesis_sets[0]])[0]["hypotheses"][0]["status"] == "supported"

            assert local_workspace.archive_version("sales") == "sales__history"
            local_workspace.add("sales__raw_2", pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "revenue": [10, 10]}))
            local_workspace.derive("sales__raw_2", "sales", local_workspace.get("sales__raw_2"), "v2")
            route["value"] = "distribution"
            maybe_create_hypothesis_set("revenue distribution", _intent("directed_analysis", clarity="clear", recommended_action="run_analysis"), state)
            assert len(state.hypothesis_sets) == 2
            old = hydrate_hypothesis_refs([state.hypothesis_sets[0]])[0]
            assert old["hypotheses"][0]["status"] == "stale"
            assert old["evidence_exclusions"][0]["evidence_id"] == "ev_same_plan_old"
            assert state.hypothesis_sets[1]["route"] == "distribution"
    finally:
        cfg.sessions_dir = old_sessions
