from __future__ import annotations

import logging
import re
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

logger = logging.getLogger("changetrace.retention")

# Patterns for sensitive credentials
CREDENTIAL_PATTERNS = [
    # GitHub Tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{50,255}"),
    # OpenAI and Anthropic Tokens
    re.compile(r"sk-[A-Za-z0-9_\-]{20,255}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,255}"),
    # Slack Tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,255}"),
    # AWS Keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # Private Keys
    re.compile(r"-----BEGIN[ A-Z0-9_-]+PRIVATE KEY-----[\s\S]*?-----END[ A-Z0-9_-]+PRIVATE KEY-----"),
    # Bearer Tokens
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_=]*"),
    # Generic Secrets in key=value assignments (literal quoted or unquoted strings)
    re.compile(r"""(?i)((?:api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['"]?)([A-Za-z0-9_\-\.]{16,})(['"]?)"""),
]

SENSITIVE_KEY_SUBSTRINGS = {
    "password", "token", "secret", "authorization", "cookie", "api_key", "credential", "private_key",
}


def redact_credentials(text: str) -> str:
    """Detect and redact API keys, tokens, and private keys from string content."""
    if not text:
        return text
    redacted = text
    for pattern in CREDENTIAL_PATTERNS:
        # If the pattern contains capturing groups around key=val, preserve key and redact secret
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1[REDACTED]\3", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def sanitize_metadata(data: Any) -> Any:
    """Recursively sanitize metadata dicts/lists to remove passwords, tokens, and secrets."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_str = str(key).lower()
            if any(s in key_str for s in SENSITIVE_KEY_SUBSTRINGS):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_metadata(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_metadata(item) for item in data]
    elif isinstance(data, str):
        return redact_credentials(data)
    return data


def _rowcount(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


class RetentionService:
    """Manages tenant data isolation, cascading deletions, session pruning, and credential hygiene."""

    def __init__(self, storage_root: Path | str | None = None) -> None:
        self.storage_root = Path(storage_root).resolve() if storage_root else None

    def prune_expired_sessions(self, session: Session, current_timestamp: int | None = None) -> int:
        """Remove expired web session tokens from the database."""
        from apps.api.changetrace_api.models import WebSession

        now_ts = current_timestamp or int(time.time())
        stmt = delete(WebSession).where(WebSession.expires_at < now_ts)
        result = session.execute(stmt)
        session.commit()
        count = _rowcount(result)
        logger.info("Pruned %d expired web sessions", count)
        return count

    def purge_repository(self, session: Session, repository_id: str) -> dict[str, int]:
        """Cascade-purge all repository data, snapshots, change requests, analysis runs, and on-disk files."""
        from apps.api.changetrace_api.models import (
            AnalysisJob,
            AnalysisRun,
            Artifact,
            ChangeRequest,
            EvidenceRecord,
            FindingFeedback,
            Repository,
            RepositorySnapshot,
        )

        repo = session.get(Repository, repository_id)
        if repo is None:
            return {"repositories": 0}

        counts: dict[str, int] = {
            "findings_feedback": 0,
            "analysis_artifacts": 0,
            "analysis_runs": 0,
            "analysis_jobs": 0,
            "evidence": 0,
            "snapshots": 0,
            "change_requests": 0,
            "repositories": 0,
        }

        # Find all snapshots
        snapshot_records = session.scalars(
            select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id)
        ).all()
        snapshot_ids = [s.id for s in snapshot_records]

        # Find all change requests
        cr_records = session.scalars(
            select(ChangeRequest).where(ChangeRequest.repository_id == repository_id)
        ).all()
        cr_ids = [c.id for c in cr_records]

        # Find analysis runs for these change requests
        run_records = session.scalars(
            select(AnalysisRun).where(AnalysisRun.change_request_id.in_(cr_ids))
        ).all() if cr_ids else []
        run_ids = [r.id for r in run_records]

        # Delete dependent records in dependency order
        for model, col, ids, key in (
            (FindingFeedback, FindingFeedback.analysis_id, run_ids, "findings_feedback"),
            (Artifact, Artifact.analysis_id, run_ids, "analysis_artifacts"),
            (AnalysisRun, AnalysisRun.id, run_ids, "analysis_runs"),
            (AnalysisJob, AnalysisJob.change_request_id, cr_ids, "analysis_jobs"),
            (EvidenceRecord, EvidenceRecord.repository_snapshot_id, snapshot_ids, "evidence"),
            (RepositorySnapshot, RepositorySnapshot.id, snapshot_ids, "snapshots"),
            (ChangeRequest, ChangeRequest.id, cr_ids, "change_requests"),
        ):
            if ids:
                counts[key] = _rowcount(session.execute(delete(model).where(col.in_(ids))))

        # Delete repository
        session.delete(repo)
        counts["repositories"] = 1
        session.commit()

        # Clean up filesystem storage
        if self.storage_root and self.storage_root.exists():
            resolved_root = self.storage_root.resolve()
            for snap_id in snapshot_ids:
                snap_path = (self.storage_root / snap_id).resolve()
                if snap_path.exists() and snap_path != resolved_root and snap_path.is_relative_to(resolved_root):
                    shutil.rmtree(snap_path, ignore_errors=True)
            repo_path = (self.storage_root / repository_id).resolve()
            if repo_path.exists() and repo_path != resolved_root and repo_path.is_relative_to(resolved_root):
                shutil.rmtree(repo_path, ignore_errors=True)

        logger.info("Purged repository %s: %s", repository_id, counts)
        return counts

    def purge_organization(self, session: Session, organization_id: str) -> dict[str, int]:
        """Cascade-purge an organization, including all users, repositories, sessions, and audit logs."""
        from apps.api.changetrace_api.models import (
            AuditLog,
            Organization,
            Repository,
            User,
            WebSession,
        )

        org = session.get(Organization, organization_id)
        if org is None:
            return {"organizations": 0}

        aggregate_counts: dict[str, int] = {
            "organizations": 1,
            "users": 0,
            "web_sessions": 0,
            "audit_logs": 0,
        }

        # Purge all repositories for the organization
        repos = session.scalars(select(Repository).where(Repository.organization_id == organization_id)).all()
        for repo in repos:
            for k, v in self.purge_repository(session, repo.id).items():
                aggregate_counts[k] = aggregate_counts.get(k, 0) + v

        # Find and purge users, sessions, and audit logs
        users = session.scalars(select(User).where(User.organization_id == organization_id)).all()
        user_ids = [u.id for u in users]
        for model, col, count_key in (
            (WebSession, WebSession.user_id, "web_sessions"),
            (User, User.id, "users"),
        ):
            if user_ids:
                aggregate_counts[count_key] = _rowcount(session.execute(delete(model).where(col.in_(user_ids))))

        aggregate_counts["audit_logs"] = _rowcount(
            session.execute(delete(AuditLog).where(AuditLog.organization_id == organization_id))
        )

        # Delete organization
        session.delete(org)
        session.commit()

        logger.info("Purged organization %s: %s", organization_id, aggregate_counts)
        return aggregate_counts

    def prune_old_snapshots(self, session: Session, retention_days: int = 30) -> dict[str, int]:
        """Prune snapshots older than retention_days along with their evidence and on-disk files."""
        from apps.api.changetrace_api.models import EvidenceRecord, RepositorySnapshot

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        old_snapshots = session.scalars(
            select(RepositorySnapshot).where(RepositorySnapshot.created_at < cutoff)
        ).all()
        if not old_snapshots:
            return {"snapshots_pruned": 0, "evidence_pruned": 0}

        snap_ids = [s.id for s in old_snapshots]
        ev_res = session.execute(delete(EvidenceRecord).where(EvidenceRecord.repository_snapshot_id.in_(snap_ids)))
        snap_res = session.execute(delete(RepositorySnapshot).where(RepositorySnapshot.id.in_(snap_ids)))
        session.commit()

        if self.storage_root and self.storage_root.exists():
            resolved_root = self.storage_root.resolve()
            for snap_id in snap_ids:
                snap_path = (self.storage_root / snap_id).resolve()
                if snap_path.exists() and snap_path != resolved_root and snap_path.is_relative_to(resolved_root):
                    shutil.rmtree(snap_path, ignore_errors=True)

        return {
            "snapshots_pruned": _rowcount(snap_res),
            "evidence_pruned": _rowcount(ev_res),
        }
