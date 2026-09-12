import uuid

from changetrace_api.main import app
from fastapi.testclient import TestClient


def headers(tenant: str, role: str = "OWNER") -> dict[str, str]:
    return {"x-organization-id": tenant, "x-user-id": str(uuid.uuid4()), "x-role": role}


def test_invalid_identifiers_and_missing_fields_return_client_errors():
    with TestClient(app) as client:
        assert client.get("/api/v1/repositories/not-a-uuid").status_code == 422
        assert client.post("/api/v1/repositories", json={"name": "missing source"}).status_code == 422
        assert client.post("/api/v1/changes", json={}).status_code == 422


def test_viewer_cannot_create_repository(tmp_path):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/repositories",
            headers=headers(str(uuid.uuid4()), "VIEWER"),
            json={"name": "private", "source_path": str(tmp_path)},
        )
        assert response.status_code == 403


def test_cross_tenant_change_and_analysis_job_are_hidden(tmp_path):
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    with TestClient(app) as client:
        repository = client.post(
            "/api/v1/repositories",
            headers=headers(tenant_a),
            json={"name": "private", "source_path": str(tmp_path)},
        ).json()
        change = client.post(
            "/api/v1/changes",
            headers=headers(tenant_a),
            json={"repository_id": repository["id"], "description": "A sufficiently long private change"},
        ).json()
        assert client.get(f"/api/v1/changes/{change['id']}", headers=headers(tenant_b)).status_code == 404
        job = client.post(f"/api/v1/changes/{change['id']}/analyze", headers=headers(tenant_a)).json()
        assert client.get(f"/api/v1/jobs/{job['id']}", headers=headers(tenant_b)).status_code == 404


def test_security_headers_and_rate_limit(monkeypatch):
    import changetrace_api.main as main

    monkeypatch.setattr(main.settings, "rate_limit_per_minute", 1)
    main._rate_windows.clear()
    with TestClient(app) as client:
        first = client.get("/health")
        second = client.get("/health")
    assert first.status_code == 200
    assert first.headers["x-content-type-options"] == "nosniff"
    assert first.headers["x-frame-options"] == "DENY"
    assert second.status_code == 429
    assert second.headers["x-content-type-options"] == "nosniff"
    assert second.headers["x-frame-options"] == "DENY"
    assert second.headers["content-security-policy"] == "default-src 'self'"
    main._rate_windows.clear()
