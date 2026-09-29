import uuid
import pytest
from fastapi.testclient import TestClient
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.config import Settings
from apps.api.changetrace_api.database import SessionLocal
from apps.api.changetrace_api.models import Organization, GitHubInstallation, User, Repository, FindingFeedback
from services.github.webhooks import GitHubWebhookHandler


def test_github_installation_account_name_does_not_hijack_existing_tenant():
    with SessionLocal() as session:
        victim_org = Organization(id=str(uuid.uuid4()), name="ConfusedDeputyVictim")
        victim_user = User(
            id=str(uuid.uuid4()),
            organization_id=victim_org.id,
            email="owner@victim.com",
            role="OWNER",
        )
        session.add_all([victim_org, victim_user])
        session.commit()

    attacker_inst_id = 99887711
    handler = GitHubWebhookHandler()
    payload = {
        "action": "created",
        "installation": {
            "id": attacker_inst_id,
            "account": {
                "login": "ConfusedDeputyVictim",
                "id": 554433,
                "type": "User",
            },
            "permissions": {"pull_requests": "write"},
        },
    }
    delivery_id = str(uuid.uuid4())
    res = handler.process("installation", payload, delivery_id=delivery_id)
    assert res.get("status") == "installation_registered"

    with SessionLocal() as session:
        inst = session.get(GitHubInstallation, attacker_inst_id)
        assert inst is not None
        # Attacker's installation MUST NOT be attached to the victim organization
        assert inst.organization_id != victim_org.id
        org = session.get(Organization, inst.organization_id)
        assert org.id != victim_org.id


def test_production_config_rejects_insecure_settings():
    # Production with auth_mode='development' must fail
    with pytest.raises(ValueError, match="CHANGETRACE_AUTH_MODE"):
        Settings(
            environment="production",
            session_secret="a" * 32,
            session_cookie_secure=True,
            auth_mode="development",
        )

    # Production with session_cookie_secure=False must fail
    with pytest.raises(ValueError, match="CHANGETRACE_SESSION_COOKIE_SECURE"):
        Settings(
            environment="production",
            session_secret="a" * 32,
            session_cookie_secure=False,
            auth_mode="oauth",
        )


def test_member_role_forbidden_from_destructive_admin_operations():
    client = TestClient(app)

    with SessionLocal() as session:
        org = Organization(id=str(uuid.uuid4()), name="RBAC Test Org")
        repo = Repository(id=str(uuid.uuid4()), organization_id=org.id, name="rbac-repo")
        session.add_all([org, repo])
        session.commit()

    # MEMBER role attempting to delete repository must be rejected with 403
    resp = client.delete(
        f"/api/v1/repositories/{repo.id}",
        headers={
            "X-User-ID": str(uuid.uuid4()),
            "X-Organization-ID": org.id,
            "X-Role": "MEMBER",
        },
    )
    assert resp.status_code == 403
    assert "Administrator" in resp.json()["detail"] or "admin" in resp.json()["detail"].lower()

    # MEMBER role attempting to prune sessions must be rejected with 403
    resp_prune = client.post(
        "/api/v1/retention/prune-sessions",
        headers={
            "X-User-ID": str(uuid.uuid4()),
            "X-Organization-ID": org.id,
            "X-Role": "MEMBER",
        },
    )
    assert resp_prune.status_code == 403

    # ADMIN or OWNER role is permitted
    resp_owner = client.delete(
        f"/api/v1/repositories/{repo.id}",
        headers={
            "X-User-ID": str(uuid.uuid4()),
            "X-Organization-ID": org.id,
            "X-Role": "OWNER",
        },
    )
    assert resp_owner.status_code == 200


def test_webhook_requires_delivery_id():
    client = TestClient(app)
    # Post webhook without X-GitHub-Delivery header
    resp = client.post(
        "/api/v1/github/webhooks",
        json={"action": "ping"},
        headers={"X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 400
    assert "X-GitHub-Delivery" in resp.json()["detail"]


def test_feedback_upsert_prevents_metric_poisoning():
    client = TestClient(app)
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    analysis_id = str(uuid.uuid4())
    finding_id = "RISK-12345"

    with SessionLocal() as session:
        org = Organization(id=org_id, name="Feedback Test Org")
        from apps.api.changetrace_api.models import AnalysisRun, ChangeRequest
        repo = Repository(id=str(uuid.uuid4()), organization_id=org_id, name="feedback-repo")
        cr = ChangeRequest(id=str(uuid.uuid4()), organization_id=org_id, repository_id=repo.id, description="test")
        run = AnalysisRun(
            id=analysis_id,
            organization_id=org_id,
            change_request_id=cr.id,
            snapshot_id="snap-test",
            commit_sha="commit-test",
            analyzer_version="0.2.0",
            model_version="mock-v1",
            result={"risks": [{"risk_id": finding_id}], "test_gaps": []},
        )
        session.add_all([org, repo, cr, run])
        session.commit()

    headers = {
        "X-User-ID": user_id,
        "X-Organization-ID": org_id,
        "X-Role": "MEMBER",
    }

    # Submit feedback first time
    resp1 = client.post(
        f"/api/v1/analyses/{analysis_id}/findings/{finding_id}/feedback",
        json={"decision": "ACCEPTED", "reason": "first confirmation"},
        headers=headers,
    )
    assert resp1.status_code == 201

    # Submit feedback second time for the same finding
    resp2 = client.post(
        f"/api/v1/analyses/{analysis_id}/findings/{finding_id}/feedback",
        json={"decision": "REJECTED", "reason": "changed mind to reject"},
        headers=headers,
    )
    assert resp2.status_code == 201

    with SessionLocal() as session:
        entries = session.scalars(
            session.query(FindingFeedback).filter(
                FindingFeedback.analysis_id == analysis_id,
                FindingFeedback.finding_id == finding_id,
                FindingFeedback.user_id == user_id,
            ).statement
        ).all()
        # Must be upserted to 1 row, not 2 rows!
        assert len(entries) == 1
        assert entries[0].decision == "REJECTED"
        assert entries[0].reason == "changed mind to reject"
