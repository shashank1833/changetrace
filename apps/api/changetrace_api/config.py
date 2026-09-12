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


@lru_cache
def get_settings() -> Settings:
    return Settings()
