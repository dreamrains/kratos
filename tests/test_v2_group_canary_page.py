from data_agent.web.app import create_app


def test_group_canary_exposes_explicit_method_and_recommendation_controls():
    client = create_app().test_client()
    response = client.get("/v2-group-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_group_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "双组指标比较" in html
    assert 'id="metric"' in html
    assert 'id="group"' in html
    assert 'id="analysis-unit"' in html
    assert 'id="recommendation-intent"' in html
    assert 'id="action-risk"' in html
    assert "/api/v2/group-comparison" in js
    assert "artifact_created" in js
    assert "data-chart-loaded" in js
    assert "ask_user" not in js
