from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.user_service import create_user


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/session/login",
        json={"username": username, "password": password, "next_path": "/"},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_admin_can_create_and_update_users(
    auth_client: TestClient,
    auth_headers: dict[str, str],
    workspace,
):
    create_response = auth_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "pmaria",
            "email": "pmaria@example.com",
            "full_name": "Maria PM",
            "role": "project_manager",
            "password": "secure-pass-1",
            "is_active": True,
        },
    )
    assert create_response.status_code == 201, create_response.text
    created_user = create_response.json()
    assert created_user["role"] == "project_manager"

    update_response = auth_client.patch(
        f"/api/admin/users/{created_user['id']}",
        headers=auth_headers,
        json={"role": "finance_approver", "is_active": True},
    )
    assert update_response.status_code == 200
    assert update_response.json()["role"] == "finance_approver"

    list_response = auth_client.get("/api/admin/users")
    assert list_response.status_code == 200
    assert len(list_response.json()) >= 2


def test_viewer_cannot_write_or_manage_users(session, settings, auth_client: TestClient, auth_headers: dict[str, str], workspace):
    viewer = create_user(
        session,
        workspace_id=workspace.id,
        username="viewer1",
        email="viewer1@example.com",
        password="viewer-pass-1",
        role="viewer",
        full_name="Viewer User",
        is_active=True,
    )

    with TestClient(create_app(settings)) as viewer_client:
        viewer_headers = login(viewer_client, username=viewer.username, password="viewer-pass-1")

        write_response = viewer_client.post(
            "/api/projects",
            headers=viewer_headers,
            json={
                "name": "Should Fail",
                "project_code": "FAIL-1",
                "client_name": "Client",
                "location": "Houston, TX",
                "sector": "industrial",
                "status": "precon",
                "contract_value_usd": 1,
                "target_margin_pct": 1,
                "notes": "",
            },
        )
        assert write_response.status_code == 403

        admin_response = viewer_client.get("/api/admin/users")
        assert admin_response.status_code == 403


def test_cross_tenant_access_is_denied(
    settings,
    auth_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project: dict[str, object],
    second_workspace_user,
):
    _, outsider = second_workspace_user

    with TestClient(create_app(settings)) as outsider_client:
        outsider_headers = login(outsider_client, username=outsider.username, password="outsider-password")
        assert outsider_headers["X-CSRF-Token"]

        detail_response = outsider_client.get(f"/api/projects/{seeded_project['id']}")
        assert detail_response.status_code == 404

        list_response = outsider_client.get("/api/projects")
        assert list_response.status_code == 200
        assert list_response.json() == []
