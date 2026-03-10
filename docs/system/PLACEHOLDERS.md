# PLACEHOLDERS.md
Central ledger for all unresolved decisions and missing required facts across all epics.
Rule: if a required value is unknown, create/update an entry here and reference its PH-ID in code/docs.
Rule: do not invent values to "move forward"; use allowed temporary defaults only.
Rule: use the format `PH-<EPIC-ID>-<nnn>` for all new entries (e.g. PH-EPIC-B-001). Legacy entries PH-001–004 predate this convention.

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

## PH-004 — Enforce CI Invariants (TEST_STUB)
Status: OPEN
Epic: Epic A
Blocking: NO (subsystems not yet fully built)
Decision needed: implementations for schema validation, idempotency, budget exhaustion, and send gating.
Forbidden assumptions: invariants cannot be silently omitted.
Temporary default allowed: skipped test referencing PH-004 that the CI pipeline explicitly checks for.
Acceptance stub: CI grep check ensures PH-004 remains in the pytest skip reason.

---

## PH-EPIC-B-001 — Scorecard ID formula (ID_FORMULA)
Status: OPEN
Epic: Epic B
Blocking: NO (Scorecard not yet implemented; placeholder deferred until B6)
Decision needed: whether the Scorecard ID formula needs a scoring version identifier beyond current examples, and if so what the frozen format is
Forbidden assumptions: do not invent a versioned Scorecard ID formula without explicit lock
Temporary default allowed: use sha256-based content hash of entity_ref + computed_at until frozen
Acceptance stub: Scorecard ID generation is deterministic and covered by tests when B6 is implemented

## PH-EPIC-B-002 — Send provider enum expansion (PROVIDER_ENUM)
Status: OPEN
Epic: Epic B
Blocking: NO (sending disabled; SEND_SRC_01 is the only locked provider in v0.1)
Decision needed: whether additional send provider enum values are needed before Epic C, and what their identifiers are
Forbidden assumptions: do not expand provider enum beyond SEND_SRC_01 without explicit lock
Temporary default allowed: SEND_SRC_01 only; all other providers are out of scope for Epic B
Acceptance stub: send_attempt.provider field accepts SEND_SRC_01; no external send side effects in Epic B

## PH-EPIC-B-003 — ApprovalDecision reviewer role model (SCHEMA)
Status: OPEN
Epic: Epic B
Blocking: NO (ApprovalDecision not yet implemented; placeholder deferred until B9)
Decision needed: whether the ApprovalDecision schema needs a multi-reviewer model or role expansion beyond a single reviewer_id + reviewer_role
Forbidden assumptions: do not widen the approval schema to multi-reviewer without explicit lock
Temporary default allowed: single reviewer_id + reviewer_role fields as defined in the canonical shape
Acceptance stub: ApprovalDecision stores reviewer fields as specified; schema matches contract when B9 is implemented

---

## PH-EPIC-E-001 — Real account discovery adapter selection (PROVIDER_ENUM)
Status: OPEN
Epic: Epic E
Blocking: NO for interface/tests; YES for real-adapter production of external discovery data
Decision needed: Choose the first real account discovery source (e.g. registry-based source such as AJPES or an existing lead source) and bind it to a stable provider enum value.
Forbidden assumptions: Do not invent a provider not chosen by the human. Do not claim coverage or legality characteristics not documented by the chosen source.
Temporary default allowed: dummy_predictable adapter for tests and local deterministic verification only.
Acceptance stub: DummyPredictableAdapter returns valid AccountDiscoveryResult; real adapter slot remains unbound until decided.

## PH-EPIC-E-002 — max_accounts_per_query_object cap value (POLICY_VALUE)
Status: OPEN
Epic: Epic E
Blocking: NO if local config default is used; contract still requires the cap to exist
Decision needed: Choose the exact per-query-object account cap for discovery runs.
Forbidden assumptions: Do not leave per-query account growth unbounded.
Temporary default allowed: 10 (as specified in the Epic E contract locked_defaults)
Acceptance stub: Discovery run stops at per-query-object cap; cap value is config-driven and not hard-coded beyond the temporary default.

---

## PH-EPIC-G-001 — Real people search adapter selection (PROVIDER_ENUM)
Status: OPEN
Epic: Epic G
Blocking: NO for interface/tests; YES for real-adapter production of contact data
Decision needed: Choose the first real people search source (e.g. LinkedIn API, Clay, Apollo) and bind it to a stable provider enum value.
Forbidden assumptions: Do not invent a provider not chosen by the human. Do not claim coverage or legality characteristics not documented by the chosen source.
Temporary default allowed: dummy_predictable_people adapter for tests and local deterministic verification only.
Acceptance stub: DummyPredictablePeopleAdapter returns valid ContactCandidate list; real adapter slot remains unbound until decided.
