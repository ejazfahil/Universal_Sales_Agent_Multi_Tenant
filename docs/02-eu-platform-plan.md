# Part 2 — Repo Adoption, Full Vertical Map, and the EU Platform Strategy

> Companion to [`01-master-plan.md`](01-master-plan.md). That document specifies the **replica**. This one specifies the **product**: what to reuse, every vertical Blotout/Evo operates, and how to build something they structurally cannot ship in Europe.
> **Researched:** 2026-09-04. Repo analysed at `HEAD` (~1,650 LOC Python, MIT).

---

## PART A — Repo analysis: `fauzan111/Multi-Tenant-AI-Customer-Support-Agent-Platform`

### A.1 Verdict

**Adopt it as the Phase 2 backend skeleton. Do not start from scratch.**

It is small (~1,650 LOC), MIT-licensed, and — critically — its central architectural decision is *the same one I independently specified* in Master Plan §5.3:

> *"The LLM handles language (phrasing a grounded answer). Deterministic code handles the decision that must be right: whether retrieval is confident enough."* — repo README

That is the HITL gate. The repo also already carries EU framing in its schema: `models.py` describes `AuditLog` as *"the EU AI Act / GDPR spine"*, with `decided_by: "llm" | "code"` and a nullable `human_approved`. Those are exactly the columns an Article 12 (logging) and Article 14 (human oversight) audit needs.

**Estimated saving: 5–8 days of Phase 2.** It does not touch Phase 1 (frontend) at all.

### A.2 What it actually is

| Aspect | Detail |
|---|---|
| Stack | Python 3.12 · FastAPI · **LangGraph** · SQLAlchemy 2 · Postgres + pgvector · Celery + Redis · structlog |
| Agent | 4-node LangGraph: `retrieve` → `decide` → (`generate` \| `escalate`) → END |
| Isolation | `tenant_id` filter at the **storage layer**, not the prompt |
| Endpoints | `POST /tenants/signup` · `POST /documents` · `POST /chat` · `GET /usage` · `GET /health` |
| Tests | 12 unit tests incl. `test_tenant_isolation.py`; load test = 90 req / 3 tenants, **0 cross-tenant leaks**, 52.6 req/s |
| Ship | Dockerfile, docker-compose, GitHub Actions CI, `render.yaml` |

### A.3 Code quality — honest read

**Genuinely good:**

- `app/rag/vector_store.py` is the standout. A `VectorStore` ABC where *every* method signature requires `tenant_id`, with two backends sharing identical isolation semantics so the isolation test runs without Postgres. The SQL comment marks the boundary explicitly:
  ```sql
  WHERE tenant_id = :tid   -- <-- the isolation boundary
  ```
  It names the risk it defends (OWASP LLM Top-10 #1) in the module docstring. That is senior-level defensive design.
- `support_graph.py` refuses to let the model self-assess confidence. `_decide_node` is four lines of pure comparison. Correct.
- Offline fallback (`HashEmbedder` + extractive answer) means the whole product demos with zero API keys. Excellent for development and for EU tenants who want a no-transfer mode.
- Docstrings explain *why*, not *what*. Rare.

**Weak or wrong for our use case:**

| # | Issue | Severity |
|---|---|---|
| 1 | **No tool use at all.** The agent only retrieves and phrases. There is no tool node, no action execution. Our agent must call `shopify.refund_order`. | **Blocking** |
| 2 | **No approval queue.** `Escalation` is fire-and-forget (open/resolved) with no `draft`, no `decision`, no `edited_draft`. The entire EvoAI UI is built on draft → approve/edit/deny → send. | **Blocking** |
| 3 | `confidence = results[0].score` — raw cosine similarity of the single top chunk. That is *retrieval* confidence. Gating a €89 refund on it is unsafe. | **High** |
| 4 | No learning loop — no corrections, clustering, or guidelines. | High |
| 5 | No commerce integration; customers are just an opaque `end_user_ref` string. | High |
| 6 | Isolation is app-layer only. No Postgres RLS. Consistent and tested, but one forgotten `WHERE` leaks. | High |
| 7 | `AuditLog` is *"immutable-by-convention"* — a comment, not a constraint. No append-only trigger, no revoked `UPDATE`/`DELETE`. **An EU AI Act Article 12 log that can be edited is not a log.** | High |
| 8 | No Alembic. Schema via raw `CREATE TABLE IF NOT EXISTS`. | Medium |
| 9 | `record_usage(tokens=len(answer) // 4)` — a character heuristic, not real usage. Cost-per-resolution built on this is fiction. | Medium |
| 10 | No GDPR endpoints: no DSAR export, no erasure, no retention policy. | **Blocking for EU** |
| 11 | No consent model. | Blocking for EU |
| 12 | Embeddings are `HashEmbedder` or **OpenAI** — a US sub-processor with no EU pinning. | Blocking for EU |
| 13 | No streaming, no WebSocket. The live inbox in Phase 1 needs push. | Medium |
| 14 | `Message.role` enum is only `USER`/`AGENT` — no `system`, no `ai_draft`, no `internal_note`. | Low |

### A.4 Integration plan — keep / extend / replace

| Path | Action | Notes |
|---|---|---|
| `app/rag/vector_store.py` | **Keep as-is** | Add RLS + an HNSW index. The ABC is right. |
| `app/db/models.py` | **Keep + extend** | Add the Master Plan §4.2 tables. Make `AuditLog` truly append-only. |
| `app/agents/support_graph.py` | **Keep the shape, replace the guts** | Add `plan` → `tools` → `gate` → `draft` nodes. See A.5. |
| `app/billing/usage.py`, `UsageRecord` | **Keep, fix metering** | Wire real `response.usage`, add `cost_cents`. |
| `app/auth/tenant.py` | **Keep pattern, harden** | Dev JWT → real sessions + RBAC (`owner`/`agent`/`viewer`). |
| `app/escalation.py` | **Replace** | Becomes the approval-queue subsystem. |
| `app/rag/embeddings.py` | **Replace provider** | Drop OpenAI. EU-hosted embeddings (see C.4). |
| `tests/unit/test_tenant_isolation.py` + `scripts/load_test.py` | **Keep and extend** | Add a money-action test: no refund without an approval row. |
| `app/llm/client.py` | **Replace** | Anthropic SDK with Tool Runner per Master Plan §5.1. |
| Docker/CI/`render.yaml` | **Keep** | Retarget deploy to EU region (C.5). |

### A.5 The graph we actually need

The repo's 4-node graph becomes 7 nodes. The new `gate` node is Master Plan §5.3, unchanged:

```
retrieve ─→ plan ─→ tools ─→ gate ─┬─→ execute ──→ END   (autonomous)
   │                                ├─→ queue ────→ END   (needs approval)
   └─ tenant-scoped                 └─→ escalate ─→ END   (low confidence / novel)
```

`retrieve` and the tenant scoping come free from the repo. `gate` stays deterministic code. Only `plan` and `draft` touch the LLM.

**Replace the confidence signal.** Single-chunk cosine is not enough to authorise money:

```python
confidence = min(
    retrieval_score,        # repo's existing signal — keep it
    grounding_score,        # every claim traceable to a tool result?
    policy_match_score,     # does a guideline actually cover this case?
    1.0 - novelty_score,    # how far from anything seen before?
)
```
Take the **minimum**, never the average — one weak signal must be able to veto.

---

## PART B — Complete vertical map of Blotout / Evo AI

Four layers. They sell the stack; most competitors sell one layer.

### Layer 1 — Signal infrastructure (Blotout core, the real moat)

| Product | What it does |
|---|---|
| **EdgeTag** | First-party pixel + server-side CAPI to Meta, Google, TikTok, Klaviyo. **1P identity graph** stitching users across devices and sessions. Per-channel event tailoring. Claimed 94% match rate vs ~40% on a stock web pixel; +25–30% Meta ROAS. |
| **Consent** | Region-aware enforcement across **EU, UK, CA**. Jurisdictions listed: GDPR · CCPA · CPRA · CTDPA · VCDPA. |
| **ConsentIQ** | Consent *analytics*. Quantifies signal loss as revenue. Headline claim: **"40–60% of your remarketing audience on Meta, Google, and TikTok is already gone — blocked by consent rejections."** Tracks the cascade: reduced audience → degraded match rate → suppressed optimisation signal → lower ROAS → wrong budget decisions. AI-detected misconfiguration, auto-remediation, flat-fee pre-litigation support. Ships as a Shopify app. |
| **Data governance** | Single-tenant deployment · "no PII required to operate" · SOC 2 Type II · HIPAA. |

### Layer 2 — Agent applications (Evo AI: "one brain, three surfaces")

| Agent | Workflows | Claimed metrics |
|---|---|---|
| **Sales** | cart recovery · product advisor · upsell/cross-sell | 3.4× cart-recovery lift · $42.3K assisted revenue/mo |
| **Support** | order tracking · returns & refunds · exchanges · complaint resolution | 85–90% auto-resolved · 4.8 CSAT · 12s first response |
| **Search** | personalised discovery from history, not keywords · records unmet demand | 38% search-to-cart |

Shared memory is the pitch: *"whatever one of them learns about a shopper, the other two know before the shopper's next click."*

### Layer 3 — Agentic commerce (where they're heading)

**Five agent archetypes:** reorder agents · shopping agents · customer-service agents · sales agents · subscription managers.

**Twelve production workflows** — this is the concrete build backlog:

| # | Workflow | Systems | Metric |
|---|---|---|---|
| 1 | Order-status resolution | email, OMS, carrier APIs | CSAT 4.7+ (their highest) |
| 2 | Autonomous return processing | policy DB, RMA, fulfilment, billing | ~8 min tier-1 time saved/return |
| 3 | Refund-on-spot for clear cases | order confirmation, billing | kills 48h investigation queues |
| 4 | Address change before fulfilment | OMS | ~90s resolution |
| 5 | Subscription pause/skip/swap/resume | subscription, billing | reflected in seconds |
| 6 | Pre-cancel retention flow | customer DB, LTV, retention policy | saves relationships without escalation |
| 7 | Product Q&A from catalog + **return data by SKU** | catalog, returns DB | honest answers lift conversion |
| 8 | Compatibility / configuration checks | product DB, compatibility rules | returns drop |
| 9 | Inventory-aware recommendations | inventory, catalog | cuts OOS abandonment |
| 10 | Conversational cart recovery | cart, engagement platform | ~38% of carts recovered |
| 11 | Pre-purchase doubt resolution | catalog, brand positioning docs | conversion lift |
| 12 | Defect / complaint pattern detection | tickets, product DB, alerting | quality issues flagged in hours |

**Five agentic-readiness capabilities** they say a brand must have: machine-readable product data · programmatic cart/checkout/returns APIs · real-time inventory · trusted agent authentication · governance frameworks.

**Channel shift:** product discovery moving inside ChatGPT, Perplexity, Claude, Gemini; agent-to-agent transactions between shopper agents and brand agents.

### Layer 4 — Packaging & GTM

- **Agency software:** multi-tenant admin · white-label dashboards · bulk deployment across brands · revenue tracking · admin APIs.
- **Segments:** DTC brands + marketing agencies.
- **Positioned against:** Gorgias, Zendesk, Kustomer, Gladly.
- **Outcome pricing:** cost-per-resolution as the honest metric; "30–40% CX cost reduction, guaranteed or free."

### B.1 What they have that we won't (be honest)

EdgeTag's identity graph is ~a decade of infrastructure across 1,300–5,000 brands. **Do not rebuild it.** Integrate with Shopify Customer Accounts, Segment/RudderStack, or Klaviyo profiles. Our wedge is Layer 2 + compliance, not Layer 1.

---

## PART C — The EU strategy

This is where the opportunity actually is, and it is time-boxed.

### C.1 The regulatory clock — we are already inside it

| Date | Event | Status as of 2026-09-04 |
|---|---|---|
| 2 Aug 2026 | **EU AI Act high-risk obligations enforceable** — risk management, data governance, logging, transparency, human oversight, cyber resilience, post-market monitoring | **In force, 1 month ago** |
| 2 Aug 2026 | **Article 50 transparency** applies — disclose that the user is talking to a machine; mark synthetic output | **In force** |
| **2 Dec 2026** | Grace period ends for systems placed on market **before** 2 Aug 2026 | **~3 months away** |

Every EU brand running a pre-August chatbot has a December deadline and most don't know it. That is the wedge.

### C.2 The compliance trap in Evo's own design — sentiment analysis

The EvoAI demo carries a `sentiment` field with values including `"frustrated"`, and the Master Plan's gate uses it (`if run.sentiment == "frustrated"`).

**Customer-facing emotion recognition is classified HIGH-RISK under the EU AI Act as of August 2026.** Shipping it in the EU pulls the entire product into: conformity assessment, technical documentation, CE marking, EU database registration, post-market monitoring — a different company, not a different feature.

Meanwhile *"a service agent that checks order status, books an appointment, or answers a product question is limited risk, and transparency is the whole of your obligation."*

**Decision — bake this into the architecture:**

> **Do not ship emotion/sentiment inference in the EU build.**
> Replace `sentiment` with `urgency`, computed **deterministically** from non-inferred signals: SLA remaining, order value, repeat-contact count, explicit refund/complaint keywords, channel. Same routing behaviour, same UI chip, no emotion classifier, stays limited-risk.

This one substitution is worth more than any feature on the roadmap. Copying Evo's schema uncritically would import their EU liability.

### C.3 The inference-geography finding — verified, and it changes the design

I checked this rather than assuming. **Anthropic's `inference_geo` parameter accepts only `"us"` or `"global"`. There is no `"eu"` value.** It is GA on the first-party Claude API and Claude Platform on AWS; unsupported on Bedrock, Vertex, and Foundry.

**You therefore cannot pin Claude inference inside the EEA.** Any EU sales deck promising "EU-only AI processing" with a US-hosted frontier model is wrong, and EU procurement now asks specifically: *"where is it processed, who can access it, which legal regime applies."*

**The architecture that actually answers this — a PII pseudonymisation gateway at the EEA boundary:**

```
EU customer ─→ EU app (Frankfurt) ─→ [PSEUDONYMISATION GATEWAY] ─→ Claude
                    │                          │
              Postgres (EU)            tokenise: names, emails, addresses,
              token vault (EU)         phone, order refs, free-text PII
                    │                          ↓
                    └────── detokenise ←── model reasons over tokens only
```

The model sees `<CUSTOMER_7f3a>` and `<ORDER_91b2>`, never "Maya Chen" or "#4821". Personal data never leaves the EEA; only pseudonymised tokens cross. The vault stays in Frankfurt.

This turns Blotout's marketing line — *"no PII required to operate"* — into an actual enforced technical control, which is a stronger claim than theirs. Layer on top:

1. Anthropic DPA + SCCs / EU-US Data Privacy Framework as the Art. 44–49 mechanism for residual transfer.
2. Zero-retention configuration.
3. Contractual no-training terms.
4. **No-transfer mode** for tenants who contractually forbid any egress: route to an EU-hosted open-weights model. The repo's offline extractive fallback is already a working degraded path — extend it rather than inventing one.

### C.4 GDPR checklist — build these, they are not optional

| Requirement | Implementation |
|---|---|
| Lawful basis | Per-tenant config; consent vs legitimate interest, recorded per processing purpose |
| Data minimisation | Pseudonymisation gateway (C.3) |
| DPA | Signed with tenants; Anthropic DPA upstream |
| EEA residency | Postgres, Redis, object storage, logs — all EU region. Token vault EU-only. |
| Sub-processor transparency | Public, versioned sub-processor list + change notification |
| **DSAR / access** | `GET /api/gdpr/export?subject=` → machine-readable bundle of every message, run, trace |
| **Erasure** | `DELETE /api/gdpr/subject/{id}` → cascade across messages, chunks, vectors, token vault. **Must include pgvector chunks** — the repo has `delete_document` but no subject-level erasure. |
| No-training | Contractual + technical; assert in DPA |
| Audit logging | The repo's `AuditLog`, made genuinely append-only |
| Retention | Per-tenant TTL job; default 90 days for conversation content |
| Embeddings | Drop OpenAI. EU-hosted embedding service, or self-hosted `multilingual-e5` / BGE-M3 in-region — also better for multilingual EU (see C.6). |

### C.5 EU deployment

Frankfurt or Dublin. Managed Postgres with PITR, EU-only. Sentry/OTel EU tenancy. `render.yaml` retargeted or replaced with Fly/Hetzner/Scaleway EU. **No US-region log sink** — logs contain conversation content.

### C.6 Multilingual is a hard EU requirement, not a nice-to-have

24 official languages. The demo already hints at it (a Spanish ticket, `Producto · piel grasa`). Requirements:
- Embeddings must be genuinely multilingual — `HashEmbedder` and English-tuned models both fail. Use BGE-M3 or multilingual-e5.
- Retrieval must work cross-lingual: German query against English knowledge base.
- Draft replies in the customer's language; audit trail and merchant UI in the merchant's.
- Article 50 disclosure must be localised per language.

---

## PART D — Revised architecture and roadmap

### D.1 Merged phase plan

Master Plan Phases 1 and 3–6 stand. Phase 2 is replaced, and two EU phases are inserted.

| Phase | Scope | Change | Est. |
|---|---|---|---|
| **1** | Frontend replica | Unchanged | 5–8 d |
| **2′** | **Fork the repo**, extend schema, add RLS, Alembic, real auth, WebSocket, Shopify | Was 8–12 d | **4–7 d** |
| **2.5** | **EU compliance core** — pseudonymisation gateway, token vault, DSAR/erasure, consent model, append-only audit, EU deploy | **NEW** | 6–9 d |
| **3** | Agent core + HITL gate + tool layer | Graph extends the repo's | 8–12 d |
| **3.5** | **EU AI Act conformity** — Art. 50 disclosure, Art. 12 logging, Art. 14 oversight evidence, urgency-not-emotion, tech documentation | **NEW** | 4–6 d |
| **4** | Learning loop | Unchanged | 8–12 d |
| **5** | Evals + governance | + multilingual eval set | 7–11 d |
| **6** | Production | EU regions only | 5–8 d |
| | **Total** | | **~10–14 weeks** |

Net: the repo pays for roughly half of the EU compliance work it adds.

### D.2 Vertical build order (from Layer 3's twelve workflows)

Ship in this order — cheapest to verify, highest CSAT first:

**Wave 1 (read-only, autonomous-safe, no money):** order-status resolution (#1) · product Q&A (#7) · inventory-aware recommendations (#9) · compatibility checks (#8).
Read-only tools, no approval needed, immediate CSAT. Proves the loop with zero financial risk.

**Wave 2 (reversible writes, gated):** address change before fulfilment (#4) · subscription pause/skip/swap (#5) · conversational cart recovery (#10) · pre-purchase doubt resolution (#11).

**Wave 3 (money, always gated until a rule earns promotion):** return processing (#2) · refund-on-spot (#3) · pre-cancel retention (#6).

**Wave 4 (analytics):** defect/complaint pattern detection (#12) — the highest-margin feature and nobody else ships it well.

### D.3 Positioning: what we sell that they cannot

| # | Us | Them |
|---|---|---|
| 1 | **PII never leaves the EEA** — pseudonymisation gateway, enforced, auditable | US-hosted processing, DPA + SCC paperwork |
| 2 | **EU AI Act conformity pack** — Art. 50 disclosure, Art. 12 logs, Art. 14 oversight evidence, exportable for audit | Not addressed publicly |
| 3 | **No emotion recognition** — deterministic urgency, deliberately limited-risk | Ships sentiment inference |
| 4 | **Live cost-per-resolution ledger** from real token usage | Argues the metric, shows a static number |
| 5 | **Replayable, diffable reasoning traces** — a policy simulator | Trace is display-only |
| 6 | **Visible autonomy ladder** with one-click demote | Implied, not exposed |
| 7 | **True multilingual** across 24 EU languages | English-first |
| 8 | **No-transfer mode** — EU-hosted model for strict tenants | Not offered |

Items 1–3 and 8 are structural. A US company on a US inference stack cannot match them without re-architecting.

### D.4 Tickets

**EPIC F — Repo adoption**
- **F1** Fork; retarget package to `app/`; strip the demo pptx; pin deps. **AC:** existing 12 tests pass unchanged.
- **F2** Alembic; convert `ensure_schema()` to migrations. **AC:** up/down clean; `CREATE TABLE IF NOT EXISTS` gone.
- **F3** Extend schema with Master Plan §4.2 tables (`agent_runs`, `approvals`, `actions`, `workflows`, `guidelines`, `orders`, `customers`). **AC:** every table has `tenant_id`.
- **F4** Postgres RLS on all tenant tables. **AC:** with RLS on and a wrong tenant GUC, cross-tenant `SELECT` returns 0 rows even with the `WHERE` clause removed.
- **F5** Append-only `AuditLog`: revoke `UPDATE`/`DELETE` from app role + a `BEFORE UPDATE OR DELETE` trigger that raises. **AC:** an `UPDATE audit_logs` from the app role raises; the attempt is itself logged.
- **F6** Real usage metering from `response.usage`; add `cost_cents`. **AC:** `len(answer)//4` heuristic deleted; cost within 1% of the Anthropic dashboard.
- **F7** Multi-signal confidence per A.5. **AC:** a high-cosine, low-grounding case scores low and does not auto-execute.

**EPIC G — EU compliance core**
- **G1** Pseudonymisation gateway + EU token vault. Detect and tokenise names, emails, phones, addresses, order refs, and free-text PII in both directions. **AC:** a golden set of 50 messages containing PII produces **zero** raw identifiers in the outbound payload, verified by asserting on the serialized request body; round-trip detokenisation is lossless.
- **G2** DSAR export + subject erasure cascading to `support_chunks` and the token vault. **AC:** after erasure, no vector search on any tenant returns that subject's content, and the vault entry is gone.
- **G3** Consent model with region-aware enforcement (EU/UK/CA) and per-purpose lawful basis. **AC:** processing without a valid basis is refused at the API boundary and logged.
- **G4** EU-only deploy: Frankfurt/Dublin Postgres+Redis+storage, EU log sink. **AC:** no egress to a non-EU region in a network audit, LLM egress excepted and documented.
- **G5** Replace OpenAI embeddings with EU-hosted multilingual (BGE-M3 or multilingual-e5). **AC:** German query retrieves the correct English chunk in an eval set.

**EPIC H — EU AI Act conformity**
- **H1** Article 50 disclosure in every channel, localised. **AC:** every conversation opens with an AI disclosure in the customer's language; presence asserted in E2E tests.
- **H2** `sentiment` → deterministic `urgency`. Remove every emotion classifier from the EU build. **AC:** grep finds no emotion/sentiment inference in the EU code path; urgency is computed from SLA, order value, repeat count, keywords, channel only.
- **H3** Article 12 logging + Article 14 human-oversight evidence export. **AC:** one command produces an audit bundle for any date range: every decision, who decided, the trace, whether a human approved.
- **H4** Technical documentation pack + sub-processor register. **AC:** a reviewer can answer "where is EU personal data processed" from the docs alone.

---

## PART E — Answering your question directly

**"Can this repo be implemented with our AI Sales solution?"**

Yes — adopt it, with eyes open about what it is. It is a **multi-tenant RAG support-agent skeleton with a correct deterministic-gate philosophy**, not a sales agent. It contributes the boring, high-value 40%: tenant isolation, audit spine, usage metering, graph structure, tests, CI, deploy. It contributes **none** of the differentiating 60%: tool use, approval queue, learning loop, commerce integration, sales agent.

The reason to take it is not the code volume — 1,650 LOC is two days of typing. It is that **its central design decision agrees with ours**, its isolation boundary is properly placed and load-tested, and its audit table was already written with the EU AI Act in mind. Rewriting that from scratch would produce the same thing, worse.

Three things to fix before trusting it with money: single-chunk cosine as the confidence signal (A.5), app-layer-only isolation (F4), and an audit log that is immutable only by comment (F5).

**On the EU:** the timing is unusually good and it is the strongest part of this plan. The AI Act's high-risk obligations went live on 2 August 2026 and the transparency grace period closes on 2 December 2026 — roughly three months out. Every EU brand running a pre-August chatbot needs to act, and the incumbents are all US-inference-stack companies.

The single most valuable finding in this round is the one I verified rather than assumed: **Claude's `inference_geo` accepts only `"us"` or `"global"` — EU inference pinning is not available.** That is not a blocker, but it means the honest EU architecture is *pseudonymisation at the boundary*, not "EU-hosted AI". Building that gateway (G1) makes "no PII leaves the EEA" a technically enforced, auditable claim rather than a paperwork one — and it is the one thing on this list a US competitor cannot answer with a contract amendment.

The second most valuable finding: **do not copy Evo's `sentiment` field into an EU product.** Customer-facing emotion recognition is high-risk under the AI Act as of last month; deterministic urgency scoring gets identical routing behaviour and stays limited-risk.

---

*Read next: [`01-master-plan.md`](01-master-plan.md) Part 3 (Phase 1 tickets). Start at A1 — the frontend replica is unaffected by everything in this document.*
