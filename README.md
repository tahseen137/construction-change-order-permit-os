# Construction Change-Order & Permit OS

Construction Change-Order & Permit OS is a production-ready workflow product for US commercial general contractors. It connects permit blockers, scope changes, subcontractor pricing, owner approvals, and exportable change-order packages in one secure workspace.

## What it does

- Stores multi-tenant workspaces, named users, projects, permits, change events, RFQs, quotes, change orders, approvals, documents, and notifications.
- Automatically creates linked change events when a permit hits a blocker, revision request, or failed inspection.
- Supports manual permit intake, bulk CSV permit import, document upload, lightweight extraction, and owner-package exports.
- Routes approvals by configurable thresholds across project managers, finance approvers, and workspace admins.
- Includes account-based auth, role-based permissions, CSRF protection, login lockouts, audit activity, Docker packaging, Alembic migrations, and Render deployment config.

## Product scope

This v1 is designed for mid-market commercial GC teams that still run critical permit and change-order work in spreadsheets, email, and ad hoc folders. It is not a full ERP, accounting suite, or municipality filing system.

## Stack

- FastAPI
- SQLAlchemy
- Alembic
- Pydantic and pydantic-settings
- Jinja2 plus vanilla JavaScript and CSS
- Local or S3-compatible object storage
- Optional Postmark email delivery
- pytest with coverage
- Docker and Render deployment config

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Test

```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

## Core API

- `GET /health`
- `GET /ready`
- `GET /api/session`
- `POST /api/session/login`
- `POST /api/session/logout`
- `GET /api/dashboard`
- `GET /api/activity`
- `GET /api/admin/users`
- `POST /api/admin/users`
- `PATCH /api/admin/users/{user_id}`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `GET /api/projects/{project_id}/permits`
- `POST /api/projects/{project_id}/permits`
- `POST /api/permits/import`
- `PATCH /api/permits/{permit_id}`
- `POST /api/permits/{permit_id}/documents`
- `GET /api/projects/{project_id}/change-events`
- `POST /api/projects/{project_id}/change-events`
- `PATCH /api/change-events/{change_event_id}`
- `POST /api/change-events/{change_event_id}/rfqs`
- `POST /api/change-events/{change_event_id}/quotes`
- `POST /api/change-events/{change_event_id}/change-orders`
- `POST /api/change-orders/{change_order_id}/submit-approval`
- `POST /api/change-orders/{change_order_id}/approval-steps/{step_id}/decision`

## Production notes

- Use Postgres through `DATABASE_URL` in shared environments.
- Keep `AUTO_CREATE_SCHEMA=false` in production and let Alembic own schema rollout.
- Set `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, and `SESSION_SECRET` before giving users access.
- Use `STORAGE_BACKEND=s3` plus the S3 settings when you want durable document storage outside the local filesystem.
- `start.sh` runs `alembic upgrade head` before starting Uvicorn.
- See [launch-readiness.md](/Users/ring_/OneDrive/Documents/Playground/construction-change-order-permit-os/docs/launch-readiness.md) for the operating checklist.
