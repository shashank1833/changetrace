from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Cookie, Header, HTTPException, Request, WebSocket, status
from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal
from .models import User, WebSession


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_request_loopback(host: str | None, forwarded_for: str | None = None) -> bool:
    if not host or not _is_loopback(host):
        return False
    if forwarded_for:
        for ip_part in forwarded_for.split(","):
            clean_ip = ip_part.strip()
            if clean_ip and not _is_loopback(clean_ip):
                return False
    return True


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: str


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_session(user_id: str) -> tuple[str, int]:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + settings.session_ttl_seconds
    with SessionLocal() as session:
        session.add(
            WebSession(
                id=str(__import__("uuid").uuid4()), user_id=user_id, token_hash=_digest(token), expires_at=expires_at
            )
        )
        session.commit()
    return token, expires_at


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with SessionLocal() as session:
        item = session.scalar(select(WebSession).where(WebSession.token_hash == _digest(token)))
        if item:
            session.delete(item)
            session.commit()


def oauth_state() -> str:
    settings = get_settings()
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    value = f"{timestamp}.{nonce}"
    signature = hmac.new(settings.session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def validate_oauth_state(value: str) -> None:
    settings = get_settings()
    try:
        timestamp, nonce, signature = value.split(".", 2)
        unsigned = f"{timestamp}.{nonce}"
        expected = hmac.new(settings.session_secret.encode(), unsigned.encode(), hashlib.sha256).hexdigest()
        valid_age = 0 <= int(time.time()) - int(timestamp) <= 600
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid OAuth state") from None
    if not valid_age or not hmac.compare_digest(signature, expected):
        raise HTTPException(400, "Invalid or expired OAuth state")


def current_principal(
    request: Request = None,  # type: ignore
    changetrace_session: str | None = Cookie(default=None),
    x_user_id: UUID = Header(default=UUID("00000000-0000-0000-0000-000000000001")),
    x_organization_id: UUID = Header(default=UUID("00000000-0000-0000-0000-000000000001")),
    x_role: str = Header(default="OWNER"),
) -> Principal:
    settings = get_settings()
    if changetrace_session:
        with SessionLocal() as session:
            web_session = session.scalar(select(WebSession).where(WebSession.token_hash == _digest(changetrace_session)))
            if web_session and web_session.expires_at > int(time.time()):
                user = session.get(User, web_session.user_id)
                if user:
                    return Principal(UUID(user.id), UUID(user.organization_id), user.role)
            elif web_session:
                session.delete(web_session)
                session.commit()
    if settings.auth_mode == "development":
        if request is not None:
            client_host = request.client.host if request.client else "unknown"
            forwarded = request.headers.get("x-forwarded-for")
            if not _is_request_loopback(client_host, forwarded):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Header-based development authentication is restricted to local loopback",
                )
        if x_role not in {"OWNER", "ADMIN", "MEMBER", "VIEWER"}:
            raise HTTPException(status_code=403, detail="Invalid role")
        return Principal(x_user_id, x_organization_id, x_role)
    if not changetrace_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")


def require_write(principal: Principal) -> None:
    if principal.role == "VIEWER":
        raise HTTPException(status_code=403, detail="Viewer cannot modify resources")


def require_admin(principal: Principal) -> None:
    if principal.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Administrator or owner privileges required")


def authenticate_websocket(websocket: WebSocket) -> Principal:
    settings = get_settings()
    session_token = websocket.cookies.get("changetrace_session")
    if not session_token and settings.environment != "production":
        session_token = websocket.query_params.get("token")
    if session_token:
        with SessionLocal() as session:
            web_session = session.scalar(select(WebSession).where(WebSession.token_hash == _digest(session_token)))
            if web_session and web_session.expires_at > int(time.time()):
                user = session.get(User, web_session.user_id)
                if user:
                    return Principal(UUID(user.id), UUID(user.organization_id), user.role)
            elif web_session:
                session.delete(web_session)
                session.commit()
    if settings.auth_mode == "development":
        client_host = websocket.client.host if websocket.client else "unknown"
        forwarded = websocket.headers.get("x-forwarded-for")
        if not _is_request_loopback(client_host, forwarded):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Header-based development authentication is restricted to local loopback",
            )
        org_header = websocket.headers.get("x-organization-id", "00000000-0000-0000-0000-000000000001")
        user_header = websocket.headers.get("x-user-id", "00000000-0000-0000-0000-000000000001")
        role_header = websocket.headers.get("x-role", "OWNER")
        if role_header not in {"OWNER", "ADMIN", "MEMBER", "VIEWER"}:
            raise HTTPException(status_code=403, detail="Invalid role")
        try:
            return Principal(UUID(user_header), UUID(org_header), role_header)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Invalid development auth headers") from exc
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
