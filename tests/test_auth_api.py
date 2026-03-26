from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_and_session_status(client: TestClient):
    login_response = client.post(
        "/api/session/login",
        json={"username": "admin", "password": "pilot-password", "next_path": "/"},
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["authenticated"] is True
    assert payload["current_user"]["username"] == "admin"
    assert payload["csrf_token"]

    session_response = client.get("/api/session")
    assert session_response.status_code == 200
    assert session_response.json()["authenticated"] is True


def test_invalid_login_locks_after_retries(client: TestClient):
    for _ in range(5):
        response = client.post(
            "/api/session/login",
            json={"username": "admin", "password": "wrong-password", "next_path": "/"},
        )

    assert response.status_code == 401
    assert "locked" in response.json()["detail"].lower()


def test_csrf_required_for_write_calls(client: TestClient):
    login_response = client.post(
        "/api/session/login",
        json={"username": "admin", "password": "pilot-password", "next_path": "/"},
    )
    assert login_response.status_code == 200

    response = client.post(
        "/api/projects",
        json={
            "name": "CSRF Test",
            "project_code": "CSRF-1",
            "client_name": "Client",
            "location": "Dallas, TX",
            "sector": "industrial",
            "status": "precon",
            "contract_value_usd": 5000000,
            "target_margin_pct": 10,
            "notes": "",
        },
    )

    assert response.status_code == 403
    assert "csrf" in response.json()["detail"].lower()
