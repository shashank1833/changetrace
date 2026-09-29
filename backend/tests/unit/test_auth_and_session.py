import time
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from apps.api.changetrace_api.config import get_settings
from apps.api.changetrace_api.database import SessionLocal, create_schema
from apps.api.changetrace_api.models import Organization, User, WebSession
from apps.api.changetrace_api.security import (
    authenticate_websocket,
    create_session,
    current_principal,
    revoke_session,
)


@pytest.fixture(autouse=True)
def setup_db():
    create_schema()
    with SessionLocal() as session:
        # Create test org and user
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Auth Org")
        user = User(id=user_id, organization_id=org_id, email="auth_test@example.com", role="OWNER")
        session.add_all([org, user])
        session.commit()
        yield user_id, org_id


def test_create_and_revoke_session(setup_db):
    user_id, org_id = setup_db
    token, expires_at = create_session(user_id)
    assert token is not None
    assert expires_at > int(time.time())

    with SessionLocal() as session:
        ws = session.scalar(select(WebSession).where(WebSession.user_id == user_id))
        assert ws is not None
        assert ws.expires_at == expires_at

    revoke_session(token)

    with SessionLocal() as session:
        ws = session.scalar(select(WebSession).where(WebSession.user_id == user_id))
        assert ws is None


def test_current_principal_with_session(setup_db):
    user_id, org_id = setup_db
    token, _ = create_session(user_id)

    # In production auth mode
    settings = get_settings()
    orig_mode = settings.auth_mode
    try:
        settings.auth_mode = "github"
        principal = current_principal(changetrace_session=token)
        assert str(principal.user_id) == user_id
        assert str(principal.organization_id) == org_id
        assert principal.role == "OWNER"

        # Missing token raises 401
        with pytest.raises(HTTPException) as exc_info:
            current_principal(changetrace_session=None)
        assert exc_info.value.status_code == 401
    finally:
        settings.auth_mode = orig_mode


def test_authenticate_websocket(setup_db):
    user_id, org_id = setup_db
    token, _ = create_session(user_id)

    mock_ws = MagicMock()
    mock_ws.cookies = {"changetrace_session": token}
    mock_ws.query_params = {}
    mock_ws.headers = {}

    settings = get_settings()
    orig_mode = settings.auth_mode
    try:
        settings.auth_mode = "github"
        principal = authenticate_websocket(mock_ws)
        assert str(principal.user_id) == user_id
        assert str(principal.organization_id) == org_id

        # Unauthorized websocket
        unauth_ws = MagicMock()
        unauth_ws.cookies = {}
        unauth_ws.query_params = {}
        unauth_ws.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            authenticate_websocket(unauth_ws)
        assert exc_info.value.status_code == 401
    finally:
        settings.auth_mode = orig_mode
