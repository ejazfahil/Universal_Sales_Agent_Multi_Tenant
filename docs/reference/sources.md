# Sources

Annotated bibliography for the research behind this project.

**A deliberate choice:** this repository is public, so third-party articles are **linked, not mirrored**. Vendor blog posts and marketing pages are copyrighted; bulk-copying them into a public repo is a licensing problem regardless of intent. What is stored locally is either officially reusable (EU legislative text), factual data (colour values, published prices), or written from scratch.

Retrieved 2026-09-04 to 2026-09-06. Web content changes — re-verify before relying on a figure in a customer-facing document.

---

## Stored locally

| File | Contents | Provenance |
|---|---|---|
| `eu-ai-act-obligations.md` | Articles 12, 14, 50 summarised and mapped to tickets | Summaries written here; EU legislative text is officially reusable |
| `design-tokens.css` | Colour, typography and layout values | Factual values extracted from a public stylesheet |

---

## Regulation — authoritative

| Source | Use |
|---|---|
| [EUR-Lex 32024R1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) | **The AI Act itself.** Cite this, not a summary, in any compliance claim. |
| [European Commission — AI regulatory framework](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) | Official guidance and implementation timeline |
| [artificialintelligenceact.eu](https://artificialintelligenceact.eu/high-level-summary/) | Article-by-article browsing. Convenient, unofficial. |
| [AI Act penalty structure](https://www.euaiact.com/key-issue/1) | €35M/7%, €15M/3%, €7.5M/1% tiers |
| [Article 50 enforcement analysis](https://www.aiactblog.nl/en/posts/article-50-enforcement-fines-ai-act-2026) | Confirms Art. 50 was **not** postponed by the Digital Omnibus |
| [Stibbe — transparency obligations](https://www.stibbe.com/publications-and-insights/the-ai-acts-transparency-obligations-rules-scope-and-timeline) | Law-firm reading of scope and timeline |

**GDPR** — Art. 15 (access), 17 (erasure), 28 (processor), 44–49 (transfers) govern the DSAR, erasure and cross-border design. Read at [EUR-Lex 32016R0679](https://eur-lex.europa.eu/eli/reg/2016/679/oj).

---

## Market and competitive

| Source | Use |
|---|---|
| [Fin AI — pricing comparison](https://fin.ai/learn/ai-customer-service-agent-pricing-comparison) | Per-resolution pricing across vendors |
| [Fin AI — agents compared](https://fin.ai/learn/ai-customer-service-agents-compared) | Resolution-rate benchmarks (70–84% band) |
| [Aissist — 18-vendor pricing benchmark](https://aissist.io/industries/ai-agent-pricing-benchmark-2026) | Decagon, Sierra, Kore.ai contract sizes |
| [Lorikeet — cost per resolution vs BPO](https://www.lorikeetcx.ai/articles/ai-vs-outsourcing-support-cost-per-resolution-2026) | Framing of the cost-per-resolution metric |

⚠️ Vendor-published comparisons are marketing. Treat competitor figures as directional; verify our own numbers against our own eval set.

---

## Reference product — Evo AI / Blotout

| Source | Use |
|---|---|
| [getevo.ai](https://getevo.ai/) · [demo](https://demo.getevo.ai/) | The UI and interaction model specified in `docs/01-master-plan.md` |
| [blotout.io](https://www.blotout.io/) · [EdgeTag](https://www.blotout.io/edgetag) · [ConsentIQ](https://www.blotout.io/consentiq) | The four-layer vertical map in `docs/02` §B |
| [AI agent governance](https://getevo.ai/post/ai-agent-governance-for-customer-support-preventing-hallucination-privacy-leaks) | Their four governance domains — accuracy, action, privacy, policy drift |
| [Agentic support guide](https://getevo.ai/post/agentic-customer-support-guide-2026) | Agentic vs rule-based definitions |
| [12 agentic workflows](https://getevo.ai/post/12-agentic-ecommerce-workflows-already-running-in-2026) | The vertical build backlog in `docs/02` §B Layer 3 |
| [What is an AI sales agent](https://getevo.ai/post/what-is-an-ai-sales-agent-the-2026-guide) | Assistant vs replacement autonomy ladder |
| [Cost per resolution](https://getevo.ai/post/cost-per-resolution-support-metric) | The metric we adopt and instrument properly |
| [TechCrunch — Blotout seed](https://techcrunch.com/2021/11/03/blotout-raises-3m-seed-to-build-privacy-focused-customer-data-platform/) · [Crunchbase](https://www.crunchbase.com/organization/blotout) | Company background |

---

## Technical

| Source | Use |
|---|---|
| [`fauzan111/Multi-Tenant-AI-Customer-Support-Agent-Platform`](https://github.com/fauzan111/Multi-Tenant-AI-Customer-Support-Agent-Platform) | **MIT.** Backend skeleton adopted in `docs/02` §A — tenant-scoped vector store, audit spine, deterministic gate philosophy. Linked, not vendored; fork it when M0-2 starts. |
| [Anthropic API docs](https://docs.claude.com/en/api/) | Tool Runner, adaptive thinking, prompt caching, `inference_geo` |
| [Shopify Admin GraphQL](https://shopify.dev/docs/api/admin-graphql) | Order, customer, refund and fulfilment tools |
| [pgvector](https://github.com/pgvector/pgvector) | Vector storage with tenant-scoped SQL filtering |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) · [multilingual-e5](https://huggingface.co/intfloat/multilingual-e5-large) | Candidate EU-hostable multilingual embeddings (ticket G5) |
| [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | LLM01 prompt injection, LLM06 data disclosure — the threat model behind invariants I3 and I5 |

---

## Verified findings worth restating

Two claims in this project were checked rather than assumed. Both shape the architecture:

1. **`inference_geo` accepts only `"us"` or `"global"`.** There is no EU value, on any platform. EU inference pinning for a frontier model is not available — hence pseudonymisation at the EEA boundary. *(Verified against the Anthropic platform-availability reference, 2026-09-04.)*

2. **The reference product's demo makes zero API calls.** Its metrics, tickets and reasoning traces are hardcoded client-side and timer-driven. *(Verified by network trace and JS bundle analysis, 2026-09-04.)* This is why M0 is a working vertical slice rather than a prettier mock.
