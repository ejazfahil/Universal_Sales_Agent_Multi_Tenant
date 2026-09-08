"""Measure PII detection recall against the labelled corpus.

Reports two numbers, because they answer different questions:

* **Span recall** — of all labelled PII values, what fraction did the detector
  find? This is the research number.
* **Message leak rate** — in how many messages did *any* labelled value survive
  into the outbound payload? This is the number that matters operationally: one
  missed identifier leaks the customer regardless of how many were caught.

Both are measured twice: with the roster populated from our own records (the
production path, since we usually know the customer) and with it empty (pattern
detection alone, the harder case).

Run:  uv run python -m evals.pii_recall
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.privacy.detectors import Roster
from app.privacy.gateway import build
from evals.corpus import LabelledMessage
from evals.corpus import build as build_corpus


@dataclass
class Result:
    label: str
    spans_total: int
    spans_found: int
    messages_total: int
    messages_leaking: int
    missed: list[str]

    @property
    def span_recall(self) -> float:
        return self.spans_found / self.spans_total if self.spans_total else 1.0

    @property
    def message_leak_rate(self) -> float:
        return self.messages_leaking / self.messages_total if self.messages_total else 0.0


def evaluate(corpus: list[LabelledMessage], *, use_roster: bool) -> Result:
    tenant = "eval-tenant-0000-0000-000000000000"
    spans_total = spans_found = messages_leaking = 0
    missed: list[str] = []

    for msg in corpus:
        roster = (
            Roster(
                names=[v for v in msg.known if " " in v and "@" not in v and not v.startswith("#")],
                emails=[v for v in msg.known if "@" in v],
                order_refs=[v for v in msg.known if v.startswith("#")],
            )
            if use_roster
            else Roster()
        )
        p = build(tenant, roster)
        tokenised = p.tokenise({"messages": [{"content": msg.text}]})
        body = json.dumps(tokenised, ensure_ascii=False)

        leaked_here = False
        for value in msg.pii:
            spans_total += 1
            if value.lower() in body.lower():
                leaked_here = True
                missed.append(value)
            else:
                spans_found += 1
        if leaked_here:
            messages_leaking += 1

    return Result(
        label="with roster" if use_roster else "patterns only",
        spans_total=spans_total,
        spans_found=spans_found,
        messages_total=len(corpus),
        messages_leaking=messages_leaking,
        missed=missed,
    )


def main() -> int:
    corpus = build_corpus(200)
    print(
        f"Corpus: {len(corpus)} messages, "
        f"{sum(len(m.pii) for m in corpus)} labelled PII spans, "
        f"{len({m.lang for m in corpus})} languages\n"
    )

    for use_roster in (True, False):
        r = evaluate(corpus, use_roster=use_roster)
        print(f"--- {r.label} ---")
        print(f"  span recall        {r.span_recall:6.1%}  ({r.spans_found}/{r.spans_total})")
        print(
            f"  message leak rate  {r.message_leak_rate:6.1%}  "
            f"({r.messages_leaking}/{r.messages_total} messages leaked something)"
        )
        if r.missed:
            from collections import Counter

            common = Counter(
                "email"
                if "@" in m
                else "order"
                if m.startswith("#")
                else "phone/iban/card"
                if any(c.isdigit() for c in m) and " " in m
                else "name/address"
                for m in r.missed
            )
            print(f"  missed by kind     {dict(common)}")
            print(f"  examples           {r.missed[:4]}")
        print()

    print("Caveat: the corpus is synthetic and template-generated, so these are")
    print("upper bounds. A held-out corpus of real messages, labelled by someone")
    print("other than the detector's author, is the honest benchmark.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
