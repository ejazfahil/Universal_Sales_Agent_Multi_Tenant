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
| 2026-09-06 | M0-1 Scaffold + CI | ✅ | `ruff check` clean · `ruff format --check` clean (13 files) · `mypy --strict app/` → **Success: no issues found in 5 source files** · `pytest -q` → **9 passed** · live `GET /health` → **200** `{"status":"ok","version":"0.1.0","environment":"local","region":"eu-central-1","region_is_eea":true}` · `docker compose config` → **VALID**. ⚠️ `docker compose up` not executed — Docker daemon not running on this machine. See Blockers. |
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

| Ticket | Blocker | Tried | Needed |
|---|---|---|---|
| M0-1 | `docker compose up → GET /health 200` could not be executed | Docker 29.5.3 and Compose v5.1.4 are installed, but `docker info` reports the daemon is not running. Validated the compose file statically with `docker compose config` (VALID) and verified the same endpoint over real HTTP against a local uvicorn process (200). | Start Docker Desktop, then run `docker compose up -d && curl -i localhost:8000/health` and tick the box below. The container path is unverified until someone does. |

## Decisions log

Record any judgement call a future agent would otherwise re-litigate.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-06 | M0 is a thin vertical slice, not the full replica UI | A polished UI over mock data is exactly what the reference product already has. Our claim is that ours is real, so the first milestone must prove the architecture end to end rather than the pixels. |
| 2026-09-06 | `sentiment` replaced by deterministic `urgency` | Customer-facing emotion recognition is high-risk under the EU AI Act from 2026-08-02. Deterministic urgency gives identical routing and keeps the system limited-risk. |
| 2026-09-06 | Pseudonymisation gateway rather than "EU-hosted model" | Verified: Anthropic `inference_geo` accepts only `us`/`global`; there is no EU value. Tokenising at the EEA boundary is the honest architecture. |
| 2026-09-06 | Ruff excludes `docs/` | `ruff format` formats Python inside fenced Markdown blocks. Left unconfigured it silently rewrites the illustrative code in the specification documents — CI would have reformatted `docs/01` and `docs/02`. `extend-exclude = ["docs", ".venv"]`. |
| 2026-09-06 | Region is a validated setting, not deployment trivia | `Settings` refuses to boot in `staging`/`production` outside an EEA region. Invariant I5 is meaningless if the app itself runs in Ohio, so the guard fails closed at startup rather than being a wiki page. `/health` reports `region_is_eea` so a probe surfaces misconfiguration. |
| 2026-09-06 | I6 guard added to CI at M0-1, before any agent code exists | Cheaper to establish the tripwire while `app/` is empty than to retrofit it after someone copies a `sentiment` field from the reference fixtures. Verified in both directions: passes clean, and fires on a planted violation. |
| 2026-09-06 | `httpx2` instead of `httpx` for the test client | Starlette's `TestClient` emits `StarletteDeprecationWarning` with `httpx`. Swapped in `pyproject.toml`; warning count dropped 2 → 1. |

## Verification gates (M0 exit)

- [ ] Tenant B cannot read tenant A's data with RLS on and no `WHERE` clause
- [ ] `UPDATE audit_logs` raises at the database
- [ ] Serialized Anthropic request body contains zero raw identifiers
- [ ] Conversation opens with a localised AI disclosure
- [ ] Erasure removes the subject from Postgres, pgvector and the vault
- [ ] `pytest tests/ -q` green; injection eval 0/30 breaches
- [ ] `ruff check .` and `mypy --strict app/` clean
