# Epic I Specs — Copy/Paste Markdown

## spec-i1.md

# Spec I1 — Sending Stage Handler Skeleton

**Spec ID:** I1  
**Epic:** epic-i  
**Title:** Sending stage handler skeleton with fail-closed gating

## Goal

Implement the `sending_dispatch` stage handler as a distinct worker path that consumes only payload version `1`, verifies all required preconditions, and fails closed when sending is disabled or policy conditions are not satisfied.

Under `safe_v0_1`, the default result is safe parking, not delivery.

## Scope

### In scope
- Stage routing for `sending_dispatch`
- Payload validation for `draft_id` and `decision_id`
- Canonical record loading for `OutreachDraft`, `ApprovalDecision`, `Contact`, and `Account`
- Gate evaluation needed to decide whether the item parks, retries, or proceeds to sandbox path
- Deterministic parked or fail-closed outcomes when sending is disabled or prerequisites are missing

### Out of scope
- Real ESP integration
- External network calls
- Mailbox probing
- Reply ingestion
- New canonical tables
- Provider-specific behavior beyond locked placeholder `SEND_SRC_01` and `PH-001`

## Contract touchpoints

### Consumed stage
- `sending_dispatch`

### Supported payload versions
- `1`

### Required payload fields
- `draft_id`
- `decision_id`

### Required preconditions
- `ApprovalDecision.status == approved`
- `ApprovalDecision.policy_pack_id == safe_v0_1`
- `OutreachDraft exists`
- `SendGate == PASS`

### Fail-closed rules
- If approval is missing, do not send
- If required canonical records are missing, park or contract-fail deterministically
- If policy evaluation is incomplete, do not send

### Locked defaults
- `send_enabled: false`
- `send_provider_enum: SEND_SRC_01`
- `send_mode: sandbox_log_sink_only`
- `external_send_side_effects: forbidden`

## Implementation requirements

- Add a dedicated sending handler behind the stage router
- Accept only `payload.v == 1`; unsupported versions must produce `contract_error`
- Load and verify `OutreachDraft`, `ApprovalDecision`, linked `Contact`, and linked `Account` before any send-path work
- Enforce approval contract exactly:
  - `approved` status only
  - required review fields present
  - no STOP-gate override behavior
- Evaluate gates in locked order:
  1. `HardSafetyGate`
  2. `BudgetGate`
  3. `DataQualityGate`
  4. `EvidenceGate`
  5. `FitScoreGate`
  6. `ContactabilityGate`
  7. `DraftClaimEvidenceGate`
  8. `SendGate`
- When `send_enabled=false`, return routing outcome `park safely`
- Do not create a `SendAttempt` when disabled
- Use redacted structured events only
- Never log full email, phone, or full message body

## Deliverables
- Sending handler module for `sending_dispatch`
- Payload validator for version `1`
- Precondition and gate-evaluation service for send eligibility
- Structured event or outcome writes for park, retry, and fail-closed decisions
- Unit tests covering disabled-send behavior, missing approval, missing records, and unsupported payload version

## Acceptance criteria
- A `sending_dispatch` work item with valid `draft_id` and `decision_id` but `send_enabled=false` is parked safely
- No `SendAttempt` row is created when disabled
- Missing `ApprovalDecision` or non-`approved` status blocks progression deterministically
- Unsupported payload version yields `contract_error`
- Missing required canonical records yields park or fail-closed behavior, not partial send behavior

## AI build prompt

Implement `spec-i1` for Epic I.

Build a dedicated `sending_dispatch` handler that consumes only payload version `1` with fields `draft_id` and `decision_id`.

Use the existing Data Spine models only:
- `OutreachDraft`
- `ApprovalDecision`
- `Contact`
- `Account`
- `SendAttempt`

Enforce the Epic I contract exactly:
- approval must exist
- approval status must be `approved`
- approval `policy_pack_id` must be `safe_v0_1`
- the draft must exist
- policy evaluation must complete before any send-path action

Gate order must be:
`HardSafetyGate -> BudgetGate -> DataQualityGate -> EvidenceGate -> FitScoreGate -> ContactabilityGate -> DraftClaimEvidenceGate -> SendGate`

Respect locked defaults:
- `send_enabled=false`
- provider enum `SEND_SRC_01`
- mode `sandbox_log_sink_only`
- no external send side effects

When disabled, park safely and do not create a `SendAttempt`.

Do not add new canonical tables or provider-specific enums.

Write redacted structured events only.

Add tests proving:
- disabled sends park safely
- missing approvals fail closed
- missing records fail closed
- unsupported payload versions return `contract_error`

