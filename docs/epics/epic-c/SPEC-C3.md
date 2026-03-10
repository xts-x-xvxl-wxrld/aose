# SPEC-C3 — Idempotency guard

## Goal
Implement a deterministic idempotency guard so replay or duplicate processing does not create duplicate protected side effects.

## Scope boundary
In scope:
- Pre-side-effect idempotency lookup
- Deterministic no-op behavior when protected output already exists
- Guarding protected writes and next-stage enqueue side effects
- Contract-compliant idempotent success behavior and event emission

Out of scope:
- Replay endpoint API itself
- New canonical ID formulas
- Changes to Epic B uniqueness and identifier contracts
- Business logic for downstream generation beyond guarded writes

## Contract authority
This spec is subordinate to `docs/epics/epic-c/CONTRACT-C.yaml`.
If implementation details conflict with the contract, the contract wins.

## Contract touchpoints
- `idempotency.baseline_guarantee`
- `idempotency.required_guard_behavior`
- `idempotency.protected_side_effects_minimum`
- `idempotency.allowed_replay_results`
- `idempotency.forbidden_replay_results`
- `replay.invariants`
- `queue_handoff.required_invariants`
- `canonical_enums.structured_event_types`
- `canonical_enums.structured_event_outcomes`
- Epic B deterministic IDs and idempotency key conventions inherited by Epic C

## Required behavior
1. Before any protected side effect is created, handler must check for existing output by:
   - `idempotency_key`, or
   - another replay-stable unique key defined by the canonical model
2. If protected output already exists, handler must:
   - become deterministic no-op,
   - not duplicate rows,
   - emit `handler_noop_idempotent`,
   - return a success-compatible outcome
3. At minimum, guard must protect:
   - derivative writes owned by a handler
   - `outreach_drafts`
   - `approval_decisions` via `decision_key` reuse
   - `send_attempts`
   - next-stage enqueue side effects when uniqueness is deterministic
4. Replay may only result in:
   - no-op against existing output
   - create missing output exactly once
   - safe rerun when protected output does not yet exist
   - same bounded park reason
   - same contract failure if input is still invalid
5. Replay must never result in:
   - duplicate side effects
   - duplicate `send_attempts`
   - duplicate drafts for the same protected key
   - bypassed policy checks
   - fresh decision when `decision_key` already exists

## Deliverables
- Shared idempotency guard module/decorator/helper
- DB access layer utilities for protected output lookup
- Integration into at least one representative protected write path and queue handoff path
- Unit/integration tests for:
  - duplicate work item processing
  - existing draft no-op
  - existing approval decision reuse
  - existing send attempt no-op
  - next-stage enqueue not duplicated when protected by deterministic uniqueness

## Implementation constraints
- Guard check must happen before protected create side effects.
- Guard cannot depend on in-memory process state only.
- Success-compatible no-op must be observable through structured event emission.
- Idempotency behavior must survive worker restart and replay.

## Acceptance checks
1. Processing the same protected-write work item twice results in only one persisted protected row.
2. Reprocessing a draft-generation work item does not create a second draft for the same idempotency key.
3. Reprocessing an approval-request work item reuses the existing `decision_key` outcome rather than creating a new decision.
4. Reprocessing a sending-dispatch work item does not create a second `SendAttempt`.
5. Reprocessing a handoff-producing work item does not enqueue duplicate next-stage work when deterministic uniqueness is in place.
6. CI proves the minimum gate: rerunning the same `WorkItem` does not duplicate protected side effects.
7. CI proves the minimum gate: replay preserves no-duplicate guarantees.

## Done definition
This ticket is done when at-least-once processing is safe for protected side effects and replay produces deterministic no-op or exactly-once creation behavior.

## AI build prompt
Implement SPEC-C3 for Epic C.

Use the Epic C contract and inherited Epic B idempotency conventions as the sole authority.

Build a shared idempotency guard with these rules:
- before protected side effects, look up existing output by `idempotency_key` or replay-stable unique key
- if output exists, do not create duplicates
- emit `handler_noop_idempotent`
- return a success-compatible outcome
- protect at minimum drafts, approval decisions, send attempts, derivative writes, and deterministic next-stage enqueue side effects

Deliver:
- shared idempotency helper/decorator
- DB lookup utilities
- tests proving duplicate processing does not duplicate protected rows
- tests for draft reuse, decision reuse, send-attempt no-op, and protected next-stage enqueue

Do not invent new ID formulas.
Do not rely on process memory for correctness.
Do not bypass policy or budget checks during replay.
