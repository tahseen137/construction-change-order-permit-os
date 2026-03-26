from __future__ import annotations

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.db import build_database_state
from app.models import NotificationJob
from app.notifications import send_notification


@celery_app.task(name="notifications.send")
def send_notification_task(notification_job_id: str) -> str:
    settings = get_settings()
    database = build_database_state(settings)
    session: Session = database.session_factory()
    try:
        job = session.get(NotificationJob, notification_job_id)
        if job is None:
            return "missing"
        send_notification(job, settings)
        session.add(job)
        session.commit()
        return job.status
    finally:
        session.close()
        database.engine.dispose()
