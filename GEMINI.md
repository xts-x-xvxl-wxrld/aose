# GEMINI.md — AI Outbound Support Engine (SaaS Prototype)

## Purpose of this file
This file enforces non-negotiable build behavior for coding assistants. It must not restate contracts, schemas, stage vocabularies, or field shapes.

If anything in this file conflicts with sources of truth listed below, this file loses.

## Sources of truth (do not duplicate here)
1) Data Spine contract (canonical data shapes, stage vocabulary, idempotency/dedup semantics):
- `docs/data-spine-v0.1.md`

2) Guardrails + governance (safety constraints, redaction expectations, policy defaults):
- `docs/policy/` (or the project’s policy pack file if not yet split)

3) Architectural decisions (why a dependency/approach was chosen):
- `docs/adr/`

4) Epic-specific build constraints and deterministic workflow rules (if present):
- `AGENT_RULES.md`, `SPEC.md`, `contract.yaml`, and any Epic documents under `docs/`

Rule: never introduce a new “mini-contract” in comments, READMEs, or this file. Add/adjust the contract only in the canonical contract docs.

## Mission (thin slice only)
Build a working SaaS prototype of an Outbound Support Engine using a Data Spine + Modular Organs architecture:
SellerProfile → QueryObjects → Account discovery → Fit/Intent scorecard → Contacts (manual import allowed) → Drafts + evidence anchors → Approval.
Sending exists but is gated and disabled by default.

## Operator control (no autonomous project running)
- Do not “rush execution.” Do not run multi-stage build sequences unless the operator provides an explicit ticket/prompt for that stage.
- Stay within the current ticket scope. If more work is needed, write a short TODO list for follow-up tickets.

## Non-goals (v0.1)
- No improvisational multi-step agents that invent new flows.
- No automatic sending during early testing.
- No heavy enrichment, mailbox probing, or scraping frameworks unless explicitly requested.
- No secrets in repo. No credentials committed.

## Non-negotiable architectural invariants
1) Data Spine is the system of record
- Canonical records live in Postgres.
- WorkItems are the only objects moving through the queue.
- All stage semantics and record shapes must match `docs/data-spine-v0.1.md`.

2) Organs are replaceable modules
- Each organ reads one WorkItem at one stage and writes canonical outputs plus structured events.
- Organs never call each other directly. They enqueue the next WorkItem.

3) Replay safety is mandatory
- Reprocessing must be a no-op or deterministic overwrite.
- Idempotency must prevent duplicate side effects.
- If deterministic behavior is unclear, do not invent rules: add a TODO marked “open for review” and stop.

4) Evidence-grounded outputs
- Scorecards and drafts must link claims/reasons to Evidence IDs.
- Personalization anchors must reference evidence IDs (no free-floating claims).

5) Attempts are bounded
- External calls (sources/models/paid tools) must consume attempt budget and stop at zero.
- When attempts are exhausted, park safely with a machine-readable reason.

## Safety switch (sending)
- Sending is disabled by default via a feature flag / env var.
- When disabled, `sending_dispatch` must park safely and create zero provider side effects.

## Data handling and logging (must comply)
- Canonical tables may store PII only when needed for system function.
- Structured events must be redacted by default: no raw emails/phones, no full message bodies, no secrets.
- Log only what is required for replay/explainability and debugging.

## Repo conventions (minimum)
Monorepo layout:
- `api/`     FastAPI app, REST endpoints, minimal admin views if needed
- `worker/`  queue consumer, stage router, organ handlers
- `web/`     minimal UI (thin)
- `docs/`    contracts, prompts, ADRs, policy
- `infra/`   docker-compose, local scripts

## Build rules (how to change the system)
- Prefer small, mergeable diffs. Avoid broad refactors.
- Any DB schema change requires migrations. No “handwaved” schema.
- Add tests for deterministic IDs and idempotency/replay behavior where relevant.
- Every handler writes structured events: inputs/outputs/metrics/outcome/error_code.
- If a dependency choice is ambiguous, pick the simplest viable option and record it in `docs/adr/`.

## Local dev ergonomics (required)
- `make dev` boots Postgres+Redis and runs api+worker.
- `make test` runs unit tests.
- `make fmt` and `make lint` exist and are enforced in CI.
- Provide `.env.example` and read config from env vars.

## Ticket output expectation (definition of “done”)
For any implementation ticket:
- code + migrations
- tests
- minimal docs update (only if a canonical doc is changed)
- runnable verification steps (commands + expected outcomes)
