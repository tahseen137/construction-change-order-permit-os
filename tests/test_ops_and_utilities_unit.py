from __future__ import annotations

from pathlib import Path

import pytest

from app.ai import extract_document_artifacts
from app.celery_app import celery_app
from app.config import Settings
from app.db import build_database_state, database_is_ready, ensure_database_url_directory, init_database
from app.notifications import queue_notification, send_notification
from app.storage import LocalStorageClient, S3StorageClient, build_storage_client
from app.tasks import send_notification_task


def test_ai_extraction_handles_text_json_and_binary():
    text_result = extract_document_artifacts(
        "revision-letter.txt",
        "text/plain",
        b"Permit number AB-12\nDelay is 3 week\nBudget impact $22,500\n",
    )
    assert text_result.extracted_fields["schedule_impact_days"] == 21
    assert text_result.extracted_fields["amount_candidates_usd"][0] == 22500

    json_result = extract_document_artifacts(
        "facts.json",
        "application/json",
        b'{"permit_number":"AB-12","body":"pricing pending"}',
    )
    assert json_result.extracted_fields["json_preview"]["permit_number"] == "AB-12"

    binary_result = extract_document_artifacts("scan.pdf", "application/pdf", b"%PDF-binary")
    assert binary_result.extraction_confidence == 0.1


def test_storage_round_trip_and_directory_setup(tmp_path: Path, monkeypatch):
    settings = Settings(
        app_env="test",
        database_url=f"sqlite:///{(tmp_path / 'ops.db').resolve()}",
        uploads_dir=tmp_path / "uploads",
    )
    ensure_database_url_directory(settings.resolved_database_url)
    assert settings.uploads_dir.parent.exists()

    local_client = LocalStorageClient(settings.uploads_dir)
    stored = local_client.store_bytes(
        workspace_slug="pilot-gc",
        filename="permit.txt",
        content=b"hello world",
        content_type="text/plain",
    )
    assert local_client.read_bytes(stored.storage_key) == b"hello world"
    assert build_storage_client(settings).__class__ is LocalStorageClient

    class FakeS3Client:
        def __init__(self):
            self.payloads = {}

        def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
            self.payloads[Key] = Body

        def get_object(self, Bucket, Key):  # noqa: N803
            return {"Body": type("Body", (), {"read": lambda self: self.payload})()}

    fake_client = FakeS3Client()
    fake_client.get_object = lambda Bucket, Key: {"Body": type("Body", (), {"read": lambda self: fake_client.payloads[Key]})()}
    monkeypatch.setattr("app.storage.boto3.client", lambda *args, **kwargs: fake_client)
    s3_settings = Settings(app_env="test", storage_backend="s3", s3_bucket="demo-bucket")
    s3_client = S3StorageClient(s3_settings)
    stored_s3 = s3_client.store_bytes(
        workspace_slug="pilot-gc",
        filename="permit.txt",
        content=b"s3 body",
        content_type="text/plain",
    )
    assert s3_client.read_bytes(stored_s3.storage_key) == b"s3 body"


def test_notifications_and_task_flow(tmp_path: Path, monkeypatch):
    settings = Settings(
        app_env="test",
        database_url=f"sqlite:///{(tmp_path / 'notify.db').resolve()}",
        uploads_dir=tmp_path / "uploads",
        session_secret="task-secret",
        bootstrap_admin_username="admin",
        bootstrap_admin_password="pilot-password",
        bootstrap_admin_email="admin@example.com",
        auto_create_schema=True,
    )
    database = build_database_state(settings)
    init_database(database)
    assert database_is_ready(database) is True

    with database.session_factory() as session:
        from app.user_service import ensure_bootstrap_workspace_admin, list_workspaces

        ensure_bootstrap_workspace_admin(session, settings)
        workspace = list_workspaces(session)[0]
        job = queue_notification(
            session,
            workspace_id=workspace.id,
            notification_type="approval_request",
            recipient_email="pm@example.com",
            subject="Approval needed",
            payload={"body": "Please review"},
        )
        simulated = send_notification(job, settings)
        assert simulated.status == "simulated"

    monkeypatch.setattr("app.tasks.get_settings", lambda: settings)
    monkeypatch.setattr("app.tasks.build_database_state", lambda _: database)
    with database.session_factory() as session:
        queued_job = queue_notification(
            session,
            workspace_id=workspace.id,
            notification_type="approval_request",
            recipient_email="pm@example.com",
            subject="Approval needed",
            payload={"body": "Please review again"},
        )
        result = send_notification_task(queued_job.id)
        assert result == "simulated"

    assert celery_app.main == "construction_change_order_permit_os"


def test_config_validation_and_security_edges():
    with pytest.raises(ValueError):
        Settings(bootstrap_admin_username="admin")
