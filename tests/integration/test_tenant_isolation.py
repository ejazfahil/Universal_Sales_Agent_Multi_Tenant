"""M0-2 acceptance: invariant I2 — tenant isolation at the storage layer.

The decisive test is :func:`test_cross_tenant_select_without_where_returns_zero`.
It issues a bare ``SELECT * FROM customers`` — no ``WHERE tenant_id`` anywhere —
while the session is scoped to tenant B, and asserts nothing comes back. That is
the difference between isolation and a convention: if the boundary depended on
application code remembering a filter, this query would leak every row.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.integration.conftest import requires_db

pytestmark = requires_db


def _customers_visible(conn: sa.Connection) -> int:
    """Count customers with NO tenant filter of any kind."""
    return int(conn.execute(sa.text("SELECT count(*) FROM customers")).scalar_one())


def test_cross_tenant_select_without_where_returns_zero(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """★ The acceptance criterion. Scoped to B, tenant A's rows are invisible."""
    tenant_a, tenant_b = two_tenants

    with migrated.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)})
        assert _customers_visible(conn) == 1, "tenant A should see exactly its own customer"

    with migrated.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_b)})
        visible = _customers_visible(conn)

    assert visible == 1, "tenant B should see exactly its own customer, not A's"

    # And explicitly: querying A's id while scoped to B yields nothing.
    with migrated.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_b)})
        leaked = conn.execute(
            sa.text("SELECT count(*) FROM customers WHERE tenant_id = :a"), {"a": tenant_a}
        ).scalar_one()

    assert leaked == 0, "cross-tenant read leaked — invariant I2 is broken"


def test_unset_guc_sees_nothing(migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    """Fail closed: a request that forgot to set the tenant sees no data at all."""
    with migrated.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', NULL, true)"))
        assert _customers_visible(conn) == 0


def test_rls_is_forced_on_every_tenant_table(migrated: Engine) -> None:
    """FORCE matters: without it the table owner bypasses every policy."""
    expected = {
        "users",
        "customers",
        "orders",
        "conversations",
        "messages",
        "agent_runs",
        "approvals",
        "actions",
        "audit_logs",
    }
    with migrated.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = ANY(:names)"
            ),
            {"names": sorted(expected)},
        ).all()

    found = {r[0] for r in rows}
    assert found == expected, f"missing tables: {expected - found}"
    for name, enabled, forced in rows:
        assert enabled, f"{name}: RLS not enabled"
        assert forced, f"{name}: RLS not FORCEd — the owner would bypass it"


def test_write_into_another_tenant_is_rejected(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """WITH CHECK: scoped to B, you cannot insert a row belonging to A."""
    tenant_a, tenant_b = two_tenants
    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_b)})
        conn.execute(
            sa.text("INSERT INTO customers (id, tenant_id, name) VALUES (:id, :tid, 'smuggled')"),
            {"id": uuid.uuid4(), "tid": tenant_a},
        )
