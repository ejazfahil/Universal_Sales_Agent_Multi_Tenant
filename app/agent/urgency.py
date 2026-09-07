"""Deterministic urgency — the replacement for sentiment analysis.

Invariant I6. Customer-facing emotion recognition became a high-risk AI system
under the EU AI Act on 2026-08-02. This module reaches the same routing decision
from facts that are already in our database, inferring nothing about anyone's
emotional state:

* how little time is left on the response SLA
* how much the order was worth
* how many times this person has already written in
* whether the message names a refund, a complaint, or a deadline

Every input is observable and auditable. Asked "why was this marked urgent?",
the answer is a list of measurements rather than a model's opinion — which is
also what makes it explainable to a regulator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Urgency = Literal["low", "normal", "high", "urgent"]

#: Words that reliably indicate a time-critical or escalated request. Kept
#: deliberately small and literal — this is keyword matching, not sentiment.
ESCALATION_TERMS: tuple[str, ...] = (
    "refund",
    "complaint",
    "complain",
    "cancel",
    "chargeback",
    "lawyer",
    "legal",
    "urgent",
    "asap",
    "immediately",
    "deadline",
    "before friday",
    "still waiting",
    "third time",
    "unacceptable",
)

_TERM_RE = re.compile("|".join(re.escape(t) for t in ESCALATION_TERMS), re.IGNORECASE)


@dataclass(frozen=True)
class UrgencySignals:
    """Observable facts. No inferred state."""

    sla_minutes_remaining: int | None = None
    order_value_cents: int = 0
    prior_contacts: int = 0
    message: str = ""

    @property
    def matched_terms(self) -> list[str]:
        return sorted({m.group(0).lower() for m in _TERM_RE.finditer(self.message)})


@dataclass(frozen=True)
class UrgencyResult:
    level: Urgency
    score: int
    reasons: list[str] = field(default_factory=list)


def assess(signals: UrgencySignals) -> UrgencyResult:
    """Score the request and map it to a level.

    Additive scoring rather than a decision tree: each factor contributes
    independently, so the explanation is a list a human can check line by line.
    """
    score = 0
    reasons: list[str] = []

    sla = signals.sla_minutes_remaining
    if sla is not None:
        if sla <= 0:
            score += 4
            reasons.append("SLA already breached")
        elif sla <= 15:
            score += 3
            reasons.append(f"SLA due in {sla} min")
        elif sla <= 60:
            score += 1
            reasons.append(f"SLA due in {sla} min")

    if signals.order_value_cents >= 20_000:
        score += 2
        reasons.append(f"high order value (€{signals.order_value_cents / 100:.0f})")
    elif signals.order_value_cents >= 5_000:
        score += 1
        reasons.append(f"order value €{signals.order_value_cents / 100:.0f}")

    if signals.prior_contacts >= 3:
        score += 3
        reasons.append(f"{signals.prior_contacts} previous contacts")
    elif signals.prior_contacts >= 1:
        score += 1
        reasons.append(f"{signals.prior_contacts} previous contact(s)")

    terms = signals.matched_terms
    if terms:
        score += min(3, len(terms))
        reasons.append("mentions " + ", ".join(f"'{t}'" for t in terms[:3]))

    if score >= 6:
        level: Urgency = "urgent"
    elif score >= 3:
        level = "high"
    elif score >= 1:
        level = "normal"
    else:
        level = "low"

    return UrgencyResult(level=level, score=score, reasons=reasons)
