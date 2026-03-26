from __future__ import annotations

from celery import Celery

from app.config import get_settings


settings = get_settings()

celery_app = Celery(
    "construction_change_order_permit_os",
    broker=settings.redis_url if settings.redis_url else "memory://",
    backend=settings.redis_url if settings.redis_url else "cache+memory://",
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager or settings.app_env == "test",
    task_ignore_result=False,
)
