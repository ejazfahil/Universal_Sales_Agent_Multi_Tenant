# Universal Sales Agent — Multi-Tenant, EU-Compliant

**An agentic customer support and sales platform for European e-commerce brands, where the compliance layer is the architecture rather than a policy document.**

> **Status: pre-implementation.** The research and specification are complete and public in `docs/`. Code starts at Milestone M0. This README describes what is being built and why — not a shipped product.

---

## The problem

By 2026 an AI helpdesk is a commodity. Resolution rates cluster at 70–84%, pricing has standardised near $0.90–$1.00 per resolution, and the category consolidated when Salesforce agreed to acquire Intercom/Fin for ~$3.6B. Building a better chatbot is not a business.

Two things happened at once that the incumbents are not built for:

1. **EU AI Act enforcement began on 2 August 2026.** The AI Office and national market surveillance authorities now have full powers. Article 50 transparency was *not* postponed. Systems placed on the market before August have until **2 December 2026**. Penalties reach €15M or 3% of worldwide turnover for high-risk violations.

2. **Frontier-model inference cannot be pinned to the EEA.** Anthropic's `inference_geo` parameter accepts `"us"` or `"global"` — there is no EU value. Every vendor on a US inference stack answers EU data residency with paperwork.

European mid-market brands are therefore buying AI support under a deadline, from vendors who cannot give them a clean answer on where personal data is processed.

## The approach

Personal data never leaves the EEA — enforced in code, not contracts.

```
EU shopper ──▶ EU app (Frankfurt) ──▶ [PSEUDONYMISATION GATEWAY] ──▶ Claude
                    │                            │
              Postgres (EU)              tokenise names, emails, addresses,
              token vault (EU)           phone numbers, order refs, free text
                    │                            ▼
                    └──── detokenise ◀──── model reasons over tokens only
```

The model sees `<CUSTOMER_7f3a>` and `<ORDER_91b2>`. It never sees a name. The vault stays in-region. The test asserts on the **serialized outbound request body**, so the guarantee is verifiable rather than claimed.

### Four design decisions that follow from that

| Decision | Consequence |
|---|---|
| **Deterministic gate, not model judgement** | The LLM drafts language. Code decides whether an action executes. No money action runs without an approval row — at any confidence. |
| **No emotion recognition** | Customer-facing emotion inference became high-risk in August 2026. Urgency is computed from SLA, order value, repeat contacts and keywords instead. Same routing, limited-risk classification. |
| **Isolation at the storage layer** | Postgres row-level security on every tenant table. Never a prompt instruction. Tested by dropping the `WHERE` clause and asserting zero rows. |
| **Audit log append-only in the database** | `REVOKE UPDATE, DELETE` plus a trigger. An Article 12 log that can be edited is not a log. |

## Who it is for

**Primary:** EU mid-market DTC brands, €5–50M GMV, 500–5,000 tickets/month, selling across three or more EU countries. Large enough to have a real support cost and a named GDPR owner; too small for a six-figure enterprise contract; multilingual by necessity.

**Secondary:** EU e-commerce agencies running 10–50 brands. Multi-tenancy is the architecture, so one agency relationship lands many tenants.

**Later:** compliance-heavy adjacencies — parapharmacy, supplements, medical devices — where compliance is existential rather than a line item.

## Architecture

Python 3.12 · FastAPI · SQLAlchemy 2 · Postgres 16 + pgvector · Redis · Anthropic Claude (`claude-opus-5`) · EU-hosted multilingual embeddings.

```
app/
├── privacy/      pseudonymisation gateway, PII detectors, EU token vault
├── agent/        tool runner, tool classification, deterministic gate, confidence
├── compliance/   Article 50 disclosure, Article 12 audit writer
├── api/          chat, approvals, gdpr, health
└── db/           tenant-scoped models, RLS
```

Confidence is the **minimum** of retrieval, grounding, policy-match and inverse-novelty — never the average, so any single weak signal can veto an autonomous action.

## Documentation

| Document | Contents |
|---|---|
| **[`BUILD_PROMPT.md`](BUILD_PROMPT.md)** | The execution spec — invariants, M0 tickets with acceptance criteria, anti-patterns, verification gates |
| [`CLAUDE.md`](CLAUDE.md) | Repository operating rules |
| [`docs/01-master-plan.md`](docs/01-master-plan.md) | Reference UI specification, data model, gate design, API surface |
| [`docs/02-eu-platform-plan.md`](docs/02-eu-platform-plan.md) | EU architecture, GDPR checklist, AI Act analysis, vertical map |
| [`docs/03-market-and-positioning.md`](docs/03-market-and-positioning.md) | Market analysis, ICP, competitive landscape, honest assessment of what is and is not defensible |
| [`docs/reference/`](docs/reference/) | Working references — [AI Act obligations mapped to tickets](docs/reference/eu-ai-act-obligations.md), [design tokens](docs/reference/design-tokens.css), [annotated sources](docs/reference/sources.md) |
| [`PROGRESS.md`](PROGRESS.md) | Execution ledger |

## Roadmap

| Milestone | Scope |
|---|---|
| **M0** | Thin vertical slice — one tenant, order-status resolution, real tool calls, approval queue, audit log, pseudonymisation gateway. Read-only, no money. |
| M1 | Widen read-only: product Q&A, inventory-aware recommendations, compatibility checks |
| M2 | Reversible writes, gated: address change, subscription changes, cart recovery |
| M3 | Money, always gated: returns, refunds, retention. Autonomy ladder with instant demotion on reversal. |
| M4 | Learning loop: corrections → clustering → draft guidelines → human review |
| M5 | Full operator UI |
| M6 | EU AI Act conformity pack |

## Honest scope

What is genuinely differentiated here is the compliance substrate and the deliberate limited-risk classification — both architectural, and expensive for a US-inference incumbent to retrofit. The agent loop itself is not novel, and this project does not attempt to rebuild a first-party identity graph; it integrates with Shopify Customer Accounts or a CDP instead.

The compliance advantage has a shelf life. Competitors will stand up EU regions. The window is roughly 12–18 months, after which the learning loop and switching costs have to hold the account.

## License

MIT
