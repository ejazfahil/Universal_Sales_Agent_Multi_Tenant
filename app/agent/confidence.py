"""Confidence scoring.

Four independent signals, combined with ``min`` rather than a mean. A mean lets
three comfortable numbers drown one alarming one — which is precisely the case
where a human should look. Taking the minimum gives any single signal a veto.

The components are kept, not just the composite. Showing an operator one
reassuring ``94%`` is how automation bias is manufactured; the EU AI Act asks
deployers to mitigate that (Art. 14(4)), so the UI surfaces the *weakest*
signal and names it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Confidence:
    retrieval: float
    grounding: float
    policy_match: float
    novelty: float

    @property
    def score(self) -> float:
        """The composite. Minimum, never mean."""
        return min(self.retrieval, self.grounding, self.policy_match, 1.0 - self.novelty)

    @property
    def weakest(self) -> str:
        """Which signal is holding the score down. Shown to the operator."""
        return min(
            (
                ("retrieval", self.retrieval),
                ("grounding", self.grounding),
                ("policy_match", self.policy_match),
                ("novelty", 1.0 - self.novelty),
            ),
            key=lambda pair: pair[1],
        )[0]

    def as_dict(self) -> dict[str, float]:
        return {
            "confidence": round(self.score, 3),
            "retrieval_score": round(self.retrieval, 3),
            "grounding_score": round(self.grounding, 3),
            "policy_match_score": round(self.policy_match, 3),
            "novelty_score": round(self.novelty, 3),
        }


def grounding_score(claims: int, supported: int) -> float:
    """Share of factual claims traceable to a tool result. Invariant I8.

    No claims at all scores 1.0: a reply that asserts nothing cannot be
    ungrounded. Asserting things with no tool evidence scores 0.
    """
    if claims <= 0:
        return 1.0
    return max(0.0, min(1.0, supported / claims))
