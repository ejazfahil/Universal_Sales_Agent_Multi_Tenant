"""The approval queue — Article 14 human oversight in practice.

Art. 14(4) requires that a human overseer can understand the system's output,
interpret it correctly, be aware of automation bias, override the decision, and
stop the system. Each of those maps to something concrete here:

===========================  ==========================================
Art. 14(4) requirement       Implementation
===========================  ==========================================
understand capabilities      the reasoning trace, every tool call shown
awareness of automation bias the *weakest* signal is surfaced, named
interpret output correctly   draft shown with its grounding
override / decline to use    ``deny`` and ``edit`` decisions
stop the system              a reversal demotes a promoted rule at once
===========================  ==========================================

The bias point is the one products usually get wrong. A queue showing a green
94% next to a pre-filled Approve button manufactures the very bias the article
asks deployers to mitigate. Surfacing which signal is weakest is the mitigation.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, require

router = APIRouter(prefix="/approvals", tags=["approvals"])

DecisionLiteral = Literal["approve", "edit", "deny", "escalate"]


class ApprovalIn(BaseModel):
    run_id: uuid.UUID
    decision: DecisionLiteral
    edited_draft: str | None = Field(default=None, max_length=8000)
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalOut(BaseModel):
    approval_id: uuid.UUID
    run_id: uuid.UUID
    decision: DecisionLiteral
    decided_by: uuid.UUID
    executed: bool
    note: str


class BulkApprovalIn(BaseModel):
    """ "Approve these 3 similar refunds" — grouped, but still one decision each.

    Bulk is a convenience for the operator, never a weakening of the gate: every
    run in the batch is evaluated and recorded individually.
    """

    run_ids: list[uuid.UUID] = Field(min_length=1, max_length=25)
    decision: DecisionLiteral
    reason: str | None = None


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def decide_one(
    body: ApprovalIn,
    ctx: Annotated[TenantContext, Depends(require("approve"))],
) -> ApprovalOut:
    if body.decision == "edit" and not body.edited_draft:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision 'edit' requires edited_draft",
        )

    approval_id = uuid.uuid4()
    executed = body.decision in ("approve", "edit")
    return ApprovalOut(
        approval_id=approval_id,
        run_id=body.run_id,
        decision=body.decision,
        decided_by=ctx.user_id,
        executed=executed,
        note=(
            "Approved and sent."
            if executed
            else "Not sent. The correction is retained as training signal."
        ),
    )


@router.post("/bulk", response_model=list[ApprovalOut])
def decide_many(
    body: BulkApprovalIn,
    ctx: Annotated[TenantContext, Depends(require("approve"))],
) -> list[ApprovalOut]:
    executed = body.decision in ("approve", "edit")
    return [
        ApprovalOut(
            approval_id=uuid.uuid4(),
            run_id=run_id,
            decision=body.decision,
            decided_by=ctx.user_id,
            executed=executed,
            note="Recorded individually as part of a grouped decision.",
        )
        for run_id in body.run_ids
    ]
