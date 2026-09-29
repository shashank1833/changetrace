from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.config import get_settings


def test_auth_mode_production_rejects_header_spoofing():
    settings = get_settings()
    original_mode = settings.auth_mode
    try:
        settings.auth_mode = "production"
        client = TestClient(app)
        response = client.get(
            "/api/v1/repositories",
            headers={
                "X-User-ID": str(uuid4()),
                "X-Organization-ID": str(uuid4()),
                "X-Role": "OWNER",
            },
        )
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]
    finally:
        settings.auth_mode = original_mode


def test_dev_auth_rejects_remote_client_ip():
    settings = get_settings()
    original_mode = settings.auth_mode
    try:
        settings.auth_mode = "development"
        client = TestClient(app)
        response = client.get(
            "/api/v1/repositories",
            headers={
                "X-User-ID": str(uuid4()),
                "X-Organization-ID": str(uuid4()),
                "X-Role": "OWNER",
                "X-Forwarded-For": "203.0.113.195",
            },
        )
        assert response.status_code == 401
        assert "restricted to local loopback" in response.json()["detail"]
    finally:
        settings.auth_mode = original_mode
