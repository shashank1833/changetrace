from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from apps.api.changetrace_api.security import current_principal, authenticate_websocket


def test_remote_client_spoofing_forwarded_for_is_rejected():
    mock_request = MagicMock()
    mock_request.client.host = "203.0.113.195"
    mock_request.headers = {
        "x-forwarded-for": "127.0.0.1",
        "x-role": "OWNER",
        "x-user-id": "00000000-0000-0000-0000-000000000001",
        "x-organization-id": "00000000-0000-0000-0000-000000000001",
    }
    with pytest.raises(HTTPException) as exc_info:
        current_principal(request=mock_request, changetrace_session=None)
    assert exc_info.value.status_code == 401
    assert "restricted to local loopback" in exc_info.value.detail


def test_remote_websocket_spoofing_forwarded_for_is_rejected():
    mock_ws = MagicMock()
    mock_ws.client.host = "203.0.113.195"
    mock_ws.cookies = {}
    mock_ws.query_params = {}
    mock_ws.headers = {
        "x-forwarded-for": "127.0.0.1",
        "x-role": "OWNER",
    }
    with pytest.raises(HTTPException) as exc_info:
        authenticate_websocket(mock_ws)
    assert exc_info.value.status_code == 401
    assert "restricted to local loopback" in exc_info.value.detail


def test_loopback_client_allowed_in_development():
    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {
        "x-role": "OWNER",
        "x-user-id": "00000000-0000-0000-0000-000000000001",
        "x-organization-id": "00000000-0000-0000-0000-000000000001",
    }
    principal = current_principal(request=mock_request, changetrace_session=None, x_role="OWNER")
    assert principal.role == "OWNER"
