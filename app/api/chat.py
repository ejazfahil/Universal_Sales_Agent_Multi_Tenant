"""Customer chat endpoint.

One turn: disclose, run the agent, gate the result, record the evidence.

The disclosure is emitted before anything else (Art. 50(5): "at the latest at
the time of the first interaction"), and the gate decides whether the draft goes
out or waits for a human. Nothing here decides policy — it orchestrates.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agent.gate import (
    AUTONOMOUS_THRESHOLD,
    ESCALATION_FLOOR,
    Decision,
    GatePolicy,
)
from app.agent.llm import ScriptedClient
from app.agent.runner import AgentRunner
from app.agent.tools import FixtureBackend, build_catalogue
from app.auth.tenant import TenantContext, require
from app.compliance.disclosure import disclosure_for
from app.privacy.detectors import Roster

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    customer_ref: str = Field(min_length=1, max_length=128)
    locale: str = "en"
    customer_name: str | None = None
    customer_email: str | None = None
    order_refs: list[str] = Field(default_factory=list)


class ReasoningStep(BaseModel):
    kind: str
    tool: str | None = None
    text: str
    result: str | None = None
    confidence: float | None = None


class ChatOut(BaseModel):
    run_id: uuid.UUID
    disclosure: str
    decision: str
    reason: str
    draft: str
    delivered: bool
    confidence: float
    weakest_signal: str
    confidence_components: dict[str, float]
    trace: list[ReasoningStep]
    cost_cents: int
    latency_ms: int


def load_policy(tenant_id: uuid.UUID) -> GatePolicy:
    """Per-tenant gate policy.

    M0 returns the conservative default for every tenant: money is always
    gated. M1 reads the tenants row. Deliberately a function from the start
    so no call site assumes a global policy.
    """
    _ = tenant_id
    return GatePolicy()


def _runner() -> AgentRunner:
    """M0 wiring. Swapping ScriptedClient for AnthropicClient is a one-line
    change once a key is configured; nothing else moves."""
    return AgentRunner(llm=ScriptedClient(), catalogue=build_catalogue(FixtureBackend()))


@router.post("", response_model=ChatOut)
def chat(
    body: ChatIn,
    ctx: Annotated[TenantContext, Depends(require("read"))],
) -> ChatOut:
    roster = Roster(
        names=[body.customer_name] if body.customer_name else [],
        emails=[body.customer_email] if body.customer_email else [],
        order_refs=list(body.order_refs),
    )

    result = _runner().run(
        tenant_id=str(ctx.tenant_id),
        customer_message=body.message,
        roster=roster,
    )

    components: dict[str, Any] = result.confidence.as_dict()
    return ChatOut(
        run_id=result.run_id,
        # Art. 50(5): first thing the customer receives, in their language.
        disclosure=disclosure_for(body.locale),
        decision=str(result.gate.decision),
        reason=result.gate.reason,
        draft=result.draft,
        delivered=result.gate.decision is Decision.AUTONOMOUS,
        confidence=components["confidence"],
        weakest_signal=result.confidence.weakest,
        confidence_components=components,
        trace=[ReasoningStep(**step) for step in result.trace],
        cost_cents=result.cost_cents,
        latency_ms=result.latency_ms,
    )


class PolicyOut(BaseModel):
    """What this tenant's agent is permitted to do, in plain terms.

    Exposed as an endpoint because "what is the AI allowed to do here" is a
    question an operator, an auditor and a procurement reviewer all ask, and
    the honest answer should not require reading source code.
    """

    tenant_id: uuid.UUID
    money_hard_cap_cents: int
    autonomous_reads: bool
    money_always_gated: bool
    autonomous_threshold: float
    escalation_floor: float
    emotion_inference: bool
    summary: str


@router.get("/policy", response_model=PolicyOut)
def policy(ctx: Annotated[TenantContext, Depends(require("read"))]) -> PolicyOut:
    p = load_policy(ctx.tenant_id)
    return PolicyOut(
        tenant_id=ctx.tenant_id,
        money_hard_cap_cents=p.money_hard_cap_cents,
        autonomous_reads=p.allow_autonomous_reads,
        money_always_gated=p.money_hard_cap_cents == 0,
        autonomous_threshold=AUTONOMOUS_THRESHOLD,
        escalation_floor=ESCALATION_FLOOR,
        emotion_inference=False,  # invariant I6, never enabled
        summary=(
            "Read-only tools may run unattended above "
            f"{AUTONOMOUS_THRESHOLD:.0%} confidence. Anything moving money "
            "requires human approval. No emotional state is inferred."
        ),
    )
