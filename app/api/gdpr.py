"""GDPR subject rights: Article 15 (access) and Article 17 (erasure).

The detail most implementations miss is that erasure has to reach the vector
store and the token vault, not only the relational rows a foreign key happens to
cascade from. A subject deleted from ``customers`` but still present as an
embedding is not erased.

Audit rows are the deliberate exception. Article 12 requires retention, and the
two obligations reconcile through pseudonymisation rather than deletion: the
personal data inside an audit row is redacted, the record of the decision
survives. Deleting the evidence to satisfy an erasure request would trade one
compliance failure for another.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.tenant import TenantContext, require

router = APIRouter(prefix="/gdpr", tags=["gdpr"])

#: Stores that must be reached by an erasure, in dependency order.
ERASURE_TARGETS: tuple[str, ...] = (
    "messages",
    "agent_runs",
    "conversations",
    "orders",
    "customers",
    "vector_chunks",
    "token_vault",
)


class ErasureScope(BaseModel):
    """What an erasure covers — published so the guarantee is inspectable."""

    deleted_from: list[str]
    retained: list[str]
    rationale: str


@router.get("/erasure-scope", response_model=ErasureScope)
def erasure_scope(ctx: Annotated[TenantContext, Depends(require("read"))]) -> ErasureScope:
    _ = ctx
    return ErasureScope(
        deleted_from=list(ERASURE_TARGETS),
        retained=["audit_logs"],
        rationale=(
            "Article 17 erasure removes the subject from operational stores, the "
            "vector index and the pseudonymisation vault. Audit records are "
            "retained under Article 12; personal data within them is redacted "
            "rather than deleted, so the record of each decision survives."
        ),
    )
