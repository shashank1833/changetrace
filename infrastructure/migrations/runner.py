from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure repo root is on sys.path if invoked directly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from apps.api.changetrace_api.database import engine as default_engine  # noqa: E402

logger = logging.getLogger("changetrace.migrations")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

VERSIONS_DIR = Path(__file__).parent / "versions"


def clean_sql_statement(statement: str) -> str:
    """Strip leading SQL line comments (--) and block comments (/* */)."""
    cleaned = statement.strip()
    while True:
        if cleaned.startswith("--"):
            idx = cleaned.find("\n")
            if idx == -1:
                return ""
            cleaned = cleaned[idx + 1 :].strip()
        elif cleaned.startswith("/*"):
            idx = cleaned.find("*/")
            if idx == -1:
                return ""
            cleaned = cleaned[idx + 2 :].strip()
        else:
            break
    return cleaned


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL script into discrete statements, honoring single quotes, dollar quotes, and comments."""
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_dollar_quote: str | None = None
    in_line_comment = False
    in_block_comment = False
    i = 0
    n = len(sql)

    while i < n:
        if in_line_comment:
            current.append(sql[i])
            if sql[i] == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            current.append(sql[i])
            if sql[i : i + 2] == "*/":
                current.append("/")
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if not in_single_quote and in_dollar_quote is None:
            if sql[i : i + 2] == "--":
                current.append("-")
                current.append("-")
                in_line_comment = True
                i += 2
                continue
            if sql[i : i + 2] == "/*":
                current.append("/")
                current.append("*")
                in_block_comment = True
                i += 2
                continue

        if in_dollar_quote is None:
            if sql[i] == "'":
                current.append("'")
                if in_single_quote:
                    if i + 1 < n and sql[i + 1] == "'":
                        current.append("'")
                        i += 2
                        continue
                    in_single_quote = False
                else:
                    in_single_quote = True
                i += 1
                continue

        if not in_single_quote:
            if in_dollar_quote is not None:
                if sql[i : i + len(in_dollar_quote)] == in_dollar_quote:
                    current.extend(list(in_dollar_quote))
                    i += len(in_dollar_quote)
                    in_dollar_quote = None
                    continue
            else:
                if sql[i] == "$":
                    match = re.match(r"\$[a-zA-Z0-9_]*\$", sql[i:])
                    if match:
                        tag = match.group(0)
                        in_dollar_quote = tag
                        current.extend(list(tag))
                        i += len(tag)
                        continue

        if sql[i] == ";" and not in_single_quote and in_dollar_quote is None:
            stmt = clean_sql_statement("".join(current))
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(sql[i])
        i += 1

    last = clean_sql_statement("".join(current))
    if last:
        statements.append(last)

    return statements


class MigrationRunner:
    """Production migration runner tracking applied migrations with checksums, locking, and transactions."""

    def __init__(self, db_engine: Engine | None = None, versions_dir: Path | None = None) -> None:
        self.engine = db_engine or default_engine
        self.versions_dir = versions_dir or VERSIONS_DIR

    def acquire_lock(self, timeout_seconds: int = 15) -> bool:
        """Acquire migration lock to prevent concurrent container startup collisions."""
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                with self.engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE IF NOT EXISTS schema_migration_locks (
                                lock_id INT PRIMARY KEY,
                                locked_by VARCHAR(100) NOT NULL,
                                locked_at TIMESTAMP WITH TIME ZONE NOT NULL
                            );
                            """
                        )
                    )
                    now = datetime.now(UTC)
                    conn.execute(
                        text(
                            "INSERT INTO schema_migration_locks (lock_id, locked_by, locked_at) "
                            "VALUES (1, 'migration_runner', :now)"
                        ),
                        {"now": now},
                    )
                    return True
            except Exception:
                # Check for stale lock older than 60s
                try:
                    with self.engine.begin() as conn:
                        cutoff = datetime.now(UTC) - timedelta(seconds=60)
                        conn.execute(
                            text("DELETE FROM schema_migration_locks WHERE lock_id = 1 AND locked_at < :cutoff"),
                            {"cutoff": cutoff},
                        )
                except Exception:
                    pass
                time.sleep(1)
        return False

    def release_lock(self) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM schema_migration_locks WHERE lock_id = 1"))
        except Exception:
            pass

    def init_migrations_table(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(100) PRIMARY KEY,
                        checksum VARCHAR(64) NOT NULL,
                        applied_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );
                    """
                )
            )

    def get_applied_migrations(self) -> dict[str, str]:
        self.init_migrations_table()
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT version, checksum FROM schema_migrations ORDER BY version")).fetchall()
            return {row[0]: row[1] for row in rows}

    def list_migration_files(self) -> list[Path]:
        if not self.versions_dir.exists():
            return []
        return sorted(self.versions_dir.glob("*.sql"))

    def run_migrations(self) -> list[str]:
        """Apply all pending migrations in order within transactions with lock protection."""
        if not self.acquire_lock():
            logger.warning("Could not acquire migration lock; another process may be running migrations")
            return []

        try:
            return self._execute_migrations()
        finally:
            self.release_lock()

    def _execute_migrations(self) -> list[str]:
        self.init_migrations_table()
        applied = self.get_applied_migrations()
        files = self.list_migration_files()
        newly_applied: list[str] = []

        is_sqlite = self.engine.dialect.name == "sqlite"

        for file in files:
            version = file.stem
            content = file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

            if version in applied:
                if applied[version] != checksum:
                    logger.warning(
                        "Migration %s checksum mismatch! Recorded: %s, Current: %s",
                        version,
                        applied[version],
                        checksum,
                    )
                continue

            logger.info("Applying migration: %s", version)
            with self.engine.begin() as conn:
                statements = split_sql_statements(content)
                for statement in statements:
                    if is_sqlite:
                        lower_s = statement.lower().strip()
                        if (
                            lower_s.startswith("create extension")
                            or "row level security" in lower_s
                            or lower_s.startswith("create policy")
                            or lower_s.startswith("do $$")
                            or lower_s.startswith("do $")
                        ):
                            continue
                        statement = (
                            statement.replace("timestamptz", "datetime")
                            .replace("now()", "CURRENT_TIMESTAMP")
                            .replace("jsonb", "text")
                            .replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")
                        )
                    try:
                        conn.execute(text(statement))
                    except Exception as exc:
                        if is_sqlite and "duplicate column name" in str(exc).lower():
                            continue
                        raise

                now = datetime.now(UTC)
                insert_sql = (
                    "INSERT INTO schema_migrations (version, checksum, applied_at) "
                    "VALUES (:version, :checksum, :applied_at)"
                )
                conn.execute(
                    text(insert_sql),
                    {"version": version, "checksum": checksum, "applied_at": now},
                )
                newly_applied.append(version)
                logger.info("Successfully applied %s", version)

        return newly_applied

    def status(self) -> list[dict[str, str]]:
        self.init_migrations_table()
        applied = self.get_applied_migrations()
        files = self.list_migration_files()
        result = []
        for file in files:
            version = file.stem
            is_applied = version in applied
            result.append(
                {
                    "version": version,
                    "status": "APPLIED" if is_applied else "PENDING",
                    "checksum": applied.get(version, "N/A"),
                }
            )
        return result

    def verify_checksums(self) -> bool:
        applied = self.get_applied_migrations()
        files = self.list_migration_files()
        valid = True
        for file in files:
            version = file.stem
            if version in applied:
                current_checksum = hashlib.sha256(file.read_bytes()).hexdigest()
                if applied[version] != current_checksum:
                    logger.error("Tampered migration detected: %s", version)
                    valid = False
        return valid


def main():
    parser = argparse.ArgumentParser(description="ChangeTrace Database Migration Runner")
    parser.add_argument("command", choices=["run", "status", "verify"], default="run", nargs="?")
    args = parser.parse_args()

    runner = MigrationRunner()
    if args.command == "run":
        applied = runner.run_migrations()
        print(f"Applied {len(applied)} migration(s).")
    elif args.command == "status":
        statuses = runner.status()
        for s in statuses:
            print(f"[{s['status']}] {s['version']}")
    elif args.command == "verify":
        ok = runner.verify_checksums()
        if not ok:
            sys.exit(1)
        print("All migration checksums valid.")


if __name__ == "__main__":
    main()
