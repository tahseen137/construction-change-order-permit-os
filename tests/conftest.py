from __future__ import annotations

import sys
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

loaded_app = sys.modules.get("app")
if loaded_app is not None:
    loaded_file = Path(getattr(loaded_app, "__file__", ""))
    if ROOT not in loaded_file.parents:
        for module_name in list(sys.modules):
            if module_name == "app" or module_name.startswith("app."):
                sys.modules.pop(module_name, None)

from app.config import Settings
from app.db import build_database_state, init_database
from app.main import create_app
from app.models import User, Workspace
from app.user_service import create_user, create_workspace, ensure_bootstrap_workspace_admin, list_users, list_workspaces


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{(tmp_path / 'construction-test.db').resolve()}",
        uploads_dir=tmp_path / "uploads",
        session_secret="test-session-secret",
        bootstrap_workspace_name="Pilot GC Workspace",
        bootstrap_admin_username="admin",
        bootstrap_admin_password="pilot-password",
        bootstrap_admin_email="admin@example.com",
        auto_create_schema=True,
        celery_task_always_eager=True,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(settings: Settings) -> Generator[Session, None, None]:
    database = build_database_state(settings)
    init_database(database, auto_create_schema=True)
    db_session = database.session_factory()
    ensure_bootstrap_workspace_admin(db_session, settings)
    try:
        yield db_session
    finally:
        db_session.close()
        database.engine.dispose()


@pytest.fixture
def workspace(session: Session) -> Workspace:
    return list_workspaces(session)[0]


@pytest.fixture
def admin_user(session: Session) -> User:
    return list_users(session)[0]


def login(client: TestClient, username: str = "admin", password: str = "pilot-password") -> dict[str, str]:
    response = client.post(
        "/api/session/login",
        json={"username": username, "password": password, "next_path": "/"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return {"X-CSRF-Token": payload["csrf_token"]}


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    login(client)
    return client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    return login(client)


@pytest.fixture
def seeded_project(auth_client: TestClient, auth_headers: dict[str, str]) -> dict[str, object]:
    response = auth_client.post(
        "/api/projects",
        headers=auth_headers,
        json={
            "name": "Riverside Medical Office",
            "project_code": "RMO-01",
            "client_name": "Harbor Capital",
            "location": "Austin, TX",
            "sector": "healthcare",
            "status": "precon",
            "contract_value_usd": 18000000,
            "target_margin_pct": 12.5,
            "notes": "Pilot project for permit and change-order coordination.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def second_workspace_user(session: Session) -> tuple[Workspace, User]:
    second_workspace = create_workspace(session, name="Second GC Workspace")
    outsider = create_user(
        session,
        workspace_id=second_workspace.id,
        username="outsider",
        email="outsider@example.com",
        password="outsider-password",
        role="workspace_admin",
        full_name="Outside Admin",
        is_active=True,
    )
    return second_workspace, outsider
