"""Make the money constraint prove what it claims. Invariant I1, strengthened.

Migration 0001 shipped ``CHECK (tool_class <> 'MONEY' OR approval_id IS NOT
NULL)``. External review pointed out how little that proves: a CHECK cannot
reference another table, so it establishes only that a MONEY row *points at*
an approval. It cannot show the decision was ``approve`` rather than ``deny``,
that the approval belongs to this run, that the approver is not the requester,
that one approval was not reused across several actions, or that the approved
amount covers the action.

Five holes, closed with the right tool for each:

1. **Decision was approve/edit** — a composite FK to
   ``approvals(id, agent_run_id, decision)`` carries the decision into
   ``actions``, where a CHECK constrains it. Structural, not procedural.
2. **Approval belongs to this run** — the same composite FK carries
   ``agent_run_id``, and a CHECK requires it to equal the action's own run.
3. **One approval, one action** — a partial unique index.
4. **Approver is not the requester** — a trigger; separation of duties needs to
   compare two tables.
5. **Approved amount covers the action** — same trigger.

FKs and CHECKs are preferred wherever they can express the rule, because they
cannot be disabled per-session the way a trigger can.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # Who asked for the run — needed for separation of duties.
    op.add_column(
        "agent_runs",
        sa.Column("requested_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    # What the human actually authorised.
    op.add_column(
        "approvals",
        sa.Column("approved_amount_cents", sa.Integer(), nullable=False, server_default="0"),
    )

    # Target for the composite FK.
    op.create_unique_constraint(
        "uq_approvals_id_run_decision", "approvals", ["id", "agent_run_id", "decision"]
    )

    # Carry the approval's run and decision onto the action so a CHECK can see them.
    op.add_column("actions", sa.Column("approval_run_id", UUID, nullable=True))
    op.add_column("actions", sa.Column("approval_decision", sa.String(), nullable=True))

    op.create_foreign_key(
        "fk_actions_approval_composite",
        "actions",
        "approvals",
        ["approval_id", "approval_run_id", "approval_decision"],
        ["id", "agent_run_id", "decision"],
        ondelete="RESTRICT",
    )

    # (1) A MONEY action must carry an approval whose decision authorises it.
    op.create_check_constraint(
        "ck_money_requires_approving_decision",
        "actions",
        # NULL IN (...) evaluates to NULL, and a CHECK passes on NULL — it only
        # fails on FALSE. Without the IS NOT NULL guard a MONEY action with no
        # approval at all slips through. Caught by test in CI, not by review.
        "tool_class <> 'MONEY' OR (approval_decision IS NOT NULL "
        "AND approval_decision IN ('approve', 'edit'))",
    )
    # (2) The approval must belong to this action's own run.
    op.create_check_constraint(
        "ck_approval_matches_run",
        "actions",
        "approval_id IS NULL OR approval_run_id = agent_run_id",
    )
    # All three approval columns travel together or not at all.
    op.create_check_constraint(
        "ck_approval_columns_consistent",
        "actions",
        "(approval_id IS NULL AND approval_run_id IS NULL AND approval_decision IS NULL)"
        " OR (approval_id IS NOT NULL AND approval_run_id IS NOT NULL"
        " AND approval_decision IS NOT NULL)",
    )

    # (3) One approval authorises exactly one action.
    op.execute(
        "CREATE UNIQUE INDEX uq_actions_one_approval_each "
        "ON actions (approval_id) WHERE approval_id IS NOT NULL"
    )

    # (4) and (5): cross-table rules a CHECK cannot express.
    op.execute("""
        CREATE OR REPLACE FUNCTION actions_approval_integrity()
        RETURNS TRIGGER AS $$
        DECLARE
            approver  uuid;
            requester uuid;
            authorised integer;
        BEGIN
            IF NEW.approval_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT a.decided_by, a.approved_amount_cents
              INTO approver, authorised
              FROM approvals a WHERE a.id = NEW.approval_id;

            SELECT r.requested_by INTO requester
              FROM agent_runs r WHERE r.id = NEW.agent_run_id;

            -- Separation of duties. NULL approver means an unattributed
            -- approval, which is not good enough to move money.
            IF NEW.tool_class = 'MONEY' AND approver IS NULL THEN
                RAISE EXCEPTION
                    'money action requires an attributed approver (approval %)',
                    NEW.approval_id
                    USING ERRCODE = 'restrict_violation';
            END IF;

            IF approver IS NOT NULL AND requester IS NOT NULL AND approver = requester THEN
                RAISE EXCEPTION
                    'separation of duties: approver % also requested run %',
                    approver, NEW.agent_run_id
                    USING ERRCODE = 'restrict_violation';
            END IF;

            -- The human authorised a number; the action may not exceed it.
            IF NEW.tool_class = 'MONEY' AND NEW.amount_cents > COALESCE(authorised, 0) THEN
                RAISE EXCEPTION
                    'action amount %c exceeds approved amount %c',
                    NEW.amount_cents, COALESCE(authorised, 0)
                    USING ERRCODE = 'restrict_violation';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_actions_approval_integrity
        BEFORE INSERT OR UPDATE ON actions
        FOR EACH ROW EXECUTE FUNCTION actions_approval_integrity();
    """)

    # The original constraint is now subsumed by ck_money_requires_approving_decision.
    op.drop_constraint("ck_money_action_requires_approval", "actions", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_money_action_requires_approval",
        "actions",
        "tool_class <> 'MONEY' OR approval_id IS NOT NULL",
    )
    op.execute("DROP TRIGGER IF EXISTS trg_actions_approval_integrity ON actions")
    op.execute("DROP FUNCTION IF EXISTS actions_approval_integrity()")
    op.execute("DROP INDEX IF EXISTS uq_actions_one_approval_each")
    op.drop_constraint("ck_approval_columns_consistent", "actions", type_="check")
    op.drop_constraint("ck_approval_matches_run", "actions", type_="check")
    op.drop_constraint("ck_money_requires_approving_decision", "actions", type_="check")
    op.drop_constraint("fk_actions_approval_composite", "actions", type_="foreignkey")
    op.drop_column("actions", "approval_decision")
    op.drop_column("actions", "approval_run_id")
    op.drop_constraint("uq_approvals_id_run_decision", "approvals", type_="unique")
    op.drop_column("approvals", "approved_amount_cents")
    op.drop_column("agent_runs", "requested_by")
