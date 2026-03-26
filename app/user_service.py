from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from re import sub

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User, Workspace
from app.security import hash_password, verify_password


WRITER_ROLES = {"workspace_admin", "project_manager", "project_engineer", "finance_approver", "platform_admin"}
ADMIN_ROLES = {"workspace_admin", "platform_admin"}
FINANCE_APPROVER_ROLES = {"workspace_admin", "finance_approver", "platform_admin"}


def _now() -> datetime:
    return datetime.now(UTC)


def _slugify(value: str) -> str:
    slug = sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
    return slug or "workspace"


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def has_users(session: Session) -> bool:
    statement = select(func.count()).select_from(User)
    return bool(session.scalar(statement))


def get_user_by_id(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == normalize_username(username))
    return session.scalars(statement).first()


def get_workspace(session: Session, workspace_id: str) -> Workspace | None:
    return session.get(Workspace, workspace_id)


def list_workspaces(session: Session) -> list[Workspace]:
    statement = select(Workspace).order_by(Workspace.created_at.asc())
    return list(session.scalars(statement))


def list_users(session: Session, workspace_id: str | None = None) -> list[User]:
    statement = select(User)
    if workspace_id:
        statement = statement.where(User.workspace_id == workspace_id)
    statement = statement.order_by(User.created_at.asc(), User.username.asc())
    return list(session.scalars(statement))


def count_active_admins(session: Session, workspace_id: str | None) -> int:
    statement = select(func.count()).select_from(User).where(User.role == "workspace_admin", User.is_active.is_(True))
    if workspace_id:
        statement = statement.where(User.workspace_id == workspace_id)
    return int(session.scalar(statement) or 0)


def create_workspace(session: Session, *, name: str) -> Workspace:
    slug = _slugify(name)
    existing = session.scalars(select(Workspace).where(Workspace.slug == slug)).first()
    if existing:
        return existing
    workspace = Workspace(name=name.strip(), slug=slug)
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


def create_user(
    session: Session,
    *,
    workspace_id: str | None,
    username: str,
    email: str,
    password: str,
    role: str,
    full_name: str = "",
    is_active: bool = True,
) -> User:
    normalized_username = normalize_username(username)
    normalized_email = normalize_email(email)
    if get_user_by_username(session, normalized_username):
        raise ValueError("A user with that username already exists")
    existing_email = session.scalars(select(User).where(User.email == normalized_email)).first()
    if existing_email:
        raise ValueError("A user with that email already exists")

    user = User(
        workspace_id=workspace_id,
        username=normalized_username,
        email=normalized_email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user(
    session: Session,
    user: User,
    *,
    full_name: str | None = None,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
    acting_user: User | None = None,
) -> User:
    target_role = role if role is not None else user.role
    target_is_active = is_active if is_active is not None else user.is_active

    is_last_active_admin = user.role == "workspace_admin" and user.is_active and count_active_admins(session, user.workspace_id) <= 1
    if is_last_active_admin and (target_role != "workspace_admin" or not target_is_active):
        raise ValueError("Keep at least one active workspace admin in the tenant")
    if acting_user and acting_user.id == user.id and is_active is False:
        raise ValueError("You cannot deactivate your own account")

    if full_name is not None:
        user.full_name = full_name.strip()
    if email is not None:
        normalized_email = normalize_email(email)
        existing = session.scalars(select(User).where(User.email == normalized_email, User.id != user.id)).first()
        if existing:
            raise ValueError("A user with that email already exists")
        user.email = normalized_email
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if password:
        user.password_hash = hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def ensure_bootstrap_workspace_admin(session: Session, settings: Settings) -> User | None:
    if not settings.bootstrap_admin_configured:
        return None

    workspace = create_workspace(session, name=settings.bootstrap_workspace_name)
    existing_user = get_user_by_username(session, settings.bootstrap_admin_username or "")
    if existing_user:
        return existing_user

    return create_user(
        session,
        workspace_id=workspace.id,
        username=settings.bootstrap_admin_username or "admin",
        email=settings.bootstrap_admin_email or f"admin@{workspace.slug}.local",
        password=settings.bootstrap_admin_password or "",
        role="workspace_admin",
        full_name="Workspace Administrator",
        is_active=True,
    )


@dataclass
class AuthResult:
    user: User | None
    error: str | None = None


def authenticate_user(session: Session, username: str, password: str, settings: Settings) -> AuthResult:
    user = get_user_by_username(session, username)
    if user is None or not user.is_active:
        return AuthResult(user=None, error="Invalid credentials")

    now = _now()
    locked_until = _coerce_utc(user.locked_until)
    if locked_until and locked_until > now:
        return AuthResult(user=None, error="Account temporarily locked. Try again later.")

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_attempts = 0
        session.add(user)
        session.commit()
        locked_until = _coerce_utc(user.locked_until)
        if locked_until and locked_until > now:
            return AuthResult(user=None, error="Account temporarily locked. Try again later.")
        return AuthResult(user=None, error="Invalid credentials")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    session.add(user)
    session.commit()
    session.refresh(user)
    return AuthResult(user=user)


def can_write(user: User | None) -> bool:
    return bool(user and user.role in WRITER_ROLES)


def can_manage_users(user: User | None) -> bool:
    return bool(user and user.role in ADMIN_ROLES)


def can_approve_financials(user: User | None) -> bool:
    return bool(user and user.role in FINANCE_APPROVER_ROLES)
