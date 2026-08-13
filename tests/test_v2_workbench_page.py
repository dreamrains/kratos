from data_agent.web.app import create_app


def test_v2_workbench_exposes_all_explicit_analysis_kinds_and_overlay():
    client = create_app().test_client()
    response = client.get("/v2-workbench")
    html = response.get_data(as_text=True)
    js = client.get("/static/js/v2_workbench.js").get_data(as_text=True)

    assert response.status_code == 200
    for kind in (
        "descriptive", "factor_relationship", "date_transformation",
        "group_comparison", "time_trend", "forecast",
        "multi_finding_synthesis", "exploratory_python",
    ):
        assert f'value="{kind}"' in html
    assert '<details id="activity-overlay"' in html
    assert '<details id="activity-overlay" open' not in html
    assert "/api/v2/analyze" in js
    assert "question.disabled" not in js
    assert "ask_user" not in js
    assert "AbortController" not in js


def test_v2_workbench_has_bound_date_confirmation_controls():
    client = create_app().test_client()
    html = client.get("/v2-workbench").get_data(as_text=True)
    js = client.get("/static/js/v2_workbench.js").get_data(as_text=True)

    assert 'id="confirmation"' in html
    assert "/api/v2/transform-dates/resolve" in js
    assert "transformation?.status==='pending'" in js
    assert "expected_parent_version_id" in js
    assert "expected_parent_content_fingerprint" in js


def test_v2_workbench_stop_is_independent_and_does_not_abort_sse_client_side():
    client = create_app().test_client()
    html = client.get("/v2-workbench").get_data(as_text=True)
    js = client.get("/static/js/v2_workbench.js").get_data(as_text=True)

    assert 'id="stop"' in html
    assert "/api/v2/runs/stop" in js
    assert "turn_interrupted" in js
    assert "AbortController" not in js
    assert "confirm(" not in js
