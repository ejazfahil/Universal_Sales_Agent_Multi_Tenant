"""Initial multi-tenant schema.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tenants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("data_region", sa.String(), nullable=False, server_default="eu-central-1"),
        sa.Column("money_hard_cap_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="agent"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('owner', 'agent', 'viewer')", name="ck_role_valid"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"])

    op.create_table(
        "customers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("locale", sa.String(), nullable=False, server_default="en"),
        sa.Column("tier", sa.String(), nullable=True),
        sa.Column("ltv_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])

    op.create_table(
        "orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "customer_id", UUID, sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_ref", sa.String(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="EUR"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("placed_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"])

    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "customer_id", UUID, sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("channel", sa.String(), nullable=False, server_default="chat"),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="awaiting"),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("urgency", sa.String(), nullable=False, server_default="normal"),
        sa.Column("locale", sa.String(), nullable=False, server_default="en"),
        sa.Column("disclosed_at", TS, nullable=True),
        sa.Column("sla_due_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "channel IN ('chat', 'email', 'whatsapp', 'instagram', 'sms', 'phone')",
            name="ck_channel_valid",
        ),
        sa.CheckConstraint(
            "status IN ('awaiting', 'escalated', 'auto', 'resolved')", name="ck_status_valid"
        ),
        # Invariant I6: urgency is deterministic. There is no sentiment column.
        sa.CheckConstraint(
            "urgency IN ('low', 'normal', 'high', 'urgent')", name="ck_urgency_valid"
        ),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])

    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "conversation_id",
            UUID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('customer', 'agent', 'ai', 'system')", name="ck_role_valid"),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "conversation_id",
            UUID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("retrieval_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("grounding_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("policy_match_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("novelty_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("trace", JSONB, nullable=False, server_default="[]"),
        sa.Column("draft", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('running', 'drafted', 'gated', 'executed', 'failed')",
            name="ck_status_valid",
        ),
    )
    op.create_index("ix_agent_runs_tenant_id", "agent_runs", ["tenant_id"])
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])

    op.create_table(
        "approvals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "agent_run_id", UUID, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column(
            "decided_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("edited_draft", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision IN ('approve', 'edit', 'deny', 'escalate')", name="ck_decision_valid"
        ),
    )
    op.create_index("ix_approvals_tenant_id", "approvals", ["tenant_id"])
    op.create_index("ix_approvals_agent_run_id", "approvals", ["agent_run_id"])

    op.create_table(
        "actions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "agent_run_id", UUID, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "approval_id", UUID, sa.ForeignKey("approvals.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("tool_class", sa.String(), nullable=False),
        sa.Column("args", JSONB, nullable=False, server_default="{}"),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reversible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("executed_at", TS, nullable=True),
        sa.Column("reversed_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "tool_class IN ('READ', 'WRITE', 'MONEY', 'CONTROL')", name="ck_tool_class_valid"
        ),
        # Invariant I1, enforced by the database: a MONEY action cannot exist
        # without an approval. Not advisory — Postgres rejects the INSERT.
        sa.CheckConstraint(
            "tool_class <> 'MONEY' OR approval_id IS NOT NULL",
            name="ck_money_action_requires_approval",
        ),
    )
    op.create_index("ix_actions_tenant_id", "actions", ["tenant_id"])
    op.create_index("ix_actions_agent_run_id", "actions", ["agent_run_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("trace_id", UUID, nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("human_approved", sa.Boolean(), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("decided_by IN ('llm', 'code', 'human')", name="ck_decided_by_valid"),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_trace_id", "audit_logs", ["trace_id"])
    op.create_index("ix_audit_logs_tenant_created", "audit_logs", ["tenant_id", "created_at"])


def downgrade() -> None:
    for table in (
        "audit_logs",
        "actions",
        "approvals",
        "agent_runs",
        "messages",
        "conversations",
        "orders",
        "customers",
        "users",
        "tenants",
    ):
        op.drop_table(table)
