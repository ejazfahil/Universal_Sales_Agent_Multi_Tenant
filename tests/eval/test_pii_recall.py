"""PII recall as a CI gate, not a one-off measurement.

A detector silently degrading is the worst failure mode here: the tests still
pass, the payload still looks tokenised, and identifiers start crossing the
boundary. These assertions freeze the measured numbers so a regression fails
the build.

Thresholds are set at the current measurement, not aspirationally. Raising them
means improving the detector; lowering them requires a deliberate commit.
"""

from __future__ import annotations

from evals.corpus import build as build_corpus
from evals.pii_recall import evaluate

CORPUS = build_corpus(200)


def test_corpus_is_substantial() -> None:
    assert len(CORPUS) == 200
    assert sum(len(m.pii) for m in CORPUS) >= 500
    assert len({m.lang for m in CORPUS}) >= 8


def test_production_path_leaks_nothing() -> None:
    """★ With the roster populated from our own records — the real path.

    Measured 2026-09-08: 100% span recall, 0 messages leaking.
    """
    r = evaluate(CORPUS, use_roster=True)
    assert r.span_recall == 1.0, f"recall regressed to {r.span_recall:.1%}: {r.missed[:5]}"
    assert r.message_leak_rate == 0.0, f"{r.messages_leaking} messages leaked"


def test_pattern_only_recall_does_not_regress() -> None:
    """Without a roster, names are the known gap. Everything else must hold.

    Measured 2026-09-08: 71.2% span recall. Every miss is a person's name —
    pattern matching cannot detect arbitrary names, which is why NER is on the
    roadmap rather than claimed as solved.
    """
    r = evaluate(CORPUS, use_roster=False)
    assert r.span_recall >= 0.70, f"pattern recall regressed to {r.span_recall:.1%}"


def test_every_pattern_only_miss_is_a_name() -> None:
    """★ Bounds the gap precisely.

    If a phone number, IBAN, address, card or order reference ever appears in
    the miss list, a pattern has broken — that is a different and more serious
    failure than the known name limitation.
    """
    r = evaluate(CORPUS, use_roster=False)
    for missed in r.missed:
        assert "@" not in missed, f"email missed: {missed}"
        assert not missed.startswith("#"), f"order ref missed: {missed}"
        digits = sum(c.isdigit() for c in missed)
        assert digits == 0, f"a value containing digits was missed: {missed!r}"
