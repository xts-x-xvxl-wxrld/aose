# SPEC-C1 — Stage router

## Goal
Implement a deterministic stage router that maps a `WorkItem.stage` to exactly one handler or to a terminal parked/contract-failure outcome.

## Scope boundary
In scope:
- Table-driven explicit handler registry
- Exact stage-to-handler resolution
- Parked-stage terminal handling
- Unknown-stage deterministic contract failure handling
- Router-level structured event emission needed to prove routing outcomes

Out of scope:
- Handler business logic
- Retry backoff numbers
- Provider selection
- Replay endpoint
- Any changes to Epic B canonical IDs, WorkItem fields, or stage names

## Contract authority
This spec is subordinate to `docs/epics/epic-c/CONTRACT-C.yaml`.
If implementation details conflict with the contract, the contract wins.

## Contract touchpoints
- `routing.router_model = table_driven_explicit_registry`
- `routing.exact_match_rule.enabled = true`
- `routing.exact_match_rule.no_fuzzy_matching = true`
- `routing.exact_match_rule.no_alias_guessing = true`
- `routing.exact_match_rule.no_reflection_discovery = true`
- `routing.parked_stage_rule`
- `routing.unknown_stage_rule`
- `canonical_enums.stages`
- `canonical_enums.parked_stage_prefix`
- `canonical_enums.structured_event_types`
- `canonical_enums.structured_event_outcomes`
- `canonical_enums.error_codes`
- `outcome_rules`
- `queue_handoff.required_invariants`

## Required behavior
1. Router input is one persisted `WorkItem`.
2. Router resolves handler dispatch only by exact match against canonical stage strings.
3. A stage beginning with `parked:` must never dispatch to a normal handler.
4. A parked stage is treated as a terminal route and acknowledged cleanly.
5. Unknown stages must:
   - preserve the original stage value,
   - produce `contract_error`,
   - emit a terminal contract-failure outcome,
   - not retry,
   - park immediately according to contract behavior.
6. Router must not discover handlers dynamically by reflection or naming convention.
7. Handlers must not invoke downstream handlers directly; only queue handoff via new `WorkItem` is allowed.

## Deliverables
- `worker/router.py` with explicit registry-based routing
- `worker/registry.py` or equivalent static handler registry
- Unit tests for:
  - known canonical stage dispatch
  - parked stage terminal routing
  - unknown stage contract failure
  - rejection of non-exact aliases or fuzzy matches
- Minimal integration path from worker consume loop to router

## Implementation constraints
- Registry keys must be canonical stage strings only.
- No fallback routing.
- No implicit module import based on stage names.
- No mutation of stage labels during routing.
- Router may return only one of:
  - `handler_dispatch`
  - `parked_terminal`
  - `contract_failure`

## Acceptance checks
1. Given a `WorkItem.stage` of `intent_fit_scoring`, router dispatches only to the registered `intent_fit_scoring` handler.
2. Given a `WorkItem.stage` of `parked:no_signal`, router does not dispatch any normal handler and returns terminal parked handling.
3. Given a `WorkItem.stage` of `intent-fit-scoring`, router does not attempt normalization or aliasing; it fails as a contract error.
4. Given an unknown stage, system emits structured failure outcome and does not schedule retry.
5. CI proves the minimum gate: unknown stage becomes `contract_error` and emits structured failure event.
6. CI proves the minimum gate: parked stage does not dispatch to a normal handler.

## Done definition
This ticket is done when routing is deterministic, exact-match only, parked stages are terminal, and unknown stages fail in the contract-defined way.

## AI build prompt
Implement SPEC-C1 for Epic C.

Use the existing Epic C contract as the sole authority for routing behavior.

Build a deterministic stage router for `WorkItem.stage` with these rules:
- explicit static registry only
- exact canonical stage match only
- no fuzzy matching
- no alias guessing
- no reflection-based handler discovery
- stages starting with `parked:` are terminal and must not dispatch to normal handlers
- unknown stages must produce `contract_error`, emit terminal failure outcome, and not retry

Deliver:
- router module
- explicit handler registry
- tests for known stage, parked stage, and unknown stage behavior
- worker integration path that calls the router

Do not implement business logic for handlers beyond what is required to test routing.
Do not invent new stage names, error codes, or event types.
Do not let handlers call each other directly.
