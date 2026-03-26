from __future__ import annotations

from fastapi.testclient import TestClient


def test_dashboard_and_project_lifecycle(auth_client: TestClient, auth_headers: dict[str, str]):
    dashboard_response = auth_client.get("/api/dashboard")
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["active_projects"] == 0

    create_response = auth_client.post(
        "/api/projects",
        headers=auth_headers,
        json={
            "name": "Lakeside Warehouse",
            "project_code": "LW-200",
            "client_name": "Northwind Holdings",
            "location": "Chicago, IL",
            "sector": "industrial",
            "status": "precon",
            "contract_value_usd": 24000000,
            "target_margin_pct": 11.2,
            "notes": "Warehouse and cold-storage buildout.",
        },
    )
    assert create_response.status_code == 201, create_response.text
    project = create_response.json()

    list_response = auth_client.get("/api/projects")
    assert list_response.status_code == 200
    projects = list_response.json()
    assert len(projects) == 1
    assert projects[0]["project_code"] == "LW-200"

    detail_response = auth_client.get(f"/api/projects/{project['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Lakeside Warehouse"

    update_response = auth_client.patch(
        f"/api/projects/{project['id']}",
        headers=auth_headers,
        json={"status": "active", "notes": "Bid won and mobilization started."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "active"

    dashboard_after = auth_client.get("/api/dashboard")
    assert dashboard_after.status_code == 200
    assert dashboard_after.json()["active_projects"] == 1


def test_project_export_returns_nested_snapshot(
    auth_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project: dict[str, object],
):
    export_response = auth_client.get(f"/api/projects/{seeded_project['id']}/export")
    assert export_response.status_code == 200
    payload = export_response.json()
    assert payload["project"]["project_code"] == "RMO-01"
    assert payload["permits"] == []
    assert payload["change_events"] == []
