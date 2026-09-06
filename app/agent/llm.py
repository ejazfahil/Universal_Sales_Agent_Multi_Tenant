"""LLM boundary.

An interface, not a direct SDK call, for three reasons that all matter here:
the whole pipeline stays testable without spending money; the EEA no-transfer
mode needs a second implementation; and the pseudonymisation gateway has to sit
*at* this boundary, where the outbound bytes actually are.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import get_settings


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"

    @property
    def refused(self) -> bool:
        """Safety classifiers return HTTP 200 with stop_reason 'refusal'.

        Reading ``content`` without checking this yields an empty answer that
        looks like a successful turn.
        """
        return self.stop_reason == "refusal"


class LLMClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...


# Anthropic list prices, cents per million tokens. Used for the cost ledger.
PRICING_CENTS_PER_MTOK: dict[str, tuple[int, int]] = {
    "claude-opus-5": (500, 2500),
    "claude-sonnet-5": (200, 1000),
    "claude-haiku-4-5": (100, 500),
}


def cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """Cost of one call, in cents. From real usage — never estimated from
    string length, which is how a cost-per-resolution figure becomes fiction."""
    inp, out = PRICING_CENTS_PER_MTOK.get(model, (0, 0))
    return round((input_tokens * inp + output_tokens * out) / 1_000_000)


class AnthropicClient:
    """Real client. Claude Opus 5 with adaptive thinking and server-side
    fallbacks, per CLAUDE.md."""

    def __init__(self, model: str | None = None) -> None:
        from anthropic import Anthropic

        self._client = Anthropic()
        self._model = model or get_settings().model_main

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        # The adapter speaks plain dicts on purpose so the rest of the app never
        # imports SDK types. The SDK wants its own TypedDicts here; this is the
        # single boundary where that mismatch is absorbed.
        response = self._client.beta.messages.create(  # type: ignore[call-overload]
            model=self._model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=messages,
            tools=tools or [],
        )
        # Check stop_reason before touching content: refusal is a 200.
        if response.stop_reason == "refusal":
            return LLMResponse(text="", stop_reason="refusal")

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                # Parse, never string-match: escaping varies by model.
                raw = block.input
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
                tool_calls.append({"id": block.id, "name": block.name, "input": args})

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=str(response.stop_reason),
        )


@dataclass
class ScriptedClient:
    """Deterministic client for tests and offline demos.

    Replays a queue of responses. Records every payload it was handed, so tests
    can assert on exactly what would have crossed the EEA boundary.
    """

    responses: list[LLMResponse] = field(default_factory=list)
    seen_payloads: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.seen_payloads.append({"system": system, "messages": messages, "tools": tools or []})
        if not self.responses:
            return LLMResponse(text="(no scripted response)", input_tokens=10, output_tokens=5)
        return self.responses.pop(0)
