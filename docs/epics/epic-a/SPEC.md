# Epic A — Repo + Local Environment (Foundation)

## Purpose
Create a deterministic local development foundation you stop thinking about: a single monorepo with an API, a worker, a minimal web UI, and docs; reproducible local stack (Postgres + Redis); and CI sanity checks (format, lint, unit tests).

All implementation-level choices (ports, service names, frameworks, exact Make targets, CI runners) are defined in `docs/epics/epic-a/CONTRACT.yaml`. This SPEC defines intent, scope, and acceptance.

## Scope (In)
A1. Monorepo skeleton
- Create a single repository with these top-level directories:
  - `api/` (Python API service)
  - `worker/` (Python worker service)
  - `web/` (minimal UI scaffold)
  - `docs/` (project docs, including system + epic docs)

A2. Local stack via Docker Compose
- Provide `docker-compose.yml` (or equivalent compose config per CONTRACT) to run:
  - Postgres
  - Redis
- Ensure the API can connect to Postgres.
- Ensure the worker can connect to Redis.

A3. CI sanity pipeline
- Add CI workflow that runs on PR and main pushes (per CONTRACT).
- Enforce:
  - formatting checks
  - lint checks
  - unit tests
- Ensure failing tests fail the workflow.

## Out of Scope (Not in Epic A)
- Production deployment, hosting, or domains
- Authentication, billing, payments
- Email sending, outbound automation, “real” business logic
- Full UI/UX
- Observability stack (metrics/tracing) beyond minimal logs
- Integration tests / e2e tests (unit tests only unless CONTRACT explicitly adds more)
- Any non-local dependencies requiring paid SaaS state

## Constraints and Guardrails
- Determinism: decisions live in CONTRACT; no silent decisions; missing details become placeholders.
- Idempotency: rerun does not create duplicates or drift.
- Safety defaults:
  - Policy pack defaults to `safe_v0_1`.
  - Any “send” capability is disabled by default and must not be implemented in Epic A; only configuration touchpoints may be reserved.

## Deliverables (Artifacts)
Repo root:
- `README.md` describing how to run dev/test/lint
- `Makefile` exposing dev/test/lint/fmt targets per CONTRACT
- `.env.example` containing required env vars (safe dummy values)
- `docker-compose.yml` (or compose file specified by CONTRACT)
- CI workflow under `.github/workflows/` (file name per CONTRACT)

Services:
- `api/` scaffold with a minimal runnable server process
- `worker/` scaffold with a minimal runnable worker process
- `web/` minimal scaffold (can be placeholder UI; must build/run per CONTRACT if required)
- `docs/` includes system + epic docs, and reserved integration docs:
  - `docs/system/AGENT_RULES.md`
  - `docs/epics/epic-a/SPEC.md`
  - `docs/epics/epic-a/CONTRACT.yaml`
  - `docs/epics/epic-a/PLACEHOLDERS.md`
  - `docs/policy/policy-pack-safe-v0_1.md`
  - `docs/data-spine/DATA-SPINE-v0.1.md`

## Acceptance Criteria (Hard Gates)

### A1 — Monorepo skeleton
Acceptance:
- The repo contains `api/`, `worker/`, `web/`, `docs/` at top-level.
- `make dev` brings up the API and Postgres such that:
  - API process is running (reachable on the configured local port)
  - API can connect to Postgres (connection attempt succeeds; health endpoint or startup log confirms)

### A2 — Docker compose for Postgres + Redis
Acceptance:
- Docker compose starts Postgres and Redis reproducibly.
- API connects to Postgres using `DATABASE_URL` from `.env.example` (or contract-defined env schema).
- Worker connects to Redis using `REDIS_URL` from `.env.example` (or contract-defined env schema).

### A3 — CI sanity pipeline
Acceptance:
- A PR fails if:
  - formatting check fails
  - lint check fails
  - unit tests fail
- CI runs on pull requests and pushes to main (or contract-defined branches).
- Local equivalents exist via Make targets and match CI behavior (same toolchain, same commands).

## Verification Procedure (What “done” looks like)
The agent must run (or output as UNEXECUTED with reason) the contract-defined commands that prove acceptance. Minimum expected checks:
- `make dev` (API + DB up)
- `make test` (unit tests)
- `make lint` (lint gate)
- `make fmt` or `make format-check` (format gate; naming per CONTRACT)
- `docker compose up` (or via make) shows Postgres + Redis healthy (healthchecks if present)

Evidence required in the execution report:
- Commands executed
- Pass/fail per command
- If unexecuted: explicit reason + expected success signal

## Placeholders Policy (Controlled TBD)
- Any missing decision required to implement this epic must be registered in `docs/epics/epic-a/PLACEHOLDERS.md` with:
  - placeholder id (`PH-EPIC-A-###`)
  - missing decision
  - default stub behavior to use now
  - impact on acceptance (must not block unless SPEC explicitly allows)
  - follow-up acceptance test for resolution

## Parallelization (Allowed)
Two lanes are allowed if they do not overlap file ownership:
- Infra lane: root tooling, compose, CI, `api/`, `worker/`, `docs/epics`, `docs/system`
- Web lane: `web/` only

If a change crosses lanes, split into separate commits with clear ownership.

## Definition of Done
Epic A is complete only when:
- All deliverables exist and match the CONTRACT.
- All acceptance criteria A1–A3 are verified as PASS (or reported UNEXECUTED with reason in environments that cannot run commands).
- Any uncertainty is explicitly captured in PLACEHOLDERS with default stubs and follow-up tests.