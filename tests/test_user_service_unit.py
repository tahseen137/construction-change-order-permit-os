from __future__ import annotations

import pytest

from app.config import Settings
from app.user_service import (
    authenticate_user,
    count_active_admins,
    create_user,
    normalize_email,
    normalize_username,
    update_user,
)


def test_user_service_normalization_and_duplicates(session, workspace):
    assert normalize_username("  Admin.User ") == "admin.user"
    assert normalize_email(" USER@EXAMPLE.COM ") == "user@example.com"

    created = create_user(
        session,
        workspace_id=workspace.id,
        username="engineer1",
        email="engineer1@example.com",
        password="engineer-pass",
        role="project_engineer",
        full_name="Engineer One",
        is_active=True,
    )
    assert created.username == "engineer1"

    with pytest.raises(ValueError):
        create_user(
            session,
            workspace_id=workspace.id,
            username="engineer1",
            email="different@example.com",
            password="engineer-pass",
            role="project_engineer",
            full_name="Duplicate Username",
            is_active=True,
        )

    with pytest.raises(ValueError):
        create_user(
            session,
            workspace_id=workspace.id,
            username="engineer2",
            email="engineer1@example.com",
            password="engineer-pass",
            role="project_engineer",
            full_name="Duplicate Email",
            is_active=True,
        )


def test_user_service_prevents_last_admin_deactivation_and_self_disable(session, workspace, admin_user):
    assert count_active_admins(session, workspace.id) == 1

    with pytest.raises(ValueError):
        update_user(
            session,
            admin_user,
            role="viewer",
            acting_user=admin_user,
        )

    with pytest.raises(ValueError):
        update_user(
            session,
            admin_user,
            is_active=False,
            acting_user=admin_user,
        )

    manager = create_user(
        session,
        workspace_id=workspace.id,
        username="manager1",
        email="manager1@example.com",
        password="manager-pass",
        role="project_manager",
        full_name="Manager One",
        is_active=True,
    )
    updated = update_user(session, manager, role="finance_approver", email="finance1@example.com")
    assert updated.role == "finance_approver"
    assert updated.email == "finance1@example.com"


def test_authenticate_user_success_and_failure(session, admin_user):
    settings = Settings(
        app_env="test",
        session_secret="secret",
        bootstrap_admin_username="admin",
        bootstrap_admin_password="pilot-password",
    )

    success = authenticate_user(session, "admin", "pilot-password", settings)
    assert success.user is not None
    assert success.error is None

    failure = authenticate_user(session, "admin", "wrong-password", settings)
    assert failure.user is None
    assert failure.error == "Invalid credentials"
