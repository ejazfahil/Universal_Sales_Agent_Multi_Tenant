# Execution Ledger

Append only. Never rewrite history. Update in the **same commit** as the work.

Format: `| date | ticket | status | evidence / notes |`
Status: ✅ done · 🟡 in progress · ⛔ blocked · ⬜ todo

---

## Current milestone: **M0 — thin vertical slice**

Spec: [`BUILD_PROMPT.md`](BUILD_PROMPT.md) §5. Read it before starting a ticket.

| Date | Ticket | Status | Evidence / notes |
|---|---|---|---|
| 2026-09-06 | — | ✅ | Research + specification complete. `docs/01`, `docs/02`, `docs/03` published. |
| | M0-1 Scaffold + CI | ⬜ | |
| | M0-2 Schema, migrations, RLS | ⬜ | |
| | M0-3 Append-only audit log | ⬜ | |
| | M0-4 Tenant auth + RBAC | ⬜ | |
| | M0-5 Pseudonymisation gateway | ⬜ | |
| | M0-6 Tool layer | ⬜ | |
| | M0-7 Agent runner | ⬜ | |
| | M0-8 Confidence + gate | ⬜ | |
| | M0-9 Approvals + Art. 50 + GDPR | ⬜ | |
| | M0-10 Minimal operator UI | ⬜ | |
| | M0-11 Injection eval | ⬜ | |

## Blockers

*None yet. Log any blocker here with the ticket id, what you tried, and what you need — then take the next unblocked ticket.*

## Decisions log

Record any judgement call a future agent would otherwise re-litigate.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-06 | M0 is a thin vertical slice, not the full replica UI | A polished UI over mock data is exactly what the reference product already has. Our claim is that ours is real, so the first milestone must prove the architecture end to end rather than the pixels. |
| 2026-09-06 | `sentiment` replaced by deterministic `urgency` | Customer-facing emotion recognition is high-risk under the EU AI Act from 2026-08-02. Deterministic urgency gives identical routing and keeps the system limited-risk. |
| 2026-09-06 | Pseudonymisation gateway rather than "EU-hosted model" | Verified: Anthropic `inference_geo` accepts only `us`/`global`; there is no EU value. Tokenising at the EEA boundary is the honest architecture. |

## Verification gates (M0 exit)

- [ ] Tenant B cannot read tenant A's data with RLS on and no `WHERE` clause
- [ ] `UPDATE audit_logs` raises at the database
- [ ] Serialized Anthropic request body contains zero raw identifiers
- [ ] Conversation opens with a localised AI disclosure
- [ ] Erasure removes the subject from Postgres, pgvector and the vault
- [ ] `pytest tests/ -q` green; injection eval 0/30 breaches
- [ ] `ruff check .` and `mypy --strict app/` clean
