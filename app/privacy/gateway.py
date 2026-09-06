"""The pseudonymisation gateway — invariant I5.

Anthropic's ``inference_geo`` accepts only ``us`` or ``global``; there is no EU
value, so inference on a frontier model cannot be pinned inside the EEA. Rather
than claim otherwise, this gateway makes the claim we *can* support: personal
data never crosses the border, because it is replaced before it does.

    EU app ──▶ [tokenise] ──▶ Claude ──▶ [detokenise] ──▶ EU app
                   │                            ▲
                   └──── vault stays in the EEA ┘

The model sees ``<CUSTOMER_7f3a>``. It reasons about the customer perfectly well
— consistent tokens preserve identity within a conversation — but the value is
meaningless without the vault, which never leaves.

**The verification that matters is on the serialized bytes.** Checking a
pre-serialisation dict proves nothing: a name can hide in a nested field, a
tool argument, or a system prompt built elsewhere. :func:`assert_clean` walks
the JSON that is actually about to be sent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.privacy.detectors import Roster, detect
from app.privacy.vault import TokenVault


class PIILeakError(RuntimeError):
    """Raised when raw PII is found in a payload bound for a non-EEA service.

    This is deliberately fatal. A leak that is logged and swallowed is a leak.
    """


@dataclass
class Pseudonymiser:
    """Bidirectional tokeniser for one request."""

    vault: TokenVault
    roster: Roster

    def tokenise_text(self, text: str) -> str:
        """Replace every detected PII span with a stable token."""
        detections = detect(text, self.roster)
        if not detections:
            return text
        out: list[str] = []
        cursor = 0
        for d in detections:
            out.append(text[cursor : d.start])
            out.append(self.vault.tokenise(d.kind, d.value))
            cursor = d.end
        out.append(text[cursor:])
        return "".join(out)

    def tokenise(self, payload: Any) -> Any:  # noqa: ANN401 — mirrors arbitrary JSON
        """Recursively tokenise every string in a JSON-shaped structure."""
        if isinstance(payload, str):
            return self.tokenise_text(payload)
        if isinstance(payload, dict):
            return {k: self.tokenise(v) for k, v in payload.items()}
        if isinstance(payload, list):
            return [self.tokenise(v) for v in payload]
        return payload

    def detokenise(self, text: str) -> str:
        return self.vault.detokenise(text)

    def assert_clean(self, payload: Any) -> None:  # noqa: ANN401 — mirrors arbitrary JSON
        """Fail if raw PII survives anywhere in the serialized payload.

        Serialises first, on purpose. The question is not "is the object I built
        clean" but "is the request body about to leave the EEA clean" — and the
        second is the only one a regulator would ask.
        """
        body = json.dumps(payload, ensure_ascii=False, default=str)
        leaks: list[str] = []

        for _kind, value in self.roster.entries():
            if re.search(re.escape(value), body, flags=re.IGNORECASE):
                leaks.append(value)

        for d in detect(body, None):
            # Tokens themselves look like nothing else; anything else is a leak.
            leaks.append(d.value)

        if leaks:
            preview = ", ".join(sorted({leak[:40] for leak in leaks})[:5])
            raise PIILeakError(
                f"Invariant I5: {len(leaks)} raw identifier(s) in payload bound for "
                f"non-EEA inference — {preview}"
            )


def build(tenant_id: str, roster: Roster) -> Pseudonymiser:
    return Pseudonymiser(vault=TokenVault(tenant_id=tenant_id), roster=roster)
