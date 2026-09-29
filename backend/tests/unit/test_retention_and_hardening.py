from __future__ import annotations

import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.changetrace_api.models import (
    AnalysisJob,
    AnalysisRun,
    Artifact,
    AuditLog,
    Base,
    ChangeRequest,
    FindingFeedback,
    Organization,
    Repository,
    RepositorySnapshot,
    User,
    WebSession,
)
from services.retention.service import (
    RetentionService,
    redact_credentials,
    sanitize_metadata,
)


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_retention.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session


def test_redact_credentials():
    text = "Here is my token: ghp_123456789012345678901234567890123456 and AWS AKIAIOSFODNN7EXAMPLE."
    redacted = redact_credentials(text)
    assert "ghp_" not in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "[REDACTED]" in redacted

    bearer_text = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "e30.t-IDcSemACt8x4iTMCda8Yhe3iZaWbvV5XKSTbuAn0M"
    )
    redacted_bearer = redact_credentials(bearer_text)
    assert "[REDACTED]" in redacted_bearer


def test_sanitize_metadata():
    meta = {
        "user": "alice",
        "api_key": "super_secret_123456",
        "nested": {
            "password": "mypassword123",
            "normal_field": "public_data",
        },
        "items": [
            {"token": "ghp_abcdef123456789012345678901234567890"},
            {"safe": "hello"},
        ],
    }
    sanitized = sanitize_metadata(meta)
    assert sanitized["user"] == "alice"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["normal_field"] == "public_data"
    assert sanitized["items"][0]["token"] == "[REDACTED]"
    assert sanitized["items"][1]["safe"] == "hello"


def test_prune_expired_sessions(db_session: Session):
    service = RetentionService()
    now_ts = int(time.time())

    org = Organization(id="org-1", name="Test Org")
    user = User(id="user-1", organization_id="org-1", email="user@test.com", role="MEMBER")
    db_session.add_all([org, user])
    db_session.commit()

    active_session = WebSession(id="sess-1", user_id="user-1", token_hash="hash1", expires_at=now_ts + 3600)
    expired_session = WebSession(id="sess-2", user_id="user-1", token_hash="hash2", expires_at=now_ts - 3600)
    db_session.add_all([active_session, expired_session])
    db_session.commit()

    pruned = service.prune_expired_sessions(db_session, current_timestamp=now_ts)
    assert pruned == 1

    remaining = db_session.scalars(select(WebSession)).all()
    assert len(remaining) == 1
    assert remaining[0].id == "sess-1"


def test_purge_repository_and_organization_cascade(db_session: Session, tmp_path: Path):
    storage_root = tmp_path / "snapshots"
    storage_root.mkdir()
    repo_dir = storage_root / "repo-1"
    repo_dir.mkdir()
    (repo_dir / "snapshot_file.txt").write_text("data")

    service = RetentionService(storage_root=storage_root)

    org = Organization(id="org-cascade", name="Cascade Org")
    user = User(id="user-cascade", organization_id="org-cascade", email="cascade@test.com", role="ADMIN")
    repo = Repository(id="repo-1", organization_id="org-cascade", name="repo-1", default_branch="main")
    snap = RepositorySnapshot(id="snap-1", repository_id="repo-1", commit_sha="abc1234", version="1.0", status="READY")
    cr = ChangeRequest(
        id="cr-1", organization_id="org-cascade", repository_id="repo-1", description="Change", status="OPEN"
    )
    job = AnalysisJob(id="job-1", organization_id="org-cascade", change_request_id="cr-1", status="COMPLETED")
    run = AnalysisRun(
        id="run-1",
        organization_id="org-cascade",
        change_request_id="cr-1",
        snapshot_id="snap-1",
        commit_sha="abc1234",
        analyzer_version="1.0",
        model_version="1.0",
        result={},
    )
    art = Artifact(
        id="art-1",
        analysis_id="run-1",
        repository_snapshot_id="snap-1",
        kind="RISK",
        payload={},
    )
    fb = FindingFeedback(
        id="fb-1",
        organization_id="org-cascade",
        analysis_id="run-1",
        finding_id="art-1",
        user_id="user-cascade",
        decision="REJECTED",
        reason="False positive",
        analyzer_version="1.0",
    )
    audit = AuditLog(
        id="audit-1",
        organization_id="org-cascade",
        actor_id="user-cascade",
        action="CREATE",
        resource_type="REPOSITORY",
        resource_id="repo-1",
    )
    db_session.add_all([org, user, repo, snap, cr, job, run, art, fb, audit])
    db_session.commit()

    # Purge repository
    counts = service.purge_repository(db_session, "repo-1")
    assert counts["repositories"] == 1
    assert counts["change_requests"] == 1
    assert counts["analysis_runs"] == 1
    assert counts["analysis_artifacts"] == 1
    assert counts["findings_feedback"] == 1
    assert not repo_dir.exists()

    # Verify repository is gone
    assert db_session.get(Repository, "repo-1") is None
    assert db_session.get(ChangeRequest, "cr-1") is None
    assert db_session.get(AnalysisRun, "run-1") is None

    # Now purge organization
    org_counts = service.purge_organization(db_session, "org-cascade")
    assert org_counts["organizations"] == 1
    assert org_counts["users"] == 1
    assert org_counts["audit_logs"] == 1
    assert db_session.get(Organization, "org-cascade") is None
    assert db_session.get(User, "user-cascade") is None
