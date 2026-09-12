import uuid

from changetrace_api.main import app
from fastapi.testclient import TestClient


def test_repository_is_not_visible_to_another_tenant(tmp_path):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/repositories",
            headers={"x-organization-id": tenant_a},
            json={"name": "private", "source_path": str(tmp_path), "default_branch": "main"},
        )
        assert created.status_code == 201
        repository_id = created.json()["id"]
        response = client.get(f"/api/v1/repositories/{repository_id}", headers={"x-organization-id": tenant_b})
        assert response.status_code == 404


def test_evidence_is_not_visible_to_another_tenant():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/evidence/E-does-not-exist",
            headers={"x-organization-id": str(uuid.uuid4())},
        )
        assert response.status_code == 404


def test_change_rejects_ambiguous_diff_and_ref_comparison():
    with TestClient(app) as client:
        repository = client.post(
            "/api/v1/repositories",
            json={"name": "safe", "source_path": ".", "default_branch": "main"},
        ).json()
        response = client.post(
            "/api/v1/changes",
            json={
                "repository_id": repository["id"],
                "description": "A sufficiently long proposed change",
                "proposed_diff": "diff --git a/a b/a",
                "base_ref": "main",
                "target_ref": "feature",
            },
        )
        assert response.status_code == 422
