
## spec-i2.md

# Spec I2 — Sandbox Sender

**Spec ID:** I2  
**Epic:** epic-i  
**Title:** Sandbox log-sink sender with strict idempotent `SendAttempt` creation

## Goal

Implement the only allowed send execution path in v0.1:

Create or reuse a `SendAttempt` exactly once per idempotency key, then write a redacted sandbox log-sink record.

No real delivery, no external network calls, and no test inbox behavior.

## Scope

### In scope
- `SendAttempt` create-or-reuse logic
- Deterministic `send_id` and `idempotency_key`
- Sandbox execution path using local log sink or structured event sink only
- Redacted logging of template metadata, claim hashes, and evidence references

### Out of scope
- ESP or API delivery
- Test inbox delivery
- Webhook callbacks
- Provider polling
- Mailbox sync
- Reply capture
- Token generation for unsubscribe links beyond placeholder presence checks

## Contract touchpoints

### Required `SendAttempt` fields
- `send_id`
- `draft_id`
- `channel`
- `provider`
- `status`
- `idempotency_key`
- `policy_pack_id`
- `created_at`

### Canonical formulas
- `send_id = "send:<draft_id>:<channel>"`
- `idempotency_key = "send:<draft_id>:<channel>:v1"`

### Locked fields
- `provider = SEND_SRC_01`
- `policy_pack_id = safe_v0_1`
- `initial_status = queued`

### Replay rule
Reprocessing the same `sending_dispatch` work item must be a no-op or deterministic reuse of the same `SendAttempt` row.

### Sandbox behavior

#### Allowed
- Create or reuse `SendAttempt`
- Write redacted structured events or outcomes
- Write to sandbox log sink only

#### Forbidden
- Real ESP delivery
- External network send calls
- Mailbox probing
- Reply ingestion

## Implementation requirements

- Build a `sandbox_log_sink_only` sender adapter or service
- Keep it internal-only and side-effect-bounded
- Before creating a `SendAttempt`, compute:
  - `send_id = send:<draft_id>:<channel>`
  - `idempotency_key = send:<draft_id>:<channel>:v1`
- Enforce uniqueness on both `send_id` and `idempotency_key`
- On replay, fetch and reuse the existing row
- Initial `SendAttempt.status` must be `queued`
- Persist only redacted output in the sandbox log sink:
  - domain only or hashes for recipient identity
  - `template_id` or deterministic draft reference
  - claim hashes
  - linked `evidence_ids`
  - no full message body
  - no full email address
- Keep provider value fixed to `SEND_SRC_01` until `PH-001` is resolved

## Deliverables
- Sandbox sender service or adapter
- `SendAttempt` create-or-reuse repository logic
- Redacted sandbox log sink writer
- Replay-safe tests
- Tests proving zero external network send behavior

## Acceptance criteria
- On an allowed sandbox path, at most one `SendAttempt` row exists per idempotency key
- Replaying the same work item does not create duplicate `SendAttempt` rows
- The sandbox path writes a redacted sink record
- No full email or body is logged
- No network send side effects occur
- Provider is always `SEND_SRC_01` in Epic I v0.1
