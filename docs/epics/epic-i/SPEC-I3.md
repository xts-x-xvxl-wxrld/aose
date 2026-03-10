## spec-i3.md

# Spec I3 — Rate Limiting and Compliance Hooks

**Spec ID:** I3  
**Epic:** epic-i  
**Title:** Deterministic throttling and compliance enforcement for sandbox-first sending

## Goal

Implement the rate-limit and compliance decision layer required by Epic I so the sending handler can enforce throttles, suppression, free-domain blocking, generic-mailbox blocking, minimum email-confidence thresholds, and unsubscribe placeholder requirements before any sandbox send path is allowed.

Even when `send_enabled=false`, these checks must remain codified and testable.

## Scope

### In scope
- Read and enforce `safe_v0_1` send limits
- Deterministic STOP, REVIEW, and PASS evaluation for send-adjacent rules
- Suppression source checks
- Free email domain and generic mailbox checks
- Email confidence threshold checks
- Unsubscribe token placeholder presence check
- Deterministic park behavior on limit hit or policy block

### Out of scope
- Real unsubscribe token generation
- Real list-unsubscribe headers
- Real provider suppression APIs
- Real campaign delivery scheduling
- Circuit-breaker-driven provider shutdown logic beyond deterministic sandbox-first outcomes

## Contract touchpoints

### Rate limits when enabled
- `max_sends_per_day: 20`
- `max_sends_per_hour: 5`
- `max_sends_per_target_domain_per_24h: 1`

### Behavior on limit hit
- Do not create duplicate `SendAttempt`
- Park or fail closed deterministically
- No burst bypasses

### Stop conditions
- Missing website/domain and missing unique company identifier
- Target channel is a free email domain
- Suppression hit in `global_dnc`, `complaint_suppression`, or `campaign_suppression`
- Only a generic mailbox exists
- Email confidence `< 0.60`
- Email explicitly invalid

### Review conditions
- Evidence count `< 2` distinct categories
- Role/title ambiguous and no LinkedIn URL
- Email confidence `0.60..0.79`
- Any specific draft claim lacks linked Evidence IDs

### Pass conditions
- Email confidence `>= 0.80`
- Required evidence and approval conditions satisfied
- No STOP gate active

### Compliance hooks
- Suppression sources:
  - `global_dnc`
  - `campaign_suppression`
  - `complaint_suppression`
  - `bounced_suppression`
- `unsubscribe.token_placeholder_required = true`
- Token generation deferred
- List enforcement required before any future real send

### Override rules
STOP outcomes for `HardSafetyGate`, `BudgetGate`, and suppression or complaint blocks must not be overridable.

## Implementation requirements

- Build a policy evaluator for send throttling and compliance decisions
- Implement rolling-window counters or equivalent deterministic query logic for:
  - per day
  - per hour
  - per target domain per 24h
- Limit checks must execute before sandbox `SendAttempt` creation
- On any limit hit, park deterministically
- Do not create a duplicate `SendAttempt`
- Add suppression lookup hooks against canonical suppression sources
- Tables may be empty initially, but logic must exist
- Enforce free email domain block list and generic-mailbox local-part block list from `safe_v0_1`
- Use `Contact.channels[].confidence` and validation status to enforce `ContactabilityGate`
- Require unsubscribe placeholder presence in the draft or send context
- Keep token generation deferred
- Unsupported claims without evidence must force REVIEW, not PASS

## Deliverables
- Send-throttle evaluator
- Suppression and compliance evaluator
- Free-domain and generic-mailbox classifiers
- Email-confidence gate logic
- Unsubscribe placeholder checker
- Unit and integration tests for throttle, suppression, review, and stop paths

## Acceptance criteria
- A simulated burst beyond hourly or daily caps parks deterministically
- More than one send to the same target domain within 24 hours is blocked deterministically
- Suppression hits cannot be overridden into send
- Free-email-domain or generic-mailbox contacts are STOP-blocked for send
- Email confidence `< 0.60` is STOP
- Email confidence `0.60..0.79` is REVIEW
- Email confidence `>= 0.80` may PASS if other gates clear
- Missing unsubscribe placeholder blocks progression to any future real-send path and remains visible in sandbox-first validation
- Unsupported draft claims without evidence produce REVIEW before send
