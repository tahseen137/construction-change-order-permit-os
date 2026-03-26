from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityEvent, User


def list_activity_events(session: Session, workspace_id: str, limit: int = 50) -> list[ActivityEvent]:
    statement = (
        select(ActivityEvent)
        .where(ActivityEvent.workspace_id == workspace_id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def record_activity(
    session: Session,
    *,
    workspace_id: str | None,
    action: str,
    entity_type: str,
    description: str,
    actor_user: User | None = None,
    actor_username: str | None = None,
    entity_id: str | None = None,
    project_id: str | None = None,
    details: dict[str, object] | None = None,
) -> ActivityEvent:
    event = ActivityEvent(
        workspace_id=workspace_id or (actor_user.workspace_id if actor_user else None),
        actor_user_id=actor_user.id if actor_user else None,
        actor_username=actor_username or (actor_user.username if actor_user else "system"),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        description=description,
        details=details or {},
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
