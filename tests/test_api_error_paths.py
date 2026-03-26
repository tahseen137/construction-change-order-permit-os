from __future__ import annotations

from fastapi.testclient import TestClient


def test_workspace_templates_and_logout(auth_client: TestClient, auth_headers: dict[str, str], seeded_project: dict[str, object]):
    workspace_response = auth_client.get("/api/workspace")
    assert workspace_response.status_code == 200
    assert workspace_response.json()["name"] == "Pilot GC Workspace"

    permits_response = auth_client.get(f"/api/projects/{seeded_project['id']}/permits")
    change_events_response = auth_client.get(f"/api/projects/{seeded_project['id']}/change-events")
    assert permits_response.status_code == 200
    assert change_events_response.status_code == 200
    assert permits_response.json() == []
    assert change_events_response.json() == []

    permit_template = auth_client.get("/api/reference/permit-template.csv")
    change_template = auth_client.get("/api/reference/change-event-template.csv")
    assert permit_template.status_code == 200
    assert "Building Permit" in permit_template.text
    assert change_template.status_code == 200
    assert "Lobby glazing scope gap" in change_template.text

    logout_response = auth_client.post("/api/session/logout", headers=auth_headers)
    assert logout_response.status_code == 200
    assert logout_response.json()["authenticated"] is False


def test_duplicate_project_and_change_order_numbers_return_400(
    auth_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project: dict[str, object],
):
    duplicate_project = auth_client.post(
        "/api/projects",
        headers=auth_headers,
        json={
            "name": "Duplicate Project",
            "project_code": "RMO-01",
            "client_name": "Client",
            "location": "Austin, TX",
            "sector": "healthcare",
            "status": "precon",
            "contract_value_usd": 1000,
            "target_margin_pct": 10,
            "notes": "",
        },
    )
    assert duplicate_project.status_code == 400

    change_event_response = auth_client.post(
        f"/api/projects/{seeded_project['id']}/change-events",
        headers=auth_headers,
        json={
            "source_type": "owner_request",
            "title": "Owner adds signage package",
            "affected_scope": "Exterior signage",
            "subcontractor_name": "SignCo",
            "owner_reference": "ASI-3",
            "cost_impact_usd": 12000,
            "schedule_impact_days": 2,
            "status": "internal_review",
            "summary": "Owner requested upgraded signage package.",
            "risk_tags": [],
            "notes": "",
        },
    )
    change_event_id = change_event_response.json()["id"]

    first_change_order = auth_client.post(
        f"/api/change-events/{change_event_id}/change-orders",
        headers=auth_headers,
        json={
            "kind": "owner",
            "number": "PCO-3",
            "title": "Signage package",
            "amount_usd": 12000,
            "schedule_impact_days": 2,
            "description": "Signage package upgrade.",
        },
    )
    assert first_change_order.status_code == 201

    duplicate_change_order = auth_client.post(
        f"/api/change-events/{change_event_id}/change-orders",
        headers=auth_headers,
        json={
            "kind": "owner",
            "number": "PCO-3",
            "title": "Duplicate signage package",
            "amount_usd": 9000,
            "schedule_impact_days": 1,
            "description": "Duplicate number should fail.",
        },
    )
    assert duplicate_change_order.status_code == 400


def test_missing_resources_return_not_found(auth_client: TestClient, auth_headers: dict[str, str]):
    project_response = auth_client.get("/api/projects/not-a-real-project")
    document_response = auth_client.get("/api/documents/not-a-real-document/download")
    permit_update_response = auth_client.patch(
        "/api/permits/not-a-real-permit",
        headers=auth_headers,
        json={"status": "approved"},
    )

    assert project_response.status_code == 404
    assert document_response.status_code == 404
    assert permit_update_response.status_code == 404
