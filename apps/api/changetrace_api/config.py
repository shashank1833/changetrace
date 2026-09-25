from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
