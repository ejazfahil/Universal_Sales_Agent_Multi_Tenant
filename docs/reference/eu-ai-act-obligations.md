# EU AI Act — operative obligations mapped to implementation

> **What this is:** a structured working summary of the AI Act articles this system is built against, each mapped to the ticket that implements it.
> **What this is not:** the authoritative legal text. These are summaries, not verbatim quotations. Before any compliance claim or audit, read the official text at [EUR-Lex 32024R1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) and take legal advice.
> Compiled 2026-09-06.

---

## Timeline

| Date | Event | Status |
|---|---|---|
| 2 Aug 2026 | High-risk obligations enforceable. AI Office + national market surveillance authorities hold full powers. | **In force** |
| 2 Aug 2026 | Article 50 transparency applies. **Not** postponed by the Digital Omnibus. | **In force** |
| **2 Dec 2026** | Grace period ends for systems placed on the market before 2 Aug 2026 | **Pending** |

## Penalties

| Violation | Ceiling |
|---|---|
| Prohibited practices (Art. 5) | €35M or **7%** of worldwide annual turnover |
| High-risk / GPAI obligations | €15M or **3%** |
| Incorrect or misleading information to authorities | €7.5M or **1%** |

Enforcement guidance signals that organisations which ignored the rules entirely face the harshest treatment, not those showing genuine effort with residual gaps. **Demonstrable good-faith compliance is the operative standard.**

---

## Our risk classification — and why it is a design constraint

| System behaviour | Classification | Consequence |
|---|---|---|
| Order status, returns, product Q&A, appointment booking | **Limited risk** | Transparency (Art. 50) is the *whole* obligation |
| Customer-facing **emotion recognition** | **High risk** | Risk management, data governance, logging, human oversight, cyber resilience, post-market monitoring, conformity assessment, CE marking, EU database registration |

**This is why invariant I6 exists.** Shipping sentiment inference moves the entire product from "add a disclosure banner" to "run a conformity assessment and register in the EU database." We compute `urgency` deterministically instead and stay limited-risk by construction.

Note also **Art. 50(3)**: a *deployer* of an emotion recognition system must inform the persons exposed to it — an additional obligation stacked on top of the high-risk classification. There is no cheap path to shipping sentiment in the EU.

---

## Article 50 — Transparency

*Summary of operative paragraphs.*

| ¶ | Obligation | Applies to us? |
|---|---|---|
| **50(1)** | Providers must ensure AI systems interacting directly with natural persons **inform them of that interaction** — unless it is obvious to a reasonably well-informed person in context. | **Yes — core obligation** |
| 50(2) | Synthetic audio/image/video/text must be marked **machine-readably** as artificially generated, effective and robust so far as technically feasible. | Partially — our drafts are AI-generated text sent to customers |
| 50(3) | Deployers of **emotion recognition / biometric categorisation** must inform exposed persons and process data per GDPR. | **No — by design.** We ship neither. |
| 50(4) | Deepfakes and AI-generated public-interest text must be disclosed. Carve-out where content underwent **human editorial review**. | Edge case — note the human-review carve-out interacts with our approval queue |
| **50(5)** | Information must be given **clearly and distinguishably, at the latest at the time of first interaction**, and meet accessibility requirements. | **Yes — timing and accessibility are testable** |
| 50(6) | Does not displace Chapter III requirements or other Union/national transparency duties. | Noted |

### Implementation

- **Ticket M0-9**, invariant **I7**. Disclosure injected at conversation open, localised per customer language, in every channel.
- 50(5) makes the *timing* testable: assert the disclosure is the first outbound content, not buried later.
- Accessibility is part of the obligation — the disclosure must survive screen readers, not just render visually.
- Do not rely on the 50(1) "obvious" carve-out. It is a defence, not a design.

---

## Article 12 — Record-keeping

*Summary of operative paragraphs.*

| ¶ | Obligation |
|---|---|
| 12(1) | High-risk systems must **technically allow automatic recording of events (logs) over the system lifetime**. |
| 12(2) | Logging must capture events relevant to: (a) identifying situations where the system may present a risk or need substantial modification; (b) facilitating post-market monitoring; (c) enabling deployers to monitor operation. |
| 12(3) | For Annex III biometric systems: usage period timestamps, reference databases, matching input data, and the natural persons who verified results. |

### Implementation

- **Tickets M0-3 and M0-7**, invariant **I4**.
- `audit_logs` is append-only **enforced by the database** — `REVOKE UPDATE, DELETE` plus a trigger that raises. A log that can be edited is not a log.
- `agent_runs.trace` stores the full reasoning trace as the traceability record.
- 12(2)(b) *post-market monitoring* is why cost, latency and confidence are recorded per run, not just the outcome.
- We are limited-risk, so Art. 12 does not strictly bind us — **we implement it anyway**, because it is the artefact that wins procurement and it is far cheaper to build in than to retrofit if classification ever changes.

---

## Article 14 — Human oversight

*Summary of operative paragraphs.*

| ¶ | Obligation |
|---|---|
| 14(1) | High-risk systems must be designed so they **can be effectively overseen by natural persons** while in use, including appropriate human-machine interface tools. |
| 14(2) | Oversight must aim to prevent or minimise risks to health, safety and fundamental rights, under intended use *and* reasonably foreseeable misuse. |
| 14(3) | Measures proportionate to autonomy and context — built into the system by the provider, or identified for the deployer to implement. |
| 14(4) | Overseers must be able to: understand capacities and limitations; **be aware of automation bias**; correctly interpret output; **decline to use or override** the decision; and **stop the system**. |
| 14(5) | Biometric identification requires independent verification by two qualified persons. |

### Implementation — this article *is* the approval queue

Article 14(4) reads like a specification of the operator surface:

| 14(4) requirement | Our implementation |
|---|---|
| Understand capacities and limitations | Reasoning trace shows every tool call, source and confidence signal |
| Awareness of **automation bias** | Confidence is the `min()` of four signals, displayed — not a single reassuring number. Low-grounding cases are surfaced, not hidden. |
| Correctly interpret output | Draft shown with its grounding, not as a bare answer |
| **Decline to use / override** | Deny and Edit actions in the approval queue |
| **Stop the system** | Autonomy ladder demotion — any reversal instantly returns a promoted rule to gated |

Automation bias is the one most products fail. An approval queue that shows a green 94% badge and a pre-filled Approve button *manufactures* automation bias. Displaying which signal is weakest is the mitigation.

---

## What we build even though we are limited-risk

Deliberate over-compliance, because it is cheap now and is the actual sales artefact:

- Article 12 logging (append-only, DB-enforced)
- Article 14 oversight evidence (approval queue as the record)
- Post-market monitoring signals (cost, latency, confidence, reversal rate per run)
- Exportable audit bundle for any date range — **ticket H3**

## Open questions for counsel

1. Does a draft reply reviewed and approved by a human before sending fall within the Art. 50(4) human-editorial-review carve-out?
2. Does deterministic urgency scoring from SLA, order value and keywords stay clearly outside "emotion recognition" as defined in Art. 3? *(Our position: yes — it infers no emotional state. Confirm before making the claim in marketing.)*
3. Provider vs deployer status when we supply the platform and the brand configures the policies.

---

## Sources

- [EUR-Lex 32024R1689 — official consolidated text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) — **authoritative**
- [artificialintelligenceact.eu — Article 50](https://artificialintelligenceact.eu/article/50/) · [Article 12](https://artificialintelligenceact.eu/article/12/) · [Article 14](https://artificialintelligenceact.eu/article/14/)
- [High-level summary](https://artificialintelligenceact.eu/high-level-summary/)
- [European Commission — regulatory framework](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
- [Penalty structure](https://www.euaiact.com/key-issue/1)
