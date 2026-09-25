from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200))


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    github_user_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(30), default="MEMBER")


class WebSession(Base):
    __tablename__ = "web_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GitHubInstallation(Base, TimestampMixin):
    __tablename__ = "github_installations"
    installation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    account_login: Mapped[str] = mapped_column(String(200))
    account_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_type: Mapped[str] = mapped_column(String(50), default="Organization")
    permissions_json: Mapped[dict] = mapped_column(JSON, default=dict)


class GitHubWebhookDelivery(Base):
    __tablename__ = "github_webhook_deliveries"
    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    installation_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_path: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(String(200), default="main")
    snapshots: Mapped[list[RepositorySnapshot]] = relationship(back_populates="repository")


class RepositorySnapshot(Base, TimestampMixin):
    __tablename__ = "repository_snapshots"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="VALID")
    repository: Mapped[Repository] = relationship(back_populates="snapshots")


class ChangeRequest(Base, TimestampMixin):
    __tablename__ = "change_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    proposed_diff: Mapped[str | None] = mapped_column(Text)
    base_ref: Mapped[str | None] = mapped_column(String(200))
    target_ref: Mapped[str | None] = mapped_column(String(200))
    github_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")


class AnalysisJob(Base, TimestampMixin):
    __tablename__ = "analysis_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    change_request_id: Mapped[str] = mapped_column(ForeignKey("change_requests.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    progress: Mapped[str] = mapped_column(String(3), default="0")
    analysis_id: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)


class AnalysisRun(Base, TimestampMixin):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    change_request_id: Mapped[str] = mapped_column(ForeignKey("change_requests.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(String(80), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64))
    analyzer_version: Mapped[str] = mapped_column(String(30))
    model_version: Mapped[str] = mapped_column(String(100))
    result: Mapped[dict] = mapped_column(JSON)


class EvidenceRecord(Base, TimestampMixin):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    repository_snapshot_id: Mapped[str] = mapped_column(String(80), index=True)
    type: Mapped[str] = mapped_column(String(40))
    file: Mapped[str] = mapped_column(Text)
    line_start: Mapped[str] = mapped_column(String(10))
    line_end: Mapped[str] = mapped_column(String(10))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class FindingFeedback(Base):
    __tablename__ = "finding_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    analyzer_version: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# Flexible analysis artifacts are stored in versioned AnalysisRun JSON for the MVP; these
# tables reserve normalized identities and FKs for graph-scale querying in PostgreSQL.
class Artifact(Base, TimestampMixin):
    __tablename__ = "analysis_artifacts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    repository_snapshot_id: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # symbol/dependency/intent/rule/impact/risk/test_gap/link
    severity: Mapped[str | None] = mapped_column(String(20), index=True)
    confidence: Mapped[str | None] = mapped_column(String(20))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)


Index("ix_artifact_analysis_kind", Artifact.analysis_id, Artifact.kind)
