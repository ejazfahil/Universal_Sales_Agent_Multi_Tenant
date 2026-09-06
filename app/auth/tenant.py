"""Tenant context and role-based access control.

Every request carries a tenant and a role. The tenant is used to scope the
database session (which sets the RLS GUC); the role gates what the caller may
do. Both are resolved once, at the edge, so no handler has to remember.

M0 uses a signed bearer token carrying tenant and role. Session cookies and a
real identity provider land in M1 — the dependency surface here does not change.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings

Role = Literal["owner", "agent", "viewer"]

#: What each role may do. Deliberately explicit rather than a hierarchy —
#: "viewer can't approve" should be readable, not inferred from an ordering.
PERMISSIONS: dict[Role, frozenset[str]] = {
    "owner": frozenset({"read", "approve", "configure", "export"}),
    "agent": frozenset({"read", "approve"}),
    "viewer": frozenset({"read"}),
}


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: Role

    def may(self, permission: str) -> bool:
        return permission in PERMISSIONS[self.role]


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def issue_token(tenant_id: uuid.UUID, user_id: uuid.UUID, role: Role) -> str:
    """Mint a bearer token. Dev/test helper; M1 replaces this with real auth."""
    secret = get_settings().auth_secret
    body = json.dumps(
        {"tenant_id": str(tenant_id), "user_id": str(user_id), "role": role},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"{urlsafe_b64encode(body).decode()}.{_sign(body, secret)}"


def parse_token(token: str) -> TenantContext:
    """Verify and decode a bearer token, or raise 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        encoded, signature = token.split(".", 1)
        body = urlsafe_b64decode(encoded.encode())
    except (ValueError, TypeError) as exc:
        raise unauthorized from exc

    # Constant-time: a timing side channel here leaks the signature byte by byte.
    if not hmac.compare_digest(signature, _sign(body, get_settings().auth_secret)):
        raise unauthorized

    try:
        claims = json.loads(body)
        role = claims["role"]
        if role not in PERMISSIONS:
            raise unauthorized
        return TenantContext(
            tenant_id=uuid.UUID(claims["tenant_id"]),
            user_id=uuid.UUID(claims["user_id"]),
            role=role,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise unauthorized from exc


def get_tenant_context(
    authorization: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """FastAPI dependency: resolve the caller's tenant and role."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parse_token(authorization[7:])


def require(permission: str) -> Callable[[TenantContext], TenantContext]:
    """Dependency factory gating a route on a permission.

    Usage: ``ctx: TenantContext = Depends(require("approve"))``
    """

    def _dependency(ctx: Annotated[TenantContext, Depends(get_tenant_context)]) -> TenantContext:
        if not ctx.may(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{ctx.role}' may not '{permission}'",
            )
        return ctx

    return _dependency
