import json

import numpy as np
import pandas as pd

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def _events(raw: str) -> list[tuple[str, dict]]:
    parsed=[]; event_name=""; data=""
    for line in raw.splitlines():
        if line.startswith("event: "): event_name=line.removeprefix("event: ")
        elif line.startswith("data: "): data=line.removeprefix("data: ")
        elif not line and event_name and data:
            parsed.append((event_name,json.loads(data)));event_name="";data=""
    return parsed


def _client(monkeypatch,tmp_path):
    workspace=tmp_path/"workspace";inbox=workspace/"inbox";inbox.mkdir(parents=True)
    index=np.arange(70,dtype=float);channel=np.where(index%2==0,"A","B")
    pd.DataFrame({"date":pd.date_range("2026-01-01",periods=70,freq="D"),"unit_id":[f"u{i}" for i in range(70)],"channel":channel,"sales":100+1.2*index+np.where(channel=="B",12,0)}).to_csv(inbox/"combined.csv",index=False)
    monkeypatch.setattr(config_module,"_config",AgentConfig(WORKSPACE_DIR=workspace,SESSIONS_DIR=tmp_path/"sessions"))
    return create_app().test_client()


def test_v2_multi_finding_sse_two_charts_and_refresh(monkeypatch,tmp_path):
    client=_client(monkeypatch,tmp_path)
    response=client.post("/api/v2/multi-finding",json={"session_id":"session_multi_web","turn_id":"turn_multi_web","filename":"combined.csv","time_field":"date","metric":"sales","frequency":"daily","aggregation":"mean","group":"channel","analysis_unit":"unit_id","question":"销售如何变化，不同渠道是否有差异？","recommendation_intent":"act","action_risk":"low","reversible":True})
    events=_events(response.get_data(as_text=True));names=[name for name,_ in events]

    assert response.status_code==200
    assert names[0]=="turn_started"
    assert names.count("tool_started")==2
    assert names.count("artifact_created")==2
    assert names[-1]=="turn_completed"
    refreshed=client.get("/api/v2/sessions/session_multi_web/turns/turn_multi_web").get_json()
    assert refreshed["request_context"]["analysis_kind"]=="multi_finding_synthesis"
    assert len(refreshed["artifacts"])==2
    assert refreshed["blocks"][1]["chart_refs"]!=refreshed["blocks"][2]["chart_refs"]
    assert refreshed["request_context"]["recommendation_mode"]=="investigative_next_step"
    for artifact in refreshed["artifacts"]:
        chart=client.get(f"/api/v2/sessions/session_multi_web/artifacts/{artifact['chart_id']}")
        assert chart.status_code==200
        assert "/static/js/plotly-3.5.0.min.js" in chart.get_data(as_text=True)


def test_v2_multi_endpoint_rejects_non_boolean_reversibility(monkeypatch,tmp_path):
    client=_client(monkeypatch,tmp_path)
    response=client.post("/api/v2/multi-finding",json={"filename":"combined.csv","time_field":"date","metric":"sales","frequency":"daily","aggregation":"mean","group":"channel","analysis_unit":"unit_id","question":"综合分析。","reversible":"true"})
    assert response.status_code==400
    assert response.get_json()["error"]=="reversible must be a boolean"
