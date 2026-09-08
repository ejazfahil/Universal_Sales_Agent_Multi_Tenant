"""The decision gate — invariant I1, and the reason this system is auditable.

Runs *after* the model has drafted a reply and planned its actions, and *before*
anything executes. It is ordinary deterministic code: no model call, no prompt,
nothing the agent can influence. That is deliberate. A model asked "should you
be allowed to do this?" is being asked to mark its own homework, and a prompt
that decides permissions is a prompt an attacker can target.

Order matters. Hard blocks are evaluated first and cannot be overridden by any
confidence score or learned rule — the ladder can make the system *more*
cautious, never less.

Maps onto EU AI Act Art. 14(4): the operator can override (deny), decline to
use (escalate), and stop the system (demotion on reversal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.agent.confidence import Confidence
from app.agent.tools import ToolClass

# Confidence at or above which a read-only run may answer unattended.
AUTONOMOUS_THRESHOLD = 0.95
# Below this, nobody should be asked to rubber-stamp it — escalate instead.
ESCALATION_FLOOR = 0.80
# A learned rule must survive this many clean approvals before it is trusted.
RULE_PROMOTION_SUCCESSES = 20


class Decision(StrEnum):
    AUTONOMOUS = "autonomous"
    REQUIRE_APPROVAL = "require_approval"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class PlannedAction:
    tool: str
    tool_class: ToolClass
    amount_cents: int = 0
    reversible: bool = True


@dataclass(frozen=True)
class PromotedRule:
    """A pattern that has earned the right to run unattended."""

    name: str
    confidence: float
    successes: int
    recent_reversal: bool = False

    @property
    def is_trusted(self) -> bool:
        return (
            self.confidence >= AUTONOMOUS_THRESHOLD
            and self.successes >= RULE_PROMOTION_SUCCESSES
            and not self.recent_reversal
        )


@dataclass(frozen=True)
class GatePolicy:
    """Per-tenant limits. Conservative defaults: everything that moves money is
    gated until a tenant deliberately raises the cap."""

    money_hard_cap_cents: int = 0
    vip_cap_cents: int = 0
    allow_autonomous_reads: bool = True


@dataclass(frozen=True)
class GateInput:
    confidence: Confidence
    actions: list[PlannedAction] = field(default_factory=list)
    policy: GatePolicy = field(default_factory=GatePolicy)
    rule: PromotedRule | None = None
    customer_is_vip: bool = False
    urgency: str = "normal"
    grounding_failed: bool = False
    novel_intent: bool = False


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    reason: str

    @property
    def may_execute(self) -> bool:
        return self.decision is Decision.AUTONOMOUS


def _money_total(actions: list[PlannedAction]) -> int:
    return sum(a.amount_cents for a in actions if a.tool_class == "MONEY")


def decide(gi: GateInput) -> GateResult:
    """Return the gate decision. Pure function — trivially testable, and the
    single place a reviewer has to read to know what the agent may do."""

    # --- 1. Money. Structural, not conditional.
    #
    # An earlier version compared the amount against a per-tenant cap and only
    # escalated when it was exceeded. That left a hole: a small, reversible
    # refund under a non-zero cap fell through to the promoted-rule branch below
    # and executed unattended. The invariant held only because the default cap
    # happened to be zero — a guarantee resting on a default is not a guarantee,
    # and the test that was supposed to catch it passed for the wrong reason.
    #
    # There is now no path from a MONEY action to AUTONOMOUS. The cap no longer
    # decides whether a human is involved; it decides *which* human.
    money_actions = [a for a in gi.actions if a.tool_class == "MONEY"]
    if money_actions:
        money = _money_total(gi.actions)
        if money > gi.policy.money_hard_cap_cents:
            return GateResult(
                Decision.ESCALATE,
                f"money {money}c exceeds tenant cap {gi.policy.money_hard_cap_cents}c — "
                f"needs an owner, not a routine approval",
            )
        if gi.customer_is_vip and money > gi.policy.vip_cap_cents:
            return GateResult(
                Decision.ESCALATE,
                f"VIP customer and money {money}c exceeds VIP cap {gi.policy.vip_cap_cents}c",
            )
        irreversible = [a for a in money_actions if not a.reversible]
        if irreversible:
            return GateResult(
                Decision.ESCALATE, f"irreversible money action: {irreversible[0].tool}"
            )
        return GateResult(
            Decision.REQUIRE_APPROVAL, f"money action ({money}c) always requires a human"
        )

    if gi.grounding_failed:
        return GateResult(Decision.REQUIRE_APPROVAL, "claims not traceable to tool results")

    if gi.novel_intent:
        return GateResult(Decision.REQUIRE_APPROVAL, "intent not seen before")

    # Urgency is deterministic (SLA, order value, repeat contacts, keywords) —
    # not inferred emotional state. Invariant I6.
    if gi.urgency == "urgent":
        return GateResult(Decision.REQUIRE_APPROVAL, "urgent: a human should see this")

    # --- 2. A rule that has earned trust may run unattended.
    if gi.rule is not None and gi.rule.is_trusted:
        return GateResult(Decision.AUTONOMOUS, f"promoted rule '{gi.rule.name}'")

    # --- 3. Confidence bands.
    score = gi.confidence.score
    # CONTROL is not read-only: closing or reassigning a ticket mutates state.
    all_read_only = all(a.tool_class == "READ" for a in gi.actions)

    if score >= AUTONOMOUS_THRESHOLD and all_read_only and gi.policy.allow_autonomous_reads:
        return GateResult(Decision.AUTONOMOUS, f"confidence {score:.2f}, read-only")

    if score >= ESCALATION_FLOOR:
        return GateResult(
            Decision.REQUIRE_APPROVAL,
            f"confidence {score:.2f} (weakest signal: {gi.confidence.weakest})",
        )

    return GateResult(
        Decision.ESCALATE,
        f"confidence {score:.2f} below floor (weakest signal: {gi.confidence.weakest})",
    )
