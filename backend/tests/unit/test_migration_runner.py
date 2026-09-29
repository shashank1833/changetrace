from pathlib import Path

from sqlalchemy import create_engine

from infrastructure.migrations.runner import MigrationRunner


def test_migration_runner_on_isolated_db(tmp_path: Path):
    db_file = tmp_path / "test_migration.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")

    runner = MigrationRunner(db_engine=engine)
    status_before = runner.status()
    assert all(s["status"] == "PENDING" for s in status_before)

    applied = runner.run_migrations()
    assert len(applied) >= 5

    status_after = runner.status()
    assert all(s["status"] == "APPLIED" for s in status_after)

    assert runner.verify_checksums() is True


def test_migration_runner_locking(tmp_path: Path):
    db_file = tmp_path / "test_migration_lock.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")

    runner1 = MigrationRunner(db_engine=engine)
    runner2 = MigrationRunner(db_engine=engine)

    # Acquire lock on runner1
    assert runner1.acquire_lock() is True
    # runner2 should fail to acquire lock while locked
    assert runner2.acquire_lock(timeout_seconds=1) is False

    # runner1 releases lock
    runner1.release_lock()
    # runner2 can now acquire lock
    assert runner2.acquire_lock() is True
    runner2.release_lock()


def test_split_sql_statements_handles_dollar_quotes_and_comments():
    from infrastructure.migrations.runner import split_sql_statements

    sql = """
    -- Initial comment with semicolon;
    CREATE TABLE test_table (id INT, note TEXT);

    /* Block comment with ; inside */
    INSERT INTO test_table (id, note) VALUES (1, 'value;with;semicolon');

    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'foo') THEN
        CREATE POLICY foo ON test_table USING (true);
      END IF;
    END $$;

    SELECT * FROM test_table;
    """
    stmts = split_sql_statements(sql)
    assert len(stmts) == 4
    assert stmts[0].startswith("CREATE TABLE")
    assert stmts[1].startswith("INSERT INTO")
    assert "'value;with;semicolon'" in stmts[1]
    assert stmts[2].startswith("DO $$")
    assert "END $$" in stmts[2]
    assert stmts[3] == "SELECT * FROM test_table"


def test_database_schema_parity_with_sqlalchemy_models():
    from sqlalchemy import inspect

    from apps.api.changetrace_api.models import Base

    engine_mig = create_engine("sqlite:///:memory:")
    runner = MigrationRunner(db_engine=engine_mig)
    runner.run_migrations()

    engine_sa = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine_sa)

    insp_mig = inspect(engine_mig)
    insp_sa = inspect(engine_sa)

    sa_tables = set(insp_sa.get_table_names())
    for t in sorted(sa_tables):
        mig_cols = {c["name"] for c in insp_mig.get_columns(t)}
        sa_cols = {c["name"] for c in insp_sa.get_columns(t)}
        assert mig_cols == sa_cols, f"Table {t} columns differ: mig={mig_cols}, sa={sa_cols}"


