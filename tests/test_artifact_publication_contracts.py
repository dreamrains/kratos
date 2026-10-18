"""Artifact, publication, chart, and sandbox contracts; no Provider required."""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine


@pytest.fixture
def context(tmp_path, monkeypatch):
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.config import get_config
    from data_agent.session.workspace import Workspace
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    monkeypatch.setattr("data_agent.tools.visualization._current_session_id", "")
    ctx = AgentContext(session_id="artifact-contracts", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id=ctx.session_id)
    with use_agent_context(ctx):
        yield ctx


def test_stdout_dictionary_and_nested_details_do_not_require_inference(context, monkeypatch):
    from data_agent.tools.evidence_statistics import bind_computed_statistics
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    values = {
        "r1": {"output": "{'rows': np.int64(71), 'total': np.float64(1818.0)}\n"},
        "r2": {"shape": [71, 7], "quality": {"missing": 0}},
    }
    def load(ref):
        rid = ref.split("/")[-1].split("_")[0]
        return values[rid], {"receipt_id": rid, "result_ref": ref}
    monkeypatch.setattr("data_agent.tools.result_reference.load_result_reference", load)
    receipts = [{"id": rid, "tool_call_id": rid, "tool_name": tool,
                 "structured_result_sha256": "validated", "arguments": args}
                for rid, tool, args in [("r1", "run_python", {"code": "print(result)"}),
                                        ("r2", "quick_profile", {"name": "orders"})]]
    payload = {"statistical_details": {"sample_size": 999, "significance": "p<0.01"}}
    bind_computed_statistics(payload, receipts)
    _mark_statistical_detail_status(payload)
    assert payload["metrics"]["run_python"]["rows"] == 71
    assert "significance" not in payload["statistical_detail_required_fields"]
    assert payload.get("significance") != "p<0.01"
    assert "statistical_details" not in payload
    assert payload.get("sample_size") != 999
    assert payload["statistical_inference"] is False


def test_untyped_stdout_stays_unverified_with_actionable_detail(context, monkeypatch):
    from data_agent.tools.evidence_statistics import bind_computed_statistics
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    monkeypatch.setattr("data_agent.tools.result_reference.load_result_reference",
                        lambda ref: ({"output": "rows=71\ntotal=1818\n"}, {"receipt_id": "r"}))
    payload = {"metrics": {"invented": 999}, "statistical_details": {"metrics": {"invented": 999}}}
    bind_computed_statistics(payload, [{"id": "r", "tool_call_id": "r", "tool_name": "run_python",
                                      "structured_result_sha256": "validated", "arguments": {"code": "print('rows=71')"}}])
    _mark_statistical_detail_status(payload)
    assert payload["statistical_detail_status"] == "missing"
    assert not payload.get("metrics")
    assert payload["statistical_projection_gaps"][0]["reason"] == "untyped_sandbox_output"


def test_evidence_paths_are_immutable_and_registration_is_atomic(context, monkeypatch):
    from data_agent.tools.analysis_flow import _write_analysis_artifact
    from data_agent.session.history import list_artifacts
    from data_agent.tools.file_ops import _safe_path
    monkeypatch.setattr("data_agent.tools.analysis_flow._session_id", lambda: context.session_id)
    payloads = [{"id": f"ev-{i}", "claim": f"claim {i}"} for i in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: _write_analysis_artifact("evidence_record", p), payloads))
    assert len({r["saved"] for r in results}) == 12
    for result, payload in zip(results, payloads):
        assert json.loads(_safe_path(result["saved"]).read_text(encoding="utf8")) == payload
    assert len(list_artifacts(context.session_id)) == 12
    repeated = _write_analysis_artifact("evidence_record", payloads[0])
    assert repeated["saved"] == results[0]["saved"]
    assert len(list_artifacts(context.session_id)) == 12
    revised = _write_analysis_artifact("evidence_record", {**payloads[0], "claim": "revision"})
    assert revised["saved"] != repeated["saved"]
    assert json.loads(_safe_path(repeated["saved"]).read_text(encoding="utf8")) == payloads[0]


def test_read_file_pages_survive_agent_compaction_without_recursive_refs(context):
    from data_agent.agent.loop import AgentLoop
    from data_agent.tools.file_ops import _safe_path, read_file
    from data_agent.tools.registry import ToolResult
    path = _safe_path("tool_outputs/long_detail.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps({"output": "long-data-" * 2500}, ensure_ascii=False)
    path.write_text(original, encoding="utf8")
    loop = AgentLoop(client=object(), session_id=context.session_id)
    offset, parts = 0, []
    while True:
        page = read_file("tool_outputs/long_detail.json", offset=offset, max_chars=2000)
        delivered = loop._compact_tool_output(ToolResult.from_str(page), SimpleNamespace(id=f"read{offset}", name="read_file"))
        parsed = json.loads(delivered)
        parts.append(parsed["content"])
        assert parsed["path"] == "tool_outputs/long_detail.json"
        if parsed["next_offset"] is None:
            break
        assert parsed["next_offset"] > offset
        offset = parsed["next_offset"]
    assert "".join(parts) == original


def test_generated_output_loads_through_same_isolated_reference(context):
    from data_agent.tools.file_ops import write_file, _safe_path
    from data_agent.tools.data_io import _resolve_source
    write_file("cohort_paid_active.csv", "cohort,users\n2026-02,45\n")
    short = "output/cohort_paid_active.csv"
    assert _resolve_source(short) == _safe_path(short)
    assert _resolve_source(f"sessions/{context.session_id}/{short}") == _safe_path(short)
    with pytest.raises(ValueError):
        _resolve_source("sessions/another-session/output/cohort_paid_active.csv")


def test_reply_identity_uses_persisted_text_and_rejects_cross_session(context):
    from data_agent.session.history import save_session, load_session
    from data_agent.session.public_messages import assistant_replies
    from data_agent.tools.report import export_assistant_reply
    save_session([{"role": "user", "content": "analyze"},
                  {"role": "assistant", "content": "Intermediate"},
                  {"role": "tool", "content": "computed"},
                  {"role": "assistant", "content": "Final"}], context.session_id)
    reply = assistant_replies(load_session(context.session_id)["messages"])[0]
    assert reply["reply_id"]
    result = export_assistant_reply(context.session_id, "IntermediateFinal", reply_id=reply["reply_id"])
    assert result.get("status") == "exported", result
    assert export_assistant_reply("other", "", reply_id=reply["reply_id"])["error_type"] == "unbound_reply"


def test_normalized_title_cannot_silently_plot_raw_values(context, monkeypatch):
    from data_agent.tools.visualization import create_chart
    context.workspace.add("series", pd.DataFrame({"date": pd.date_range("2021-03-01", periods=3),
        "purchase": [1142., 571., 2284.], "banner": [424.77, 200., 500.], "video": [312.93, 400., 300.]}))
    monkeypatch.setattr("data_agent.tools.visualization._save_chart", lambda *args, **kwargs: "saved")
    result = create_chart("line", "series", title="三项收入（首日=100）", x_col="date",
                          y_col="purchase,banner,video", scale_mode="normalize")
    assert json.loads(result)["error_code"] == "scale_label_mismatch"


def test_index100_line_scales_arrays_and_preserves_source(context, monkeypatch):
    from data_agent.tools.visualization import create_chart
    source = pd.DataFrame({"day": [1, 2, 3], "a": [1142., 571., 2284.], "b": [424.77, 849.54, 212.385]})
    context.workspace.add("series", source.copy())
    captured = []
    monkeypatch.setattr("data_agent.tools.visualization._save_chart", lambda fig, *args, **kwargs: captured.append(fig) or "saved")
    assert create_chart("line", "series", x_col="day", y_col="a,b", scale_mode="index100") == "saved"
    assert list(captured[0].data[0].y) == pytest.approx([100, 50, 200])
    assert list(captured[0].data[1].y) == pytest.approx([100, 200, 50])
    pd.testing.assert_frame_equal(context.workspace.get("series"), source)


def test_top_n_schema_and_argument_validation_agree(context):
    from data_agent.tools.eda import top_n
    from data_agent.tools.registry import registry
    context.workspace.add("values", pd.DataFrame({"amount": [5, 1, 8]}))
    schema = registry.get("top_n").parameters["properties"]
    assert schema["n"]["type"] == "integer"
    assert schema["ascending"]["type"] == "boolean"
    for args in ({"n": "2"}, {"ascending": "false"}, {"n": True}):
        result = registry.execute("top_n", {"name": "values", "sort_by": "amount", **args})
        assert result.data["error_type"] == "invalid_tool_arguments"
    result = registry.execute("top_n", {"name": "values", "sort_by": "amount", "n": 2, "ascending": False})
    assert [row["amount"] for row in result.data["records"]] == [8, 5]


def test_autosave_and_reconstruction_preserve_derived_values_and_identity(context):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.config import get_config
    from data_agent.session.workspace import Workspace
    loop = AgentLoop(client=object(), session_id=context.session_id)
    with use_agent_context(loop.context):
        loop.context.workspace.add("source", pd.DataFrame({"x": [1, 2, 3]}))
        frame = pd.DataFrame({"x": [4, 6]}, index=[1, 2])
        loop.context.workspace.derive("source", "derived", frame, expression="filtered double")
        expected_identity = loop.context.workspace.get_data_identity("derived")
        loop.messages = [{"role": "user", "content": "derive"}, {"role": "assistant", "content": "computed"}]
        loop._auto_save()
    meta = get_config().sessions_resolved / context.session_id / "workspace_meta.json"
    assert "derived" in json.loads(meta.read_text(encoding="utf8"))
    restored = AgentLoop(client=object(), session_id=context.session_id)
    restored._restore_workspace()
    with use_agent_context(restored.context):
        pd.testing.assert_frame_equal(restored.context.workspace.get("derived"), frame)
        assert restored.context.workspace.get_data_identity("derived") == expected_identity


def test_autosave_without_workspace_scope_still_persists_session(context):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.history import load_session

    loop = AgentLoop(client=object(), session_id=context.session_id)
    loop.messages = [{"role": "user", "content": "compact"}]
    with use_agent_context(loop.context):
        assert loop.context.workspace_scope is None
        loop._auto_save()

    saved = load_session(context.session_id)
    assert saved is not None
    assert saved["messages"] == loop.messages


def test_publication_scope_rejects_unperformed_test_and_fit_extrapolation(engine):
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":range(1,8),"retention":[.4,.3,.25,.2,.15,.12,.1]}))
    request(loop,"拟合当前观测",{'kind': 'series', 'scope': {'datasets': ['orders']}})
    execute(loop,"curve_fitting",{"name":"orders","x_col":"day","y_col":"retention"})
    snapshot=snapshot_for_turn(loop)
    facts=snapshot.as_dict()["claims"]
    assert next(c["value"] for c in facts if c["label"]=="curve_fitting：claim_ceiling")=="descriptive"
    assert not any(c["target"]["tool"] in {"ab_test","forecast"} for c in facts)
    raw=json.loads(draft(snapshot))
    allowed=set(snapshot.as_dict()["requirements"][0]["claim_ids"])
    raw["sections"][0]["parts"]=[p for p in raw["sections"][0]["parts"] if p.get("ref") in allowed]
    raw["sections"][0]["parts"] += [{"kind":"claim","ref":"unperformed_test"},{"kind":"claim","ref":"future_d60"}]
    answer=PublicationService(snapshot).publish(json.dumps(raw)).as_dict()
    assert [i["code"] for i in answer["issues"]]==["unknown_claim_ref"]*2
    assert any(t["kind"]=="claim" and t["disposition"]=="accepted" for t in answer["render_trace"])
    assert answer["requirement_outcomes"][0]["status"]=="answered"


def test_paired_test_sign_matches_reported_difference(context):
    from data_agent.tools.statistics import ab_test
    context.workspace.add("paired", pd.DataFrame({"user_id": [1, 2, 3, 1, 2, 3],
        "group": [1, 1, 1, 2, 2, 2], "amount": [10, 20, 30, 8, 19, 26]}))
    result = json.loads(ab_test("paired", "group", "amount", unit_col="user_id"))
    assert result["difference"]["absolute"] < 0
    assert result["test"]["statistic"] < 0
    assert result["test"]["difference_direction"] == "second_minus_first"


def test_sandbox_internal_import_error_explains_supported_subset():
    from data_agent.tools.sandbox import _build_safe_globals
    # Exercise the lazy-import boundary directly; numpy may already have
    # cached this module after other tests, so array.sum is order-dependent.
    with pytest.raises(ImportError, match="native analysis tool") as exc:
        _build_safe_globals({})["__builtins__"]["__import__"]("numpy._core._methods")
    assert "numpy._core._methods" in str(exc.value)


def test_formal_chart_rejects_unrelated_or_stale_evidence(context):
    from data_agent.tools.visualization import create_chart
    context.workspace.add("series", pd.DataFrame({"x": [1, 2], "y": [5, 8]}))
    identity = context.workspace.get_data_identity("series")
    state = context.analysis_state
    record = state.add_evidence_record({"id": "ev", "claim": "series"})
    args = dict(chart_type="line", data="series", x_col="x", y_col="y", purpose="evidence", evidence_ids="ev")
    assert json.loads(create_chart(**args))["error_code"] == "chart_evidence_binding_mismatch"
    receipt = state.add_tool_receipt({"id": "r", "result_sha256": "sha256:test", "data_identities": {"series": identity}})
    record["result_bindings"] = [{"receipt_id": "r", "result_sha256": receipt["result_sha256"], "data_identities": receipt["data_identities"]}]
    assert create_chart(**args).startswith("Chart saved:")
    context.workspace.add("series", pd.DataFrame({"x": [1, 2], "y": [50, 80]}))
    assert json.loads(create_chart(**args))["error_code"] == "chart_evidence_binding_mismatch"


def test_explicit_output_write_and_load_share_the_same_reference(context):
    from data_agent.tools.file_ops import write_file
    from data_agent.tools.data_io import load_data
    written = write_file("output/period_summary.csv", "period,revenue\nA,1818\nB,684\n")
    assert written.summary.endswith("/output/period_summary.csv")
    assert "Error" not in load_data("output/period_summary.csv", name="period_summary")
    assert context.workspace.get("period_summary")["revenue"].tolist() == [1818, 684]
