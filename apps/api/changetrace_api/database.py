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
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE change_requests ADD COLUMN {name} {sql_type}"))


def get_session():
    with SessionLocal() as session:
        yield session
