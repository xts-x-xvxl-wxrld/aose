# spec-f1 — Scoring interface + scorecard upsert

## Goal
Implement the Epic F scoring handler contract for `intent_fit_scoring` so a worker can consume an account-scoped work item, resolve the effective scoring input deterministically, and upsert exactly one canonical `Scorecard` for that effective input.

## Scope boundary
**In scope:** work item input validation, record resolution, scorecard shape, evidence snapshot hashing, scorecard ID generation, scorecard upsert, and deterministic idempotency behavior.

**Out of scope:** rule definitions themselves, promotion to `target`, people/contact scoring, sending, approval, provider-specific enrichment logic, and any new canonical enums or record families.

## Contract touchpoints
- Canonical stage: `intent_fit_scoring`
- Consumes: WorkItem payload v1 with required `account_id` and optional `evidence_ids`
- Produces: canonical `Scorecard` record linked to `Account`
- Uses existing canonical records only:
  - `Account`
  - `Evidence`
  - `QueryObject`
  - `SellerProfile`
  - `Scorecard`

## Required behavior
The handler must accept only payload version `1`. Unsupported payload versions are contract errors.

The handler must resolve the `Account` first and fail into the contract-error lane if the account is missing or lacks the minimum required fields needed by the Epic F contract.

If `payload.evidence_ids` is present, scoring must use only those evidence records. If `payload.evidence_ids` is absent, the handler must resolve scoreable evidence already linked to the account.

Evidence eligible for account scoring must come only from the allowed categories for Epic F.

Seller context must resolve through persisted upstream linkage from `Account` provenance back to `QueryObject` and `SellerProfile`, or an equivalent persisted run context already established upstream.

The handler must build an evidence snapshot from the evidence records actually consumed by scoring.

- `evidence_snapshot_hash = sha256(sorted_used_evidence_ids_joined_by_|)`
- Input order must be lexicographically sorted before hashing

The `scorecard_id` must be:

- `scorecard:<account_id>:<sha256(scoring_version|evidence_snapshot_hash|policy_pack_id)>`

The effective idempotency key for scoring behavior must be:

- `sha256(account_id|scoring_version|evidence_snapshot_hash|policy_pack_id)`

Reprocessing the same effective input must update or no-op the same scorecard, never create a duplicate.

The persisted `Scorecard` must use the canonical account-scoped shape:

- `entity_ref`
- `fit`
- `intent`
- `scoring_version`
- `evidence_snapshot_hash`
- `policy_pack_id`
- `computed_at`

Fit and intent scores must each be integers in `0..100`.

Confidence values must be floats in `0.0..1.0`.

Reasons must be stored as structured objects, not free prose blobs.

## Data invariants
- Every stored reason must contain:
  - `code`
  - `text`
  - `evidence_ids`
- Every stored reason must reference one or more existing evidence IDs
- Empty-evidence reasons are forbidden
- If no trigger evidence exists, the handler must persist:
  - `intent.score = 0`
  - `intent.reasons = []`
- Model inference may assist internal classification, but model output alone must never become evidence and must never be stored as an unsupported reason

## Deterministic failure handling
- Missing required canonical records, unsupported payload versions, or unresolved required seller context must route to `parked:contract_error`
- No scoreable evidence must not crash the handler
- The handler must still terminate deterministically and hand off to later lane evaluation in Epic F

This ticket does not perform promotion side effects. It only guarantees deterministic scorecard persistence for valid scoring inputs.

## Deliverables
- A scoring service or handler interface for `intent_fit_scoring`
- A deterministic resolver for effective scoring input: `Account + Seller context + used Evidence`
- A scorecard builder/upsert path that persists the canonical `Scorecard` shape
- Unit tests for:
  - payload validation
  - evidence snapshot hashing
  - scorecard ID determinism
  - reason invariants
  - replay safety

## Acceptance checks
- A valid account-scoped work item with scoreable evidence writes exactly one scorecard on first run
- Re-running the same effective scoring input does not create a second scorecard
- Changing the consumed evidence set changes the evidence snapshot hash and therefore the effective scoring input
- A work item with unsupported payload version parks as `parked:contract_error`
- If no trigger evidence exists, stored `intent.score` is `0` and stored `intent.reasons` is `[]`

## AI build prompt
Implement `spec-f1` for Epic F.

Build the `intent_fit_scoring` handler interface and scorecard upsert path only.

Follow the locked Epic F contract exactly.

Consume WorkItem payload v1 with required `account_id` and optional `evidence_ids`.

Resolve seller context through persisted upstream linkage from `Account -> QueryObject -> SellerProfile`, or equivalent persisted run context.

If `evidence_ids` is provided, score only those evidence records. Otherwise resolve scoreable evidence linked to the account.

Build:

- `evidence_snapshot_hash = sha256(sorted_used_evidence_ids_joined_by_|)`
- `scorecard_id = scorecard:<account_id>:<sha256(scoring_version|evidence_snapshot_hash|policy_pack_id)>`

Persist one canonical account-scoped `Scorecard` with:

- `fit`
- `intent`
- `confidences`
- `reasons`
- `scoring_version`
- `evidence_snapshot_hash`
- `policy_pack_id`
- `computed_at`

Enforce invariants:

- every stored reason has `code`, `text`, and non-empty `evidence_ids`
- model inference never becomes `Evidence`
- if no trigger evidence exists then `intent.score=0` and `intent.reasons=[]`

Make replay idempotent by effective scoring input so reruns upsert the same `Scorecard` rather than creating duplicates.

Add tests for:

- payload version rejection
- deterministic hashing and IDs
- reason invariants
- replay safety