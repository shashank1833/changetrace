from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

from changetrace_schemas import AnalysisStatus
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from apps.api.changetrace_api.config import get_settings
from apps.api.changetrace_api.database import SessionLocal, set_tenant_context
from apps.api.changetrace_api.models import (
    AnalysisJob,
    ChangeRequest,
    GitHubInstallation,
    GitHubWebhookDelivery,
    Organization,
    Repository,
)

from .app import GitHubAppService

logger = logging.getLogger("changetrace.github.webhooks")


def verify_signature(payload_bytes: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from GitHub webhook header."""
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


class GitHubWebhookHandler:
    """Processes signed GitHub webhook events and triggers automated PR analysis with tenant isolation."""

    def __init__(self, app_service: GitHubAppService | None = None) -> None:
        self.app_service = app_service or GitHubAppService()

    def process(
        self,
        event_type: str,
        payload: dict[str, Any],
        delivery_id: str | None = None,
    ) -> dict[str, Any]:
        # 1. Atomic delivery deduplication and replay protection
        if delivery_id:
            if not self._claim_delivery(delivery_id, event_type, payload):
                logger.info("Ignoring duplicate webhook delivery %s", delivery_id)
                return {"status": "duplicate", "delivery_id": delivery_id}

        if event_type == "ping":
            self._record_delivery(delivery_id, event_type, payload)
            return {"status": "ok", "message": "pong"}

        if event_type == "installation":
            result = self._handle_installation(payload)
            self._record_delivery(delivery_id, event_type, payload)
            return result

        if event_type == "pull_request":
            action = payload.get("action")
            if action in {"opened", "synchronize", "reopened"}:
                result = self._handle_pull_request(payload)
                self._record_delivery(delivery_id, event_type, payload)
                return result
            self._record_delivery(delivery_id, event_type, payload)
            return {"status": "ignored", "action": action}

        if event_type == "check_run":
            action = payload.get("action")
            if action == "rerequested":
                result = self._handle_check_rerequest(payload)
                self._record_delivery(delivery_id, event_type, payload)
                return result
            self._record_delivery(delivery_id, event_type, payload)
            return {"status": "ignored", "action": action}

        self._record_delivery(delivery_id, event_type, payload)
        return {"status": "ignored", "event": event_type}

    def _claim_delivery(
        self,
        delivery_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """Atomically claim delivery_id using an immediate INSERT to prevent concurrent duplicate processing."""
        payload_str = json.dumps(payload, sort_keys=True)
        payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        inst_id = payload.get("installation", {}).get("id")
        try:
            with SessionLocal() as session:
                delivery = GitHubWebhookDelivery(
                    delivery_id=delivery_id,
                    event_type=event_type,
                    installation_id=int(inst_id) if inst_id else None,
                    payload_hash=payload_hash,
                )
                session.add(delivery)
                session.commit()
                return True
        except IntegrityError:
            return False
        except Exception as exc:
            logger.warning("Error during atomic delivery claim for %s: %s", delivery_id, exc)
            with SessionLocal() as session:
                return session.get(GitHubWebhookDelivery, delivery_id) is None

    def _record_delivery(
        self,
        delivery_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        organization_id: str | None = None,
        installation_id: int | None = None,
    ) -> None:
        if not delivery_id:
            return
        try:
            with SessionLocal() as session:
                delivery = session.get(GitHubWebhookDelivery, delivery_id)
                if delivery:
                    if organization_id and not delivery.organization_id:
                        delivery.organization_id = organization_id
                    if installation_id and not delivery.installation_id:
                        delivery.installation_id = installation_id
                    session.commit()
                else:
                    payload_str = json.dumps(payload, sort_keys=True)
                    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
                    inst_id = installation_id or payload.get("installation", {}).get("id")
                    delivery = GitHubWebhookDelivery(
                        delivery_id=delivery_id,
                        event_type=event_type,
                        installation_id=int(inst_id) if inst_id else None,
                        organization_id=organization_id,
                        payload_hash=payload_hash,
                    )
                    session.add(delivery)
                    session.commit()
        except Exception as exc:
            logger.debug("Failed to record webhook delivery %s: %s", delivery_id, exc)

    def _handle_installation(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        inst_data = payload.get("installation", {})
        inst_id = inst_data.get("id")
        account = inst_data.get("account", {})
        login = account.get("login", f"gh-inst-{inst_id}")

        if not inst_id:
            return {"status": "error", "error": "Missing installation id"}

        with SessionLocal() as session:
            if action in {"created", "unsuspend"}:
                from apps.api.changetrace_api.models import User

                installation = session.get(GitHubInstallation, inst_id)
                if installation:
                    org = session.get(Organization, installation.organization_id)
                else:
                    org = session.scalar(select(Organization).where(Organization.name == login))
                    org_has_other_inst = (
                        org is not None
                        and session.scalar(
                            select(GitHubInstallation).where(
                                GitHubInstallation.organization_id == org.id,
                                GitHubInstallation.installation_id != inst_id,
                            )
                        )
                        is not None
                    )
                    org_has_users = (
                        org is not None
                        and session.scalar(select(User).where(User.organization_id == org.id)) is not None
                    )
                    if not org or org_has_other_inst or org_has_users:
                        dedicated_name = f"{login}-{inst_id}" if org else login
                        org = Organization(id=str(uuid.uuid4()), name=dedicated_name)
                        session.add(org)
                        session.commit()

                set_tenant_context(session, org.id)
                if not installation:
                    installation = GitHubInstallation(
                        installation_id=inst_id,
                        organization_id=org.id,
                        account_login=login,
                        account_id=account.get("id"),
                        target_type=inst_data.get("target_type", "Organization"),
                        permissions_json=inst_data.get("permissions", {}),
                    )
                    session.add(installation)
                else:
                    installation.organization_id = org.id
                    installation.account_login = login
                    installation.permissions_json = inst_data.get("permissions", {})
                session.commit()
                return {"status": "installation_registered", "installation_id": inst_id, "organization_id": org.id}

            elif action in {"deleted"}:
                installation = session.get(GitHubInstallation, inst_id)
                if installation:
                    session.delete(installation)
                    session.commit()
                return {"status": "installation_deleted", "installation_id": inst_id}

            return {"status": "installation_updated", "action": action}

    def _handle_pull_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        pr_data = payload["pull_request"]
        repo_data = payload["repository"]
        repo_full_name = repo_data["full_name"]
        repo_url = repo_data.get("clone_url") or repo_data.get("html_url")
        pr_number = pr_data["number"]
        pr_title = pr_data.get("title", "")
        pr_body = pr_data.get("body", "") or ""
        head_sha = pr_data["head"]["sha"]
        base_ref = pr_data["base"]["ref"]

        inst_data = payload.get("installation", {})
        inst_id = inst_data.get("id")

        change_description = f"PR #{pr_number}: {pr_title}\n\n{pr_body}".strip()

        with SessionLocal() as session:
            # 1. Resolve organization tenant from GitHub installation mapping
            org = None
            if inst_id:
                installation = session.get(GitHubInstallation, inst_id)
                if installation:
                    org = session.get(Organization, installation.organization_id)

            if not org:
                settings = get_settings()
                if getattr(settings, "environment", "development") == "production":
                    return {
                        "status": "rejected",
                        "error": f"Unauthorized: No organization mapped for GitHub installation {inst_id}",
                    }
                # In development/testing, create a dedicated organization for this repo owner instead of hijacking existing tenant
                owner_login = repo_data.get("owner", {}).get("login") or f"gh-owner-{inst_id or 'anon'}"
                org = session.scalar(select(Organization).where(Organization.name == owner_login))
                if not org:
                    org = Organization(id=str(uuid.uuid4()), name=owner_login)
                    session.add(org)
                    session.commit()

                if inst_id:
                    session.add(
                        GitHubInstallation(
                            installation_id=inst_id,
                            organization_id=org.id,
                            account_login=org.name,
                            account_id=repo_data.get("owner", {}).get("id"),
                        )
                    )
                    session.commit()

            # 2. Find or create repository scoped to this tenant
            set_tenant_context(session, org.id)
            repo = session.scalar(
                select(Repository).where(
                    Repository.organization_id == org.id,
                    Repository.name == repo_full_name,
                )
            )
            if not repo:
                repo = Repository(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    name=repo_full_name,
                    github_url=repo_url,
                    default_branch=repo_data.get("default_branch", "main"),
                )
                session.add(repo)
                session.commit()

            # 3. Create ChangeRequest with GitHub metadata
            github_metadata = {
                "installation_id": inst_id,
                "repo_full_name": repo_full_name,
                "pr_number": pr_number,
                "head_sha": head_sha,
                "base_ref": base_ref,
            }
            change = ChangeRequest(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                repository_id=repo.id,
                description=change_description,
                base_ref=base_ref,
                target_ref=head_sha,
                github_metadata=github_metadata,
            )
            session.add(change)

            # 4. Create AnalysisJob
            job = AnalysisJob(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                change_request_id=change.id,
                status=AnalysisStatus.QUEUED.value,
                progress="0",
            )
            session.add(job)
            session.commit()

            # 5. Enqueue execution
            settings = get_settings()
            if settings.queue_mode == "redis":
                try:
                    from redis import Redis
                    from rq import Queue, Retry

                    from apps.api.changetrace_api.main import _run_analysis_job

                    conn = Redis.from_url(settings.redis_url)
                    conn.ping()
                    q = Queue("changetrace", connection=conn)
                    q.enqueue(_run_analysis_job, job.id, retry=Retry(max=2, interval=[10, 30]))
                except Exception:
                    import threading

                    from apps.api.changetrace_api.main import _run_analysis_job
                    thread = threading.Thread(target=_run_analysis_job, args=(job.id,), daemon=True)
                    thread.start()
            else:
                import threading

                from apps.api.changetrace_api.main import _run_analysis_job
                thread = threading.Thread(target=_run_analysis_job, args=(job.id,), daemon=True)
                thread.start()

            return {
                "status": "ingested",
                "organization_id": org.id,
                "repository_id": repo.id,
                "change_request_id": change.id,
                "job_id": job.id,
                "pr_number": pr_number,
                "head_sha": head_sha,
            }

    def _handle_check_rerequest(self, payload: dict[str, Any]) -> dict[str, Any]:
        check_run = payload.get("check_run", {})
        head_sha = check_run.get("head_sha")
        repo_data = payload.get("repository", {})
        repo_full_name = repo_data.get("full_name")
        return {
            "status": "rerequest_received",
            "repo": repo_full_name,
            "head_sha": head_sha,
        }
