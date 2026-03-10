# SPEC-C4 — Structured events table and logger

## Goal
Implement structured event persistence and logging so every handler writes canonical, redacted, machine-readable lifecycle events and the system can show the last 20 events per entity.

## Scope boundary
In scope:
- `StructuredEvent` model/table
- Event writer/logger helper
- Event validation against canonical types/outcomes
- Redaction rules for logs/events
- Query path for recent events per entity

Out of scope:
- Full analytics/BI reporting
- Long-term archival
- Vendor log sinks
- Human-facing observability dashboards beyond a basic run/recent-events view

## Contract authority
This spec is subordinate to `docs/epics/epic-c/CONTRACT-C.yaml`.
If implementation details conflict with the contract, the contract wins.

## Contract touchpoints
- `structured_events.model_name`
- `structured_events.table_name`
- `structured_events.required_fields`
- `structured_events.field_rules`
- `structured_events.run_view_requirement`
- `structured_events.terminal_outcome_rule`
- `canonical_enums.structured_event_types`
- `canonical_enums.structured_event_outcomes`
- `canonical_enums.error_codes`
- `canonical_enums.terminal_outcome_event_types`
- `redaction_and_security`
- `minimum_ci_gates`

## Required behavior
1. Persist structured events in table `structured_events`.
2. Every event must include all required fields:
   - `event_id`
   - `occurred_at`
   - `module`
   - `work_item_id`
   - `entity_ref`
   - `stage`
   - `event_type`
   - `outcome`
   - `error_code`
   - `counters`
   - `refs`
   - `v`
3. `entity_ref` must contain:
   - `type`
   - `id`
4. `stage` must equal the current `WorkItem.stage` at emission time.
5. `event_type` must be one of the canonical structured event types.
6. `outcome` must be one of the canonical structured event outcomes.
7. `error_code` must be null or one canonical error code.
8. `counters` must contain numeric-only machine metrics.
9. `refs` may include only safe machine references such as:
   - canonical IDs
   - adapter names
   - payload version
   - retry metadata
   - other contract-safe refs
10. Every handler must emit at least:
    - start event
    - terminal outcome event
11. Work item closure must use exactly one terminal event type:
    - `work_item_completed`
    - `work_item_parked`
    - `work_item_failed_contract`
    - `work_item_failed_transient`

## Redaction rules
Never log directly:
- full email addresses
- full phone numbers
- full message bodies
- raw provider secrets
- raw credentials

Allowed debug refs include:
- canonical IDs
- `contact_id`
- `evidence_ids`
- `template_id`
- `claim_hashes`
- safe hashes
- domain fragments
- provider identifiers

## Deliverables
- DB migration for `structured_events`
- ORM model for `StructuredEvent`
- Shared logger/event-writer helper
- Validation layer enforcing canonical event fields/types
- Query helper or API path for recent events per entity, limited to 20
- Unit/integration tests for:
  - start and terminal events
  - redaction behavior
  - invalid event type rejection
  - recent-events query limit

## Implementation constraints
- Free-form text blobs are not a substitute for structured fields.
- Event writer must be reusable by all handlers.
- Event persistence must not require raw PII to be stored in events.
- Structured event writes themselves must not decrement attempt budget.

## Acceptance checks
1. Running any handler writes a `handler_started` event and one terminal outcome event.
2. A contract failure writes canonical failure event type and outcome, with `error_code=contract_error`.
3. A parked outcome writes canonical parked terminal event with the parked reason represented safely in refs.
4. Events do not contain raw emails, raw phone numbers, or full message bodies.
5. Recent-events query for one entity returns at most the last 20 events in descending recency.
6. CI proves the minimum gate: handlers emit structured events at start and terminal outcome.
7. CI proves the minimum gate: structured events are redacted according to baseline policy.

## Done definition
This ticket is done when structured events are persisted, validated, redacted, and queryable in a basic recent-per-entity view, and every handler can use the shared logger consistently.

## AI build prompt
Implement SPEC-C4 for Epic C.

Use the Epic C contract as the sole authority for structured events.

Build:
- `StructuredEvent` DB model/table named `structured_events`
- migration
- shared event writer/logger
- validation enforcing canonical event types, outcomes, and error codes
- recent-events query/view limited to the last 20 events per entity

Rules:
- every handler emits `handler_started` and one terminal outcome event
- terminal events must be one of the canonical terminal outcome event types
- `stage` in the event must equal the current work-item stage
- `counters` must be numeric-only
- `refs` must contain only safe machine refs
- no raw emails, raw phone numbers, full message bodies, secrets, or credentials in events
- structured event writes must not spend attempt budget

Deliver tests proving:
- start and terminal events are written
- invalid event types are rejected
- redaction works
- recent-events view returns at most 20 events per entity
