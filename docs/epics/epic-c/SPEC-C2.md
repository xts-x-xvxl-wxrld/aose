# SPEC-C2 — Attempt budget policy

## Goal
Implement deterministic attempt-budget enforcement so budget is decremented only on meaningful external/model attempts and exhaustion parks the work item with the canonical reason.

## Scope boundary
In scope:
- Budget decrement rules
- Exhaustion handling
- Retry eligibility checks against remaining budget
- Structured event emission for budget changes and retry scheduling

Out of scope:
- Exact retry backoff numbers
- Exact cap values
- Provider-specific retry behavior
- Business-specific handler outputs

## Contract authority
This spec is subordinate to `docs/epics/epic-c/CONTRACT-C.yaml`.
If implementation details conflict with the contract, the contract wins.

## Contract touchpoints
- `work_item_runtime.requires_existing_fields`
- `attempt_budget.purpose`
- `attempt_budget.decrement_rule`
- `attempt_budget.exhaustion_rule`
- `attempt_budget.retry_rules`
- `canonical_enums.attempt_budget_decrement_on`
- `canonical_enums.error_codes`
- `canonical_enums.structured_event_types`
- `canonical_enums.structured_event_outcomes`
- `outcome_rules.parked`
- `handler_contract.budget_spend_shape`
- `handler_contract.handler_required_behavior`

## Required behavior
1. Budget state is read from the persisted `WorkItem` fields:
   - `attempt_budget_remaining`
   - `attempt_budget_policy`
2. Budget may decrement only on:
   - `source_call`
   - `model_call`
3. Budget must not decrement on:
   - local validation
   - payload parsing
   - idempotency existence check
   - db read only
   - routing decision
   - structured event write
4. If remaining budget is zero before a meaningful attempt, the handler must not proceed with budget-spending work.
5. When budget is exhausted, outcome must be:
   - `error_code = budget_exhausted`
   - parked stage/result = `parked:budget_exhausted`
   - terminal event type = `work_item_parked`
   - retry disallowed
6. `transient_error` may schedule retry only while budget remains.
7. `contract_error`, `budget_exhausted`, `no_signal`, `policy_blocked`, and `needs_human` must not schedule retry beyond the contract rules.

## Deliverables
- Budget policy module, helper, or middleware used by handlers
- Common API for recording budget-spending attempt types
- Worker-side retry eligibility logic tied to remaining budget
- Unit tests for:
  - decrement on source call
  - decrement on model call
  - no decrement on validation/read/routing/event write
  - zero budget causes deterministic parked outcome
  - transient retry allowed only while budget remains

## Implementation constraints
- No hardcoded numeric retry/backoff policy beyond what contract already locks.
- No silent budget decrement.
- No handler-local reinterpretation of allowed decrement types.
- Budget enforcement must be reusable across handlers.

## Acceptance checks
1. A handler that performs one `source_call` decrements budget by exactly one meaningful attempt.
2. A handler that only validates payload and reads DB state does not decrement budget.
3. A work item with `attempt_budget_remaining = 0` parks as `parked:budget_exhausted` before any budget-spending side effect.
4. A `transient_error` with remaining budget schedules retry and emits retry metadata.
5. A `transient_error` with zero remaining budget does not retry and parks deterministically.
6. CI proves the minimum gate: budget exhaustion produces deterministic parked outcome with reason.

## Done definition
This ticket is done when all handlers can rely on one shared attempt-budget policy that enforces decrement semantics and exhaustion semantics exactly as the contract requires.

## AI build prompt
Implement SPEC-C2 for Epic C.

Use the Epic C contract as the sole authority for attempt-budget behavior.

Build shared attempt-budget enforcement with these rules:
- decrement only on `source_call` and `model_call`
- do not decrement on validation, parsing, idempotency checks, DB read-only work, routing, or structured event writes
- if budget is already zero, do not proceed with budget-spending attempts
- budget exhaustion must park deterministically as `parked:budget_exhausted`
- `transient_error` may retry only while budget remains
- all other retry behavior must follow the contract exactly

Deliver:
- reusable budget policy helper/middleware
- retry eligibility logic
- tests proving decrement and no-decrement cases
- tests proving deterministic parking on exhaustion

Do not invent backoff numbers or cap values.
Do not let handlers implement their own conflicting budget logic.
