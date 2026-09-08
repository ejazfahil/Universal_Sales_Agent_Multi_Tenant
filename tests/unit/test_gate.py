"""M0-8 acceptance: the deterministic gate. Table-driven, every branch."""

from __future__ import annotations

import pytest

from app.agent.confidence import Confidence, grounding_score
from app.agent.gate import (
    Decision,
    GateInput,
    GatePolicy,
    PlannedAction,
    PromotedRule,
    decide,
)

CONFIDENT = Confidence(retrieval=0.99, grounding=1.0, policy_match=0.98, novelty=0.01)
MIDDLING = Confidence(retrieval=0.88, grounding=0.90, policy_match=0.90, novelty=0.05)
WEAK = Confidence(retrieval=0.55, grounding=0.60, policy_match=0.70, novelty=0.30)


def test_confidence_is_minimum_not_mean() -> None:
    """★ One alarming signal must not be averaged away by three comfortable ones."""
    c = Confidence(retrieval=0.99, grounding=0.10, policy_match=0.99, novelty=0.0)
    assert c.score == pytest.approx(0.10)
    assert c.weakest == "grounding"


def test_read_only_and_confident_runs_unattended() -> None:
    r = decide(GateInput(confidence=CONFIDENT, actions=[]))
    assert r.decision is Decision.AUTONOMOUS


def test_middling_confidence_asks_a_human() -> None:
    r = decide(GateInput(confidence=MIDDLING))
    assert r.decision is Decision.REQUIRE_APPROVAL
    assert "weakest signal" in r.reason


def test_weak_confidence_escalates_rather_than_rubber_stamping() -> None:
    r = decide(GateInput(confidence=WEAK))
    assert r.decision is Decision.ESCALATE


@pytest.mark.parametrize("amount", [1, 100, 8900, 50_000])
def test_any_money_is_gated_under_default_policy(amount: int) -> None:
    """★ Invariant I1. Under the default cap of zero, money escalates."""
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.refund", "MONEY", amount_cents=amount)],
        )
    )
    assert r.decision is Decision.ESCALATE
    assert not r.may_execute


def test_money_within_cap_still_not_autonomous_without_a_trusted_rule() -> None:
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.refund", "MONEY", amount_cents=500)],
            policy=GatePolicy(money_hard_cap_cents=1000, vip_cap_cents=1000),
        )
    )
    assert r.decision is Decision.REQUIRE_APPROVAL
    assert "always requires a human" in r.reason


def test_irreversible_money_always_gated() -> None:
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.wire", "MONEY", amount_cents=100, reversible=False)],
            policy=GatePolicy(money_hard_cap_cents=100_000, vip_cap_cents=100_000),
        )
    )
    # Escalated rather than routinely approved: an irreversible payment is not
    # something to hand to whoever is on the queue.
    assert r.decision is Decision.ESCALATE
    assert "irreversible" in r.reason


def test_vip_cap_is_enforced() -> None:
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.refund", "MONEY", amount_cents=900)],
            policy=GatePolicy(money_hard_cap_cents=10_000, vip_cap_cents=500),
            customer_is_vip=True,
        )
    )
    assert r.decision is Decision.ESCALATE
    assert "VIP" in r.reason


def test_ungrounded_answer_is_gated() -> None:
    """Invariant I8."""
    r = decide(GateInput(confidence=CONFIDENT, grounding_failed=True))
    assert r.decision is Decision.REQUIRE_APPROVAL
    assert "traceable" in r.reason


def test_novel_intent_is_gated() -> None:
    r = decide(GateInput(confidence=CONFIDENT, novel_intent=True))
    assert r.decision is Decision.REQUIRE_APPROVAL


def test_urgent_is_gated() -> None:
    """Urgency is deterministic, not inferred emotion. Invariant I6."""
    r = decide(GateInput(confidence=CONFIDENT, urgency="urgent"))
    assert r.decision is Decision.REQUIRE_APPROVAL


def test_trusted_rule_runs_unattended() -> None:
    rule = PromotedRule(name="order-status", confidence=0.99, successes=25)
    r = decide(GateInput(confidence=MIDDLING, rule=rule))
    assert r.decision is Decision.AUTONOMOUS


def test_rule_with_recent_reversal_is_demoted_instantly() -> None:
    """★ Art. 14(4) 'stop the system': one reversal revokes trust immediately."""
    rule = PromotedRule(name="order-status", confidence=0.99, successes=99, recent_reversal=True)
    r = decide(GateInput(confidence=MIDDLING, rule=rule))
    assert r.decision is Decision.REQUIRE_APPROVAL


def test_immature_rule_is_not_trusted() -> None:
    rule = PromotedRule(name="order-status", confidence=0.99, successes=3)
    assert not rule.is_trusted


def test_trusted_rule_cannot_unlock_money() -> None:
    """★ The ladder may make the system more cautious, never less."""
    rule = PromotedRule(name="refunds", confidence=1.0, successes=1000)
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.refund", "MONEY", amount_cents=99_999)],
            rule=rule,
        )
    )
    assert r.decision is not Decision.AUTONOMOUS


def test_small_reversible_refund_under_cap_is_still_gated() -> None:
    """★ REGRESSION. This case executed unattended before 2026-09-08.

    A €5 reversible refund, under a non-zero tenant cap, with a promoted rule,
    fell past the money check and hit the trusted-rule branch. The original
    version of test_trusted_rule_cannot_unlock_money missed it because it used
    €999 against the default cap of 0 — it passed for the wrong reason, which is
    precisely the failure mode this repo claims to guard against.
    """
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.refund", "MONEY", amount_cents=500, reversible=True)],
            policy=GatePolicy(money_hard_cap_cents=1000),
            rule=PromotedRule(name="small-refunds", confidence=0.99, successes=50),
        )
    )
    assert r.decision is not Decision.AUTONOMOUS
    assert not r.may_execute


@pytest.mark.parametrize("amount", [1, 99, 500, 999, 1_000, 1_001, 50_000])
@pytest.mark.parametrize("cap", [0, 500, 1_000, 100_000])
@pytest.mark.parametrize("reversible", [True, False])
@pytest.mark.parametrize("trusted", [True, False])
def test_no_money_amount_is_ever_autonomous(
    amount: int, cap: int, reversible: bool, trusted: bool
) -> None:
    """★ The structural claim, swept rather than sampled.

    112 combinations of amount, tenant cap, reversibility and rule trust. If any
    of them returns AUTONOMOUS, invariant I1 is false. Sweeping matters here:
    the original bug lived in a corner a single hand-picked case missed.
    """
    r = decide(
        GateInput(
            confidence=Confidence(1.0, 1.0, 1.0, 0.0),
            actions=[
                PlannedAction(
                    "commerce.refund", "MONEY", amount_cents=amount, reversible=reversible
                )
            ],
            policy=GatePolicy(money_hard_cap_cents=cap, vip_cap_cents=cap),
            rule=PromotedRule(name="r", confidence=1.0, successes=999) if trusted else None,
        )
    )
    assert r.decision is not Decision.AUTONOMOUS, (
        f"money became autonomous: amount={amount} cap={cap} "
        f"reversible={reversible} trusted={trusted}"
    )


def test_control_actions_are_not_treated_as_read_only() -> None:
    """CONTROL mutates state — closing or reassigning a ticket is not a read."""
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("workflow.close_ticket", "CONTROL")],
        )
    )
    assert r.decision is not Decision.AUTONOMOUS


def test_read_only_still_runs_unattended() -> None:
    """The tightening must not gate ordinary read-only work."""
    r = decide(
        GateInput(
            confidence=CONFIDENT,
            actions=[PlannedAction("commerce.lookup_order", "READ")],
        )
    )
    assert r.decision is Decision.AUTONOMOUS


@pytest.mark.parametrize(
    ("claims", "supported", "expected"),
    [(0, 0, 1.0), (2, 2, 1.0), (2, 1, 0.5), (3, 0, 0.0)],
)
def test_grounding_score(claims: int, supported: int, expected: float) -> None:
    assert grounding_score(claims, supported) == pytest.approx(expected)


def test_gate_result_may_execute_only_when_autonomous() -> None:
    assert decide(GateInput(confidence=CONFIDENT)).may_execute is True
    assert decide(GateInput(confidence=WEAK)).may_execute is False
