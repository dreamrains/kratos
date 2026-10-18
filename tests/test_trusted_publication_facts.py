"""New fact resolver must use exact existing receipt files, never model prose."""
from copy import deepcopy
import hashlib
import json

import pandas as pd
import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import get_config
from data_agent.session.workspace import Workspace


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def source(tmp_path, monkeypatch):
    cfg = get_config()
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions")
    monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    from data_agent.session.task_manager import task_manager
    monkeypatch.setattr(task_manager,"_dir",cfg.workspace_resolved/"tasks")
    monkeypatch.setattr(task_manager,"_next_id_val",0)
    workspace = Workspace()
    workspace.add("orders",pd.DataFrame({"amount":[10]*12}))
    state = AnalysisSessionState("s1")
    payload = {"rows":12,"total":120,"groups":[{"name":"D","amount":999}]}
    path = cfg.sessions_resolved/"s1"/"tool_outputs"/"tr1_detail.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    receipt = {"id":"tr1","tool_name":"describe_dataset","tool_call_id":"call1",
               "dataset_refs":["orders"],"data_identities":{"orders":workspace.get_data_identity("orders")},
               "detail_ref":{"path":"tool_outputs/tr1_detail.json","sha256":_sha(path.read_text(encoding="utf-8"))},
               "structured_result_sha256":_sha(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str))}
    state.tool_receipts = [receipt]
    ctx = AgentContext(session_id="s1",workspace=workspace,analysis_state=state)
    with use_agent_context(ctx):
        yield ctx,receipt,payload,path


def resolve(*, path=("total",), session_id="s1", receipt_id="tr1"):
    from data_agent.agent.publication.facts import resolve_result_claim
    return resolve_result_claim(session_id=session_id,receipt_id=receipt_id,
        claim_id="total",label="当前金额合计",result_path=path)


def test_fact_resolver_reloads_exact_scalar_and_group_from_receipt(source):
    ctx,receipt,_,_ = source
    scalar = resolve()
    grouped = resolve(path=("groups",0,"amount"))
    assert scalar["value"] == 120 and scalar["unit"] is None
    assert grouped["value"] == 999
    assert scalar["basis_refs"][0]["receipt_id"] == "tr1"
    assert scalar["basis_refs"][0]["result_sha256"] == receipt["structured_result_sha256"]
    assert scalar["basis_refs"][0]["data_identities"] == {"orders":ctx.workspace.get_data_identity("orders")}


@pytest.mark.parametrize("fault", ["missing_receipt","duplicate_receipt","missing_detail","legacy_filename",
    "wrong_byte_digest","wrong_result_digest","old_version","missing_identity","other_session","foreign_path","missing_field","nonfinite"])
def test_fact_resolver_rejects_unbound_or_stale_sources(source,fault):
    ctx,receipt,payload,path = source
    kwargs = {}
    if fault == "missing_receipt": kwargs["receipt_id"] = "absent"
    if fault == "duplicate_receipt": ctx.analysis_state.tool_receipts.append(deepcopy(receipt))
    if fault == "missing_detail": path.unlink()
    if fault == "legacy_filename": receipt["detail_ref"] = {}
    if fault == "wrong_byte_digest": receipt["detail_ref"]["sha256"] = "sha256:"+"b"*64
    if fault == "wrong_result_digest": receipt["structured_result_sha256"] = "sha256:"+"b"*64
    if fault == "old_version": ctx.workspace.add("orders",pd.DataFrame({"amount":[20]*12}))
    if fault == "missing_identity": receipt["data_identities"] = {}
    if fault == "other_session": kwargs["session_id"] = "other"
    if fault == "foreign_path": receipt["detail_ref"]["path"] = "sessions/other/tool_outputs/tr1_detail.json"
    if fault == "missing_field": kwargs["path"] = ("cost",)
    if fault == "nonfinite":
        payload["total"] = float("nan")
        path.write_text(json.dumps(payload),encoding="utf-8")
        receipt["detail_ref"]["sha256"] = _sha(path.read_text(encoding="utf-8"))
        receipt["structured_result_sha256"] = _sha(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str))
    with pytest.raises((ValueError,OSError)):
        resolve(**kwargs)


def test_fact_resolver_to_publication_service_keeps_real_provenance(source):
    from data_agent.agent.publication.contracts import HostSnapshot
    from data_agent.agent.publication.service import PublicationService
    ctx,_,_,_ = source
    fact = resolve()
    snap = HostSnapshot.freeze(session_id="s1",turn_id="t1",history_revision=1,requirement_revision=1,
        mode="analysis",plan_id="plan1",uses_result_context=True,
        claims=[fact],artifacts=[],data_identities={"orders":ctx.workspace.get_data_identity("orders")},
        requirements=[{"id":"r1","text":"当前金额合计","source_turn":"user1","claim_ids":["total"],
                       "open_purposes":[],"artifact_ids":[],"gap":None,"withdrawn":False}])
    raw=json.dumps({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,
                    "sections":[{"requirement_ids":["r1"],"parts":[{"kind":"claim","ref":"total"}]}]})
    answer=PublicationService(snap).publish(raw).as_dict()
    assert "120" in answer["body"] and "单位未知" in answer["body"]
    assert answer["source_snapshot"]["claims"][0]["basis_refs"][0]["receipt_id"] == "tr1"
    assert answer["requirement_outcomes"][0]["status"] == "answered"


@pytest.mark.parametrize("fault", [None,"wrong_digest","missing","other_session","foreign_path","traversal","symlink"])
def test_artifact_resolver_checks_exact_owned_file_before_publication(source, fault):
    from data_agent.agent.publication.facts import resolve_artifact
    ctx,_,_,_ = source
    cfg = get_config()
    path = cfg.sessions_resolved/"s1"/"charts"/"current chart.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"data":[]}',encoding="utf-8")
    reference = "charts/current chart.json"
    sha = "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
    session_id = "s1"
    if fault == "wrong_digest": sha = "sha256:"+"b"*64
    if fault == "missing": path.unlink()
    if fault == "other_session": session_id = "other"
    if fault == "foreign_path": reference = "sessions/other/charts/current chart.json"
    if fault == "traversal": reference = "charts/../tool_outputs/tr1_detail.json"
    if fault == "symlink":
        target = cfg.workspace_resolved/"external.json"
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('{}',encoding="utf-8")
        path.unlink()
        try: path.symlink_to(target)
        except OSError: pytest.skip("OS does not permit symlink creation")
    kwargs = dict(session_id=session_id,artifact_id="chart1",path=reference,kind="chart",description="当前图",expected_sha256=sha)
    if fault:
        with pytest.raises((ValueError,OSError)): resolve_artifact(**kwargs)
    else:
        from data_agent.agent.publication.contracts import HostSnapshot
        from data_agent.agent.publication.service import PublicationService
        artifact = resolve_artifact(**kwargs)
        snap = HostSnapshot.freeze(session_id="s1",turn_id="t1",history_revision=1,requirement_revision=1,
            mode="analysis",uses_result_context=True,claims=[],artifacts=[artifact],data_identities={},
            requirements=[{"id":"chart","text":"查看图表","source_turn":"user1","claim_ids":[],
                "open_purposes":[],"artifact_ids":["chart1"],"gap":None,"withdrawn":False}])
        answer = PublicationService(snap).publish('{}').as_dict()
        assert artifact["sha256"] == sha and artifact["session_id"] == ctx.session_id
        assert "charts/current%20chart.json" in answer["body"]
        assert answer["requirement_outcomes"][0]["status"] == "answered"


@pytest.mark.parametrize("phase", ["planning","execution","synthesis"])
def test_current_receipt_resolves_under_restricted_scope_without_raw_data_access(source, phase):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    ctx,receipt,_,_ = source
    boundary = WorkspaceScopeSnapshot(phase=phase,session_id="s1",allowed_datasets=frozenset())
    with ctx.bind_workspace_scope(boundary):
        assert ctx.workspace.get_data_identity("orders") == {}
        assert ctx.workspace.get("orders") is None
        assert resolve()["value"] == 120
        assert ctx.workspace.get_data_identity("orders") == {}
        receipt["data_identities"]["orders"]["version_id"] = "old"
        with pytest.raises(ValueError): resolve()
