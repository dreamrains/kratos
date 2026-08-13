from data_agent.web.app import create_app


def test_forecast_canary_exposes_explicit_horizon_and_backtest_journey():
    client = create_app().test_client()
    response = client.get("/v2-forecast-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_forecast_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "短期基线预测" in html
    assert 'id="time-field"' in html
    assert 'id="metric"' in html
    assert 'id="horizon"' in html
    assert 'id="frequency"' in html
    assert 'id="aggregation"' in html
    assert "/api/v2/forecast" in js
    assert "artifact_created" in js
    assert "data-chart-loaded" in js
    assert "ask_user" not in js
