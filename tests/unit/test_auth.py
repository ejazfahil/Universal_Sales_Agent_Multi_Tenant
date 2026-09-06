"""M0-4 acceptance: tenant context and RBAC."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.auth.tenant import PERMISSIONS, TenantContext, issue_token, parse_token

TENANT = uuid.uuid4()
USER = uuid.uuid4()


def test_token_round_trip() -> None:
    ctx = parse_token(issue_token(TENANT, USER, "agent"))
    assert ctx.tenant_id == TENANT
    assert ctx.user_id == USER
    assert ctx.role == "agent"


def test_tampered_token_is_rejected() -> None:
    token = issue_token(TENANT, USER, "viewer")
    body, sig = token.split(".", 1)
    forged = parse_token  # bind for clarity
    with pytest.raises(HTTPException) as exc:
        forged(f"{body}.{'0' * len(sig)}")
    assert exc.value.status_code == 401


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(HTTPException):
        parse_token("not-a-token")


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        ("owner", "approve", True),
        ("owner", "configure", True),
        ("agent", "approve", True),
        ("agent", "configure", False),
        ("viewer", "read", True),
        ("viewer", "approve", False),
        ("viewer", "export", False),
    ],
)
def test_permission_matrix(role: str, permission: str, allowed: bool) -> None:
    ctx = TenantContext(tenant_id=TENANT, user_id=USER, role=role)  # type: ignore[arg-type]
    assert ctx.may(permission) is allowed


def test_every_role_has_read() -> None:
    assert all("read" in perms for perms in PERMISSIONS.values())
