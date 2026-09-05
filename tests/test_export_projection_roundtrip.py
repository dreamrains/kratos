import http.client
import json
import threading
import numpy as np
import pytest

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import get_config
from data_agent.session.history import load_session, save_session
from data_agent.session.workspace import Workspace


@pytest.mark.parametrize("array", [list, np.array], ids=["plain-list", "numpy-typed-payload"])
def test_public_history_and_both_export_scopes_share_confirmation_and_charts(tmp_path, monkeypatch, array):
    import plotly.graph_objects as go
    from data_agent.tools.visualization import _save_chart
    from data_agent.tools.report import export_conversation, export_assistant_reply
    from data_agent.web.app import create_app
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    sid = "export-projection"
    context = AgentContext(session_id=sid, workspace=Workspace())
    with use_agent_context(context):
        chart = _save_chart(go.Figure([go.Scatter(x=array([1,2]),y=array([2,3]),name="actual"),
                                      go.Scatter(x=array([1,2]),y=array([2.1,2.9]),name="fit")]), "retained curves",
                            {"validation_status":"valid","purpose":"exploratory","title":"retained curves"})
        protocol = '<confirmation_response confirmation_id="c">\nOriginal question: methods\nUser answered: confirm_method\n</confirmation_response>'
        save_session([{"role":"user","content":"Analyze"}, {"role":"assistant","content":"Choose a method"}, {"role":"user","content":protocol},
                      {"role":"assistant","content":"","tool_calls":[]},
                      {"role":"tool","content":chart},
                      {"role":"assistant","content":"Fit and actual use the same result: 0.98240474."}], sid)
        client = create_app().test_client()
        snapshot = client.get(f"/api/sessions/{sid}").get_json()
        assert snapshot["messages"][2]["content"] == "confirm_method"
        assert snapshot["messages"][2]["is_confirmation_response"] is True
        assert load_session(sid)["messages"][2]["content"] == protocol
        for format in ("html", "markdown"):
            whole = json.loads(export_conversation(format=format))
            reply = export_assistant_reply(sid, "Fit and actual use the same result: 0.98240474.", format)
            for exported in (whole, reply):
                text = (tmp_path / exported["artifact_path"]).read_text(encoding="utf8")
                assert "confirmation_response" not in text
                assert "0.98240474" in text
                if format == "html":
                    assert text.lower().count("<!doctype html>") == 1
                    assert 'class="plotly-graph-div"' in text
                    assert '<script src="/static/' not in text
                    assert '"name":"actual"' in text and '"name":"fit"' in text
                else:
                    assert "data:image/png;base64,iVBOR" in text
            assert "confirm_method" in (tmp_path / whole["artifact_path"]).read_text(encoding="utf8")
            assert "confirm_method" not in (tmp_path / reply["artifact_path"]).read_text(encoding="utf8")
        assert export_assistant_reply("another-session", "Fit and actual use the same result: 0.98240474.")["error_type"] == "unbound_reply"
        assert client.post(f"/api/sessions/{sid}/export-reply", json={"content":"invented result"}).status_code == 400


def test_finite_sse_has_server_owned_framing_and_closes_on_real_http():
    from flask import Flask
    from werkzeug.serving import make_server
    from data_agent.web.blueprints.chat import _sse_response
    from data_agent.web.event_bus import EventQueue, SSEEvent
    app = Flask(__name__)

    @app.get("/finite-stream")
    def stream():
        queue = EventQueue()
        queue.put(SSEEvent("turn_end", {"status":"completed"}))
        queue.close()
        response = _sse_response(queue)
        assert "Connection" not in response.headers
        return response

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.01})
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    try:
        connection.request("GET", "/finite-stream")
        response = connection.getresponse()
        assert response.status == 200
        assert response.read().decode() == 'event: turn_end\ndata: {"status": "completed"}\n\n'
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(2)
    assert not thread.is_alive()
