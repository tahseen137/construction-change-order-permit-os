# Architecture

## Product shape

The application is a FastAPI monolith with server-rendered HTML for the primary workspace and JSON APIs for all operational actions. This keeps the deployment simple while still allowing rich client-side interactions for project, permit, and change-order workflows.

## Core layers

### Web layer

- `app/main.py`
- HTML templates in `app/templates`
- client-side dashboard logic in `app/static/app.js`

Responsibilities:

- session handling
- role checks
- CSRF enforcement
- page rendering
- API request routing
- response headers and basic app middleware

### Domain and service layer

- `app/services.py`
- `app/user_service.py`
- `app/activity_service.py`
- `app/scoring.py`
- `app/reporting.py`

Responsibilities:

- project lifecycle
- permit intake and change-event sync
- RFQ, quote, and change-order workflows
- approval routing and decisions
- activity logging
- exportable package generation
- operational risk rollups

### Data layer

- `app/models.py`
- `app/db.py`
- Alembic migrations under `alembic/versions`

Responsibilities:

- SQLAlchemy models
- session management
- schema lifecycle
- readiness checks

### Document and integration layer

- `app/storage.py`
- `app/ai.py`
- `app/notifications.py`
- `app/tasks.py`
- `app/celery_app.py`

Responsibilities:

- local or S3-compatible document storage
- lightweight field extraction from uploaded text documents
- email notification queueing and send behavior
- worker-friendly task entrypoints

## Data model

### Tenant and identity

- `Workspace`
- `User`
- `ActivityEvent`

### Project execution

- `Project`
- `Permit`
- `PermitDependency`
- `Inspection`
- `ChangeEvent`
- `RFQ`
- `Quote`
- `ChangeOrder`
- `ApprovalStep`
- `Document`
- `NotificationJob`

## Multi-tenant strategy

- Every operational model is scoped by `workspace_id`.
- API endpoints resolve the current user’s workspace and deny cross-tenant access.
- Admin actions are limited to workspace admins or platform admins.
- Tests cover cross-tenant access denial.

## Workflow design

### Permit-led workflow

1. User creates or imports a permit.
2. If the permit has a blocker, revision request, or failed inspection, the service layer creates or updates a linked `ChangeEvent`.
3. Users can upload supporting documents and the extraction layer pulls lightweight structured hints like schedule days, amounts, and risk tags.

### Change-order workflow

1. Users create RFQs and collect quotes on a selected change event.
2. Users create a change order from that event.
3. Submission routes approval steps based on configured thresholds.
4. Approvers act on each step and the order status updates accordingly.
5. Users can export an owner-facing markdown package.

## Deployment architecture

- Dockerized FastAPI web service
- managed Postgres on Render
- optional S3-compatible object storage
- optional Postmark for delivery
- Alembic migrations at startup through `start.sh`

## Operational notes

- The app is usable with local storage for pilot environments, but production document retention is stronger with S3-compatible storage.
- Notification sending currently works synchronously inside the approval submission path, with a Celery task entrypoint available for worker-driven evolution.
- The architecture is intentionally narrow and operationally simple so the product can be launched and supported without a broad platform team.
