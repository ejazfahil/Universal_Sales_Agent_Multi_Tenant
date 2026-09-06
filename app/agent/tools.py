"""Tool catalogue and its risk classification.

Every tool declares a class, and the class — not the model's confidence —
decides whether a human must approve it:

===========  ==========================================  ====================
Class        Meaning                                     Default gate
===========  ==========================================  ====================
READ         Retrieves information, changes nothing      Autonomous
WRITE        Mutates state, reversible                   Auto within policy
MONEY        Moves money                                 **Always gated**
CONTROL      Routing and escalation                      Autonomous
===========  ==========================================  ====================

M0 ships READ tools only. The MONEY machinery exists from day one anyway,
because retrofitting a guard after the first refund tool is written is how
guards end up with exceptions.

Adapters are fixture-backed for M0 and sit behind an interface, so swapping in
the Shopify Admin API later touches one class and no call sites.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

ToolClass = Literal["READ", "WRITE", "MONEY", "CONTROL"]


class ToolError(RuntimeError):
    """A tool failed. Never swallowed — a silent tool failure becomes a
    confident answer grounded in nothing."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    tool_class: ToolClass
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    reversible: bool = True

    @property
    def requires_approval_by_default(self) -> bool:
        return self.tool_class == "MONEY"

    def to_anthropic(self) -> dict[str, Any]:
        """Anthropic tool definition. ``strict`` guarantees input validation."""
        return {
            "name": self.name.replace(".", "_"),
            "description": self.description,
            "input_schema": self.input_schema,
            "strict": True,
        }


class CommerceBackend(Protocol):
    """What the agent needs from a commerce platform. Shopify implements this
    in M1; the fixture backend implements it now."""

    def lookup_order(self, order_ref: str) -> dict[str, Any]: ...
    def order_metadata(self, order_ref: str) -> dict[str, Any]: ...
    def track_shipment(self, order_ref: str) -> dict[str, Any]: ...


class FixtureBackend:
    """Deterministic backend for M0 and for tests.

    Not "mock data on the happy path" — it is a real implementation of the
    interface, chosen so the agent path can be exercised end to end without a
    Shopify account. Swapping it out changes one construction site.
    """

    def __init__(self, orders: dict[str, dict[str, Any]] | None = None) -> None:
        self._orders: dict[str, dict[str, Any]] = orders or {
            "#4821": {
                "order_ref": "#4821",
                "items": "Radiance Serum",
                "total_cents": 8900,
                "currency": "EUR",
                "status": "delivered",
                "placed_days_ago": 4,
            }
        }

    def lookup_order(self, order_ref: str) -> dict[str, Any]:
        order = self._orders.get(order_ref)
        if order is None:
            raise ToolError(f"order {order_ref} not found")
        return order

    def order_metadata(self, order_ref: str) -> dict[str, Any]:
        self.lookup_order(order_ref)
        return {"carrier": "DHL", "left_at": "front door", "damage_flagged": False}

    def track_shipment(self, order_ref: str) -> dict[str, Any]:
        self.lookup_order(order_ref)
        return {
            "carrier": "DHL",
            "state": "delivered",
            "delivered_days_ago": 1,
            "tracking_url": "https://carrier.example/track",
        }


_ORDER_REF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "order_ref": {
            "type": "string",
            # No sample identifier here on purpose. The gateway scans tool
            # schemas too, and an example that looks like a real order ref is
            # indistinguishable from a leak.
            "description": (
                "Order reference as supplied by the customer. May arrive as an "
                "opaque token; pass it through unchanged."
            ),
        }
    },
    "required": ["order_ref"],
    "additionalProperties": False,
}


def build_catalogue(backend: CommerceBackend) -> dict[str, ToolSpec]:
    """The M0 tool catalogue: order-status resolution. Read-only by design."""
    specs = [
        ToolSpec(
            name="commerce.lookup_order",
            description="Look up an order by reference. Returns items, total and status.",
            tool_class="READ",
            input_schema=_ORDER_REF_SCHEMA,
            handler=backend.lookup_order,
        ),
        ToolSpec(
            name="commerce.order_metadata",
            description="Carrier and delivery metadata for an order.",
            tool_class="READ",
            input_schema=_ORDER_REF_SCHEMA,
            handler=backend.order_metadata,
        ),
        ToolSpec(
            name="commerce.track_shipment",
            description="Live carrier tracking state for an order.",
            tool_class="READ",
            input_schema=_ORDER_REF_SCHEMA,
            handler=backend.track_shipment,
        ),
    ]
    return {spec.name: spec for spec in specs}
