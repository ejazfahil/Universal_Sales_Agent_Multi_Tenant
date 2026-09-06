"""M0-3 acceptance: invariant I4 — the audit log cannot be rewritten.

Article 12 asks for records of system operation. A record an operator can edit
is not evidence of anything, so these tests assert the *database* refuses —
including for a superuser, who is not constrained by grants.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.integration.conftest import requires_db, scope_to_tenant

pytestmark = requires_db


def _insert_audit(conn: sa.Connection, tenant_id: uuid.UUID) -> uuid.UUID:
    audit_id = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO audit_logs (id, tenant_id, trace_id, actor, action, decided_by, output) "
            "VALUES (:id, :tid, :trace, 'agent', 'chat.answer', 'code', 'original output')"
        ),
        {"id": audit_id, "tid": tenant_id, "trace": uuid.uuid4()},
    )
    return audit_id


def test_audit_rows_can_be_written(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        audit_id = _insert_audit(conn, tenant_a)
        found = conn.execute(
            sa.text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": audit_id}
        ).scalar_one()
    assert found == 1


def test_update_is_rejected_for_app_role(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """★ Invariant I4 for the application."""
    tenant_a, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        audit_id = _insert_audit(conn, tenant_a)

    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        conn.execute(
            sa.text("UPDATE audit_logs SET output = 'tampered' WHERE id = :id"), {"id": audit_id}
        )


def test_delete_is_rejected_for_app_role(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        audit_id = _insert_audit(conn, tenant_a)

    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        conn.execute(sa.text("DELETE FROM audit_logs WHERE id = :id"), {"id": audit_id})


def test_superuser_cannot_tamper_either(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """★ The one that matters. Grants do not bind a superuser; the trigger does.

    Without this, an operator holding production credentials could rewrite the
    evidence, and the Article 12 claim would be worthless.
    """
    tenant_a, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        audit_id = _insert_audit(conn, tenant_a)

    # No SET LOCAL ROLE — this connection is the superuser.
    with pytest.raises(sa.exc.DatabaseError, match="append-only"), migrated.begin() as conn:
        assert (
            conn.execute(sa.text("SELECT current_setting('is_superuser')")).scalar_one() == "on"
        ), "this test is meaningless unless it runs as superuser"
        conn.execute(
            sa.text("UPDATE audit_logs SET output = 'tampered' WHERE id = :id"), {"id": audit_id}
        )
