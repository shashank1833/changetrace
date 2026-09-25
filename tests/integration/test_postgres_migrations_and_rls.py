import os
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from apps.api.changetrace_api.database import set_tenant_context
from infrastructure.migrations.runner import MigrationRunner, split_sql_statements


def test_split_sql_statements_handles_postgresql_rls_and_dollar_quotes():
    """Verify that PostgreSQL RLS migration with DO $$ block is parsed cleanly into executable statements."""
    from pathlib import Path

    rls_path = Path("infrastructure/migrations/versions/004_row_level_security.sql")
    content = rls_path.read_text(encoding="utf-8")
    stmts = split_sql_statements(content)

    # 6 ALTER TABLE statements + 1 DO $$ block
    assert len(stmts) == 7
    alter_stmts = [s for s in stmts if s.startswith("ALTER TABLE")]
    target_tables = (
        "repositories",
        "change_requests",
        "analysis_jobs",
        "analysis_runs",
        "finding_feedback",
        "audit_logs",
    )
    for table in target_tables:
        assert any(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in s for s in alter_stmts)


    do_stmt = [s for s in stmts if s.startswith("DO $$")][0]
    assert "CREATE POLICY tenant_isolation_repositories ON repositories" in do_stmt
    assert "current_setting('app.current_organization_id', true)" in do_stmt
    assert do_stmt.strip().endswith("END $$")


def test_set_tenant_context_postgresql_dialect():
    """Verify that set_tenant_context dispatches the correct PostgreSQL session configuration query."""
    mock_session = MagicMock(spec=Session)
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.get_bind.return_value = mock_bind

    set_tenant_context(mock_session, "org-uuid-12345")

    assert mock_session.execute.called
    call_args = mock_session.execute.call_args
    sql_text = str(call_args[0][0])
    params = call_args[0][1]

    assert "set_config('app.current_organization_id', :org_id, true)" in sql_text
    assert params == {"org_id": "org-uuid-12345"}


@pytest.mark.integration
def test_real_postgres_migrations_and_rls_live():
    """Live integration test against a running PostgreSQL instance (when available via env)."""
    import socket

    pg_url = os.environ.get("CHANGETRACE_TEST_POSTGRES_URL")
    if not pg_url:
        try:
            s = socket.create_connection(("127.0.0.1", 5432), timeout=0.5)
            s.close()
            pg_url = "postgresql+psycopg://changetrace:local-only-change-me@localhost:5432/changetrace"
        except (TimeoutError, ConnectionRefusedError, OSError):
            pytest.skip("Live PostgreSQL is not accessible on localhost:5432; skipping live DB execution.")

    try:
        engine = create_engine(pg_url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip(f"Live PostgreSQL not reachable at {pg_url}; skipping live DB execution.")


    # Apply all migrations to the live PostgreSQL instance
    runner = MigrationRunner(db_engine=engine)
    applied = runner.run_migrations()
    assert applied is not None
    assert runner.verify_checksums() is True


    with engine.connect() as conn:
        # 1. Verify RLS is enabled on all target tables
        rls_tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND rowsecurity = true"
            )
        ).fetchall()
        enabled_table_names = {row[0] for row in rls_tables}
        expected_rls_tables = {
            "repositories",
            "change_requests",
            "analysis_jobs",
            "analysis_runs",
            "finding_feedback",
            "audit_logs",
        }
        assert expected_rls_tables.issubset(enabled_table_names)

        # 2. Verify all 6 tenant isolation policies exist
        policies = conn.execute(
            text("SELECT policyname, tablename FROM pg_policies WHERE schemaname = 'public'")
        ).fetchall()
        policy_names = {row[0] for row in policies}
        assert "tenant_isolation_repositories" in policy_names
        assert "tenant_isolation_changes" in policy_names
        assert "tenant_isolation_jobs" in policy_names
        assert "tenant_isolation_runs" in policy_names
        assert "tenant_isolation_feedback" in policy_names
        assert "tenant_isolation_audit" in policy_names

        # 3. Test multi-tenant isolation under RLS
        # Seed an organization and repository for tenant A
        conn.execute(
            text(
                "INSERT INTO organizations (id, name) VALUES ('org-a', 'Tenant A') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO repositories (id, organization_id, name, default_branch) "
                "VALUES ('repo-a', 'org-a', 'Tenant A Repo', 'main') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        conn.commit()

        # In PostgreSQL, superusers bypass RLS. Switch to a non-superuser role to test RLS policies.
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'changetrace_test_user') THEN "
                "  CREATE ROLE changetrace_test_user NOSUPERUSER NOBYPASSRLS; "
                "END IF; "
                "END $$;"
            )
        )
        conn.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO changetrace_test_user"))
        conn.execute(text("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO changetrace_test_user"))
        conn.execute(text("SET ROLE changetrace_test_user"))

        try:
            # Query with Tenant A context
            conn.execute(text("SELECT set_config('app.current_organization_id', 'org-a', true)"))
            rows_a = conn.execute(text("SELECT id FROM repositories WHERE id = 'repo-a'")).fetchall()
            assert len(rows_a) == 1

            # Query with Tenant B context -> MUST return 0 rows (isolated by RLS)
            conn.execute(text("SELECT set_config('app.current_organization_id', 'org-b', true)"))
            rows_b = conn.execute(text("SELECT id FROM repositories WHERE id = 'repo-a'")).fetchall()
            assert len(rows_b) == 0
        finally:
            conn.execute(text("RESET ROLE"))

