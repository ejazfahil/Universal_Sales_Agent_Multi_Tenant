"""M0-5 acceptance: invariant I5 — no raw PII crosses the EEA boundary.

The decisive assertion is on the **serialized request body**. Checking a
pre-serialisation object would prove nothing: PII hides in nested tool
arguments, in a system prompt assembled elsewhere, in a retrieved document. The
only meaningful question is whether the bytes leaving the process are clean.
"""

from __future__ import annotations

import json

import pytest

from app.privacy.detectors import Roster, detect
from app.privacy.gateway import PIILeakError, build
from app.privacy.vault import TOKEN_RE, mint_token

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"


def _roster() -> Roster:
    return Roster(
        names=["Maya Chen", "Noah Banerjee"],
        emails=["maya.chen@example.test"],
        order_refs=["#4821"],
        addresses=["12 Rue de Rivoli"],
        phones=["+33 6 12 34 56 78"],
    )


# 50 messages spanning EU languages, channels and PII shapes.
GOLDEN: list[str] = [
    "Hi! I'm Maya Chen and my order #4821 arrived cracked. Refund to maya.chen@example.test?",
    "Bonjour, je suis Maya Chen, commande #4821, adresse 12 Rue de Rivoli.",
    "Hallo, mein Name ist Noah Banerjee. Bestellung #4821 fehlt.",
    "Contact me on +33 6 12 34 56 78 please.",
    "My IBAN is FR76 3000 6000 0112 3456 7890 189 for the refund.",
    "Card ending 4242 4242 4242 4242 was charged twice.",
    "Ship to 12 Rue de Rivoli, 75001 Paris.",
    "maya.chen@example.test is my email, order #4821.",
    "Noah Banerjee here — where is #4821?",
    "Please call 020 7946 0958 tomorrow.",
    *[f"Order #{4800 + i} for Maya Chen, email maya.chen@example.test" for i in range(20)],
    *[f"Ich heiße Noah Banerjee, Bestellnummer #{4900 + i}." for i in range(20)],
]


def test_golden_set_has_expected_size() -> None:
    assert len(GOLDEN) == 50


@pytest.mark.parametrize("message", GOLDEN)
def test_no_raw_pii_in_serialized_payload(message: str) -> None:
    """★ The acceptance criterion, on every message in the golden set."""
    p = build(TENANT, _roster())
    payload = {
        "model": "claude-opus-5",
        "system": "You are a support agent.",
        "messages": [{"role": "user", "content": [{"type": "text", "text": message}]}],
        "metadata": {"note": message},  # nested, to prove recursion
    }
    tokenised = p.tokenise(payload)
    p.assert_clean(tokenised)  # raises if anything leaked

    body = json.dumps(tokenised, ensure_ascii=False)
    for value in ("Maya Chen", "Noah Banerjee", "maya.chen@example.test", "12 Rue de Rivoli"):
        assert value not in body, f"{value!r} survived into the outbound body"


def test_assert_clean_actually_catches_a_leak() -> None:
    """A guard that has never fired is not known to work."""
    p = build(TENANT, _roster())
    with pytest.raises(PIILeakError, match="Invariant I5"):
        p.assert_clean({"messages": [{"text": "Maya Chen wants a refund"}]})


def test_round_trip_is_lossless() -> None:
    p = build(TENANT, _roster())
    original = "Maya Chen (maya.chen@example.test) asks about #4821."
    tokenised = p.tokenise_text(original)
    assert TOKEN_RE.search(tokenised), "nothing was tokenised"
    assert p.detokenise(tokenised) == original


def test_same_value_gets_a_stable_token() -> None:
    """The model must be able to reason about one customer as one entity."""
    p = build(TENANT, _roster())
    out = p.tokenise_text("Maya Chen ordered. Later Maya Chen complained.")
    tokens = TOKEN_RE.findall(out)
    assert len(tokens) == 2
    assert tokens[0] == tokens[1]


def test_tokens_are_not_portable_between_tenants() -> None:
    """Tenant-salted: a token from A is meaningless in B."""
    assert mint_token(TENANT, "CUSTOMER", "Maya Chen") != mint_token(
        OTHER_TENANT, "CUSTOMER", "Maya Chen"
    )


def test_name_in_free_text_is_caught_via_roster() -> None:
    """The roster turns the hardest detection problem into exact matching."""
    p = build(TENANT, _roster())
    out = p.tokenise_text("the parcel for maya chen never arrived")
    assert "maya chen" not in out.lower()


def test_detects_email_without_roster() -> None:
    """Patterns catch what the roster does not know about."""
    hits = detect("write to someone.else@other.test", None)
    assert any(h.kind == "EMAIL" for h in hits)


def test_plain_text_is_untouched() -> None:
    p = build(TENANT, _roster())
    text = "Do you ship to Belgium and how long does delivery take?"
    assert p.tokenise_text(text) == text
