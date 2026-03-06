# PLACEHOLDERS.md
Central ledger for unresolved decisions and missing required facts.
Rule: if a required value is unknown, create/update an entry here and reference its PH-ID in code/docs.
Rule: do not invent values to “move forward”; use allowed temporary defaults only.

## Status values
OPEN | DECIDED | DEFERRED | DROPPED

## Entry template
## PH-XXX — <short name> (<TYPE>)
Status: OPEN
Epic: <epic-id>
Blocking: YES|NO (<why>)
Decision needed: <what human must decide>
Forbidden assumptions: <what the system must not guess>
Temporary default allowed: <what is allowed until decided>
Acceptance stub: <testable condition / invariant>

---

## PH-001 — Send provider selection (PROVIDER_ENUM)
Status: OPEN
Epic: Epic A
Blocking: NO (sending is gated/disabled in v0.1; use sandbox/log sink)
Decision needed: choose SEND_SRC_01 actual provider + auth method (later)
Forbidden assumptions: do not pick a real ESP; do not enable sending by default
Temporary default allowed: sandbox sender writes to Data Spine only; no external network calls
Acceptance stub: SendAttempt created once per idempotency_key; no external send side effects

## PH-002 — Evidence retention window (POLICY_VALUE)
Status: OPEN
Epic: Epic A
Blocking: NO (use safe default until policy is decided)
Decision needed: exact retention period (days) for EvidenceContent
Forbidden assumptions: do not delete evidence earlier than configured; do not claim compliance guarantees
Temporary default allowed: 180 days
Acceptance stub: retention_days config exists; purge job can be a no-op in v0.1 but must be idempotent

## PH-003 — Worker RQ queue name (STRING)
Status: OPEN
Epic: Epic A
Blocking: NO (use default queue for verification)
Decision needed: exact queue name(s) the worker must consume from Redis
Forbidden assumptions: do not invent production queue topologies or names
Temporary default allowed: listen to "default" queue
Acceptance stub: worker successfully connects to Redis and blocks on generic "default" queue

---

## PH-004 — Enforce CI Invariants (TEST_STUB)
Status: OPEN
Epic: Epic A
Blocking: NO (subsystems not yet fully built)
Decision needed: implementations for schema validation, idempotency, budget exhaustion, and send gating.
Forbidden assumptions: invariants cannot be silently omitted.
Temporary default allowed: skipped test referencing PH-004 that the CI pipeline explicitly checks for.
Acceptance stub: CI grep check ensures PH-004 remains in the pytest skip reason.
