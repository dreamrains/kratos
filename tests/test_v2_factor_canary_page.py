from data_agent.web.app import create_app


def test_factor_canary_is_isolated_and_uses_structured_fields():
    client = create_app().test_client()

    response = client.get("/v2-factor-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_factor_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "因素关系分析" in html
    assert 'id="target"' in html
    assert 'id="features"' in html
    assert 'id="analysis-unit"' in html
    assert 'id="time-field"' in html
    assert "/api/v2/factors" in js
    assert "artifact_created" in js
    assert "data-chart-loaded" in js
    assert "navigationRetried" in js
    assert js.index("await consumeSse(response)") < js.index(
        "renderBlocks(state.blocks, state.artifacts, true)"
    )
    assert "request_context" in js
    assert "[[chart:" not in js
    assert "[[evidence:" not in js
