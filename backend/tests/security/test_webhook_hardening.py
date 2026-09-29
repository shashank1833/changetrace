import uuid
from apps.api.changetrace_api.database import SessionLocal
from apps.api.changetrace_api.models import Organization, GitHubInstallation
from services.github.webhooks import GitHubWebhookHandler


def test_unmapped_pr_webhook_does_not_hijack_existing_tenant():
    with SessionLocal() as session:
        # Create an existing customer tenant
        customer_org = Organization(id=str(uuid.uuid4()), name="Acme Corp Customer")
        session.add(customer_org)
        session.commit()

    inst_id = 1000000 + (hash(str(uuid.uuid4())) % 500000)
    handler = GitHubWebhookHandler()
    payload = {
        "action": "opened",
        "installation": {"id": inst_id},
        "repository": {
            "full_name": "attacker-org/malicious-repo",
            "clone_url": "https://github.com/attacker-org/malicious-repo.git",
            "owner": {"login": "attacker-org", "id": 12345},
            "default_branch": "main",
        },
        "pull_request": {
            "number": 1,
            "title": "Malicious PR",
            "body": "PR description",
            "head": {"sha": "1234567890abcdef1234567890abcdef12345678"},
            "base": {"ref": "main"},
        },
    }

    result = handler.process("pull_request", payload, delivery_id=str(uuid.uuid4()))
    assert result.get("status") != "error"

    # Verify that the installation was NOT attached to Acme Corp Customer
    with SessionLocal() as session:
        inst = session.get(GitHubInstallation, inst_id)
        assert inst is not None
        assert inst.organization_id != customer_org.id
        # Must be in its own org
        org = session.get(Organization, inst.organization_id)
        assert org.name == "attacker-org"
