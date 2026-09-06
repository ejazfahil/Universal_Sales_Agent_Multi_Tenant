"""Token vault — the EEA-resident mapping between tokens and real values.

The vault never leaves the EEA. Tokens do. That asymmetry is the whole design:
a token is meaningless without this table, so the data that crosses the border
is not personal data in any usable sense.

Tokens are deterministic per (tenant, kind, value) so the same customer is the
same token across a conversation — the model can reason about "the customer"
coherently — but a token from tenant A is meaningless in tenant B because the
tenant id is part of the digest input.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"<([A-Z_]+)_([0-9a-f]{8})>")


def mint_token(tenant_id: uuid.UUID | str, kind: str, value: str) -> str:
    """Deterministic token for a value, scoped to a tenant.

    Salted with the tenant id so tokens are not portable between tenants, and
    truncated to 8 hex chars — enough to avoid collisions at conversation scale
    while staying short enough not to waste context.
    """
    digest = hashlib.sha256(f"{tenant_id}:{kind}:{value.lower()}".encode()).hexdigest()[:8]
    return f"<{kind}_{digest}>"


@dataclass
class TokenVault:
    """In-memory vault for one request.

    M0 keeps the mapping for the life of a request, which is all the round trip
    needs. M1 persists it to the EU database so a token stays stable across
    turns and can be resolved when rendering an audit trail.
    """

    tenant_id: uuid.UUID | str
    _forward: dict[str, str] = field(default_factory=dict)  # real value -> token
    _reverse: dict[str, str] = field(default_factory=dict)  # token -> real value

    def tokenise(self, kind: str, value: str) -> str:
        key = value.lower()
        if key in self._forward:
            return self._forward[key]
        token = mint_token(self.tenant_id, kind, value)
        self._forward[key] = token
        self._reverse[token] = value
        return token

    def resolve(self, token: str) -> str | None:
        return self._reverse.get(token)

    def detokenise(self, text: str) -> str:
        """Replace every known token in ``text`` with its real value."""
        return TOKEN_RE.sub(lambda m: self._reverse.get(m.group(0), m.group(0)), text)

    @property
    def size(self) -> int:
        return len(self._reverse)
