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
| 2026-09-06 | M0-2 Schema, migrations, RLS | ✅ | **AC executed in CI against a live pgvector service** — [run 34006500710](https://github.com/ejazfahil/Universal_Sales_Agent_Multi_Tenant/actions/runs/34006500710): `6 passed` in `tests/integration`, explicitly asserted not-skipped. Migrations `up → down → up` clean. `mypy --strict` 8 files clean · `ruff` clean (25 files) · unit `9 passed`. Took **3 failed CI rounds** to get right; see Decisions. |
| 2026-09-06 | M0-3 Append-only audit log | ✅ | Grants + trigger. Test asserts a **superuser** UPDATE also raises — grants alone do not bind one. |
| 2026-09-06 | M0-4 Tenant auth + RBAC | ✅ | Signed bearer token, constant-time compare. `viewer` gets 403 on `/approvals`. Settings refuse to boot staging/prod on the placeholder secret. |
| 2026-09-06 | M0-5 Pseudonymisation gateway | ✅ | 50-message golden set across EU languages, asserted on the **serialized** body. Round-trip lossless, tokens tenant-scoped, and a test proving `assert_clean` actually fires. |
| 2026-09-06 | M0-6 Tool layer | ✅ | READ/WRITE/MONEY/CONTROL classification, `strict: true` schemas, fixture backend behind a real interface. |
| 2026-09-06 | M0-7 Agent runner | ✅ | Gateway wraps the model call itself. Real `response.usage` → `cost_cents`. `stop_reason == refusal` handled as failure, not an empty answer. |
| 2026-09-06 | M0-8 Confidence + gate | ✅ | `min()` of four signals. 20+ table-driven tests incl. *a trusted rule cannot unlock money* and *one reversal demotes instantly*. |
| 2026-09-06 | M0-9 Approvals + Art. 50 + GDPR | ✅ | Disclosure in 10 EU languages with base-language fallback; verified live (`locale=de` → German). Erasure scope names vectors + vault. |
| 2026-09-06 | M0-10 Minimal operator UI | ✅ | Console at `/`, verified in a browser. Surfaces the **weakest** signal, not a composite badge. Keyboard A/E/D. |
| 2026-09-06 | M0-11 Injection eval | ✅ | 30 adversarial messages, 0 unlock money and 0 leak identifiers. Immediately caught a real bug: `#4821` used as a sample in a tool schema. |

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
| 2026-09-06 | **RLS requires a non-superuser role — `FORCE` is not enough** | First CI run against real Postgres showed RLS doing *nothing*: tenant A saw 2 customers, an unset GUC saw 2, cross-tenant INSERT succeeded. Superusers bypass RLS unconditionally; `FORCE ROW LEVEL SECURITY` subjects the table *owner*, not a superuser. Migration 0003 adds `usa_app` (NOLOGIN, NOSUPERUSER, NOBYPASSRLS) assumed via `SET LOCAL ROLE`. **The isolation test now asserts `current_setting('is_superuser') = 'off'` first**, so this cannot regress into passing for the wrong reason. |
| 2026-09-06 | RLS policy uses `NULLIF(current_setting(...), '')::uuid` | With a bare cast, an explicitly *empty* GUC hits `''::uuid` and raises `invalid input syntax for type uuid`. Raising is the wrong failure mode — an error invites an except-and-continue upstream, whereas a NULL comparison filters every row. Now fails closed and silently. |
| 2026-09-06 | I6 guard is AST-based, not `grep` | The grep guard failed CI on `app/db/models.py`, whose docstring explains why there is no sentiment column. Weakening the invariant was the wrong fix: a guard that punishes documentation gets the documentation deleted to make CI green, which defeats a control whose purpose is auditability. `scripts/check_no_emotion_inference.py` inspects identifiers, attributes, args, keywords, class/function names and non-docstring literals. Verified three ways: clean tree passes, planted `sentiment = "frustrated"` rejected, docstring naming the invariant allowed. |
| 2026-09-06 | Migration 0002 amended in place rather than superseded | Nothing is deployed and CI rebuilds from base each run, so a fix-up migration correcting a policy created seconds earlier would be noise. This stops being acceptable the moment anything is deployed. |

## Verification gates (M0 exit)

- [x] Tenant B cannot read tenant A's data with RLS on and no `WHERE` clause — *verified in CI run 34006500710, as a non-superuser role*
- [x] `UPDATE audit_logs` raises at the database
- [x] Serialized Anthropic request body contains zero raw identifiers
- [x] Conversation opens with a localised AI disclosure
- [ ] Erasure removes the subject from Postgres, pgvector and the vault — *scope published at `/gdpr/erasure-scope`; full cascade lands with M1 persistence*
- [x] `pytest tests/ -q` green; injection eval 0/30 breaches
- [x] `ruff check .` and `mypy --strict app/` clean
