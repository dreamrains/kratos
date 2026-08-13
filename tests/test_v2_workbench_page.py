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


def test_v2_workbench_has_explicit_durable_queued_steer_controls():
    client = create_app().test_client()
    html = client.get("/v2-workbench").get_data(as_text=True)
    js = client.get("/static/js/v2_workbench.js").get_data(as_text=True)

    assert 'id="steer"' in html
    assert 'id="continue-steer"' in html
    assert "/api/v2/runs/steer" in js
    assert "steer_received" in js
    assert "steer_id" in js
    assert "afterCurrentStreamCloses" in js
    assert "AbortController" not in js


def test_v2_workbench_has_explicit_one_call_planning_and_recoverable_questions():
    client = create_app().test_client()
    html = client.get("/v2-workbench").get_data(as_text=True)
    js = client.get("/static/js/v2_workbench.js").get_data(as_text=True)

    assert 'id="plan-run"' in html
    assert "估算系统规划（不调用模型）" in html
    assert 'id="plan-confirm"' in html
    assert "确认并开始分析（调用模型 1 次）" in html
    assert 'id="planning-input"' in html
    assert 'id="planning-questions"' in html
    assert 'id="planning-submit"' in html
    assert 'id="planning-estimate"' in html
    assert "保存回答并估算（不调用模型）" in html
    assert 'id="planning-confirm"' in html
    assert "确认并重新规划（调用模型 1 次）" in html
    assert "/api/v2/provider-authorizations" in js
    assert "/api/v2/planning-estimates" in js
    assert "/api/v2/plans" in js
    assert "/planning-inputs/" in js
    assert "/answers" in js
    assert "confirm_provider_call: true" in js
    assert "provider_calls_authorized: 1" in js
    assert "planning_input_id" in js
    assert "maxlength" not in html.lower()
    assert "planning_context_too_large" not in js
    assert "estimated_input_tokens" in js
    assert "model_context_window_tokens" in js
    assert "reserved_output_tokens" in js
    assert "available_input_tokens" in js


def test_v2_workbench_planning_is_only_bound_to_explicit_clicks():
    client = create_app().test_client()
    js = client.get("/static/js/v2_workbench.js").get_data(as_text=True)

    assert "byId('plan-run').addEventListener('click', planAndRun)" in js
    assert "byId('plan-confirm').addEventListener('click', confirmInitialPlanning)" in js
    assert "byId('planning-submit').addEventListener('click', answerAndReplan)" in js
    assert "byId('planning-confirm').addEventListener('click', confirmPlanningAnswer)" in js
    assert "if (params.has('turn_id')) restore();" in js
    assert "else if (params.has('plan_id')) restorePlanning();" in js
