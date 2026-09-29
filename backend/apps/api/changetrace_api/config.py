from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHANGETRACE_", env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./changetrace.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_mode: str = "inline"
    allowed_origins: str = "http://localhost:5173"
    local_repository_root: str = "."
    snapshot_storage_root: str = ".changetrace/snapshots"
    rate_limit_per_minute: int = 60
    auth_mode: str = "development"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost:8000/api/v1/auth/github/callback"
    web_url: str = "http://localhost:5173"
    session_secret: str = "change-me-in-production"
    session_ttl_seconds: int = 86400
    session_cookie_secure: bool = False
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = ""
    otel_exporter: str = "none"
    otel_endpoint: str = "http://localhost:4317"


    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        if self.environment == "production":
            if self.session_secret == "change-me-in-production":
                raise ValueError("CHANGETRACE_SESSION_SECRET must be configured with a secure random key in production")
            if self.auth_mode == "development":
                raise ValueError("CHANGETRACE_AUTH_MODE cannot be 'development' in production")
            if not self.session_cookie_secure:
                raise ValueError("CHANGETRACE_SESSION_COOKIE_SECURE must be True in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
