from data_agent.web.app import create_app


def test_transform_canary_exposes_semantic_choice_without_legacy_confirmation():
    client = create_app().test_client()

    response = client.get("/v2-transform-canary")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_transform_canary.js").get_data(as_text=True)

    assert response.status_code == 200
    assert "日期转换与语义确认" in html
    assert 'id="date-column"' in html
    assert 'id="confirmation"' in html
    assert "/api/v2/transform-dates" in js
    assert "/api/v2/transform-dates/resolve" in js
    assert "expected_parent_version_id" in js
    assert "user_input_required" in js
    assert "ask_user" not in js
    assert "[[evidence:" not in js
