from data_agent.web.app import create_app


def test_multi_canary_exposes_two_method_specs_and_semantic_sse():
    client = create_app().test_client()
    response = client.get("/v2-multi-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_multi_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "趋势与双组综合分析" in html
    assert 'id="time-field"' in html
    assert 'id="group"' in html
    assert 'id="analysis-unit"' in html
    assert "/api/v2/multi-finding" in js
    assert "time_trend" in js and "group_comparison" in js
    assert "data-chart-loaded" in js
    assert "ask_user" not in js
