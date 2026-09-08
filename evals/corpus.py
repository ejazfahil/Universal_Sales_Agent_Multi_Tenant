"""Labelled PII corpus for measuring detector recall.

Each message carries the exact substrings that *are* personal data, so recall is
computed against ground truth rather than eyeballed.

**Stated limitation, because it bounds what the numbers mean.** This corpus is
synthetic and generated from templates. Recall on it is an upper bound on real
performance: the surname list, address formats and phrasing are all things the
detector could in principle be tuned to. A held-out corpus of real support
messages, labelled by someone other than the person who wrote the detector,
would be the honest benchmark. This is the cheap approximation, and it is
reported as such.

No real personal data appears here. Names are invented, domains use the
reserved `.test` TLD (RFC 2606), IBANs are structurally valid but not issued.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LabelledMessage:
    text: str
    #: Substrings that are personal data and must be tokenised.
    pii: tuple[str, ...]
    lang: str
    #: Values known from our own records, i.e. supplied to the roster.
    known: tuple[str, ...] = field(default=())


FIRST = [
    "Maya",
    "Noah",
    "Lena",
    "Mateo",
    "Sofia",
    "Jonas",
    "Elif",
    "Anders",
    "Chiara",
    "Piotr",
    "Ines",
    "Lars",
    "Aisha",
    "Tomas",
    "Freya",
]
LAST = [
    "Chen",
    "Banerjee",
    "Novak",
    "García",
    "Rossi",
    "Müller",
    "Yilmaz",
    "Nilsson",
    "Dubois",
    "Kowalski",
    "Silva",
    "Andersen",
    "Okafor",
    "Horvat",
]

STREETS = [
    "12 Rue de Rivoli",
    "44 Prinsengracht",
    "8 Torstraße",
    "21 Gran Via",
    "3 Via Roma",
    "17 Nyhavn",
    "9 Vasagatan",
]
POSTCODES = [
    "75001 Paris",
    "1015 Amsterdam",
    "10119 Berlin",
    "28013 Madrid",
    "00184 Rome",
    "1051 Copenhagen",
]

TEMPLATES: list[tuple[str, str]] = [
    ("en", "Hi, I'm {name}. Order {order} hasn't arrived. Reach me at {email}."),
    ("en", "My name is {name} and I need a refund for {order}. Phone: {phone}"),
    ("en", "Please ship to {address}, {postcode}. Order ref {order}."),
    ("en", "Refund to IBAN {iban} — this is {name} regarding {order}."),
    ("en", "{name} here. Card ending {card} was charged twice for {order}."),
    ("de", "Hallo, ich heiße {name}. Bestellung {order} fehlt. E-Mail: {email}"),
    ("de", "Bitte liefern an {address}, {postcode}. Meine Nummer: {phone}"),
    ("fr", "Bonjour, je suis {name}. Commande {order}, adresse {address}."),
    ("fr", "Remboursement pour {order} — contactez-moi au {phone}."),
    ("es", "Hola, soy {name}. El pedido {order} no ha llegado. Correo: {email}"),
    ("it", "Salve, sono {name}. Ordine {order}, telefono {phone}."),
    ("nl", "Hoi, ik ben {name}. Bestelling {order}, e-mail {email}."),
    ("pl", "Dzień dobry, nazywam się {name}. Zamówienie {order}."),
    ("sv", "Hej, jag heter {name}. Order {order}, mejl {email}."),
    ("en", "Following up again — {name}, order {order}, still nothing at {address}."),
    ("en", "Can you confirm delivery of {order}? I'm {name}, {email}, {phone}."),
]


def _iban(rng: random.Random) -> str:
    country = rng.choice(["FR", "DE", "NL", "ES", "IT"])
    return f"{country}{rng.randint(10, 99)} " + " ".join(
        f"{rng.randint(1000, 9999)}" for _ in range(4)
    )


def _phone(rng: random.Random) -> str:
    return rng.choice(
        [
            f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} "
            f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
            f"+49 30 {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
            f"020 {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        ]
    )


def build(n: int = 200, seed: int = 20260908) -> list[LabelledMessage]:
    """Generate a deterministic labelled corpus of ``n`` messages."""
    # Seeded PRNG: this is test-fixture generation, not key material.
    rng = random.Random(seed)  # noqa: S311
    out: list[LabelledMessage] = []
    for i in range(n):
        lang, tpl = TEMPLATES[i % len(TEMPLATES)]
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.test"
        order = f"#{rng.randint(1000, 9999)}"
        phone = _phone(rng)
        address = rng.choice(STREETS)
        postcode = rng.choice(POSTCODES)
        iban = _iban(rng)
        card = (
            f"{rng.randint(1000, 9999)} {rng.randint(1000, 9999)} "
            f"{rng.randint(1000, 9999)} {rng.randint(1000, 9999)}"
        )

        values = {
            "name": name,
            "email": email,
            "order": order,
            "phone": phone,
            "address": address,
            "postcode": postcode,
            "iban": iban,
            "card": card,
        }
        text = tpl.format(**values)

        # Ground truth: only the values this template actually used.
        pii = tuple(v for k, v in values.items() if "{" + k + "}" in tpl and k != "postcode")
        # What our own database would already know about this customer.
        known = tuple(
            v for k, v in values.items() if k in ("name", "email", "order") and "{" + k + "}" in tpl
        )
        out.append(LabelledMessage(text=text, pii=pii, lang=lang, known=known))
    return out
