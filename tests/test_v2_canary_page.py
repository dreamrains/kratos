from data_agent.web.app import create_app


def test_v2_canary_page_is_isolated_and_semantic():
    response = create_app().test_client().get("/v2-canary")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Slice 1 浏览器验收页" in html
    assert "/static/js/v2_canary.js" in html
    assert 'id="progress-list"' in html
    assert 'id="answer"' in html
    assert "app.js" not in html


def test_v2_canary_javascript_uses_semantic_events_and_block_refresh():
    response = create_app().test_client().get("/static/js/v2_canary.js")
    js = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "commitment_snapshot" in js
    assert "outcome_snapshot" in js
    assert "final_block_delta" in js
    assert "turn_completed" in js
    assert "/api/v2/sessions/" in js
    assert "artifact_created" in js
    assert "chart-frame" in js
    assert "supplemental" in js
    assert "request_context" in js
    assert "[[chart:" not in js
    assert "[[evidence:" not in js
