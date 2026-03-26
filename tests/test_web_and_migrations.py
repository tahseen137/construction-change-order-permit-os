from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]


def test_login_page_redirects_for_unauthenticated_users(client: TestClient):
    redirect_response = client.get("/", follow_redirects=False)
    assert redirect_response.status_code == 303
    assert redirect_response.headers["location"].startswith("/login")

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert "Construction Change-Order & Permit OS" in login_page.text


def test_health_and_ready_routes(auth_client: TestClient):
    health = auth_client.get("/health")
    ready = auth_client.get("/ready")
    assert health.status_code == 200
    assert ready.status_code == 200


def test_alembic_upgrade_head_creates_core_tables(tmp_path):
    database_path = tmp_path / "alembic-test.db"
    database_url = f"sqlite:///{database_path}"

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }

    assert {"workspaces", "users", "projects", "permits", "change_events", "change_orders"}.issubset(tables)
