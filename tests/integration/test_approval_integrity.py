"""Invariant I1, strengthened — what the constraint now actually proves.

The original CHECK established only that a MONEY row *pointed at* an approval.
Each test below is one of the holes that left, closed by migration 0005. They
are written as attacks: every one is a way to move money that the old schema
would have permitted.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.integration.conftest import requires_db, scope_to_tenant

pytestmark = requires_db


def _user(conn: sa.Connection, tenant: uuid.UUID, email: str) -> uuid.UUID:
    uid = uuid.uuid4()
    conn.execute(
        sa.text("INSERT INTO users (id, tenant_id, email, role) VALUES (:i, :t, :e, 'agent')"),
        {"i": uid, "t": tenant, "e": email},
    )
    return uid


def _run(conn: sa.Connection, tenant: uuid.UUID, requester: uuid.UUID | None) -> uuid.UUID:
    conv, run = uuid.uuid4(), uuid.uuid4()
    conn.execute(
        sa.text("INSERT INTO conversations (id, tenant_id) VALUES (:i, :t)"),
        {"i": conv, "t": tenant},
    )
    conn.execute(
        sa.text(
            "INSERT INTO agent_runs (id, tenant_id, conversation_id, model, requested_by) "
            "VALUES (:i, :t, :c, 'claude-opus-5', :r)"
        ),
        {"i": run, "t": tenant, "c": conv, "r": requester},
    )
    return run


def _approval(
    conn: sa.Connection,
    tenant: uuid.UUID,
    run: uuid.UUID,
    decision: str,
    approver: uuid.UUID | None,
    amount: int = 10_000,
) -> uuid.UUID:
    aid = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO approvals (id, tenant_id, agent_run_id, decision, decided_by, "
            "approved_amount_cents) VALUES (:i, :t, :r, :d, :u, :amt)"
        ),
        {"i": aid, "t": tenant, "r": run, "d": decision, "u": approver, "amt": amount},
    )
    return aid


def _money_action(
    conn: sa.Connection,
    tenant: uuid.UUID,
    run: uuid.UUID,
    approval: uuid.UUID | None,
    approval_run: uuid.UUID | None,
    decision: str | None,
    amount: int = 5_000,
) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO actions (id, tenant_id, agent_run_id, approval_id, approval_run_id, "
            "approval_decision, tool, tool_class, amount_cents) "
            "VALUES (:i, :t, :r, :a, :ar, :d, 'commerce.refund_order', 'MONEY', :amt)"
        ),
        {
            "i": uuid.uuid4(),
            "t": tenant,
            "r": run,
            "a": approval,
            "ar": approval_run,
            "d": decision,
            "amt": amount,
        },
    )


def test_valid_approved_money_action_is_accepted(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """The happy path must still work, or the constraints are just a wall."""
    t, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, t)
        requester = _user(conn, t, "agent@example.test")
        approver = _user(conn, t, "lead@example.test")
        run = _run(conn, t, requester)
        appr = _approval(conn, t, run, "approve", approver, amount=10_000)
        _money_action(conn, t, run, appr, run, "approve", amount=5_000)


def test_denied_approval_cannot_authorise_money(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """★ The main gap. A reference to a DENIED approval used to satisfy the CHECK."""
    t, _ = two_tenants
    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        scope_to_tenant(conn, t)
        requester = _user(conn, t, "a@example.test")
        approver = _user(conn, t, "b@example.test")
        run = _run(conn, t, requester)
        appr = _approval(conn, t, run, "deny", approver)
        _money_action(conn, t, run, appr, run, "deny")


def test_approval_from_a_different_run_is_rejected(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """An approval for run A must not authorise an action on run B."""
    t, _ = two_tenants
    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        scope_to_tenant(conn, t)
        requester = _user(conn, t, "a2@example.test")
        approver = _user(conn, t, "b2@example.test")
        run_a = _run(conn, t, requester)
        run_b = _run(conn, t, requester)
        appr = _approval(conn, t, run_a, "approve", approver)
        _money_action(conn, t, run_b, appr, run_a, "approve")


def test_one_approval_cannot_authorise_two_actions(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Otherwise one €10 approval funds an unbounded number of refunds."""
    t, _ = two_tenants
    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        scope_to_tenant(conn, t)
        requester = _user(conn, t, "a3@example.test")
        approver = _user(conn, t, "b3@example.test")
        run = _run(conn, t, requester)
        appr = _approval(conn, t, run, "approve", approver)
        _money_action(conn, t, run, appr, run, "approve", amount=1_000)
        _money_action(conn, t, run, appr, run, "approve", amount=1_000)


def test_approver_cannot_be_the_requester(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Separation of duties: signing off your own request is not oversight."""
    t, _ = two_tenants
    with (
        pytest.raises(sa.exc.DatabaseError, match="separation of duties"),
        migrated.begin() as conn,
    ):
        scope_to_tenant(conn, t)
        same = _user(conn, t, "solo@example.test")
        run = _run(conn, t, same)
        appr = _approval(conn, t, run, "approve", same)
        _money_action(conn, t, run, appr, run, "approve")


def test_action_cannot_exceed_the_approved_amount(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """A human authorising €10 has not authorised €500."""
    t, _ = two_tenants
    with pytest.raises(sa.exc.DatabaseError, match="exceeds approved"), migrated.begin() as conn:
        scope_to_tenant(conn, t)
        requester = _user(conn, t, "a4@example.test")
        approver = _user(conn, t, "b4@example.test")
        run = _run(conn, t, requester)
        appr = _approval(conn, t, run, "approve", approver, amount=1_000)
        _money_action(conn, t, run, appr, run, "approve", amount=50_000)


def test_money_still_cannot_exist_with_no_approval(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """The original guarantee must survive the strengthening."""
    t, _ = two_tenants
    with pytest.raises(sa.exc.DatabaseError), migrated.begin() as conn:
        scope_to_tenant(conn, t)
        run = _run(conn, t, None)
        _money_action(conn, t, run, None, None, None)


def test_unattributed_approver_cannot_move_money(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """An approval with no recorded human is not oversight evidence."""
    t, _ = two_tenants
    with pytest.raises(sa.exc.DatabaseError, match="attributed approver"), migrated.begin() as conn:
        scope_to_tenant(conn, t)
        run = _run(conn, t, _user(conn, t, "a5@example.test"))
        appr = _approval(conn, t, run, "approve", None)
        _money_action(conn, t, run, appr, run, "approve")


def test_read_actions_need_no_approval(
    migrated: Engine, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """The tightening must not gate ordinary read-only work."""
    t, _ = two_tenants
    with migrated.begin() as conn:
        scope_to_tenant(conn, t)
        run = _run(conn, t, None)
        conn.execute(
            sa.text(
                "INSERT INTO actions (id, tenant_id, agent_run_id, tool, tool_class) "
                "VALUES (:i, :t, :r, 'commerce.lookup_order', 'READ')"
            ),
            {"i": uuid.uuid4(), "t": t, "r": run},
        )
