"""PII detection.

Deliberately conservative: over-tokenising costs a little readability in the
prompt, under-tokenising sends a European customer's name to a US datacentre.
When the two trade off, over-tokenise.

Detection is pattern-based with a supplied roster of known values. The roster
matters more than the patterns — we almost always know the customer's name,
email and order references from our own database before the model is called, so
the hard part of free-text name detection is mostly sidestepped. Patterns catch
what the roster misses: a second email typed into a message, a phone number, an
address, an IBAN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

#: Ordered: earlier patterns win, so an email is not also matched as a name
#: fragment. IBAN before generic numbers, longer forms before shorter.
PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b")),
    (
        "CARD",
        re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    ),
    (
        # European numbers group irregularly: "+33 6 19 45 73 32" is 1 digit then
        # four pairs, "+49 30 1234 5678" is 2 then two quads, "020 1234 5678" has
        # no country code. The earlier pattern required a 3-4 digit first group
        # and silently missed the French form entirely — 67 leaks in the eval.
        # This accepts a country code plus any run of 2+ digit groups totalling
        # 7-14 digits, which covers the national formats we see.
        "PHONE",
        re.compile(
            r"(?<![\w.])"
            r"(?:\+\d{1,3}[ .\-]?)?"  # optional country code
            r"(?:\(\d{1,4}\)[ .\-]?)?"  # optional area code in parens
            r"\d{1,4}(?:[ .\-]\d{1,4}){1,6}"  # 2+ groups of 2-4 digits
            r"(?![\w.])"
        ),
    ),
    (
        # Street addresses: house number followed by a capitalised street name.
        # Deliberately requires the leading number, because bare capitalised
        # words are far too common to tokenise safely. Covers "12 Rue de
        # Rivoli", "8 Torstraße", "44 Prinsengracht", "21 Gran Via".
        "ADDRESS",
        re.compile(
            r"\b\d{1,4}\s+"
            r"(?:[A-ZÀ-ÖØ-Þ][\w'’\-]*)"  # first word must be capitalised
            r"(?:\s+(?:de|du|des|la|le|van|der|den|di|del)\b)*"  # particles
            r"(?:\s+[A-ZÀ-ÖØ-Þ][\w'’\-]*){0,3}"
        ),
    ),
    ("ORDER", re.compile(r"#\d{3,10}\b")),
    (
        "POSTCODE",
        re.compile(r"\b(?:\d{4,5}\s?[A-Z]{0,2}|[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b"),
    ),
)

#: Phone matching is greedy by design; these would otherwise be swallowed.
_PHONE_FALSE_POSITIVES: Final[re.Pattern[str]] = re.compile(r"^(?:\d{1,2}[ .-]?\d{1,2})$|^\d{1,3}$")

#: A real phone number has at least this many digits. Without the floor, the
#: looser grouping above swallows things like "2 items on 3 May".
_MIN_PHONE_DIGITS: Final[int] = 7

#: Words that follow a number but are never a street. Without this, "2 items on
#: 3 May" tokenises the date as an address — over-tokenising is cheap but not
#: free, since it degrades what the model can reason about.
_NOT_STREET_WORDS: Final[frozenset[str]] = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "days",
        "items",
        "weeks",
        "months",
        "hours",
        "minutes",
        "euros",
        "eur",
        "usd",
        "pieces",
        "units",
        "times",
    }
)


@dataclass(frozen=True)
class Detection:
    kind: str
    value: str
    start: int
    end: int


@dataclass
class Roster:
    """Values we already know are personal, from our own records.

    Supplying these turns the hardest detection problem — is this token a
    person's name? — into an exact-match lookup.
    """

    names: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    order_refs: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)

    def entries(self) -> list[tuple[str, str]]:
        """(kind, value) pairs, longest first so 'Maya Chen' beats 'Maya'."""
        pairs: list[tuple[str, str]] = []
        for kind, values in (
            ("CUSTOMER", self.names),
            ("EMAIL", self.emails),
            ("ORDER", self.order_refs),
            ("ADDRESS", self.addresses),
            ("PHONE", self.phones),
        ):
            pairs.extend((kind, v) for v in values if v and v.strip())
        return sorted(pairs, key=lambda p: len(p[1]), reverse=True)


def detect(text: str, roster: Roster | None = None) -> list[Detection]:
    """Find PII spans in ``text``. Non-overlapping, roster matches take priority."""
    taken: list[tuple[int, int]] = []
    found: list[Detection] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in taken)

    if roster is not None:
        for kind, value in roster.entries():
            for match in re.finditer(re.escape(value), text, flags=re.IGNORECASE):
                if not _overlaps(match.start(), match.end()):
                    found.append(Detection(kind, match.group(), match.start(), match.end()))
                    taken.append((match.start(), match.end()))

    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group().strip()
            if not candidate or _overlaps(match.start(), match.end()):
                continue
            if kind == "ADDRESS":
                first_word = candidate.split()[1] if len(candidate.split()) > 1 else ""
                if first_word.lower().strip(".,") in _NOT_STREET_WORDS:
                    continue
            if kind == "PHONE" and (
                _PHONE_FALSE_POSITIVES.match(candidate)
                or sum(c.isdigit() for c in candidate) < _MIN_PHONE_DIGITS
            ):
                continue
            found.append(Detection(kind, match.group(), match.start(), match.end()))
            taken.append((match.start(), match.end()))

    return sorted(found, key=lambda d: d.start)
