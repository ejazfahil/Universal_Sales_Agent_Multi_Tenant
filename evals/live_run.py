"""Run the corpus through a real model and measure latency, cost and PII egress.

This is the measurement the README's "not measured" section names. It needs
credentials and it spends money, so it is a script you run deliberately rather
than part of the test suite.

    export ANTHROPIC_API_KEY=sk-ant-...
    uv run python -m evals.live_run --n 200

Cost estimate before you run it: roughly two API calls per conversation (one to
plan the tool call, one to answer). At Claude Opus 5 list prices and ~1.5k input
/ ~150 output tokens per call, 200 conversations is on the order of a few euros.
``--n 20`` first is sensible.

What it reports:

* latency p50 / p95 / max, end to end per conversation
* real cost from ``response.usage``, never estimated from string length
* PII egress: every payload the client was handed is scanned for raw
  identifiers, so this is a live check of invariant I5 rather than a unit test
* gate outcomes, so you can see how often the model's work is actually usable
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field

from app.agent.gate import Decision
from app.agent.runner import AgentRunner
from app.agent.tools import FixtureBackend, build_catalogue
from app.privacy.detectors import Roster
from evals.corpus import build as build_corpus


@dataclass
class Outcome:
    latencies_ms: list[float] = field(default_factory=list)
    cost_cents: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    decisions: dict[str, int] = field(default_factory=dict)
    pii_leaks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def pct(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        idx = min(int(len(ordered) * p), len(ordered) - 1)
        return ordered[idx]


def _client(provider: str):  # noqa: ANN202 - returns an LLMClient
    """Resolve a provider. The LLM boundary is a Protocol precisely so this is
    a one-line choice rather than a rewrite."""
    if provider == "anthropic":
        from app.agent.llm import AnthropicClient

        return AnthropicClient()
    raise SystemExit(f"unknown provider: {provider}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20, help="conversations to run")
    ap.add_argument("--provider", default="anthropic")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        print(
            "This script makes real API calls and costs real money; it will "
            "not run without an explicit key.",
            file=sys.stderr,
        )
        return 2

    corpus = build_corpus(args.n)
    runner = AgentRunner(llm=_client(args.provider), catalogue=build_catalogue(FixtureBackend()))
    tenant = "eval-tenant-0000-0000-000000000000"
    out = Outcome()

    print(f"Running {len(corpus)} conversations through {args.provider}…\n")
    for i, msg in enumerate(corpus, 1):
        roster = Roster(
            names=[v for v in msg.known if " " in v and "@" not in v and not v.startswith("#")],
            emails=[v for v in msg.known if "@" in v],
            order_refs=[v for v in msg.known if v.startswith("#")],
        )
        started = time.perf_counter()
        try:
            result = runner.run(tenant_id=tenant, customer_message=msg.text, roster=roster)
        except Exception as exc:  # noqa: BLE001 - one bad call must not end the run
            out.errors.append(f"{type(exc).__name__}: {exc}")
            continue
        out.latencies_ms.append((time.perf_counter() - started) * 1000)
        out.cost_cents += result.cost_cents
        out.input_tokens += result.input_tokens
        out.output_tokens += result.output_tokens
        key = str(result.gate.decision)
        out.decisions[key] = out.decisions.get(key, 0) + 1

        # Live invariant I5: scan what the client was actually handed.
        seen = json.dumps(getattr(runner.llm, "seen_payloads", []), ensure_ascii=False)
        for value in msg.pii:
            if value and value.lower() in seen.lower():
                out.pii_leaks.append(value)

        if i % 10 == 0:
            print(f"  {i}/{len(corpus)}  p50 {out.pct(0.5):.0f}ms  €{out.cost_cents / 100:.4f}")

    print("\n=== RESULTS ===")
    print(f"conversations     {len(out.latencies_ms)} ok, {len(out.errors)} errored")
    print(f"latency p50       {out.pct(0.50):.0f} ms")
    print(f"latency p95       {out.pct(0.95):.0f} ms")
    print(f"latency max       {max(out.latencies_ms, default=0):.0f} ms")
    if out.latencies_ms:
        print(f"latency mean      {statistics.mean(out.latencies_ms):.0f} ms")
    print(f"tokens            {out.input_tokens} in / {out.output_tokens} out")
    print(f"total cost        €{out.cost_cents / 100:.4f}")
    if out.latencies_ms:
        print(f"cost per conv     €{out.cost_cents / 100 / len(out.latencies_ms):.5f}")
    print(f"gate outcomes     {out.decisions}")
    print(
        f"PII leaks         {len(out.pii_leaks)}"
        + (f"  {out.pii_leaks[:5]}" if out.pii_leaks else "  ✅ none")
    )
    if out.errors:
        print(f"errors            {out.errors[:3]}")

    autonomous = out.decisions.get(str(Decision.AUTONOMOUS), 0)
    if out.latencies_ms:
        print(f"\nautonomous rate   {autonomous / len(out.latencies_ms):.1%}")
    print("\nPaste these into the README's measurement section, with the date.")
    return 1 if out.pii_leaks else 0


if __name__ == "__main__":
    raise SystemExit(main())
