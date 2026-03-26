from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import NotificationJob


def queue_notification(
    session: Session,
    *,
    workspace_id: str,
    notification_type: str,
    recipient_email: str,
    subject: str,
    payload: dict[str, object],
) -> NotificationJob:
    job = NotificationJob(
        workspace_id=workspace_id,
        notification_type=notification_type,
        recipient_email=recipient_email,
        subject=subject,
        payload=payload,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def send_notification(job: NotificationJob, settings: Settings) -> NotificationJob:
    if not settings.postmark_server_token or not job.recipient_email:
        job.status = "simulated"
        job.sent_at = datetime.now(UTC)
        return job

    response = httpx.post(
        "https://api.postmarkapp.com/email",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": settings.postmark_server_token,
        },
        json={
            "From": settings.postmark_from_email,
            "To": job.recipient_email,
            "Subject": job.subject,
            "TextBody": str(job.payload.get("body", "")),
        },
        timeout=10,
    )
    if response.is_success:
        job.status = "sent"
        job.sent_at = datetime.now(UTC)
        job.error_message = ""
    else:
        job.status = "failed"
        job.error_message = response.text[:1000]
    return job
