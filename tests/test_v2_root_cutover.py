from __future__ import annotations

from data_agent.web.app import create_app


def _client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_root_serves_v2_and_keeps_v2_workbench_as_exact_alias():
    client = _client()

    root = client.get("/")
    alias = client.get("/v2-workbench")

    assert root.status_code == 200
    assert alias.status_code == 200
    assert root.get_data() == alias.get_data()
    html = root.get_data(as_text=True)
    assert "Data Agent V2 Workbench" in html
    assert "/static/js/v2_workbench.js" in html
    assert "/static/js/app.js" not in html


def test_legacy_route_preserves_old_workbench_and_management_surface():
    client = _client()

    response = client.get("/legacy")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'x-data="chatApp()"' in html
    assert "managementCenter" in html
    assert "/static/js/app.js" in html
    assert "/static/js/v2_workbench.js" not in html


def test_root_presents_cutover_state_and_discoverable_legacy_rollback():
    html = _client().get("/").get_data(as_text=True)

    assert "尚未接管主入口" not in html
    assert "Unified V2 canary" not in html
    assert 'href="/legacy"' in html
    assert "旧版入口" in html
