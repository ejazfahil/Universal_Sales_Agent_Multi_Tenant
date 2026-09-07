"""Deterministic urgency — invariant I6's replacement for sentiment analysis.

The property that matters most is :func:`test_tone_alone_does_not_change_the_score`.
If how angrily someone writes moved the number, we would be inferring emotional
state by proxy — which is exactly what makes a system high-risk under the EU AI
Act. Facts move the score; tone does not.
"""

from __future__ import annotations

import pytest

from app.agent.confidence import Confidence
from app.agent.gate import Decision, GateInput, decide
from app.agent.urgency import UrgencySignals, assess


def test_no_signals_is_low() -> None:
    assert assess(UrgencySignals(message="hello")).level == "low"


def test_breached_sla_and_repeat_contact_is_urgent() -> None:
    r = assess(
        UrgencySignals(sla_minutes_remaining=0, prior_contacts=3, message="where is my order")
    )
    assert r.level == "urgent"
    assert any("SLA" in reason for reason in r.reasons)


@pytest.mark.parametrize(("minutes", "at_least"), [(0, 4), (10, 3), (45, 1), (600, 0)])
def test_sla_pressure_scales(minutes: int, at_least: int) -> None:
    assert assess(UrgencySignals(sla_minutes_remaining=minutes)).score >= at_least


def test_high_order_value_raises_the_score() -> None:
    cheap = assess(UrgencySignals(order_value_cents=1_000)).score
    dear = assess(UrgencySignals(order_value_cents=50_000)).score
    assert dear > cheap


def test_repeat_contacts_raise_the_score() -> None:
    once = assess(UrgencySignals(prior_contacts=1)).score
    many = assess(UrgencySignals(prior_contacts=4)).score
    assert many > once


def test_keywords_are_matched_literally() -> None:
    signals = UrgencySignals(message="I want a refund before Friday")
    assert "refund" in signals.matched_terms
    assert "before friday" in signals.matched_terms
    assert assess(signals).score >= 2


def test_tone_alone_does_not_change_the_score() -> None:
    """★ The invariant. Identical facts, opposite tone, identical result."""
    facts = {"sla_minutes_remaining": 30, "order_value_cents": 8_000, "prior_contacts": 1}
    calm = assess(UrgencySignals(**facts, message="Could you check my order please?"))
    furious = assess(UrgencySignals(**facts, message="This is absolutely appalling!!!"))
    assert calm.score == furious.score
    assert calm.level == furious.level


def test_politeness_does_not_lower_urgency() -> None:
    """The mirror case: courtesy must not get a genuinely urgent case deprioritised."""
    facts = {"sla_minutes_remaining": 0, "prior_contacts": 4}
    polite = assess(UrgencySignals(**facts, message="So sorry to bother you again!"))
    blunt = assess(UrgencySignals(**facts, message="Fix this."))
    assert polite.level == blunt.level == "urgent"


def test_reasons_are_human_checkable() -> None:
    """An auditor asking 'why urgent?' gets measurements, not an opinion."""
    r = assess(
        UrgencySignals(
            sla_minutes_remaining=5,
            order_value_cents=30_000,
            prior_contacts=4,
            message="I want a refund",
        )
    )
    assert r.level == "urgent"
    assert len(r.reasons) >= 3
    assert all(isinstance(reason, str) and reason for reason in r.reasons)


def test_urgent_forces_human_review() -> None:
    """Urgency feeds the gate: urgent never runs unattended, however confident."""
    r = assess(UrgencySignals(sla_minutes_remaining=0, prior_contacts=5, message="refund now"))
    assert r.level == "urgent"
    gated = decide(GateInput(confidence=Confidence(0.99, 1.0, 0.99, 0.0), urgency=r.level))
    assert gated.decision is Decision.REQUIRE_APPROVAL
    assert "urgent" in gated.reason
