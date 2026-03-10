# spec-f3 — Promotion rule + parked outcomes

## Goal
Implement deterministic promotion and parking behavior for Epic F so candidate accounts become `target` only when the locked promotion conditions are satisfied, and otherwise terminate into the correct parked lane without duplicate downstream side effects.

## Scope boundary
**In scope:** gate evaluation, status mutation from `candidate` to `target`, enqueueing of the next `people_search` work item, parked-stage routing, and replay-safe side-effect control.

**Out of scope:** actual people search, contact enrichment, approval, sending, or any additional target-prioritization logic beyond fit/intent output and the locked promotion rule.

## Contract touchpoints
- Promotion occurs from stage `intent_fit_scoring`
- Eligible source account statuses are `candidate` and `target`, but only `candidate` may transition to `target`
- Successful promotion must enqueue the next work item at stage `people_search`
- Parked stages allowed by the contract:
  - `parked:no_fit`
  - `parked:no_signal`
  - `parked:needs_human`
  - `parked:budget_exhausted`
  - `parked:contract_error`
  - `parked:policy_blocked`

Safe `v0_1` thresholds and caps govern fit pass/review bands and budget stop behavior.

## Promotion conditions
An account may promote only when all of the following are true:

- `HardSafetyGate = PASS`
- `BudgetGate = PASS`
- `DataQualityGate != STOP`
- `EvidenceGate = PASS`
- `fit_score >= 75`
- deterministic dedup passes

Intent does not gate promotion in v0.1.

It is explanatory and prioritization-only once an account is already a valid target.

### Promotion side effects
- Upsert the `Scorecard`
- Update `Account.status` from `candidate` to `target`
- Enqueue exactly one downstream WorkItem at stage `people_search` with payload v1 containing `account_id`

## Deterministic lane evaluation order
To avoid ambiguous routing, implement the following order of evaluation:

1. `contract_error` lane first
   - missing required canonical records
   - unsupported payload version
   - result: `parked:contract_error`

2. `blocked` lane next
   - `HardSafetyGate = STOP`
   - result: `parked:policy_blocked`

3. `budget` lane next
   - `BudgetGate = STOP`
   - result: `parked:budget_exhausted`

4. `no_signal` lane next
   - no scoreable evidence found
   - or both `fit_score = 0` and `intent_score = 0` due to absence of usable evidence
   - result: `parked:no_signal`

5. Promotion next
   - if all promotion conditions pass
   - mutate candidate to target
   - enqueue `people_search`

6. `no_fit` lane next
   - if `fit_score <= 64`
   - result: `parked:no_fit`

7. `review` lane last
   - if `fit_score in 65..74`
   - or `EvidenceGate = REVIEW`
   - or `DataQualityGate = REVIEW`
   - or source conflicts require human resolution
   - result: `parked:needs_human`

This order preserves the contract’s pass/review/stop semantics while keeping routing deterministic.

It also ensures low-fit outcomes do not promote merely because intent is high, since intent never overrides fit in Epic F v0.1.

## Idempotency and replay safety
Promotion must be idempotent by effective scoring input.

Reprocessing the same effective scoring input must not:

- duplicate the scorecard
- enqueue duplicate `people_search` work items for the same idempotency context
- re-transition an already promoted account in a way that creates extra side effects

If the account is already `target` and the same effective input is re-run, the handler may refresh the same scorecard but must treat downstream promotion side effects as already satisfied.

Replay safety must come from deterministic lookup/upsert behavior plus a unique side-effect guard for the downstream `people_search` work item derived from the same account and scoring context.

## Deliverables
- A promotion evaluator that consumes scorecard plus gate outcomes
- A deterministic parked-lane router
- An account status mutation path from `candidate` to `target`
- A downstream work-item enqueue path for `people_search` with duplicate-side-effect protection
- Integration tests covering every promotion and parking lane, including replay

## Acceptance checks
- An eligible candidate account with `fit_score >= 75`, `EvidenceGate = PASS`, and no STOP gates becomes `target` and enqueues exactly one `people_search` work item
- An account with `fit_score in 65..74` parks as `parked:needs_human`
- An account with `fit_score <= 64` parks as `parked:no_fit`
- An account with no scoreable evidence parks as `parked:no_signal`
- A hard safety stop parks as `parked:policy_blocked`
- A budget stop parks as `parked:budget_exhausted`
- A missing required canonical record or unsupported payload version parks as `parked:contract_error`
- Re-running the same work item does not duplicate the scorecard or the downstream `people_search` side effect

## AI build prompt
Implement `spec-f3` for Epic F.

Add deterministic promotion and parked-lane handling after scoring.

Promote only when all of these are true:

- `HardSafetyGate=PASS`
- `BudgetGate=PASS`
- `DataQualityGate!=STOP`
- `EvidenceGate=PASS`
- `fit_score>=75`
- deterministic dedup passes

Intent score never gates promotion in v0.1.

On promotion:

- upsert the `Scorecard`
- update `Account.status` from `candidate` to `target`
- enqueue exactly one next WorkItem at stage `people_search` with payload v1 containing `account_id`

Implement deterministic lane order:

1. `contract_error`
2. `policy_blocked`
3. `budget_exhausted`
4. `no_signal`
5. promotion
6. `no_fit`
7. `needs_human`

Use parked stages exactly as locked by the contract.

Make replay safe:

- rerunning the same effective scoring input must not duplicate `Scorecards`
- must not re-promote the account with new side effects
- must not enqueue duplicate `people_search` work items

Add integration tests for:

- promotion
- each parked lane
- replay idempotency