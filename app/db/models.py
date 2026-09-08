"""Multi-tenant data model.

Every business table carries ``tenant_id`` and is covered by a row-level
security policy (see migration 0002). Two invariants are enforced here in the
schema rather than in application code, because a constraint the database
refuses to violate is worth more than a code path someone can forget:

* **I1** — ``actions`` carries a CHECK: a MONEY-class action cannot exist
  without an ``approval_id``. No refund can be recorded without an approval row,
  regardless of what any agent decides.
* **I6** — there is deliberately no ``sentiment`` column anywhere. Conversation
  routing uses ``urgency``, computed from SLA, order value, repeat contacts and
  keywords. Inferring emotional state would make this a high-risk AI system
  under the EU AI Act (Art. 50(3) and Annex III); see
  ``docs/reference/eu-ai-act-obligations.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# --- controlled vocabularies -------------------------------------------------
TOOL_CLASSES = ("READ", "WRITE", "MONEY", "CONTROL")
APPROVAL_DECISIONS = ("approve", "edit", "deny", "escalate")
MESSAGE_ROLES = ("customer", "agent", "ai", "system")
CHANNELS = ("chat", "email", "whatsapp", "instagram", "sms", "phone")
CONVERSATION_STATUSES = ("awaiting", "escalated", "auto", "resolved")
URGENCIES = ("low", "normal", "high", "urgent")  # NOT sentiment — invariant I6
USER_ROLES = ("owner", "agent", "viewer")
RUN_STATUSES = ("running", "drafted", "gated", "executed", "failed")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _tenant_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)


def _created() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), nullable=False)


def _in(column: str, allowed: tuple[str, ...]) -> CheckConstraint:
    """CHECK constraint restricting a column to a controlled vocabulary."""
    values = ", ".join(f"'{v}'" for v in allowed)
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_{column}_valid")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(nullable=False)
    # Region this tenant's data must stay in. Invariant I5.
    data_region: Mapped[str] = mapped_column(nullable=False, default="eu-central-1")
    # Money ceiling above which an action always requires approval, in cents.
    money_hard_cap_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    email: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(nullable=False, default="agent")
    created_at: Mapped[datetime] = _created()

    __table_args__ = (_in("role", USER_ROLES), Index("ix_users_tenant_email", "tenant_id", "email"))


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    external_id: Mapped[str | None] = mapped_column(nullable=True)
    email: Mapped[str | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(nullable=True)
    locale: Mapped[str] = mapped_column(nullable=False, default="en")
    tier: Mapped[str | None] = mapped_column(nullable=True)
    ltv_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orders_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created()


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    external_ref: Mapped[str] = mapped_column(nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(nullable=False, default="EUR")
    status: Mapped[str] = mapped_column(nullable=False)
    placed_at: Mapped[datetime] = _created()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(nullable=False, default="chat")
    subject: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(nullable=False, default="awaiting")
    intent: Mapped[str | None] = mapped_column(nullable=True)
    # Deterministic, not inferred. See module docstring, invariant I6.
    urgency: Mapped[str] = mapped_column(nullable=False, default="normal")
    locale: Mapped[str] = mapped_column(nullable=False, default="en")
    # Article 50: proof the AI disclosure was delivered, and when.
    disclosed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        _in("channel", CHANNELS),
        _in("status", CONVERSATION_STATUSES),
        _in("urgency", URGENCIES),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(nullable=False)
    author: Mapped[str | None] = mapped_column(nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (_in("role", MESSAGE_ROLES),)


class AgentRun(Base):
    """One agent turn: the reasoning trace, the draft, and what it cost."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="running")
    # Who asked for this run. Needed for separation of duties: the approver of a
    # money action must not be the person who requested it.
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Confidence is min(retrieval, grounding, policy_match, 1 - novelty).
    # Components are stored, not just the composite: showing only a single
    # reassuring number is what manufactures automation bias (AI Act Art. 14(4)).
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    retrieval_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    grounding_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    policy_match_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    trace: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    draft: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Real usage from response.usage — never estimated from string length.
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (_in("status", RUN_STATUSES),)


class Approval(Base):
    """A human decision on a drafted run. The Article 14 oversight record."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The ceiling the human actually authorised. An action may not exceed it.
    approved_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decided_at: Mapped[datetime] = _created()

    __table_args__ = (
        _in("decision", APPROVAL_DECISIONS),
        # Target of the composite FK from actions: carries the run and the
        # decision so a CHECK on actions can constrain both.
        UniqueConstraint("id", "agent_run_id", "decision", name="uq_approvals_id_run_decision"),
    )


class Action(Base):
    """A tool invocation the agent performed or proposed.

    The CHECK constraint below is invariant I1 in its strongest form: a
    MONEY-class action row cannot exist without an approval. This is not
    advisory — Postgres rejects the INSERT.
    """

    __tablename__ = "actions"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: These three travel together as a composite FK to
    #: approvals(id, agent_run_id, decision), so the schema itself knows the
    #: approval belongs to this run and that its decision authorises the action.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    approval_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    approval_decision: Mapped[str | None] = mapped_column(nullable=True)
    tool: Mapped[str] = mapped_column(nullable=False)
    tool_class: Mapped[str] = mapped_column(nullable=False)
    args: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reversible: Mapped[bool] = mapped_column(nullable=False, default=True)
    executed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        _in("tool_class", TOOL_CLASSES),
        ForeignKeyConstraint(
            ["approval_id", "approval_run_id", "approval_decision"],
            ["approvals.id", "approvals.agent_run_id", "approvals.decision"],
            name="fk_actions_approval_composite",
            ondelete="RESTRICT",
        ),
        # Invariant I1: a MONEY action needs an approval whose decision
        # authorises it. Migration 0005 adds the cross-table rules a CHECK
        # cannot express — separation of duties and amount coverage.
        CheckConstraint(
            "tool_class <> 'MONEY' OR approval_decision IN ('approve', 'edit')",
            name="ck_money_requires_approving_decision",
        ),
        CheckConstraint(
            "approval_id IS NULL OR approval_run_id = agent_run_id",
            name="ck_approval_matches_run",
        ),
    )


class AuditLog(Base):
    """Immutable record of one decision. Article 12 record-keeping.

    Made genuinely append-only by migration 0003 (ticket M0-3): UPDATE and
    DELETE are revoked and a trigger raises. Until then this is a comment, and
    a comment is not a control.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    trace_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    actor: Mapped[str] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(nullable=False)
    decided_by: Mapped[str] = mapped_column(nullable=False)  # "llm" | "code" | "human"
    output: Mapped[str] = mapped_column(Text, nullable=False)
    human_approved: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        _in("decided_by", ("llm", "code", "human")),
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
    )


#: Tables carrying tenant data. Migration 0002 applies an RLS policy to each.
TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "users",
    "customers",
    "orders",
    "conversations",
    "messages",
    "agent_runs",
    "approvals",
    "actions",
    "audit_logs",
)
