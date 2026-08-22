from data_agent.web.app import create_app


def test_time_canary_exposes_explicit_time_and_recommendation_controls():
    client = create_app().test_client()
    response = client.get("/v2-time-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_time_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "历史趋势分析" in html
    assert 'id="time-field"' in html
    assert 'id="metric"' in html
    assert 'id="frequency"' in html
    assert 'id="aggregation"' in html
    assert 'id="recommendation-intent"' in html
    assert "/api/v2/time-trend" in js
    assert "artifact_created" in js
    assert "data-chart-loaded" in js
    assert "ask_user" not in js
