from data_agent.web.app import create_app


def test_python_canary_labels_output_as_exploratory_and_uses_sse():
    client = create_app().test_client()
    response = client.get("/v2-python-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_python_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "探索性 Python 补充" in html
    assert "不能作为结论证据" in html
    assert 'id="purpose"' in html
    assert 'id="code"' in html
    assert "/api/v2/exploratory-python" in js
    assert "supplemental_artifact_created" in js
    assert "ask_user" not in js
