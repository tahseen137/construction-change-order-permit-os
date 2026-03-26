from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models import (
    ApprovalStep,
    ChangeEvent,
    ChangeOrder,
    Document,
    Inspection,
    NotificationJob,
    Permit,
    PermitDependency,
    Project,
    Quote,
    RFQ,
    User,
    Workspace,
)
from app.notifications import queue_notification, send_notification
from app.permit_io import parse_permits_csv
from app.reporting import build_owner_change_order_markdown
from app.schemas import (
    ApprovalDecisionRequest,
    ChangeEventCreate,
    ChangeEventUpdate,
    ChangeOrderCreate,
    DashboardRead,
    InspectionCreate,
    PermitCreate,
    PermitImportResponse,
    PermitUpdate,
    ProjectCreate,
    ProjectUpdate,
    QuoteCreate,
    RFQCreate,
)
from app.user_service import list_users


def _today() -> date:
    return datetime.now(UTC).date()


def _project_query(workspace_id: str) -> Select[tuple[Project]]:
    return (
        select(Project)
        .where(Project.workspace_id == workspace_id)
        .options(
            selectinload(Project.permits).selectinload(Permit.dependencies),
            selectinload(Project.permits).selectinload(Permit.inspections),
            selectinload(Project.permits).selectinload(Permit.linked_change_event),
            selectinload(Project.change_events).selectinload(ChangeEvent.rfqs),
            selectinload(Project.change_events).selectinload(ChangeEvent.quotes),
            selectinload(Project.change_events)
            .selectinload(ChangeEvent.change_orders)
            .selectinload(ChangeOrder.approvals),
        )
        .order_by(Project.updated_at.desc())
    )


def list_projects(session: Session, workspace_id: str) -> list[Project]:
    return list(session.scalars(_project_query(workspace_id)))


def get_project(session: Session, workspace_id: str, project_id: str) -> Project | None:
    return session.scalars(_project_query(workspace_id).where(Project.id == project_id)).first()


def _project_code_exists(session: Session, workspace_id: str, project_code: str, exclude_project_id: str | None = None) -> bool:
    statement = select(Project).where(
        Project.workspace_id == workspace_id,
        Project.project_code == project_code.strip(),
    )
    if exclude_project_id:
        statement = statement.where(Project.id != exclude_project_id)
    return session.scalars(statement).first() is not None


def create_project(session: Session, workspace: Workspace, payload: ProjectCreate) -> Project:
    if _project_code_exists(session, workspace.id, payload.project_code):
        raise ValueError("A project with that code already exists in this workspace")
    project = Project(workspace_id=workspace.id, **payload.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def update_project(session: Session, project: Project, payload: ProjectUpdate) -> Project:
    if payload.project_code and _project_code_exists(session, project.workspace_id, payload.project_code, exclude_project_id=project.id):
        raise ValueError("A project with that code already exists in this workspace")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, project: Project) -> None:
    session.delete(project)
    session.commit()


def list_project_permits(project: Project) -> list[Permit]:
    return sorted(project.permits, key=lambda permit: permit.created_at)


def list_project_change_events(project: Project) -> list[ChangeEvent]:
    return sorted(project.change_events, key=lambda event: event.updated_at, reverse=True)


def get_permit(project: Project, permit_id: str) -> Permit | None:
    return next((permit for permit in project.permits if permit.id == permit_id), None)


def get_change_event(project: Project, change_event_id: str) -> ChangeEvent | None:
    return next((event for event in project.change_events if event.id == change_event_id), None)


def get_change_order(change_event: ChangeEvent, change_order_id: str) -> ChangeOrder | None:
    return next((change_order for change_order in change_event.change_orders if change_order.id == change_order_id), None)


def get_document(session: Session, workspace_id: str, document_id: str) -> Document | None:
    statement = select(Document).where(Document.workspace_id == workspace_id, Document.id == document_id)
    return session.scalars(statement).first()


def _permit_needs_change_event(permit: Permit) -> bool:
    return bool(
        permit.status == "revision_requested"
        or permit.current_blocker.strip()
        or permit.inspection_status == "failed"
    )


def _permit_issue_summary(permit: Permit) -> str:
    if permit.current_blocker.strip():
        return permit.current_blocker.strip()
    if permit.status == "revision_requested":
        return f"{permit.name} was sent back for revisions by {permit.jurisdiction}."
    if permit.inspection_status == "failed":
        return f"{permit.name} failed inspection and requires remediation before reinspection."
    return f"{permit.name} requires follow-up."


def _suggest_risk_tags(title: str, summary: str, source_type: str) -> list[str]:
    text = f"{title} {summary} {source_type}".casefold()
    tags: list[str] = []
    for tag, keywords in {
        "permit_blocker": ["permit", "revision", "inspection", "jurisdiction"],
        "schedule_risk": ["delay", "late", "failed", "schedule", "reinspection"],
        "owner_scope_gap": ["owner", "scope", "design change", "asi"],
        "unpriced_exposure": ["budget", "tbd", "pricing", "quote"],
    }.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)
    return tags


def _sync_change_event_from_permit_issue(session: Session, permit: Permit) -> ChangeEvent | None:
    if not _permit_needs_change_event(permit):
        return permit.linked_change_event

    title = f"Permit blocker: {permit.name}"
    summary = _permit_issue_summary(permit)
    if permit.linked_change_event:
        event = permit.linked_change_event
        event.title = title
        event.summary = summary
        event.source_type = "permit_issue"
        event.affected_scope = permit.package_name or permit.name
        event.status = "internal_review" if event.status == "draft" else event.status
        event.risk_tags = _suggest_risk_tags(title, summary, "permit_issue")
        if permit.inspection_due_date:
            event.required_action_date = permit.inspection_due_date
        session.add(event)
        return event

    event = ChangeEvent(
        workspace_id=permit.workspace_id,
        project_id=permit.project_id,
        originating_permit_id=permit.id,
        source_type="permit_issue",
        title=title,
        affected_scope=permit.package_name or permit.name,
        subcontractor_name="",
        owner_reference=permit.permit_number,
        cost_impact_usd=0.0,
        schedule_impact_days=0,
        status="internal_review",
        summary=summary,
        risk_tags=_suggest_risk_tags(title, summary, "permit_issue"),
        required_action_date=permit.inspection_due_date or permit.submission_due_date,
    )
    session.add(event)
    return event


def _apply_inspections(permit: Permit, inspections: list[InspectionCreate]) -> None:
    permit.inspections.clear()
    for inspection_payload in inspections:
        permit.inspections.append(Inspection(workspace_id=permit.workspace_id, **inspection_payload.model_dump()))


def _apply_dependencies(permit: Permit, dependencies: list[str] | None = None) -> None:
    if dependencies is None:
        return
    permit.dependencies.clear()
    for depends_on_permit_id in dependencies:
        permit.dependencies.append(
            PermitDependency(
                workspace_id=permit.workspace_id,
                depends_on_permit_id=depends_on_permit_id,
                dependency_type="blocks",
            )
        )


def create_permit(session: Session, project: Project, payload: PermitCreate) -> Permit:
    permit = Permit(workspace_id=project.workspace_id, project_id=project.id, **payload.model_dump(exclude={"dependencies", "inspections"}))
    session.add(permit)
    session.flush()

    for dependency in payload.dependencies:
        permit.dependencies.append(
            PermitDependency(
                workspace_id=project.workspace_id,
                depends_on_permit_id=dependency.depends_on_permit_id,
                dependency_type=dependency.dependency_type,
                notes=dependency.notes,
            )
        )
    for inspection in payload.inspections:
        permit.inspections.append(Inspection(workspace_id=project.workspace_id, **inspection.model_dump()))

    _sync_change_event_from_permit_issue(session, permit)
    session.commit()
    session.refresh(permit)
    return permit


def import_permits_from_csv(session: Session, project: Project, csv_content: str) -> PermitImportResponse:
    permit_payloads, errors, skipped_blank_rows = parse_permits_csv(csv_content)
    if errors:
        return PermitImportResponse(created_count=0, skipped_blank_rows=skipped_blank_rows, error_count=len(errors), errors=errors, permits=[])

    created_permits: list[Permit] = []
    for payload in permit_payloads:
        permit = Permit(workspace_id=project.workspace_id, project_id=project.id, **payload.model_dump(exclude={"dependencies", "inspections"}))
        session.add(permit)
        session.flush()
        _sync_change_event_from_permit_issue(session, permit)
        created_permits.append(permit)
    session.commit()
    for permit in created_permits:
        session.refresh(permit)
    return PermitImportResponse(
        created_count=len(created_permits),
        skipped_blank_rows=skipped_blank_rows,
        error_count=0,
        errors=[],
        permits=created_permits,  # type: ignore[arg-type]
    )


def update_permit(session: Session, permit: Permit, payload: PermitUpdate) -> Permit:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(permit, key, value)
    _sync_change_event_from_permit_issue(session, permit)
    session.add(permit)
    session.commit()
    session.refresh(permit)
    return permit


def create_change_event(session: Session, project: Project, payload: ChangeEventCreate) -> ChangeEvent:
    event = ChangeEvent(
        workspace_id=project.workspace_id,
        project_id=project.id,
        **payload.model_dump(),
    )
    if not event.risk_tags:
        event.risk_tags = _suggest_risk_tags(event.title, event.summary, event.source_type)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def update_change_event(session: Session, change_event: ChangeEvent, payload: ChangeEventUpdate) -> ChangeEvent:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(change_event, key, value)
    if not change_event.risk_tags:
        change_event.risk_tags = _suggest_risk_tags(change_event.title, change_event.summary, change_event.source_type)
    session.add(change_event)
    session.commit()
    session.refresh(change_event)
    return change_event


def create_rfq(session: Session, change_event: ChangeEvent, payload: RFQCreate) -> RFQ:
    rfq = RFQ(workspace_id=change_event.workspace_id, change_event_id=change_event.id, **payload.model_dump())
    if rfq.status == "draft" and rfq.sent_at:
        rfq.status = "sent"
    session.add(rfq)
    if change_event.status == "draft":
        change_event.status = "pricing_requested"
        session.add(change_event)
    session.commit()
    session.refresh(rfq)
    return rfq


def create_quote(session: Session, change_event: ChangeEvent, payload: QuoteCreate) -> Quote:
    quote = Quote(workspace_id=change_event.workspace_id, change_event_id=change_event.id, **payload.model_dump())
    session.add(quote)
    if payload.is_selected:
        for existing_quote in change_event.quotes:
            if existing_quote.id != quote.id:
                existing_quote.is_selected = False
                session.add(existing_quote)
        change_event.cost_impact_usd = payload.amount_usd
    if change_event.status in {"draft", "pricing_requested"}:
        change_event.status = "priced"
    session.add(change_event)
    session.commit()
    session.refresh(quote)
    return quote


def create_change_order(session: Session, change_event: ChangeEvent, payload: ChangeOrderCreate) -> ChangeOrder:
    existing = session.scalars(
        select(ChangeOrder).where(
            ChangeOrder.workspace_id == change_event.workspace_id,
            ChangeOrder.number == payload.number,
        )
    ).first()
    if existing:
        raise ValueError("A change order with that number already exists in this workspace")

    change_order = ChangeOrder(
        workspace_id=change_event.workspace_id,
        change_event_id=change_event.id,
        **payload.model_dump(),
    )
    session.add(change_order)
    if change_event.status in {"draft", "pricing_requested", "priced"}:
        change_event.status = "internal_review"
    session.add(change_event)
    session.commit()
    session.refresh(change_order)
    return change_order


def _approval_roles(amount_usd: float, settings: Settings) -> list[str]:
    roles = ["project_manager"]
    if amount_usd >= settings.approval_threshold_pm_usd:
        roles.append("finance_approver")
    if amount_usd >= settings.approval_threshold_finance_usd:
        roles.append("workspace_admin")
    return roles


def _role_display_name(role: str) -> str:
    return role.replace("_", " ").title()


def submit_change_order_for_approval(session: Session, change_order: ChangeOrder, settings: Settings) -> ChangeOrder:
    if change_order.status not in {"draft", "rejected"}:
        raise ValueError("Only draft or rejected change orders can be submitted for approval")

    workspace_users = list_users(session, change_order.workspace_id)
    for approval in list(change_order.approvals):
        session.delete(approval)
    session.flush()

    for idx, role in enumerate(_approval_roles(change_order.amount_usd, settings), start=1):
        approver = next((user for user in workspace_users if user.role == role and user.is_active), None)
        change_order.approvals.append(
            ApprovalStep(
                workspace_id=change_order.workspace_id,
                step_order=idx,
                role_required=role,
                approver_name=(approver.full_name or approver.username) if approver else _role_display_name(role),
                status="pending",
            )
        )
        if approver and approver.email:
            job = queue_notification(
                session,
                workspace_id=change_order.workspace_id,
                notification_type="approval_request",
                recipient_email=approver.email,
                subject=f"Approval requested: {change_order.number}",
                payload={
                    "body": f"Please review {change_order.number} for {change_order.title}. Amount: ${change_order.amount_usd:,.2f}.",
                    "change_order_id": change_order.id,
                },
            )
            send_notification(job, settings)
            session.add(job)

    change_order.status = "pending_approval"
    change_order.submitted_at = _today()
    change_order.change_event.status = "owner_submitted"
    session.add(change_order)
    session.add(change_order.change_event)
    session.commit()
    session.refresh(change_order)
    return change_order


def decide_approval_step(
    session: Session,
    change_order: ChangeOrder,
    step_id: str,
    payload: ApprovalDecisionRequest,
) -> ApprovalStep:
    step = next((approval for approval in change_order.approvals if approval.id == step_id), None)
    if step is None:
        raise ValueError("Approval step not found")
    if step.status != "pending":
        raise ValueError("Approval step has already been acted on")

    step.status = payload.status
    step.decision_notes = payload.decision_notes
    step.acted_at = _today()
    session.add(step)

    if payload.status == "approved":
        if all(approval.id == step.id or approval.status == "approved" for approval in change_order.approvals):
            change_order.status = "approved"
            change_order.approved_at = _today()
            change_order.change_event.status = "approved"
    elif payload.status == "rejected":
        change_order.status = "rejected"
        change_order.change_event.status = "rejected"
    else:
        change_order.status = "draft"
        change_order.change_event.status = "internal_review"

    session.add(change_order)
    session.add(change_order.change_event)
    session.commit()
    session.refresh(step)
    return step


def create_document(
    session: Session,
    *,
    workspace_id: str,
    project_id: str | None,
    permit_id: str | None,
    change_event_id: str | None,
    change_order_id: str | None,
    filename: str,
    content_type: str,
    storage_key: str,
    size_bytes: int,
    extracted_text: str,
    extraction_confidence: float,
    extracted_fields: dict[str, object],
) -> Document:
    document = Document(
        workspace_id=workspace_id,
        project_id=project_id,
        permit_id=permit_id,
        change_event_id=change_event_id,
        change_order_id=change_order_id,
        filename=filename,
        content_type=content_type,
        storage_key=storage_key,
        size_bytes=size_bytes,
        extracted_text=extracted_text,
        extraction_confidence=extraction_confidence,
        extracted_fields=extracted_fields,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def build_dashboard(session: Session, workspace_id: str) -> DashboardRead:
    today = _today()
    active_projects = int(
        session.scalar(select(func.count()).select_from(Project).where(Project.workspace_id == workspace_id, Project.status != "archived"))
        or 0
    )
    permits_at_risk = int(
        session.scalar(
            select(func.count()).select_from(Permit).where(
                Permit.workspace_id == workspace_id,
                (Permit.status == "revision_requested") | (Permit.current_blocker != "") | (Permit.inspection_status == "failed"),
            )
        )
        or 0
    )
    overdue_permits = int(
        session.scalar(
            select(func.count()).select_from(Permit).where(
                Permit.workspace_id == workspace_id,
                Permit.submission_due_date.is_not(None),
                Permit.submission_due_date < today,
                Permit.status.in_(["draft", "submitted", "revision_requested", "inspection_pending"]),
            )
        )
        or 0
    )
    pending_approvals = int(
        session.scalar(
            select(func.count()).select_from(ChangeOrder).where(
                ChangeOrder.workspace_id == workspace_id,
                ChangeOrder.status == "pending_approval",
            )
        )
        or 0
    )
    at_risk_cost_usd = float(
        session.scalar(
            select(func.coalesce(func.sum(ChangeEvent.cost_impact_usd), 0)).where(
                ChangeEvent.workspace_id == workspace_id,
                ChangeEvent.status.in_(["draft", "pricing_requested", "priced", "internal_review", "owner_submitted"]),
            )
        )
        or 0
    )
    schedule_slip_days = int(
        session.scalar(
            select(func.coalesce(func.sum(ChangeEvent.schedule_impact_days), 0)).where(
                ChangeEvent.workspace_id == workspace_id,
                ChangeEvent.status.in_(["draft", "pricing_requested", "priced", "internal_review", "owner_submitted"]),
            )
        )
        or 0
    )
    drafted_change_events = int(
        session.scalar(
            select(func.count()).select_from(ChangeEvent).where(
                ChangeEvent.workspace_id == workspace_id,
                ChangeEvent.status.in_(["draft", "pricing_requested", "priced", "internal_review"]),
            )
        )
        or 0
    )
    notification_backlog = int(
        session.scalar(
            select(func.count()).select_from(NotificationJob).where(
                NotificationJob.workspace_id == workspace_id,
                NotificationJob.status.in_(["queued", "failed"]),
            )
        )
        or 0
    )
    return DashboardRead(
        active_projects=active_projects,
        permits_at_risk=permits_at_risk,
        overdue_permits=overdue_permits,
        pending_approvals=pending_approvals,
        at_risk_cost_usd=round(at_risk_cost_usd, 2),
        schedule_slip_days=schedule_slip_days,
        drafted_change_events=drafted_change_events,
        notification_backlog=notification_backlog,
    )


def build_project_export(project: Project) -> dict[str, object]:
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "project_code": project.project_code,
            "client_name": project.client_name,
            "location": project.location,
            "sector": project.sector,
            "status": project.status,
            "contract_value_usd": project.contract_value_usd,
            "target_margin_pct": project.target_margin_pct,
        },
        "permits": [
            {
                "id": permit.id,
                "name": permit.name,
                "status": permit.status,
                "jurisdiction": permit.jurisdiction,
                "current_blocker": permit.current_blocker,
                "inspection_status": permit.inspection_status,
            }
            for permit in list_project_permits(project)
        ],
        "change_events": [
            {
                "id": event.id,
                "title": event.title,
                "status": event.status,
                "cost_impact_usd": event.cost_impact_usd,
                "schedule_impact_days": event.schedule_impact_days,
                "risk_tags": event.risk_tags,
            }
            for event in list_project_change_events(project)
        ],
    }


def owner_package_markdown(change_order: ChangeOrder) -> str:
    return build_owner_change_order_markdown(change_order.change_event.project, change_order.change_event, change_order)


@dataclass
class ProjectSummaryMetrics:
    permit_count: int
    change_event_count: int
    pending_change_order_count: int
    at_risk_cost_usd: float


def project_summary_metrics(project: Project) -> ProjectSummaryMetrics:
    pending_change_orders = 0
    at_risk_cost_usd = 0.0
    for event in project.change_events:
        if event.status in {"draft", "pricing_requested", "priced", "internal_review", "owner_submitted"}:
            at_risk_cost_usd += event.cost_impact_usd
        for change_order in event.change_orders:
            if change_order.status == "pending_approval":
                pending_change_orders += 1
    return ProjectSummaryMetrics(
        permit_count=len(project.permits),
        change_event_count=len(project.change_events),
        pending_change_order_count=pending_change_orders,
        at_risk_cost_usd=round(at_risk_cost_usd, 2),
    )
