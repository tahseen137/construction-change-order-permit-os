from functools import lru_cache
from pathlib import Path

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Construction Change-Order & Permit OS"
    app_env: str = "development"
    database_url: str | None = None
    database_path: Path = Path("data/construction_ops.db")
    uploads_dir: Path = Path("data/uploads")

    bootstrap_workspace_name: str = "Demo GC Workspace"
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_email: str | None = None
    session_secret: str | None = None
    session_max_age_seconds: int = 60 * 60 * 12
    max_login_attempts: int = 5
    login_lockout_minutes: int = 15

    trusted_hosts: str = "*"
    enable_gzip: bool = True
    enforce_https: bool = False
    auto_create_schema: bool = True

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_task_always_eager: bool = False

    storage_backend: str = "local"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    postmark_server_token: str | None = None
    postmark_from_email: str = "no-reply@example.com"

    sentry_dsn: str | None = None
    posthog_api_key: str | None = None
    posthog_host: str = "https://app.posthog.com"

    approval_threshold_pm_usd: float = 25_000
    approval_threshold_finance_usd: float = 100_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        bootstrap_present = bool(self.bootstrap_admin_username or self.bootstrap_admin_password)
        if bootstrap_present and not (self.bootstrap_admin_username and self.bootstrap_admin_password):
            raise ValueError("bootstrap_admin_username and bootstrap_admin_password must be configured together")
        if bootstrap_present and not self.session_secret:
            raise ValueError("session_secret is required when bootstrap admin auth is configured")
        if self.storage_backend not in {"local", "s3"}:
            raise ValueError("storage_backend must be either 'local' or 's3'")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("s3_bucket is required when storage_backend is 's3'")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("postgresql://"):
                return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            if self.database_url.startswith("postgres://"):
                return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
            return self.database_url
        return f"sqlite:///{self.database_path.resolve()}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bootstrap_admin_configured(self) -> bool:
        return bool(self.bootstrap_admin_username and self.bootstrap_admin_password)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_hosts(self) -> list[str]:
        hosts = [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]
        return hosts or ["*"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def session_https_only(self) -> bool:
        return self.app_env == "production" or self.enforce_https


@lru_cache
def get_settings() -> Settings:
    return Settings()
