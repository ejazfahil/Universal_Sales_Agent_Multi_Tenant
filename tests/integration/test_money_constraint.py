"""M0-2 acceptance: invariant I1 enforced by the database.

A MONEY-class action without an approval must be impossible to insert. This is
the constraint that makes "no refund without a human" a property of the schema
rather than a promise about code paths.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.integration.conftest import requires_db, scope_to_tenant

pytestmark = requires_db


def _seed_run(conn: sa.Connection, tenant_id: uuid.UUID) -> uuid.UUID:
    conv_id, run_id = uuid.uuid4(), uuid.uuid4()
    conn.execute(
        sa.text("INSERT INTO conversations (id, tenant_id) VALUES (:id, :tid)"),
        {"id": conv_id, "tid": tenant_id},
    )
    conn.execute(
        sa.text(
            "INSERT INTO agent_runs (id, tenant_id, conversation_id, model) "
            "VALUES (:id, :tid, :cid, 'claude-opus-5')"
        ),
        {"id": run_id, "tid": tenant_id, "cid": conv_id},
    )
    return run_id


def test_money_action_without_approval_is_rejected(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """★ Invariant I1. Postgres refuses the INSERT."""
    tenant_a, _ = two_tenants
    with (
        pytest.raises(sa.exc.IntegrityError, match="ck_money_action_requires_approval"),
        migrated.begin() as conn,
    ):
        scope_to_tenant(conn, tenant_a)
        run_id = _seed_run(conn, tenant_a)
        conn.execute(
            sa.text(
                "INSERT INTO actions (id, tenant_id, agent_run_id, tool, tool_class, "
                "amount_cents) VALUES (:id, :tid, :rid, 'shopify.refund_order', 'MONEY', 8900)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_a, "rid": run_id},
        )


def test_read_action_without_approval_is_allowed(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """READ-class tools are autonomous by design; no approval needed."""
    tenant_a, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, tenant_a)
        run_id = _seed_run(conn, tenant_a)
        conn.execute(
            sa.text(
                "INSERT INTO actions (id, tenant_id, agent_run_id, tool, tool_class) "
                "VALUES (:id, :tid, :rid, 'shopify.lookup_order', 'READ')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_a, "rid": run_id},
        )
