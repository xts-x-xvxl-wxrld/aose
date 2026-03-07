# CLAUDE.md — AI Outbound Support Engine

Claude-specific orientation file. Read this first, then read the referenced docs as needed.

## What this system does

AOSE is a SaaS prototype of an Outbound Support Engine: it takes a seller profile, generates structured search queries, discovers matching accounts, scores fit/intent, finds contacts, generates evidence-grounded outreach drafts, routes them through human approval, and gates sending behind a feature flag.

Pipeline stages (in order):
```
seller_profile_build → query_objects_generate → account_discovery →
intent_fit_scoring → people_search → contact_enrichment →
copy_generate → approval_request → sending_dispatch
```

Sending is **disabled by default** (`SEND_ENABLED=false`). Do not implement sending unless a contract explicitly enables it.

---

## Repository layout

```
api/        FastAPI service (port 8000) — REST endpoints, DB access, migrations
worker/     RQ worker — queue consumer, stage router, organ handlers
web/        React + TypeScript + Vite (port 5173) — minimal UI, currently a stub
docs/       Contracts, specs, runbooks, data spine
scripts/    dev.sh / dev.ps1 (thin wrappers; prefer make targets)
```

See `api/AGENT.md`, `worker/AGENT.md`, `web/AGENT.md` for per-module detail.

---

## Key commands

```bash
make dev        # Build and start full stack (API + worker + Postgres + Redis)
make test       # Run all tests inside containers
make lint       # Ruff lint (api/ + worker/)
make fmt        # Ruff format (api/ + worker/)
make db-migrate # Run Alembic migrations inside the api container
make down       # Stop all containers
```

**Windows rule:** never run pytest, ruff, or uvicorn directly on the host. Always run through `make` (which uses `docker compose run --rm`).

---

## Non-negotiable invariants

1. **Data Spine is the system of record.** Canonical records live in Postgres. WorkItems are the only objects on the queue. Never copy full records into queue payloads.

2. **Organs are replaceable modules.** Each organ reads one WorkItem at one stage, writes outputs, and enqueues the next WorkItem. Organs never call each other directly.

3. **Replay safety is mandatory.** Reprocessing must be a no-op or deterministic overwrite. Use `idempotency_key` on side-effect tables.

4. **Evidence-grounded outputs.** Scorecards and drafts must link every claim to Evidence IDs. No free-floating claims.

5. **Attempts are bounded.** External calls (source calls, model calls, paid enrichments) must decrement attempt budget and park with `budget_exhausted` when budget reaches zero.

6. **No silent decisions.** If a decision affects repo structure, ports, env vars, service names, Make targets, CI, or dependencies — it must come from a CONTRACT file. Missing decisions become placeholders in `docs/epics/<epic-id>/PLACEHOLDERS.md`.

7. **Scope control.** Only touch files required by the current ticket. No opportunistic refactors.

---

## Document authority order (read when implementing an epic)

1. `docs/system/AGENT_RULES.md` — execution rules (plan → scaffold → verify)
2. `docs/epics/<epic-id>/SPEC.md` — human intent and acceptance criteria
3. `docs/epics/<epic-id>/CONTRACT.yaml` — machine contract, single source of truth for build decisions
4. `docs/epics/<epic-id>/PLACEHOLDERS.md` — allowed TBDs with default stubs
5. `docs/data-spine/DATA-SPINE-v0.1.md` — canonical data shapes and stage vocabulary

If CONTRACT.yaml conflicts with SPEC.md, CONTRACT.yaml wins. If anything conflicts with `docs/system/AGENT_RULES.md`, AGENT_RULES.md wins.

---

## Open placeholders (as of Epic A)

| ID | Topic | Stub behaviour |
|----|-------|---------------|
| PH-001 | Send provider selection | Sandbox/no-op |
| PH-002 | Evidence retention window | 180 days default |
| PH-003 | Worker queue naming | Queue name: `"default"` |
| PH-004 | CI invariants (schema, replay, budget, send gating) | Test skipped with marker |

---

## Environment variables (see `.env.example`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `local` | Environment tag |
| `SEND_ENABLED` | `false` | Safety gate — keep false |
| `DATABASE_URL` | `postgresql+psycopg://aose:aose@postgres:5432/aose` | Postgres DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Redis DSN |
| `API_HOST` | `0.0.0.0` | uvicorn bind host |
| `API_PORT` | `8000` | uvicorn bind port |
| `WORKER_QUEUES` | `default` | RQ queue name |

Never commit `.env`. Always commit `.env.example` with safe dummy values.

---

## Definition of done (any ticket)

- Code + migrations (if DB schema changes)
- Tests for any deterministic/idempotent behaviour added
- Minimal doc update only if a canonical doc changed
- Runnable verification steps (commands + expected output)

---

## Architecture overview

See `docs/system/ARCHITECTURE.md` for the full system diagram and data flow.
