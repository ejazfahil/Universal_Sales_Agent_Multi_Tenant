# Market, ICP and Positioning

> Companion to [`01-master-plan.md`](01-master-plan.md) (what to build) and [`02-eu-platform-plan.md`](02-eu-platform-plan.md) (how, under EU constraints). This document is **why, for whom, and against whom**.
> Researched 2026-09-06. Figures are public vendor pricing and public regulation, cited at the end.

---

## 1. Executive summary

An AI helpdesk is a commodity in 2026. The category is proven, priced, and consolidating. Building a better chatbot is not a business.

What is *not* commodity: an AI support platform a European Data Protection Officer can sign off on. EU AI Act enforcement began on 2 August 2026, a hard transparency deadline falls on 2 December 2026, and frontier-model inference cannot be pinned to the EEA. Every incumbent answers EU data residency with paperwork because their architecture gives them no other answer.

**The thesis: build the compliance substrate everyone skipped, for the EU mid-market segment US vendors do not optimise for.**

Honest split: roughly 70% of this product is commodity engineering. The defensible 30% is structural rather than a feature — and it is the part that clears procurement.

---

## 2. Market state, 2026

| Fact | Implication |
|---|---|
| AI customer-service market ~**$15.1B** in 2026 | Category is proven; no need to educate the buyer |
| Salesforce agreed to acquire **Intercom/Fin for ~$3.6B** (June 2026) | The top is consolidating. Do not compete head-on. |
| Ecommerce deployments resolve **70–84%** | This is the performance bar, not a differentiator |
| Pricing standardised at **per-resolution** | The unit of value is settled; compete on total cost, not on model quality |

**Published pricing:**

| Vendor | Model | Price |
|---|---|---|
| Intercom Fin | per outcome | **$0.99**, ~76% avg resolution |
| Gorgias | per resolution | **$0.90** annual / **$1.00** monthly; overage **$1.50** |
| Decagon | platform + per conversation | ~**$50K/yr** + ~$0.99; median contract ~**$386K** |
| Sierra | custom outcome-based | **$150K+/yr** |
| Kore.ai | custom | **$300K+/yr** |

Two structural gaps fall out of this table. First, there is nothing credible between "$1 per resolution self-serve" and "$150K enterprise contract" — which is exactly where a €5–50M GMV European brand sits. Second, every one of these runs US inference.

---

## 3. Why now — two clocks

**Clock 1 — the category consolidated.** See above. Feature competition is lost before it starts.

**Clock 2 — compliance became mandatory, and that is the opening.**

| Date | Event |
|---|---|
| **2 Aug 2026** | EU AI Act enforcement live. AI Office + national market surveillance authorities hold full powers. Article 50 transparency applies — and was **not** postponed by the Digital Omnibus. |
| **2 Dec 2026** | Grace period ends for systems placed on market before August |

**Penalties:** €35M / 7% of worldwide turnover for prohibited practices; €15M / 3% for high-risk violations; €7.5M / 1% for supplying misleading information.

Regulators have signalled that the harshest enforcement targets those who ignored the rules entirely, not those who made genuine effort with residual gaps. **That is a market for demonstrable compliance, not for perfection** — which is a far easier product to build than it sounds, and a far harder one to retrofit.

**Clock 2 is the entire opportunity.** It creates urgency that cannot be manufactured by marketing, and it expires.

---

## 4. Ideal customer profile

### Primary — EU mid-market DTC brands

| Attribute | Value |
|---|---|
| GMV | €5M–50M |
| Ticket volume | 500–5,000/month |
| Markets | 3+ EU countries |
| Support team | 2–5 agents (≈ €120–300K/year) |
| Compliance | A **named** person owns GDPR, now also the AI Act |
| Stack | Shopify / Shopware / WooCommerce |

Why precisely this band:
- Large enough that support cost is a board-visible line item
- Large enough to have someone accountable for the December deadline
- Too small to get a €386K Decagon contract approved, too large for a free tier
- **Multilingual by necessity** — a Dutch brand sells in DE/FR/NL/IT; US tools are English-first
- Data residency is already a live procurement question for them

### Secondary — EU e-commerce agencies

Agencies running 10–50 brands. This is the leverage play: multi-tenancy is the architecture, so one agency relationship lands many tenants. The reference competitor sells exactly this ("agency software: multi-tenant admin, white-label dashboards, bulk deployment"), which is evidence the channel works.

### Later — compliance-heavy adjacencies

Parapharmacy, supplements, medical devices, financial-services-adjacent retail. Compliance is existential rather than a line item, so willingness to pay is materially higher.

### Explicitly not our customer

| Segment | Why not |
|---|---|
| Enterprise (>€200M) | Zendesk incumbency, 9-month cycles, legal review, and Sierra/Kore already there |
| Micro-merchants | No budget, no compliance pressure, no named GDPR owner — Gorgias free tier is genuinely fine |
| US-only brands | Our entire differentiator is irrelevant to them |

---

## 5. Competitive landscape

| Competitor | Strength | Where we win |
|---|---|---|
| **Evo AI / Blotout** (reference) | First-party identity graph across 1,300–5,000 brands; unified sales+support+search | EU residency architecture; they ship customer sentiment inference, which is now high-risk in the EU |
| **Intercom Fin** | 76% resolution, $0.99, Salesforce distribution | Mid-market EU pricing; multilingual; data residency |
| **Gorgias** | Shopify-native, entrenched in DTC | Their per-resolution double-billing is a known grievance; no EU compliance story |
| **Decagon / Sierra / Kore** | Enterprise-grade | They will not serve a €10M GMV brand at a workable price |
| **Zendesk / Kustomer / Gladly** | Incumbency | Retrofitted AI; compliance is policy documentation, not architecture |

**What none of them can currently say:** *"Your customers' personal data never leaves the EEA, and here is the test that proves it."*

---

## 6. What is defensible, honestly

### Commodity — do not pretend otherwise (~70%)

RAG over a knowledge base. Draft-and-approve. Ticket deflection. Cart recovery (owned by Klaviyo/Attentive/Postscript). Product recommendations (owned by Constructor/Algolia/Coveo). A reference implementation of the core support agent is ~1,650 lines of Python. **If we ship only this, we have built the eleventh-best AI helpdesk and we lose.**

### Defensible — structural, not features (~30%)

1. **PII never leaves the EEA.** Verified constraint: Anthropic's `inference_geo` accepts only `"us"` or `"global"`; there is no EU value. Competitors therefore answer residency with DPAs and SCCs. The pseudonymisation gateway answers it with architecture — the model reasons over `<CUSTOMER_7f3a>`, and the test asserts on the serialized outbound request body. **A competitor cannot match this with a contract amendment; only with a rebuild.**

2. **Deliberately limited-risk.** Customer-facing emotion recognition became high-risk in August 2026, carrying conformity assessment, CE marking and EU database registration. Competitors have *already shipped* sentiment inference — removing it is a product regression for them. We compute urgency deterministically from SLA, order value, repeat contacts, keywords and channel: identical routing, no classifier.

3. **Audit evidence as a product surface.** The approval queue *is* the Article 14 human-oversight record; the reasoning trace *is* the Article 12 log. One command produces an auditor-ready bundle. Everyone else retrofits this.

4. **Genuine multilingual retrieval.** Cross-lingual by design (a German query against an English knowledge base), not translation bolted onto an English pipeline.

### The uncomfortable parts

- **No distribution.** The reference competitor's real moat is not its technology — it is thousands of brands already installed. We have zero. Agencies are the only realistic answer.
- **No identity graph, and we should not build one.** That is a decade of infrastructure. Integrate with Shopify Customer Accounts or a CDP.
- **The window closes.** Competitors will stand up EU regions and pseudonymisation eventually. Realistically 12–18 months to establish position, after which the learning loop and switching costs must hold the account.
- **Compliance alone does not close deals.** It gets the meeting and clears procurement. Cost-per-resolution and resolution rate close. We must be genuinely competitive at the 70–84% bar.

---

## 7. Objection handling

| Objection | Answer |
|---|---|
| *"We already use Gorgias."* | We are not asking you to rip it out on day one. What is your answer when an auditor asks where customer personal data is processed — and what is your plan for 2 December? |
| *"Isn't this just another chatbot?"* | The chatbot is the commodity part and we say so. You are buying the audit trail and the residency guarantee. Here is the test that proves the second one. |
| *"You're a small vendor."* | Single-tenant deployment, MIT-licensed core, full data export. Your exit cost is bounded, which is more than the incumbents offer. |
| *"Claude is a US company."* | Correct, and inference cannot be pinned to the EU — which is why we pseudonymise at the boundary rather than claiming otherwise. Vendors telling you they do "EU-only AI processing" on a frontier model are describing something that does not exist. |
| *"How much?"* | Priced per resolution, below the $0.90–$1.00 band, with the compliance pack included rather than an enterprise add-on. |

---

## 8. Go-to-market sequence

1. **Land the deadline.** Content and outbound aimed squarely at 2 December 2026 — an AI Act readiness assessment as the opening artefact, not a product demo.
2. **Prove it with M0.** A working vertical slice with a real audit bundle beats a polished demo over mock data. That is exactly why M0 is sequenced ahead of the full UI.
3. **Agencies next.** One relationship, many tenants. White-label the operator surface.
4. **Then verticals.** Parapharmacy and supplements, where compliance is existential.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Compliance window closes early | Ship M0 fast; convert compliance wins into learning-loop lock-in |
| We lose on resolution rate | Benchmark against the 70–84% bar from day one; publish the eval methodology |
| Regulatory interpretation shifts | Stay in limited-risk by construction; never rely on a favourable reading |
| No distribution | Agencies first; open-source the core to earn technical credibility |
| Anthropic dependency | Adapter interface at the LLM boundary; the no-transfer mode already requires a second path |

---

## Sources

- [Fin AI — pricing comparison](https://fin.ai/learn/ai-customer-service-agent-pricing-comparison) · [Fin AI — agents compared](https://fin.ai/learn/ai-customer-service-agents-compared)
- [AI agent pricing benchmark 2026, 18 vendors](https://aissist.io/industries/ai-agent-pricing-benchmark-2026)
- [EU AI Act — Article 50 enforcement and fines](https://www.aiactblog.nl/en/posts/article-50-enforcement-fines-ai-act-2026)
- [EU AI Act — penalties](https://www.euaiact.com/key-issue/1) · [enforcement live, Aug 2026](https://enterprisedna.co/resources/news/eu-ai-act-enforcement-fines-live-gpai-august-2026/)
- [High-level summary of the AI Act](https://artificialintelligenceact.eu/high-level-summary/) · [European Commission — AI Act](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
- Reference product: [getevo.ai](https://getevo.ai/) · [blotout.io](https://www.blotout.io/)
