# SPEC-E2 — Account discovery handler + one configurable real adapter path

## Goal
Implement the Epic E account discovery handler that consumes `account_discovery` work items, invokes one configured adapter through the E1 interface, normalizes candidates, writes canonical `Account`, `AccountAlias`, `Evidence`, and optional `EvidenceContent`, and enqueues downstream `intent_fit_scoring` work items for successful candidates.

## Scope boundary
In scope:
- Epic E handler/service for one `account_discovery` work item.
- Adapter registry or selector with support for:
  - `dummy_predictable`
  - exactly one configured real adapter slot
- Candidate normalization before canonical writes.
- Canonical writes for `Account`, `AccountAlias`, `Evidence`, optional `EvidenceContent`.
- Provenance persistence.
- Downstream enqueue to `intent_fit_scoring`.

Out of scope:
- Multiple real adapters or ranking across adapters.
- Fit/intent scoring logic.
- Contact discovery.
- Manual review UI.
- Sending or approval behavior.
- Any merge heuristic beyond locked registry/domain precedence.
- Inventing a provider before PH-EPIC-E-001 is decided.

## Contract touchpoints
Consumes:
- `WorkItem.stage = account_discovery`
- payload required: `query_object_id`
- payload optional: `adapter_plan`, `run_limits_override`

Preconditions:
- referenced `QueryObject` exists
- referenced `SellerProfile` exists through `QueryObject.seller_id`
- `WorkItem.trace.policy_pack_id = safe_v0_1`

Canonical writes allowed:
- `Account`
- `AccountAlias`
- `Evidence`
- `EvidenceContent`
- `WorkItem`

Must not create:
- `Scorecard`
- `Contact`
- `OutreachDraft`
- `ApprovalDecision`
- `SendAttempt`

Downstream success stage:
- `intent_fit_scoring` with payload `{ v: 1, account_id }` :contentReference[oaicite:10]{index=10} :contentReference[oaicite:11]{index=11}

## Required behavior
1. Load `QueryObject` and `SellerProfile` from canonical storage.
2. Resolve the adapter:
   - `dummy_predictable` must always be available for tests and local deterministic verification.
   - one real adapter slot must exist in configuration, but the concrete provider enum remains blocked by `PH-EPIC-E-001` until human selection.
3. Call `search_accounts(query_object, limits, context)`.
4. Normalize each candidate before any database write.
5. Apply minimum creation rule:
   - create an `Account` only if `(legal_name + country)` or `domain` exists.
6. Map canonical account IDs by locked precedence:
   - `account:<COUNTRY>-<REGISTRY_ID>`
   - `account:<normalized_domain>`
   - `account:tmp:<sha256(country|legal_name_normalized|source_provider|source_ref)>`
7. Write aliases when present:
   - registry alias `{ source, id }`
   - normalized domain alias
   - normalized legal name alias
8. Map evidence using deterministic evidence ID:
   - `evidence:<sha256(source_type|canonical_url|captured_at_iso|sha256(snippet_text_or_empty))>`
9. Always store evidence pointer fields:
   - `url`
   - `snippet`
   - `claim_frame`
   - `provenance`
10. Store `EvidenceContent` only when capture policy allows it.
11. Persist provenance on accounts with:
   - adapter
   - query_object_id
   - captured_at
12. Persist provenance on evidence with:
   - adapter
   - query_object_id
13. For each new or deterministically updated account that survives dedup and policy checks, enqueue one downstream work item at `intent_fit_scoring` with `{ v: 1, account_id }`. :contentReference[oaicite:12]{index=12} 

## Placeholder handling
- `PH-EPIC-E-001` is open. Therefore the spec must not hardcode a specific real provider name or coverage claims.
- The code must expose a stable provider enum/config slot so a chosen provider can be bound later without changing the handler contract.
- Local and CI verification must succeed with `dummy_predictable` alone.
- Real-adapter integration tests are valid only once the human selects the actual provider. The placeholder ledger explicitly forbids inventing that provider. :contentReference[oaicite:14]{index=14}

## Deliverables
- `worker/.../handlers/account_discovery.py`
- `worker/.../services/account_discovery_service.py` or equivalent
- adapter registry/selector module
- candidate-to-canonical mapper
- canonical write helpers for account/evidence creation
- downstream work item enqueue helper
- integration tests for happy path with dummy adapter
- conditional integration test scaffold for one real adapter

## Implementation notes
- Prefer one transaction boundary per discovered candidate or one per work item, depending on current worker conventions, but canonical writes and downstream enqueue must remain replay-safe.
- Higher-trust source wins; if equal trust, newer capture wins; if still tied, stable lexicographic tiebreak on `source_ref`.
- Do not write raw provider payloads directly into canonical tables.
- Use Epic B normalization helpers rather than duplicating domain logic in Epic E.
- Candidate status after discovery must remain `candidate`; promotion belongs to Epic F. 

## Acceptance checks
- Running the handler on a valid `account_discovery` work item using `dummy_predictable` creates canonical `Account` and `Evidence` rows.
- At least one created account stores provenance linking `adapter + query_object_id + captured_at`.
- Alias rows are written when registry/domain/legal name normalized values exist.
- One downstream `intent_fit_scoring` work item is enqueued per surviving account.
- No forbidden canonical tables are written.

## Tests required
- integration: dummy adapter happy path writes `Account + Evidence`
- integration: provenance is stored on account and evidence
- integration: downstream work item is enqueued with payload `{v:1, account_id}`
- unit: candidate normalization runs before canonical writes
- unit: tmp account ID fallback is used only when registry and domain are both absent

## Failure handling
- Missing `QueryObject` or `SellerProfile` is a contract error.
- Invalid adapter result shape is a contract error.
- Transient adapter/provider failures are surfaced to orchestration for retry behavior.
- Policy-blocked candidates do not produce downstream scoring items.

## AI build prompt
Implement SPEC-E2 for Epic E. Build the `account_discovery` handler and service that load `QueryObject` and `SellerProfile`, select one adapter via the E1 interface, normalize candidates, and write canonical `Account`, `AccountAlias`, `Evidence`, and optional `EvidenceContent` records. Enforce the locked account ID precedence and deterministic evidence ID formula using existing Epic B helpers. Always store provenance on account and evidence. Enqueue one downstream `intent_fit_scoring` work item per surviving account. Do not create scorecards, contacts, drafts, approvals, or send attempts. Keep `dummy_predictable` as the default deterministic adapter for tests and expose one configurable real-adapter slot without inventing the actual provider before PH-EPIC-E-001 is decided.