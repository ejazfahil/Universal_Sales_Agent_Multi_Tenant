"""Article 12 record-keeping — writing the evidence.

Every decision the system takes gets a row: who or what decided, on what basis,
and whether a human approved. The table is append-only at the database level
(migration 0004), so this module can only ever add.

``decided_by`` is the field that matters in an audit. It distinguishes an answer
the model produced from a decision deterministic code took, which is the
difference between "the AI did something" and "the system applied a policy".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

DecidedBy = Literal["llm", "code", "human"]


@dataclass(frozen=True)
class AuditEntry:
    tenant_id: uuid.UUID
    trace_id: uuid.UUID
    actor: str
    action: str
    decided_by: DecidedBy
    output: str
    human_approved: bool | None = None


def record(session: Session, entry: AuditEntry) -> None:
    """Append one audit row. There is no update path, by design."""
    session.execute(
        sa.text(
            "INSERT INTO audit_logs "
            "(id, tenant_id, trace_id, actor, action, decided_by, output, human_approved) "
            "VALUES (:id, :tenant, :trace, :actor, :action, :decided_by, :output, :approved)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant": entry.tenant_id,
            "trace": entry.trace_id,
            "actor": entry.actor,
            "action": entry.action,
            "decided_by": entry.decided_by,
            "output": entry.output[:4000],
            "approved": entry.human_approved,
        },
    )
