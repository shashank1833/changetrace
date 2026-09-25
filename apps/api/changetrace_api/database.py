import uuid
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from .config import get_settings
from .models import Base

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_schema() -> None:
    Base.metadata.create_all(engine)
    if settings.database_url.startswith("sqlite"):
        _migrate_local_sqlite()


def _migrate_local_sqlite() -> None:
    """Keep contributor databases usable; production uses versioned SQL migrations."""
    columns = {column["name"] for column in inspect(engine).get_columns("change_requests")}
    additions = {
        "proposed_diff": "TEXT",
        "base_ref": "VARCHAR(200)",
        "target_ref": "VARCHAR(200)",
        "github_metadata": "JSON",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE change_requests ADD COLUMN {name} {sql_type}"))


# Automatically initialize schema for local SQLite
if settings.database_url.startswith("sqlite"):
    create_schema()


def get_session():
    with SessionLocal() as session:
        yield session


def set_tenant_context(session: Any, organization_id: str | uuid.UUID | None) -> None:
    """Set the PostgreSQL session variable app.current_organization_id for Row-Level Security."""
    if not organization_id:
        return
    org_str = str(organization_id)
    try:
        bind = session.get_bind()
        if bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_organization_id', :org_id, true)"),
                {"org_id": org_str},
            )
    except Exception:
        pass

