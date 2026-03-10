# SPEC-E4 — Run caps, stop rules, and deterministic terminal outcomes

## Goal
Implement deterministic run controls for Epic E account discovery so a discovery run terminates under fixed caps and stable stop rules, parks with the correct reason codes, and does not expand indefinitely.

## Scope boundary
In scope:
- Run cap enforcement.
- Per-query-object cap enforcement.
- External call budget accounting for account discovery.
- Deterministic stop rules.
- Parked outcomes for `no_signal`, `budget_exhausted`, `policy_blocked`, `needs_human`, `contract_error`, and `transient_error`.

Out of scope:
- Fit/intent thresholds.
- Contact caps.
- Send limits.
- Multi-adapter ranking logic.
- Numeric cap invention beyond locked defaults and placeholder defaults.

## Contract touchpoints
Locked caps:
- `max_accounts_per_run = 30`
- `max_external_calls_per_run = 250`
- `max_runtime_seconds_per_run = 900`
- `max_queries_per_run_default = 10`
- `timeout_seconds = 20`
- `retry_count_transient = 2`
- `backoff_seconds = [2, 8]`

Per-query-object cap:
- required by contract
- placeholder `PH-EPIC-E-002`
- temporary default allowed: `10`

Stop rules:
- `no_signal`
- `diminishing_returns`
- `budget_exhausted`
- `max_accounts_reached`

Attempt budget decrements on:
- source call
- paid provider call
- model call if used for normalization

Do not decrement on:
- pure DB read
- idempotent no-op replay 

## Required behavior
1. Build a run-limits object that resolves caps from:
   - policy/config
   - optional `run_limits_override` when permitted
   - placeholder default for `max_accounts_per_query_object` until PH-EPIC-E-002 is decided
2. Enforce these caps deterministically:
   - max accounts per run
   - max external calls per run
   - max runtime seconds per run
   - max queries per run
   - max accounts per query object
3. Apply stable stop rules:
   - `no_signal`: current processed query object yields zero new unique accounts after normalization and dedup
   - `diminishing_returns`: current query yields zero new unique accounts and remaining queries are lower priority than current
   - `budget_exhausted`: stop immediately when attempt budget reaches zero or any run cap is exceeded
   - `max_accounts_reached`: stop when max accounts per run or per query object is reached
4. Park with stable stages/reason codes:
   - `parked:no_signal`
   - `parked:budget_exhausted`
   - `parked:policy_blocked`
   - `parked:needs_human`
   - `parked:contract_error`
   - `parked:transient_error`
5. For transient errors:
   - allow retry up to 2 times
   - use the locked backoff sequence
   - if exhausted, park as `transient_error` or `budget_exhausted`
6. Do not spend budget on idempotent replay no-ops.
7. The handler must terminate predictably regardless of candidate ordering or rerun count. 

## Deliverables
- run limits/config module
- stop-rule evaluator
- budget accounting helper
- parked outcome mapper
- tests for cap enforcement and no-signal behavior

## Implementation notes
- Keep stop-rule decisions inside Epic E logic, but do not invent a divergent event schema; call the Epic C structured event writer if present.
- `diminishing_returns` should rely on stable query priority ordering from `QueryObject.priority`.
- Use monotonic counting inside the run so “new unique accounts” means post-normalization, post-dedup surviving accounts.
- Per-query-object cap must exist even before PH-EPIC-E-002 is finalized; the placeholder ledger allows temporary default `10`. :contentReference[oaicite:21]{index=21}

## Acceptance checks
- A discovery run stops when caps are reached.
- Budget exhaustion parks with stable reason code `budget_exhausted`.
- A query object producing zero new unique accounts parks as `no_signal` when applicable.
- Lower-priority remaining queries do not continue after a valid `diminishing_returns` stop.
- Idempotent no-op replay does not spend budget.

## Tests required
- integration: cap enforcement stops run deterministically
- integration: no_signal path parks correctly
- unit: external call accounting decrements only on meaningful attempts
- unit: no-op replay does not decrement budget
- unit: per-query-object cap defaults to placeholder value `10` when unresolved
- unit: retry path respects `2` retries and locked backoff data

## Failure handling
- Contract errors park immediately with no retries.
- Policy-blocked candidates do not advance downstream.
- Needs-human cases park into review lane.
- Runtime/cap exhaustion uses `budget_exhausted`, not a custom code.

## AI build prompt
Implement SPEC-E4 for Epic E. Add deterministic run controls to account discovery: cap enforcement, budget accounting, stop-rule evaluation, and stable parked outcomes. Enforce the locked caps for accounts, external calls, runtime, queries, and retries. Add a required per-query-object cap that defaults to 10 until PH-EPIC-E-002 is decided. Implement stop rules for `no_signal`, `diminishing_returns`, `budget_exhausted`, and `max_accounts_reached`. Decrement budget only on meaningful attempts, never on pure DB reads or idempotent no-op replay. Park with the stable reason codes from the contract and add tests proving deterministic termination.