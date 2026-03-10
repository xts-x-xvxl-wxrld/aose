# docs/epics/epic-g/spec-g3.md

# G3. Enrichment v0

## Goal

Implement the minimum allowed automated contact enrichment path: normalize identifiers, perform email syntax and domain-level checks up to `domain_ok`, keep LinkedIn automated validation at `unverified`, and route to `copy_generate` only when downstream channel preconditions are satisfied.

This stage must update one canonical contact at a time and remain replay-safe.

## Scope boundary

### In scope
- Contact-level enrichment worker
- Email normalization
- Syntax check
- Domain normalization
- DNS or MX check where applicable
- Channel state persistence
- Allowed downstream routing
- Transient retry behavior
- Budget exhaustion behavior

### Out of scope
- Mailbox probing
- Provider-verified automation
- Human-verified automation
- Unsupported LinkedIn existence checks
- Contact scoring
- Approval or send transitions

## Contract touchpoints

### Canonical records
- `Contact`
- `Contact.channels[]`
- Optional provenance metadata on updated channel fields

### Stages
Consumes `contact_enrichment` payload version `1` with required `contact_id` and optional `validations_requested`.

Produces:
- `copy_generate` payload version `1`
- `parked:no_signal`
- `parked:budget_exhausted`
- `parked:needs_human`
- `parked:policy_blocked`

Downstream `copy_generate` requires `seller_id + account_id + contact_id + evidence_ids`, but G3 only gates whether the contact is eligible to advance.

## Deliverables
- `worker/contact_enrichment/service.py`
- Channel validator utilities for email normalization and domain or DNS or MX checks
- Policy helper for send-blocked channel classification
- Tests for validation-level progression, replay, routing, and block conditions
- Structured events for success, retry, budget exhausted, and policy block outcomes

## Enrichment rules

### For email
- Normalize email using Epic B rules
- Run syntax validation
- Normalize domain
- Run DNS or MX check where applicable
- Automated maximum validation level is `domain_ok`
- Never automate `provider_verified`
- Never automate `human_verified`
- Never perform mailbox probing

### For LinkedIn
- Normalize URL using Epic B rules
- Automated maximum validation level stays `unverified`
- Do not automate `profile_exists` unless a trusted toolchain explicitly supports it, which Epic G does not require

## Channel persistence model

When an email channel exists on the contact:
- Invalid normalized email → set validation to `unverified` or leave unchanged if better evidence already exists
- Syntax passes → may set `syntax_ok`
- DNS or MX passes → set `domain_ok`
- Record `validated_at`
- Update `source_trace`
- Preserve required provider-derived metadata where present

Validation level is explicit, not boolean. `domain_ok` is the minimum allowed automated state for downstream flow.

## Routing rules

Advance from `contact_enrichment` to `copy_generate` only when all are true:
- Canonical `Contact` exists
- At least one allowed channel exists
- For email path, validation level is `domain_ok` or `human_verified`
- No active STOP condition from HardSafetyGate blocks that channel

Do not advance automatically when:
- Target email domain is in the free-email blocklist
- Only generic mailbox local-part exists for send
- Contact has no allowed downstream channel
- Role ambiguity requires human review
- Budget is exhausted

Store blocked contacts if valid canonical identity exists. Block only automatic flow.

Epic G may store contacts that later remain send-ineligible under policy.

## Retry and replay rules
- `contact_enrichment` work item key: `enrich:<contact_id>:email:v1`
- Transient errors retry only while the configured cap remains
- Contract errors do not retry
- Replay must not create duplicate channels or duplicate downstream work items
- Rerunning enrichment on an already `domain_ok` contact must be a no-op or deterministic overwrite

## Acceptance checks
- Contact with a syntactically valid, MX-resolving email is updated to `domain_ok`
- Contact with malformed email never reaches `domain_ok`
- Generic mailbox or free-email domain contact is stored but routed to `parked:policy_blocked` for automatic downstream flow
- LinkedIn URL is normalized but remains `unverified` in automated flow
- Replaying the same enrichment work item does not duplicate channel rows or downstream `copy_generate` work items
- Transient DNS failure retries only until cap, then parks as `parked:budget_exhausted`
- Structured events redact raw email data
