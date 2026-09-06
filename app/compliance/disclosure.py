"""Article 50 transparency — telling people they are talking to a machine.

Art. 50(1) requires that a person interacting with an AI system is informed of
that fact. Art. 50(5) adds *when* and *how*: clearly and distinguishably, at the
latest at the first interaction, meeting accessibility requirements.

Two consequences the implementation has to respect:

* **Timing is testable.** "At the latest at the first interaction" means the
  disclosure is the first thing sent, not a footer on the third reply.
* **Language matters.** A German customer informed in English has not been
  informed. Translations live here rather than in a template so the set is
  reviewable in one place.

Art. 50(1) has a carve-out where the AI nature is obvious to a reasonably
well-informed person. We do not rely on it — it is a defence, not a design.
"""

from __future__ import annotations

from typing import Final

#: Official EU languages we currently support, plus English.
DISCLOSURES: Final[dict[str, str]] = {
    "en": (
        "You're chatting with an AI assistant. A human colleague reviews anything "
        "sensitive and can take over at any time."
    ),
    "de": (
        "Sie chatten mit einem KI-Assistenten. Ein menschlicher Kollege prüft alle "
        "sensiblen Vorgänge und kann jederzeit übernehmen."
    ),
    "fr": (
        "Vous discutez avec un assistant IA. Un collègue humain vérifie tout élément "
        "sensible et peut prendre le relais à tout moment."
    ),
    "es": (
        "Está hablando con un asistente de IA. Un compañero humano revisa cualquier asunto "
        "delicado y puede intervenir en cualquier momento."
    ),
    "it": (
        "Sta parlando con un assistente IA. Un collega umano verifica ogni questione "
        "delicata e può intervenire in qualsiasi momento."
    ),
    "nl": (
        "U chat met een AI-assistent. Een menselijke collega beoordeelt alles wat "
        "gevoelig ligt en kan het altijd overnemen."
    ),
    "pt": (
        "Está a falar com um assistente de IA. Um colega humano revê qualquer assunto "
        "sensível e pode assumir a qualquer momento."
    ),
    "pl": (
        "Rozmawiasz z asystentem AI. Współpracownik weryfikuje wszystkie wrażliwe "
        "sprawy i może przejąć rozmowę w każdej chwili."
    ),
    "sv": (
        "Du chattar med en AI-assistent. En mänsklig kollega granskar allt "
        "känsligt och kan ta över när som helst."
    ),
    "da": (
        "Du chatter med en AI-assistent. En menneskelig kollega gennemgår alt "
        "følsomt og kan overtage når som helst."
    ),
}

DEFAULT_LOCALE: Final[str] = "en"


def disclosure_for(locale: str | None) -> str:
    """Return the disclosure in the customer's language, falling back to English.

    Falls back on the base language too, so 'de-AT' gets the German text rather
    than English.
    """
    if not locale:
        return DISCLOSURES[DEFAULT_LOCALE]
    key = locale.lower().replace("_", "-")
    if key in DISCLOSURES:
        return DISCLOSURES[key]
    base = key.split("-", 1)[0]
    return DISCLOSURES.get(base, DISCLOSURES[DEFAULT_LOCALE])


def supported_locales() -> list[str]:
    return sorted(DISCLOSURES)
