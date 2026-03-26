# Launch Readiness

## Production posture

- Secure, account-based access with signed session cookies, CSRF protection, login lockouts, and role-based permissions.
- Persistent project, permit, change-event, RFQ, quote, change-order, approval, and activity data in SQLite or Postgres.
- Document upload with local or S3-compatible storage and lightweight field extraction.
- Approval routing based on configurable financial thresholds.
- Repeatable schema rollout via Alembic migrations and container startup migration support.
- CI coverage gate at `90%` and local test suite covering auth, workflows, exports, isolation, migrations, and core utilities.

## Environment checklist

- Set `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_ADMIN_EMAIL`, and `SESSION_SECRET`.
- Use managed Postgres through `DATABASE_URL` in any shared environment.
- Set `AUTO_CREATE_SCHEMA=false` and `RUN_DB_MIGRATIONS=true` in production.
- Keep `TRUSTED_HOSTS` aligned to the deployment hostname and `ENFORCE_HTTPS=true` on public deployments.
- If document durability matters across deploys, use `STORAGE_BACKEND=s3` and configure the S3 settings.
- If approval emails should deliver for real, set `POSTMARK_SERVER_TOKEN` and `POSTMARK_FROM_EMAIL`.
- Add `SENTRY_DSN` and `POSTHOG_API_KEY` when you are ready for error monitoring and product analytics.

## Pre-launch verification

- Run `pytest --cov=app --cov-report=term-missing --cov-fail-under=90`.
- Run `alembic upgrade head` against a clean database.
- Confirm `/health` returns `200`.
- Confirm `/ready` returns `200` after migrations complete.
- Confirm bootstrap admin login works.
- Confirm project creation, permit intake, permit CSV import, document upload, change event creation, quote selection, change-order submission, approval action, project export, and owner-package download all work in the live app.
- Confirm cross-tenant access is denied for protected resources.

## Operating model

- Start each new deployment with one bootstrap workspace admin, then create named users from the in-app admin panel.
- Review permit imports before teams rely on downstream cost and schedule exposure.
- Treat the AI/document extraction layer as assistive only; users should confirm external-facing change-order packages before client submission.
- Rotate bootstrap credentials after first login and use user-level password resets for staff changes.
- If you keep `STORAGE_BACKEND=local`, treat Render disk storage as ephemeral and move to S3 before relying on long-lived document retention.
