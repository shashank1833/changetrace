import hashlib
import hmac
import random
import uuid
from unittest.mock import patch

import pytest
from changetrace_schemas import (
    AnalysisResult,
    ChangeDecision,
    ChangeIntent,
    DecisionStatus,
    ImpactSummary,
)

from apps.api.changetrace_api.database import SessionLocal
from apps.api.changetrace_api.models import GitHubInstallation, Organization
from services.github.app import GitHubAppService, normalize_private_key
from services.github.checks import GitHubChecksService
from services.github.webhooks import GitHubWebhookHandler, verify_signature


def test_verify_webhook_signature():
    secret = "test-secret-12345"
    payload = b'{"action": "opened", "number": 1}'
    expected_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert verify_signature(payload, expected_sig, secret) is True
    assert verify_signature(payload, "sha256=invalid-signature", secret) is False
    assert verify_signature(payload, None, secret) is False
    assert verify_signature(b'tampered payload', expected_sig, secret) is False


def test_github_app_service_mock_token():
    service = GitHubAppService()
    # In unconfigured / mock mode, generates mock installation token
    token = service.get_installation_token(12345)
    assert token == "ghs_mock_token_for_inst_12345"
    # Cached token reuse
    assert service.get_installation_token(12345) == token


def test_github_app_private_key_normalization():
    raw_key = "-----BEGIN RSA PRIVATE KEY-----\\nMIIEowIBAAKCAQEA\\n-----END RSA PRIVATE KEY-----"
    normalized = normalize_private_key(raw_key)
    assert "\n" in normalized
    assert "\\n" not in normalized


def test_github_app_production_unconfigured_rejection():
    service = GitHubAppService()
    service.environment = "production"
    with pytest.raises(RuntimeError, match="unconfigured"):
        service.get_installation_token(99999, allow_mock=False)


def test_github_checks_service_markdown():
    service = GitHubChecksService()
    result = AnalysisResult(
        repository="test-repo",
        commit_sha="abcdef1234567890",
        snapshot_id="snap-test",
        analyzer_version="0.2.0",
        model_version="deterministic-v1",
        change_request="Add refund support",
        intent=ChangeIntent(),
        impact_summary=ImpactSummary(
            affected_files=2,
            affected_components=5,
            business_rules=1,
            apis=1,
            database_entities=1,
            background_jobs=0,
            integrations=1,
            related_tests=2,
        ),
        components=[],
        graph_edges=[],
        evidence=[],
        business_rules=[],
        state_machines=[],
        contradictions=[],
        risks=[],
        test_gaps=[],
        change_plan=["Verify authorization", "Update order status"],
        decision=ChangeDecision(
            status=DecisionStatus.GO,
            rationale=["All tests pass", "No critical risks"],
            required_actions=[],
        ),
    )

    md = service.build_summary_markdown(result)
    assert "ChangeTrace Decision: **GO**" in md
    assert "Affected Files:" in md
    assert "Verify authorization" in md


def test_webhook_handler_ping():
    handler = GitHubWebhookHandler()
    res = handler.process("ping", {})
    assert res == {"status": "ok", "message": "pong"}


def test_webhook_handler_installation_and_tenant_mapping():
    handler = GitHubWebhookHandler()
    inst_id = random.randint(100000, 999999)
    delivery_id = f"del-inst-{uuid.uuid4().hex[:8]}"
    login = f"acme-{uuid.uuid4().hex[:6]}"
    install_payload = {
        "action": "created",
        "installation": {
            "id": inst_id,
            "account": {
                "login": login,
                "id": random.randint(100000, 999999),
                "type": "Organization",
            },
            "permissions": {"pull_requests": "write"},
        },
    }
    res = handler.process("installation", install_payload, delivery_id=delivery_id)
    assert res["status"] == "installation_registered"
    assert res["installation_id"] == inst_id

    # Verify installation record in database
    with SessionLocal() as session:
        inst = session.get(GitHubInstallation, inst_id)
        assert inst is not None
        assert inst.account_login == login
        org = session.get(Organization, inst.organization_id)
        assert org is not None
        assert org.name == login

    # Now verify PR for this installation is mapped to the same organization
    pr_payload = {
        "action": "opened",
        "installation": {"id": inst_id},
        "number": 101,
        "pull_request": {
            "number": 101,
            "title": "Add tenant feature",
            "body": "Tenant isolated PR",
            "head": {"sha": "deadbeef11112222", "ref": "feat/tenant"},
            "base": {"ref": "main"},
        },
        "repository": {
            "full_name": f"{login}/core-api",
            "clone_url": f"https://github.com/{login}/core-api.git",
            "default_branch": "main",
        },
    }
    pr_del_id = f"del-pr-{uuid.uuid4().hex[:8]}"
    pr_res = handler.process("pull_request", pr_payload, delivery_id=pr_del_id)
    assert pr_res["status"] == "ingested"
    assert pr_res["organization_id"] == inst.organization_id


def test_webhook_handler_delivery_deduplication():
    handler = GitHubWebhookHandler()
    payload = {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "number": 42,
            "title": "Add order return workflow",
            "body": "Implements return status for delivered items",
            "head": {"sha": "1111222233334444", "ref": "feat/returns"},
            "base": {"ref": "main"},
        },
        "repository": {
            "full_name": "org/orders-service",
            "clone_url": "https://github.com/org/orders-service.git",
            "default_branch": "main",
        },
    }

    delivery_id = f"test-delivery-{uuid.uuid4().hex}"
    res1 = handler.process("pull_request", payload, delivery_id=delivery_id)
    assert res1["status"] == "ingested"

    # Replay same delivery
    res2 = handler.process("pull_request", payload, delivery_id=delivery_id)
    assert res2["status"] == "duplicate"
    assert res2["delivery_id"] == delivery_id


def test_analysis_completion_triggers_github_checks():
    from apps.api.changetrace_api.main import _run_analysis_job
    from apps.api.changetrace_api.models import AnalysisJob, ChangeRequest, Repository

    uid = uuid.uuid4().hex[:8]
    job_id = f"job-chk-{uid}"
    repo_id = f"repo-chk-{uid}"
    change_id = f"change-chk-{uid}"

    with SessionLocal() as session:
        org = Organization(name=f"Checks Test Org {uid}")
        session.add(org)
        session.commit()

        repo = Repository(
            id=repo_id,
            organization_id=org.id,
            name="org/orders-service",
            source_path="tests/evaluation/demo_repository",
        )
        change = ChangeRequest(
            id=change_id,
            organization_id=org.id,
            repository_id=repo.id,
            description="Add return orders",
            github_metadata={
                "installation_id": 12345,
                "repo_full_name": "org/orders-service",
                "pr_number": 77,
                "head_sha": "abcd1234efgh5678",
            },
        )
        job = AnalysisJob(
            id=job_id,
            organization_id=org.id,
            change_request_id=change.id,
            status="QUEUED",
            progress="0",
        )
        session.add_all([repo, change, job])
        session.commit()

    with patch("services.github.checks.GitHubChecksService.create_or_update_check_run") as mock_check, \
         patch("services.github.checks.GitHubChecksService.post_pr_comment") as mock_comment:
        mock_check.return_value = {"id": 1, "status": "completed"}
        mock_comment.return_value = {"id": 1, "status": "posted"}

        _run_analysis_job(job_id)

        assert mock_check.called
        call_kwargs = mock_check.call_args.kwargs
        assert call_kwargs["repo_full_name"] == "org/orders-service"
        assert call_kwargs["head_sha"] == "abcd1234efgh5678"

        assert mock_comment.called
        comment_kwargs = mock_comment.call_args.kwargs
        assert comment_kwargs["repo_full_name"] == "org/orders-service"
        assert comment_kwargs["pr_number"] == 77


def test_webhook_atomic_duplicate_claim():
    handler = GitHubWebhookHandler()
    delivery_id = f"atomic-del-{uuid.uuid4().hex}"
    payload = {"action": "ping"}

    # First claim succeeds
    assert handler._claim_delivery(delivery_id, "ping", payload) is True
    # Immediate concurrent claim fails atomically
    assert handler._claim_delivery(delivery_id, "ping", payload) is False


def test_webhook_signature_verification_enforcement():
    from fastapi.testclient import TestClient

    from apps.api.changetrace_api.config import get_settings
    from apps.api.changetrace_api.main import app

    client = TestClient(app)
    settings = get_settings()

    # When secret is configured, unsigned webhook is rejected with 403
    old_secret = settings.github_webhook_secret
    try:
        settings.github_webhook_secret = "super-secret-key"
        res = client.post("/api/v1/github/webhooks", content=b'{"action":"ping"}')
        assert res.status_code == 403
        assert "Invalid or missing webhook signature" in res.json()["detail"]
    finally:
        settings.github_webhook_secret = old_secret

