from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


def _timestamp() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_timestamp)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_timestamp, onupdate=_timestamp)


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_workspaces_slug"),
        Index("ix_workspaces_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="workspace")
    projects: Mapped[list["Project"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_workspace_id", "workspace_id"),
        Index("ix_users_role", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(24), default="workspace_admin", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace | None] = relationship(back_populates="users")
    activity_events: Mapped[list["ActivityEvent"]] = relationship(back_populates="actor")


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_workspace_id", "workspace_id"),
        Index("ix_activity_events_created_at", "created_at"),
        Index("ix_activity_events_action", "action"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_timestamp)

    actor: Mapped[User | None] = relationship(back_populates="activity_events")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "project_code", name="uq_projects_workspace_code"),
        Index("ix_projects_workspace_id", "workspace_id"),
        Index("ix_projects_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    project_code: Mapped[str] = mapped_column(String(40), nullable=False)
    client_name: Mapped[str] = mapped_column(String(160), nullable=False)
    location: Mapped[str] = mapped_column(String(160), nullable=False)
    sector: Mapped[str] = mapped_column(String(32), default="industrial", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="precon", nullable=False)
    contract_value_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_margin_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    permits: Mapped[list["Permit"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Permit.created_at",
    )
    change_events: Mapped[list["ChangeEvent"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ChangeEvent.updated_at.desc()",
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="project")


class Permit(TimestampMixin, Base):
    __tablename__ = "permits"
    __table_args__ = (
        Index("ix_permits_workspace_id", "workspace_id"),
        Index("ix_permits_project_id", "project_id"),
        Index("ix_permits_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(160), nullable=False)
    package_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    permit_number: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    responsible_owner: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    submission_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    revision_requested_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    inspection_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inspection_status: Mapped[str] = mapped_column(String(24), default="not_scheduled", nullable=False)
    current_blocker: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    project: Mapped[Project] = relationship(back_populates="permits")
    dependencies: Mapped[list["PermitDependency"]] = relationship(
        back_populates="permit",
        cascade="all, delete-orphan",
        foreign_keys="PermitDependency.permit_id",
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="permit",
        cascade="all, delete-orphan",
        order_by="Inspection.scheduled_for",
    )
    linked_change_event: Mapped["ChangeEvent | None"] = relationship(back_populates="originating_permit", uselist=False)
    documents: Mapped[list["Document"]] = relationship(back_populates="permit")


class PermitDependency(TimestampMixin, Base):
    __tablename__ = "permit_dependencies"
    __table_args__ = (
        UniqueConstraint("permit_id", "depends_on_permit_id", name="uq_permit_dependencies_pair"),
        Index("ix_permit_dependencies_workspace_id", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    permit_id: Mapped[str] = mapped_column(ForeignKey("permits.id", ondelete="CASCADE"), nullable=False)
    depends_on_permit_id: Mapped[str] = mapped_column(ForeignKey("permits.id", ondelete="CASCADE"), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(40), default="blocks", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    permit: Mapped[Permit] = relationship(back_populates="dependencies", foreign_keys=[permit_id])
    depends_on_permit: Mapped[Permit] = relationship(foreign_keys=[depends_on_permit_id])


class Inspection(TimestampMixin, Base):
    __tablename__ = "inspections"
    __table_args__ = (
        Index("ix_inspections_workspace_id", "workspace_id"),
        Index("ix_inspections_permit_id", "permit_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    permit_id: Mapped[str] = mapped_column(ForeignKey("permits.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="scheduled", nullable=False)
    inspector_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    permit: Mapped[Permit] = relationship(back_populates="inspections")


class ChangeEvent(TimestampMixin, Base):
    __tablename__ = "change_events"
    __table_args__ = (
        Index("ix_change_events_workspace_id", "workspace_id"),
        Index("ix_change_events_project_id", "project_id"),
        Index("ix_change_events_status", "status"),
        UniqueConstraint("originating_permit_id", name="uq_change_events_originating_permit"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    originating_permit_id: Mapped[str | None] = mapped_column(ForeignKey("permits.id", ondelete="SET NULL"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="owner_request", nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    affected_scope: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    subcontractor_name: Mapped[str] = mapped_column(String(140), default="", nullable=False)
    owner_reference: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    cost_impact_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    schedule_impact_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    required_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    project: Mapped[Project] = relationship(back_populates="change_events")
    originating_permit: Mapped[Permit | None] = relationship(back_populates="linked_change_event")
    rfqs: Mapped[list["RFQ"]] = relationship(back_populates="change_event", cascade="all, delete-orphan")
    quotes: Mapped[list["Quote"]] = relationship(back_populates="change_event", cascade="all, delete-orphan")
    change_orders: Mapped[list["ChangeOrder"]] = relationship(
        back_populates="change_event",
        cascade="all, delete-orphan",
        order_by="ChangeOrder.updated_at.desc()",
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="change_event")


class RFQ(TimestampMixin, Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        Index("ix_rfqs_workspace_id", "workspace_id"),
        Index("ix_rfqs_change_event_id", "change_event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    change_event_id: Mapped[str] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False)
    subcontractor_name: Mapped[str] = mapped_column(String(140), nullable=False)
    scope_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    sent_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    change_event: Mapped[ChangeEvent] = relationship(back_populates="rfqs")
    quotes: Mapped[list["Quote"]] = relationship(back_populates="rfq")


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_workspace_id", "workspace_id"),
        Index("ix_quotes_change_event_id", "change_event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    change_event_id: Mapped[str] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False)
    rfq_id: Mapped[str | None] = mapped_column(ForeignKey("rfqs.id", ondelete="SET NULL"), nullable=True)
    subcontractor_name: Mapped[str] = mapped_column(String(140), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quoted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    inclusions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exclusions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    change_event: Mapped[ChangeEvent] = relationship(back_populates="quotes")
    rfq: Mapped[RFQ | None] = relationship(back_populates="quotes")


class ChangeOrder(TimestampMixin, Base):
    __tablename__ = "change_orders"
    __table_args__ = (
        Index("ix_change_orders_workspace_id", "workspace_id"),
        Index("ix_change_orders_change_event_id", "change_event_id"),
        Index("ix_change_orders_status", "status"),
        UniqueConstraint("workspace_id", "number", name="uq_change_orders_workspace_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    change_event_id: Mapped[str] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="owner", nullable=False)
    number: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    schedule_impact_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    executed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    change_event: Mapped[ChangeEvent] = relationship(back_populates="change_orders")
    approvals: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="change_order",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.step_order",
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="change_order")


class ApprovalStep(TimestampMixin, Base):
    __tablename__ = "approval_steps"
    __table_args__ = (
        Index("ix_approval_steps_workspace_id", "workspace_id"),
        Index("ix_approval_steps_change_order_id", "change_order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    change_order_id: Mapped[str] = mapped_column(ForeignKey("change_orders.id", ondelete="CASCADE"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role_required: Mapped[str] = mapped_column(String(24), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    decision_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    acted_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    change_order: Mapped[ChangeOrder] = relationship(back_populates="approvals")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_workspace_id", "workspace_id"),
        Index("ix_documents_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    permit_id: Mapped[str | None] = mapped_column(ForeignKey("permits.id", ondelete="CASCADE"), nullable=True)
    change_event_id: Mapped[str | None] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"), nullable=True)
    change_order_id: Mapped[str | None] = mapped_column(ForeignKey("change_orders.id", ondelete="CASCADE"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    extracted_fields: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="documents")
    permit: Mapped[Permit | None] = relationship(back_populates="documents")
    change_event: Mapped[ChangeEvent | None] = relationship(back_populates="documents")
    change_order: Mapped[ChangeOrder | None] = relationship(back_populates="documents")


class NotificationJob(TimestampMixin, Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        Index("ix_notification_jobs_workspace_id", "workspace_id"),
        Index("ix_notification_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
