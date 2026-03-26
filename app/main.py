from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Generator
from uuid import uuid4

import sentry_sdk
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.activity_service import list_activity_events, record_activity
from app.ai import extract_document_artifacts
from app.auth import (
    auth_required,
    clear_session,
    csrf_token_matches,
    current_session_user_id,
    ensure_csrf_token,
    is_authenticated,
    login_redirect,
    refresh_session_from_user,
    sanitize_next_path,
    set_authenticated_user_session,
)
from app.config import Settings, get_settings
from app.db import DatabaseState, build_database_state, database_is_ready, init_database
from app.models import ChangeEvent, ChangeOrder, Document, Permit, Project, User, Workspace
from app.permit_io import change_event_template_csv, permit_template_csv
from app.schemas import (
    ActivityEventRead,
    ApprovalDecisionRequest,
    ApprovalStepRead,
    ChangeEventCreate,
    ChangeEventRead,
    ChangeEventUpdate,
    ChangeOrderCreate,
    ChangeOrderRead,
    CurrentUserResponse,
    DashboardRead,
    DocumentRead,
    InspectionRead,
    OwnerPackageRead,
    PermitCreate,
    PermitImportRequest,
    PermitImportResponse,
    PermitRead,
    PermitUpdate,
    PermissionSummary,
    ProjectCreate,
    ProjectRead,
    ProjectSummary,
    ProjectUpdate,
    QuoteCreate,
    QuoteRead,
    RFQCreate,
    RFQRead,
    SessionLoginRequest,
    SessionStatusResponse,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
    WorkspaceRead,
)
from app.services import (
    build_dashboard,
    build_project_export,
    create_change_event,
    create_change_order,
    create_document,
    create_permit,
    create_project,
    create_quote,
    create_rfq,
    decide_approval_step,
    delete_project,
    get_change_event,
    get_change_order,
    get_document,
    get_permit,
    get_project,
    import_permits_from_csv,
    list_project_change_events,
    list_project_permits,
    list_projects,
    owner_package_markdown,
    project_summary_metrics,
    submit_change_order_for_approval,
    update_change_event,
    update_permit,
    update_project,
)
from app.storage import StorageClient, build_storage_client
from app.user_service import (
    authenticate_user,
    can_approve_financials,
    can_manage_users,
    can_write,
    create_user as create_workspace_user,
    ensure_bootstrap_workspace_admin,
    get_user_by_id,
    list_users as list_workspace_users,
    update_user as update_workspace_user,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _workspace_read(workspace: Workspace | None) -> WorkspaceRead | None:
    return WorkspaceRead.model_validate(workspace) if workspace else None


def _current_user_response(user: User | None) -> CurrentUserResponse | None:
    return CurrentUserResponse.model_validate(user) if user else None


def _permission_summary(user: User | None, request: Request) -> PermissionSummary:
    if not auth_required(request):
        return PermissionSummary(can_write=True, can_manage_users=True, can_approve_financials=True)
    return PermissionSummary(
        can_write=can_write(user),
        can_manage_users=can_manage_users(user),
        can_approve_financials=can_approve_financials(user),
    )


def _session_status(request: Request, user: User | None, next_path: str | None = "/") -> SessionStatusResponse:
    workspace = user.workspace if user else None
    authenticated = is_authenticated(request, user)
    csrf_token = ensure_csrf_token(request) if auth_required(request) and authenticated else None
    return SessionStatusResponse(
        auth_required=auth_required(request),
        authenticated=authenticated,
        next_path=next_path,
        csrf_token=csrf_token,
        current_user=_current_user_response(user),
        workspace=_workspace_read(workspace),
        permissions=_permission_summary(user, request),
    )


def _inspection_read(inspection) -> InspectionRead:
    return InspectionRead.model_validate(inspection)


def _permit_read(permit: Permit) -> PermitRead:
    return PermitRead(
        id=permit.id,
        workspace_id=permit.workspace_id,
        project_id=permit.project_id,
        name=permit.name,
        jurisdiction=permit.jurisdiction,
        package_name=permit.package_name,
        permit_number=permit.permit_number,
        responsible_owner=permit.responsible_owner,
        status=permit.status,  # type: ignore[arg-type]
        submission_due_date=permit.submission_due_date,
        submitted_at=permit.submitted_at,
        approved_at=permit.approved_at,
        revision_requested_at=permit.revision_requested_at,
        inspection_due_date=permit.inspection_due_date,
        expiration_date=permit.expiration_date,
        revision_count=permit.revision_count,
        inspection_status=permit.inspection_status,  # type: ignore[arg-type]
        current_blocker=permit.current_blocker,
        notes=permit.notes,
        dependencies=[
            {
                "id": dependency.id,
                "permit_id": dependency.permit_id,
                "depends_on_permit_id": dependency.depends_on_permit_id,
                "dependency_type": dependency.dependency_type,
                "notes": dependency.notes,
            }
            for dependency in permit.dependencies
        ],
        inspections=[_inspection_read(inspection) for inspection in permit.inspections],
        linked_change_event_id=permit.linked_change_event.id if permit.linked_change_event else None,
        created_at=permit.created_at,
        updated_at=permit.updated_at,
    )


def _approval_step_read(step) -> ApprovalStepRead:
    return ApprovalStepRead.model_validate(step)


def _change_order_read(change_order: ChangeOrder) -> ChangeOrderRead:
    return ChangeOrderRead(
        id=change_order.id,
        change_event_id=change_order.change_event_id,
        kind=change_order.kind,  # type: ignore[arg-type]
        number=change_order.number,
        title=change_order.title,
        status=change_order.status,  # type: ignore[arg-type]
        amount_usd=change_order.amount_usd,
        schedule_impact_days=change_order.schedule_impact_days,
        submitted_at=change_order.submitted_at,
        approved_at=change_order.approved_at,
        executed_at=change_order.executed_at,
        description=change_order.description,
        approvals=[_approval_step_read(step) for step in change_order.approvals],
        created_at=change_order.created_at,
        updated_at=change_order.updated_at,
    )


def _quote_read(quote) -> QuoteRead:
    return QuoteRead.model_validate(quote)


def _rfq_read(rfq) -> RFQRead:
    return RFQRead.model_validate(rfq)


def _change_event_read(change_event: ChangeEvent) -> ChangeEventRead:
    return ChangeEventRead(
        id=change_event.id,
        workspace_id=change_event.workspace_id,
        project_id=change_event.project_id,
        originating_permit_id=change_event.originating_permit_id,
        source_type=change_event.source_type,  # type: ignore[arg-type]
        title=change_event.title,
        affected_scope=change_event.affected_scope,
        subcontractor_name=change_event.subcontractor_name,
        owner_reference=change_event.owner_reference,
        cost_impact_usd=change_event.cost_impact_usd,
        schedule_impact_days=change_event.schedule_impact_days,
        status=change_event.status,  # type: ignore[arg-type]
        summary=change_event.summary,
        risk_tags=list(change_event.risk_tags),
        required_action_date=change_event.required_action_date,
        notes=change_event.notes,
        rfqs=[_rfq_read(rfq) for rfq in change_event.rfqs],
        quotes=[_quote_read(quote) for quote in change_event.quotes],
        change_orders=[_change_order_read(change_order) for change_order in change_event.change_orders],
        created_at=change_event.created_at,
        updated_at=change_event.updated_at,
    )


def _project_summary(project: Project) -> ProjectSummary:
    metrics = project_summary_metrics(project)
    return ProjectSummary(
        id=project.id,
        workspace_id=project.workspace_id,
        name=project.name,
        project_code=project.project_code,
        client_name=project.client_name,
        location=project.location,
        sector=project.sector,  # type: ignore[arg-type]
        status=project.status,  # type: ignore[arg-type]
        contract_value_usd=project.contract_value_usd,
        target_margin_pct=project.target_margin_pct,
        start_date=project.start_date,
        end_date=project.end_date,
        created_at=project.created_at,
        updated_at=project.updated_at,
        permit_count=metrics.permit_count,
        change_event_count=metrics.change_event_count,
        pending_change_order_count=metrics.pending_change_order_count,
        at_risk_cost_usd=metrics.at_risk_cost_usd,
    )


def _project_read(project: Project) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        workspace_id=project.workspace_id,
        name=project.name,
        project_code=project.project_code,
        client_name=project.client_name,
        location=project.location,
        sector=project.sector,  # type: ignore[arg-type]
        status=project.status,  # type: ignore[arg-type]
        contract_value_usd=project.contract_value_usd,
        target_margin_pct=project.target_margin_pct,
        start_date=project.start_date,
        end_date=project.end_date,
        notes=project.notes,
        permits=[_permit_read(permit) for permit in list_project_permits(project)],
        change_events=[_change_event_read(event) for event in list_project_change_events(project)],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _document_read(document: Document) -> DocumentRead:
    return DocumentRead.model_validate(document)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    database_state = build_database_state(resolved_settings)
    storage_client = build_storage_client(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if resolved_settings.sentry_dsn:
            sentry_sdk.init(dsn=resolved_settings.sentry_dsn, environment=resolved_settings.app_env)

        init_database(database_state, auto_create_schema=resolved_settings.auto_create_schema)
        app.state.settings = resolved_settings
        app.state.database = database_state
        app.state.storage = storage_client

        with database_state.session_factory() as session:
            ensure_bootstrap_workspace_admin(session, resolved_settings)
            app.state.auth_required = bool(list_workspace_users(session))

        yield
        database_state.engine.dispose()

    app = FastAPI(title=resolved_settings.app_name, version="0.1.0", lifespan=lifespan)

    if resolved_settings.enable_gzip:
        app.add_middleware(GZipMiddleware, minimum_size=500)
    if resolved_settings.session_secret:
        app.add_middleware(
            SessionMiddleware,
            secret_key=resolved_settings.session_secret,
            session_cookie="construction_ops_session",
            same_site="lax",
            https_only=resolved_settings.session_https_only,
            max_age=resolved_settings.session_max_age_seconds,
        )
    if resolved_settings.allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved_settings.allowed_hosts)
    if resolved_settings.enforce_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    @app.middleware("http")
    async def add_response_headers(request: Request, call_next):
        request_id = uuid4().hex
        started_at = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - started_at) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        if request.url.path in {"/", "/login"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    def get_database_state(request: Request) -> DatabaseState:
        return request.app.state.database  # type: ignore[return-value]

    def get_storage_client(request: Request) -> StorageClient:
        return request.app.state.storage  # type: ignore[return-value]

    def get_session(database: DatabaseState = Depends(get_database_state)) -> Generator[Session, None, None]:
        session = database.session_factory()
        try:
            yield session
        finally:
            session.close()

    def get_current_user(request: Request, session: Session = Depends(get_session)) -> User | None:
        if not auth_required(request):
            return None
        user_id = current_session_user_id(request)
        if not user_id:
            return None
        user = get_user_by_id(session, user_id)
        if user is None or not user.is_active:
            clear_session(request)
            return None
        refresh_session_from_user(request, user)
        return user

    def require_api_access(request: Request, current_user: User | None = Depends(get_current_user)) -> User | None:
        if not auth_required(request):
            return None
        if current_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return current_user

    def require_workspace(current_user: User | None = Depends(require_api_access), session: Session = Depends(get_session)) -> Workspace:
        if current_user is None or current_user.workspace_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace context required")
        workspace = session.get(Workspace, current_user.workspace_id)
        if workspace is None or not workspace.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace not available")
        return workspace

    def require_write_access(request: Request, current_user: User | None = Depends(get_current_user)) -> User | None:
        user = require_api_access(request, current_user)
        if user is not None and not can_write(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write access required")
        return user

    def require_admin_access(request: Request, current_user: User | None = Depends(get_current_user)) -> User | None:
        user = require_api_access(request, current_user)
        if user is not None and not can_manage_users(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace admin access required")
        return user

    def require_csrf_protection(request: Request, current_user: User | None = Depends(get_current_user)) -> None:
        if not auth_required(request) or current_user is None:
            return
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token_matches(request, csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")

    def require_project(
        project_id: str,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
    ) -> Project:
        project = get_project(session, workspace.id, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def readiness(database: DatabaseState = Depends(get_database_state)) -> dict[str, str]:
        if not database_is_ready(database):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"status": "ready"}

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, current_user: User | None = Depends(get_current_user)) -> Response:
        if not auth_required(request):
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        if is_authenticated(request, current_user):
            return RedirectResponse(url=sanitize_next_path(request.query_params.get("next")), status_code=status.HTTP_303_SEE_OTHER)
        return HTMLResponse(
            templates.get_template("login.html").render(
                request=request,
                next_path=sanitize_next_path(request.query_params.get("next")),
            )
        )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, current_user: User | None = Depends(get_current_user)) -> Response:
        if auth_required(request) and not is_authenticated(request, current_user):
            return RedirectResponse(url=login_redirect("/"), status_code=status.HTTP_303_SEE_OTHER)
        workspace = current_user.workspace if current_user else None
        return HTMLResponse(
            templates.get_template("index.html").render(
                request=request,
                auth_required=auth_required(request),
                current_user=_current_user_response(current_user),
                workspace=_workspace_read(workspace),
                permissions=_permission_summary(current_user, request),
                csrf_token=ensure_csrf_token(request) if is_authenticated(request, current_user) else "",
            )
        )

    @app.get("/api/session", response_model=SessionStatusResponse)
    def session_status(request: Request, current_user: User | None = Depends(get_current_user)) -> SessionStatusResponse:
        return _session_status(request, current_user, "/")

    @app.post("/api/session/login", response_model=SessionStatusResponse)
    def login_session(payload: SessionLoginRequest, request: Request, session: Session = Depends(get_session)) -> SessionStatusResponse:
        next_path = sanitize_next_path(payload.next_path)
        result = authenticate_user(session, payload.username, payload.password, request.app.state.settings)
        if result.user is None:
            clear_session(request)
            record_activity(
                session,
                workspace_id=None,
                action="auth.login_failed",
                entity_type="session",
                entity_id=None,
                actor_username=payload.username,
                description=f"Failed login attempt for {payload.username}.",
                details={"username": payload.username},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result.error or "Invalid credentials")

        set_authenticated_user_session(request, result.user)
        record_activity(
            session,
            workspace_id=result.user.workspace_id,
            action="auth.login",
            entity_type="session",
            entity_id=result.user.id,
            actor_user=result.user,
            description=f"{result.user.username} signed in.",
        )
        return _session_status(request, result.user, next_path)

    @app.post(
        "/api/session/logout",
        response_model=SessionStatusResponse,
        dependencies=[Depends(require_api_access), Depends(require_csrf_protection)],
    )
    def logout_session(
        request: Request,
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_api_access),
    ) -> SessionStatusResponse:
        if current_user is not None:
            record_activity(
                session,
                workspace_id=current_user.workspace_id,
                action="auth.logout",
                entity_type="session",
                entity_id=current_user.id,
                actor_user=current_user,
                description=f"{current_user.username} signed out.",
            )
        clear_session(request)
        return SessionStatusResponse(
            auth_required=auth_required(request),
            authenticated=False,
            next_path="/login",
            csrf_token=None,
            current_user=None,
            workspace=None,
            permissions=PermissionSummary(can_write=False, can_manage_users=False, can_approve_financials=False),
        )

    @app.get("/api/dashboard", response_model=DashboardRead, dependencies=[Depends(require_api_access)])
    def dashboard_endpoint(workspace: Workspace = Depends(require_workspace), session: Session = Depends(get_session)) -> DashboardRead:
        return build_dashboard(session, workspace.id)

    @app.get("/api/activity", response_model=list[ActivityEventRead], dependencies=[Depends(require_api_access)])
    def activity_endpoint(workspace: Workspace = Depends(require_workspace), session: Session = Depends(get_session)) -> list[ActivityEventRead]:
        return [ActivityEventRead.model_validate(event) for event in list_activity_events(session, workspace.id)]

    @app.get("/api/admin/users", response_model=list[UserRead], dependencies=[Depends(require_admin_access)])
    def list_users_endpoint(workspace: Workspace = Depends(require_workspace), session: Session = Depends(get_session)) -> list[UserRead]:
        return [UserRead.model_validate(user) for user in list_workspace_users(session, workspace.id)]

    @app.post(
        "/api/admin/users",
        response_model=UserRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_admin_access), Depends(require_csrf_protection)],
    )
    def create_user_endpoint(
        payload: UserCreateRequest,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_admin_access),
    ) -> UserRead:
        try:
            user = create_workspace_user(
                session,
                workspace_id=workspace.id,
                username=payload.username,
                email=payload.email,
                password=payload.password,
                role=payload.role,
                full_name=payload.full_name,
                is_active=payload.is_active,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        record_activity(
            session,
            workspace_id=workspace.id,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            actor_user=current_user,
            description=f"{current_user.username if current_user else 'system'} created user {user.username}.",
            details={"role": user.role, "email": user.email},
        )
        return UserRead.model_validate(user)

    @app.patch(
        "/api/admin/users/{user_id}",
        response_model=UserRead,
        dependencies=[Depends(require_admin_access), Depends(require_csrf_protection)],
    )
    def update_user_endpoint(
        user_id: str,
        payload: UserUpdateRequest,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_admin_access),
    ) -> UserRead:
        user = get_user_by_id(session, user_id)
        if user is None or user.workspace_id != workspace.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        try:
            updated = update_workspace_user(
                session,
                user,
                full_name=payload.full_name,
                email=payload.email,
                role=payload.role,
                is_active=payload.is_active,
                password=payload.password,
                acting_user=current_user,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        record_activity(
            session,
            workspace_id=workspace.id,
            action="user.updated",
            entity_type="user",
            entity_id=updated.id,
            actor_user=current_user,
            description=f"{current_user.username if current_user else 'system'} updated user {updated.username}.",
            details=payload.model_dump(exclude_unset=True),
        )
        return UserRead.model_validate(updated)

    @app.get("/api/workspace", response_model=WorkspaceRead, dependencies=[Depends(require_api_access)])
    def workspace_endpoint(workspace: Workspace = Depends(require_workspace)) -> WorkspaceRead:
        return WorkspaceRead.model_validate(workspace)

    @app.get("/api/reference/permit-template.csv", dependencies=[Depends(require_api_access)])
    def permit_template_endpoint() -> PlainTextResponse:
        return PlainTextResponse(
            content=permit_template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="permit-intake-template.csv"'},
        )

    @app.get("/api/reference/change-event-template.csv", dependencies=[Depends(require_api_access)])
    def change_event_template_endpoint() -> PlainTextResponse:
        return PlainTextResponse(
            content=change_event_template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="change-event-template.csv"'},
        )

    @app.get("/api/projects", response_model=list[ProjectSummary], dependencies=[Depends(require_api_access)])
    def list_projects_endpoint(workspace: Workspace = Depends(require_workspace), session: Session = Depends(get_session)) -> list[ProjectSummary]:
        return [_project_summary(project) for project in list_projects(session, workspace.id)]

    @app.post(
        "/api/projects",
        response_model=ProjectRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def create_project_endpoint(
        payload: ProjectCreate,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ProjectRead:
        try:
            project = create_project(session, workspace, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        project = get_project(session, workspace.id, project.id) or project
        record_activity(
            session,
            workspace_id=workspace.id,
            action="project.created",
            entity_type="project",
            entity_id=project.id,
            actor_user=current_user,
            project_id=project.id,
            description=f"{current_user.username if current_user else 'system'} created project {project.name}.",
            details={"project_code": project.project_code, "client_name": project.client_name},
        )
        return _project_read(project)

    @app.get("/api/projects/{project_id}", response_model=ProjectRead, dependencies=[Depends(require_api_access)])
    def get_project_endpoint(project: Project = Depends(require_project)) -> ProjectRead:
        return _project_read(project)

    @app.patch(
        "/api/projects/{project_id}",
        response_model=ProjectRead,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def update_project_endpoint(
        payload: ProjectUpdate,
        project: Project = Depends(require_project),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ProjectRead:
        try:
            project = update_project(session, project, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        refreshed = get_project(session, project.workspace_id, project.id) or project
        record_activity(
            session,
            workspace_id=project.workspace_id,
            action="project.updated",
            entity_type="project",
            entity_id=project.id,
            actor_user=current_user,
            project_id=project.id,
            description=f"{current_user.username if current_user else 'system'} updated project {project.name}.",
            details=payload.model_dump(exclude_unset=True),
        )
        return _project_read(refreshed)

    @app.delete(
        "/api/projects/{project_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def delete_project_endpoint(
        project: Project = Depends(require_project),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> Response:
        snapshot = {"project_id": project.id, "project_name": project.name}
        delete_project(session, project)
        record_activity(
            session,
            workspace_id=project.workspace_id,
            action="project.deleted",
            entity_type="project",
            entity_id=snapshot["project_id"],
            actor_user=current_user,
            project_id=snapshot["project_id"],
            description=f"{current_user.username if current_user else 'system'} deleted project {snapshot['project_name']}.",
            details=snapshot,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/projects/{project_id}/permits", response_model=list[PermitRead], dependencies=[Depends(require_api_access)])
    def list_permits_endpoint(project: Project = Depends(require_project)) -> list[PermitRead]:
        return [_permit_read(permit) for permit in list_project_permits(project)]

    @app.post(
        "/api/projects/{project_id}/permits",
        response_model=PermitRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def create_permit_endpoint(
        payload: PermitCreate,
        project: Project = Depends(require_project),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> PermitRead:
        permit = create_permit(session, project, payload)
        refreshed = get_project(session, project.workspace_id, project.id) or project
        permit = get_permit(refreshed, permit.id) or permit
        record_activity(
            session,
            workspace_id=project.workspace_id,
            action="permit.created",
            entity_type="permit",
            entity_id=permit.id,
            actor_user=current_user,
            project_id=project.id,
            description=f"{current_user.username if current_user else 'system'} added permit {permit.name}.",
            details={"status": permit.status, "jurisdiction": permit.jurisdiction},
        )
        return _permit_read(permit)

    @app.post(
        "/api/permits/import",
        response_model=PermitImportResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def import_permits_endpoint(
        payload: PermitImportRequest,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> PermitImportResponse:
        project = get_project(session, workspace.id, payload.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        result = import_permits_from_csv(session, project, payload.csv_content)
        if result.error_count:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": result.errors})
        session.expire_all()
        refreshed = get_project(session, workspace.id, project.id) or project
        refreshed_permits = list_project_permits(refreshed)
        created_permits = refreshed_permits[-result.created_count :] if result.created_count else []
        record_activity(
            session,
            workspace_id=workspace.id,
            action="permit.imported",
            entity_type="project",
            entity_id=project.id,
            actor_user=current_user,
            project_id=project.id,
            description=f"{current_user.username if current_user else 'system'} imported {len(created_permits)} permits into {project.name}.",
            details={"created_count": len(created_permits)},
        )
        return PermitImportResponse(
            created_count=len(created_permits),
            skipped_blank_rows=result.skipped_blank_rows,
            error_count=0,
            errors=[],
            permits=[_permit_read(permit) for permit in created_permits],
        )

    @app.patch(
        "/api/permits/{permit_id}",
        response_model=PermitRead,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def update_permit_endpoint(
        permit_id: str,
        payload: PermitUpdate,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> PermitRead:
        permit = session.get(Permit, permit_id)
        if permit is None or permit.workspace_id != workspace.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permit not found")
        permit = update_permit(session, permit, payload)
        project = get_project(session, workspace.id, permit.project_id)
        refreshed = get_permit(project, permit.id) if project else permit
        record_activity(
            session,
            workspace_id=workspace.id,
            action="permit.updated",
            entity_type="permit",
            entity_id=permit.id,
            actor_user=current_user,
            project_id=permit.project_id,
            description=f"{current_user.username if current_user else 'system'} updated permit {permit.name}.",
            details=payload.model_dump(exclude_unset=True),
        )
        return _permit_read(refreshed or permit)

    @app.post(
        "/api/permits/{permit_id}/documents",
        response_model=DocumentRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    async def upload_permit_document_endpoint(
        permit_id: str,
        file: UploadFile = File(...),
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        storage: StorageClient = Depends(get_storage_client),
        current_user: User | None = Depends(require_write_access),
    ) -> DocumentRead:
        permit = session.get(Permit, permit_id)
        if permit is None or permit.workspace_id != workspace.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permit not found")
        content = await file.read()
        stored = storage.store_bytes(
            workspace_slug=workspace.slug,
            filename=file.filename or "document.bin",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
        extraction = extract_document_artifacts(file.filename or "document.bin", file.content_type or "application/octet-stream", content)
        document = create_document(
            session,
            workspace_id=workspace.id,
            project_id=permit.project_id,
            permit_id=permit.id,
            change_event_id=permit.linked_change_event.id if permit.linked_change_event else None,
            change_order_id=None,
            filename=file.filename or "document.bin",
            content_type=file.content_type or "application/octet-stream",
            storage_key=stored.storage_key,
            size_bytes=stored.size_bytes,
            extracted_text=extraction.extracted_text,
            extraction_confidence=extraction.extraction_confidence,
            extracted_fields=extraction.extracted_fields,
        )
        if permit.linked_change_event:
            schedule_days = extraction.extracted_fields.get("schedule_impact_days")
            amount_candidates = extraction.extracted_fields.get("amount_candidates_usd")
            if isinstance(schedule_days, int):
                permit.linked_change_event.schedule_impact_days = max(permit.linked_change_event.schedule_impact_days, schedule_days)
            if isinstance(amount_candidates, list) and amount_candidates:
                first_amount = amount_candidates[0]
                if isinstance(first_amount, (float, int)):
                    permit.linked_change_event.cost_impact_usd = max(permit.linked_change_event.cost_impact_usd, float(first_amount))
            session.add(permit.linked_change_event)
            session.commit()
        record_activity(
            session,
            workspace_id=workspace.id,
            action="document.uploaded",
            entity_type="document",
            entity_id=document.id,
            actor_user=current_user,
            project_id=permit.project_id,
            description=f"{current_user.username if current_user else 'system'} uploaded {document.filename} for permit {permit.name}.",
            details={"extraction_confidence": document.extraction_confidence},
        )
        return _document_read(document)

    @app.get("/api/documents/{document_id}/download", dependencies=[Depends(require_api_access)])
    def download_document_endpoint(
        document_id: str,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        storage: StorageClient = Depends(get_storage_client),
    ) -> Response:
        document = get_document(session, workspace.id, document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        local_path = resolved_settings.uploads_dir / document.storage_key if resolved_settings.storage_backend == "local" else None
        if local_path and local_path.exists():
            return FileResponse(local_path, media_type=document.content_type, filename=document.filename)
        payload = storage.read_bytes(document.storage_key)
        return Response(
            content=payload,
            media_type=document.content_type,
            headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
        )

    @app.get("/api/projects/{project_id}/change-events", response_model=list[ChangeEventRead], dependencies=[Depends(require_api_access)])
    def list_change_events_endpoint(project: Project = Depends(require_project)) -> list[ChangeEventRead]:
        return [_change_event_read(event) for event in list_project_change_events(project)]

    @app.post(
        "/api/projects/{project_id}/change-events",
        response_model=ChangeEventRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def create_change_event_endpoint(
        payload: ChangeEventCreate,
        project: Project = Depends(require_project),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ChangeEventRead:
        event = create_change_event(session, project, payload)
        refreshed_project = get_project(session, project.workspace_id, project.id) or project
        refreshed_event = get_change_event(refreshed_project, event.id) or event
        record_activity(
            session,
            workspace_id=project.workspace_id,
            action="change_event.created",
            entity_type="change_event",
            entity_id=event.id,
            actor_user=current_user,
            project_id=project.id,
            description=f"{current_user.username if current_user else 'system'} created change event {event.title}.",
            details={"status": event.status, "source_type": event.source_type},
        )
        return _change_event_read(refreshed_event)

    @app.patch(
        "/api/change-events/{change_event_id}",
        response_model=ChangeEventRead,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def update_change_event_endpoint(
        change_event_id: str,
        payload: ChangeEventUpdate,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ChangeEventRead:
        statement = select(ChangeEvent).where(ChangeEvent.id == change_event_id, ChangeEvent.workspace_id == workspace.id)
        change_event = session.scalars(statement).first()
        if change_event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change event not found")
        updated = update_change_event(session, change_event, payload)
        refreshed_project = get_project(session, workspace.id, updated.project_id)
        refreshed_event = get_change_event(refreshed_project, updated.id) if refreshed_project else updated
        record_activity(
            session,
            workspace_id=workspace.id,
            action="change_event.updated",
            entity_type="change_event",
            entity_id=updated.id,
            actor_user=current_user,
            project_id=updated.project_id,
            description=f"{current_user.username if current_user else 'system'} updated change event {updated.title}.",
            details=payload.model_dump(exclude_unset=True),
        )
        return _change_event_read(refreshed_event or updated)

    @app.post(
        "/api/change-events/{change_event_id}/rfqs",
        response_model=RFQRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def create_rfq_endpoint(
        change_event_id: str,
        payload: RFQCreate,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> RFQRead:
        statement = select(ChangeEvent).where(ChangeEvent.id == change_event_id, ChangeEvent.workspace_id == workspace.id)
        change_event = session.scalars(statement).first()
        if change_event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change event not found")
        rfq = create_rfq(session, change_event, payload)
        record_activity(
            session,
            workspace_id=workspace.id,
            action="rfq.created",
            entity_type="rfq",
            entity_id=rfq.id,
            actor_user=current_user,
            project_id=change_event.project_id,
            description=f"{current_user.username if current_user else 'system'} created RFQ for {change_event.title}.",
            details={"subcontractor_name": rfq.subcontractor_name, "status": rfq.status},
        )
        return RFQRead.model_validate(rfq)

    @app.post(
        "/api/change-events/{change_event_id}/quotes",
        response_model=QuoteRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def create_quote_endpoint(
        change_event_id: str,
        payload: QuoteCreate,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> QuoteRead:
        statement = select(ChangeEvent).where(ChangeEvent.id == change_event_id, ChangeEvent.workspace_id == workspace.id)
        change_event = session.scalars(statement).first()
        if change_event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change event not found")
        quote = create_quote(session, change_event, payload)
        record_activity(
            session,
            workspace_id=workspace.id,
            action="quote.created",
            entity_type="quote",
            entity_id=quote.id,
            actor_user=current_user,
            project_id=change_event.project_id,
            description=f"{current_user.username if current_user else 'system'} recorded quote for {change_event.title}.",
            details={"amount_usd": quote.amount_usd, "is_selected": quote.is_selected},
        )
        return QuoteRead.model_validate(quote)

    @app.post(
        "/api/change-events/{change_event_id}/change-orders",
        response_model=ChangeOrderRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def create_change_order_endpoint(
        change_event_id: str,
        payload: ChangeOrderCreate,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ChangeOrderRead:
        statement = select(ChangeEvent).where(ChangeEvent.id == change_event_id, ChangeEvent.workspace_id == workspace.id)
        change_event = session.scalars(statement).first()
        if change_event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change event not found")
        try:
            change_order = create_change_order(session, change_event, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        refreshed_project = get_project(session, workspace.id, change_event.project_id)
        refreshed_event = get_change_event(refreshed_project, change_event.id) if refreshed_project else change_event
        refreshed_change_order = get_change_order(refreshed_event, change_order.id) if refreshed_event else change_order
        record_activity(
            session,
            workspace_id=workspace.id,
            action="change_order.created",
            entity_type="change_order",
            entity_id=change_order.id,
            actor_user=current_user,
            project_id=change_event.project_id,
            description=f"{current_user.username if current_user else 'system'} created change order {change_order.number}.",
            details={"amount_usd": change_order.amount_usd, "kind": change_order.kind},
        )
        return _change_order_read(refreshed_change_order or change_order)

    @app.post(
        "/api/change-orders/{change_order_id}/submit-approval",
        response_model=ChangeOrderRead,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def submit_approval_endpoint(
        change_order_id: str,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ChangeOrderRead:
        statement = select(ChangeOrder).where(ChangeOrder.id == change_order_id, ChangeOrder.workspace_id == workspace.id)
        change_order = session.scalars(statement).first()
        if change_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change order not found")
        try:
            updated = submit_change_order_for_approval(session, change_order, resolved_settings)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        record_activity(
            session,
            workspace_id=workspace.id,
            action="change_order.submitted",
            entity_type="change_order",
            entity_id=updated.id,
            actor_user=current_user,
            project_id=updated.change_event.project_id,
            description=f"{current_user.username if current_user else 'system'} submitted change order {updated.number} for approval.",
            details={"status": updated.status, "approval_count": len(updated.approvals)},
        )
        return _change_order_read(updated)

    @app.post(
        "/api/change-orders/{change_order_id}/approval-steps/{step_id}/decision",
        response_model=ApprovalStepRead,
        dependencies=[Depends(require_write_access), Depends(require_csrf_protection)],
    )
    def approval_decision_endpoint(
        change_order_id: str,
        step_id: str,
        payload: ApprovalDecisionRequest,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
        current_user: User | None = Depends(require_write_access),
    ) -> ApprovalStepRead:
        statement = (
            select(ChangeOrder)
            .where(ChangeOrder.id == change_order_id, ChangeOrder.workspace_id == workspace.id)
            .options(selectinload(ChangeOrder.approvals), selectinload(ChangeOrder.change_event))
        )
        change_order = session.scalars(statement).first()
        if change_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change order not found")
        matching_step = next((step for step in change_order.approvals if step.id == step_id), None)
        if matching_step is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval step not found")
        if current_user and current_user.role not in {"workspace_admin", "platform_admin"} and current_user.role != matching_step.role_required:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to act on this approval step")
        try:
            step = decide_approval_step(session, change_order, step_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        record_activity(
            session,
            workspace_id=workspace.id,
            action="approval.acted",
            entity_type="approval_step",
            entity_id=step.id,
            actor_user=current_user,
            project_id=change_order.change_event.project_id,
            description=f"{current_user.username if current_user else 'system'} marked approval step {step.step_order} as {step.status}.",
            details={"change_order_id": change_order.id, "status": step.status},
        )
        return ApprovalStepRead.model_validate(step)

    @app.get("/api/change-orders/{change_order_id}/package.md", response_model=OwnerPackageRead, dependencies=[Depends(require_api_access)])
    def change_order_package_endpoint(
        change_order_id: str,
        workspace: Workspace = Depends(require_workspace),
        session: Session = Depends(get_session),
    ) -> OwnerPackageRead:
        statement = (
            select(ChangeOrder)
            .where(ChangeOrder.id == change_order_id, ChangeOrder.workspace_id == workspace.id)
            .options(selectinload(ChangeOrder.approvals), selectinload(ChangeOrder.change_event).selectinload(ChangeEvent.project))
        )
        change_order = session.scalars(statement).first()
        if change_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change order not found")
        return OwnerPackageRead(change_order_id=change_order.id, markdown=owner_package_markdown(change_order))

    @app.get("/api/projects/{project_id}/export", dependencies=[Depends(require_api_access)])
    def project_export_endpoint(project: Project = Depends(require_project)) -> dict[str, object]:
        return build_project_export(project)

    return app


app = create_app()
