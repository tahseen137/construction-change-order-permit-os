from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


UserRole = Literal["platform_admin", "workspace_admin", "project_manager", "project_engineer", "finance_approver", "viewer"]
ProjectStatus = Literal["precon", "active", "closeout", "archived"]
SectorType = Literal["office", "retail", "industrial", "healthcare", "hospitality", "mixed_use", "other"]
PermitStatus = Literal["draft", "submitted", "revision_requested", "approved", "inspection_pending", "closed", "expired"]
InspectionStatus = Literal["not_scheduled", "scheduled", "passed", "failed", "rescheduled"]
ChangeEventSource = Literal["owner_request", "permit_issue", "field_issue", "rfi", "design_change", "schedule_delay"]
ChangeEventStatus = Literal["draft", "pricing_requested", "priced", "internal_review", "owner_submitted", "approved", "rejected", "executed"]
RFQStatus = Literal["draft", "sent", "received", "closed"]
ChangeOrderKind = Literal["owner", "subcontract"]
ChangeOrderStatus = Literal["draft", "pending_approval", "approved", "rejected", "executed"]
ApprovalStatus = Literal["pending", "approved", "rejected", "needs_changes"]


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    default_currency: str
    is_active: bool


class PermissionSummary(BaseModel):
    can_write: bool
    can_manage_users: bool
    can_approve_financials: bool


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str | None
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None


class SessionStatusResponse(BaseModel):
    auth_required: bool
    authenticated: bool
    next_path: str | None = None
    csrf_token: str | None = None
    current_user: CurrentUserResponse | None = None
    workspace: WorkspaceRead | None = None
    permissions: PermissionSummary = PermissionSummary(
        can_write=False,
        can_manage_users=False,
        can_approve_financials=False,
    )


class SessionLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=1, max_length=200)
    next_path: str = Field(default="/", max_length=500)


class UserRead(CurrentUserResponse):
    created_at: datetime
    updated_at: datetime
    failed_login_attempts: int
    locked_until: datetime | None


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field(default="", max_length=120)
    role: UserRole = "project_engineer"
    password: str = Field(..., min_length=8, max_length=200)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=5, max_length=255)
    full_name: str | None = Field(default=None, max_length=120)
    role: UserRole | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    is_active: bool | None = None


class ActivityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str | None
    actor_user_id: str | None
    actor_username: str
    action: str
    entity_type: str
    entity_id: str | None
    project_id: str | None
    description: str
    details: dict[str, object]
    created_at: datetime


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=160)
    project_code: str = Field(..., min_length=2, max_length=40)
    client_name: str = Field(..., min_length=2, max_length=160)
    location: str = Field(..., min_length=2, max_length=160)
    sector: SectorType = "industrial"
    status: ProjectStatus = "precon"
    contract_value_usd: float = Field(default=0, ge=0)
    target_margin_pct: float = Field(default=0, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    notes: str = Field(default="", max_length=4000)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    project_code: str | None = Field(default=None, min_length=2, max_length=40)
    client_name: str | None = Field(default=None, min_length=2, max_length=160)
    location: str | None = Field(default=None, min_length=2, max_length=160)
    sector: SectorType | None = None
    status: ProjectStatus | None = None
    contract_value_usd: float | None = Field(default=None, ge=0)
    target_margin_pct: float | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PermitDependencyCreate(BaseModel):
    depends_on_permit_id: str
    dependency_type: str = Field(default="blocks", min_length=2, max_length=40)
    notes: str = Field(default="", max_length=1000)


class InspectionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    scheduled_for: date | None = None
    status: InspectionStatus = "scheduled"
    inspector_name: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    permit_id: str
    name: str
    scheduled_for: date | None
    status: InspectionStatus
    inspector_name: str
    notes: str
    created_at: datetime
    updated_at: datetime


class PermitBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    jurisdiction: str = Field(..., min_length=2, max_length=160)
    package_name: str = Field(default="", max_length=160)
    permit_number: str = Field(default="", max_length=80)
    responsible_owner: str = Field(default="", max_length=120)
    status: PermitStatus = "draft"
    submission_due_date: date | None = None
    submitted_at: date | None = None
    approved_at: date | None = None
    revision_requested_at: date | None = None
    inspection_due_date: date | None = None
    expiration_date: date | None = None
    revision_count: int = Field(default=0, ge=0)
    inspection_status: InspectionStatus = "not_scheduled"
    current_blocker: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=4000)


class PermitCreate(PermitBase):
    dependencies: list[PermitDependencyCreate] = Field(default_factory=list)
    inspections: list[InspectionCreate] = Field(default_factory=list)


class PermitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=160)
    package_name: str | None = Field(default=None, max_length=160)
    permit_number: str | None = Field(default=None, max_length=80)
    responsible_owner: str | None = Field(default=None, max_length=120)
    status: PermitStatus | None = None
    submission_due_date: date | None = None
    submitted_at: date | None = None
    approved_at: date | None = None
    revision_requested_at: date | None = None
    inspection_due_date: date | None = None
    expiration_date: date | None = None
    revision_count: int | None = Field(default=None, ge=0)
    inspection_status: InspectionStatus | None = None
    current_blocker: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=4000)


class PermitDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    permit_id: str
    depends_on_permit_id: str
    dependency_type: str
    notes: str


class PermitRead(PermitBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    project_id: str
    dependencies: list[PermitDependencyRead]
    inspections: list[InspectionRead]
    linked_change_event_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChangeEventBase(BaseModel):
    source_type: ChangeEventSource = "owner_request"
    title: str = Field(..., min_length=3, max_length=180)
    affected_scope: str = Field(default="", max_length=180)
    subcontractor_name: str = Field(default="", max_length=140)
    owner_reference: str = Field(default="", max_length=120)
    cost_impact_usd: float = Field(default=0, ge=0)
    schedule_impact_days: int = Field(default=0, ge=0)
    status: ChangeEventStatus = "draft"
    summary: str = Field(default="", max_length=4000)
    risk_tags: list[str] = Field(default_factory=list, max_length=10)
    required_action_date: date | None = None
    notes: str = Field(default="", max_length=4000)


class ChangeEventCreate(ChangeEventBase):
    originating_permit_id: str | None = None


class ChangeEventUpdate(BaseModel):
    source_type: ChangeEventSource | None = None
    title: str | None = Field(default=None, min_length=3, max_length=180)
    affected_scope: str | None = Field(default=None, max_length=180)
    subcontractor_name: str | None = Field(default=None, max_length=140)
    owner_reference: str | None = Field(default=None, max_length=120)
    cost_impact_usd: float | None = Field(default=None, ge=0)
    schedule_impact_days: int | None = Field(default=None, ge=0)
    status: ChangeEventStatus | None = None
    summary: str | None = Field(default=None, max_length=4000)
    risk_tags: list[str] | None = Field(default=None, max_length=10)
    required_action_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class RFQCreate(BaseModel):
    subcontractor_name: str = Field(..., min_length=2, max_length=140)
    scope_summary: str = Field(..., min_length=5, max_length=4000)
    status: RFQStatus = "draft"
    sent_at: date | None = None
    due_at: date | None = None
    notes: str = Field(default="", max_length=2000)


class RFQRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    change_event_id: str
    subcontractor_name: str
    scope_summary: str
    status: RFQStatus
    sent_at: date | None
    due_at: date | None
    notes: str
    created_at: datetime
    updated_at: datetime


class QuoteCreate(BaseModel):
    subcontractor_name: str = Field(..., min_length=2, max_length=140)
    rfq_id: str | None = None
    amount_usd: float = Field(..., ge=0)
    quoted_at: date | None = None
    inclusions: str = Field(default="", max_length=4000)
    exclusions: str = Field(default="", max_length=4000)
    is_selected: bool = False
    notes: str = Field(default="", max_length=2000)


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    change_event_id: str
    rfq_id: str | None
    subcontractor_name: str
    amount_usd: float
    quoted_at: date | None
    inclusions: str
    exclusions: str
    is_selected: bool
    notes: str
    created_at: datetime
    updated_at: datetime


class ApprovalStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    change_order_id: str
    step_order: int
    role_required: str
    approver_name: str
    status: ApprovalStatus
    decision_notes: str
    acted_at: date | None
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRequest(BaseModel):
    status: Literal["approved", "rejected", "needs_changes"]
    decision_notes: str = Field(default="", max_length=2000)


class ChangeOrderCreate(BaseModel):
    kind: ChangeOrderKind = "owner"
    number: str = Field(..., min_length=2, max_length=60)
    title: str = Field(..., min_length=3, max_length=180)
    amount_usd: float = Field(..., ge=0)
    schedule_impact_days: int = Field(default=0, ge=0)
    description: str = Field(default="", max_length=4000)


class ChangeOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    change_event_id: str
    kind: ChangeOrderKind
    number: str
    title: str
    status: ChangeOrderStatus
    amount_usd: float
    schedule_impact_days: int
    submitted_at: date | None
    approved_at: date | None
    executed_at: date | None
    description: str
    approvals: list[ApprovalStepRead]
    created_at: datetime
    updated_at: datetime


class ChangeEventRead(ChangeEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    project_id: str
    originating_permit_id: str | None
    rfqs: list[RFQRead]
    quotes: list[QuoteRead]
    change_orders: list[ChangeOrderRead]
    created_at: datetime
    updated_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    project_id: str | None
    permit_id: str | None
    change_event_id: str | None
    change_order_id: str | None
    filename: str
    content_type: str
    storage_key: str
    size_bytes: int
    extracted_text: str
    extraction_confidence: float
    extracted_fields: dict[str, object]
    created_at: datetime
    updated_at: datetime


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    project_code: str
    client_name: str
    location: str
    sector: SectorType
    status: ProjectStatus
    contract_value_usd: float
    target_margin_pct: float
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime
    permit_count: int
    change_event_count: int
    pending_change_order_count: int
    at_risk_cost_usd: float


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    permits: list[PermitRead]
    change_events: list[ChangeEventRead]
    created_at: datetime
    updated_at: datetime


class PermitImportRequest(BaseModel):
    project_id: str
    csv_content: str = Field(..., min_length=1, max_length=500_000)


class PermitImportResponse(BaseModel):
    created_count: int
    skipped_blank_rows: int
    error_count: int
    errors: list[str]
    permits: list[PermitRead]


class ChangeEventImportRow(BaseModel):
    title: str
    source_type: ChangeEventSource
    affected_scope: str
    subcontractor_name: str
    owner_reference: str
    cost_impact_usd: float
    schedule_impact_days: int
    required_action_date: date | None
    summary: str


class NotificationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    notification_type: str
    recipient_email: str
    subject: str
    status: str
    payload: dict[str, object]
    sent_at: datetime | None
    error_message: str
    created_at: datetime
    updated_at: datetime


class DashboardRead(BaseModel):
    active_projects: int
    permits_at_risk: int
    overdue_permits: int
    pending_approvals: int
    at_risk_cost_usd: float
    schedule_slip_days: int
    drafted_change_events: int
    notification_backlog: int


class OwnerPackageRead(BaseModel):
    change_order_id: str
    markdown: str


class WorkspaceSeedSummary(BaseModel):
    workspace: WorkspaceRead
    current_user: CurrentUserResponse
