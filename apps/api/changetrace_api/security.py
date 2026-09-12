from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: str


def current_principal(
    x_user_id: UUID = Header(default=UUID("00000000-0000-0000-0000-000000000001")),
    x_organization_id: UUID = Header(default=UUID("00000000-0000-0000-0000-000000000001")),
    x_role: str = Header(default="OWNER"),
) -> Principal:
    # Development header auth is replaceable by validated GitHub OAuth/App sessions.
    if x_role not in {"OWNER", "ADMIN", "MEMBER", "VIEWER"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")
    return Principal(x_user_id, x_organization_id, x_role)


def require_write(principal: Principal) -> None:
    if principal.role == "VIEWER":
        raise HTTPException(status_code=403, detail="Viewer cannot modify resources")
