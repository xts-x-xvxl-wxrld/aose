# SPEC-E3 — Deterministic dedup, alias idempotency, and replay safety

## Goal
Guarantee that Epic E account discovery is deterministic under reruns: the same discovery input must not produce duplicate surviving `Account` records for the same registry ID or normalized domain, must not duplicate aliases, and must not duplicate `Evidence` rows for the same deterministic evidence ID.

## Scope boundary
In scope:
- Dedup logic for canonical account creation/update.
- Alias idempotency rules.
- Evidence idempotency rules.
- Replay-safe behavior for the Epic E handler when the same work item or logically equivalent input is processed again.

Out of scope:
- Cross-account fuzzy merge logic by name + address.
- Contact dedup.
- Scoring dedup.
- Structured event schema design.
- Queue retry policy itself.

## Contract touchpoints
Account primary logic:
- primary: `country + registry_id`
- fallback: `normalized_domain`
- deferred: `name + address`

Deterministic guarantees:
- rerun same discovery input -> no second surviving `Account` for same registry ID or normalized domain
- alias insertion idempotent
- evidence creation idempotent by `evidence_id`
- replay becomes no-op or deterministic overwrite when side effects already exist under canonical ID or applicable idempotency key 

## Required behavior
1. Before creating an account, resolve canonical identity in this order:
   - existing account by `(country, registry_id)` if registry ID present
   - existing account by `normalized_domain` if registry ID absent or unmatched
   - otherwise create new canonical account by locked precedence rules
2. Alias insertion must be idempotent:
   - inserting the same registry alias again must not create a duplicate row
   - inserting the same normalized domain again must not create a duplicate row
   - inserting the same normalized legal name again must not create a duplicate row
3. Evidence insertion must be idempotent by deterministic `evidence_id`.
4. Reprocessing the same work item must:
   - not create duplicate account rows
   - not create duplicate alias rows
   - not create duplicate evidence rows
   - not enqueue duplicate downstream rows if the downstream work item identity is already represented by deterministic key or existing canonical state
5. If a rerun finds existing canonical rows, allowed behavior is:
   - no-op
   - deterministic overwrite of mutable non-identity fields
   - deterministic provenance append/update consistent with trust precedence
6. Trust conflict resolution must remain deterministic:
   - higher-trust source wins
   - if equal trust, newer capture wins
   - if still tied, stable lexicographic tiebreak on `source_ref` 

## Deliverables
- dedup resolver module for accounts
- alias upsert helpers
- evidence upsert helpers
- replay-safety tests
- uniqueness constraints or application-level guards where missing

## Implementation notes
- Prefer DB-backed uniqueness where possible, backed by deterministic application logic.
- Keep tmp-account creation as last resort only.
- Do not introduce fuzzy merge behavior in Epic E.
- Do not mutate canonical IDs once chosen in a way that breaks replay history; if future upgrade logic exists, it must preserve alias history and deterministic traceability, matching the spine’s alias-based identity model. :contentReference[oaicite:18]{index=18}

## Acceptance checks
- Rerunning the same discovery input does not duplicate `Account` rows for the same registry ID.
- Rerunning the same discovery input does not duplicate `Account` rows for the same normalized domain.
- Rerunning the same discovery input does not duplicate `Evidence` rows for the same `evidence_id`.
- Alias rows remain unique and stable after rerun.
- The handler resolves to the same surviving account identity on replay.

## Tests required
- unit: account ID mapping `registry > domain > tmp`
- unit: evidence ID determinism
- unit: alias insertion idempotency
- unit: rerun replay safety produces no duplicate accounts
- integration: repeated handler execution on same input remains stable
- integration: equal candidate data with different ordering still resolves to same surviving canonical rows

## Failure handling
- Ambiguous identity cases outside locked precedence should surface as `needs_human` or remain deferred, not silently fuzzy-merged.
- Constraint collisions should resolve into deterministic fetch-and-reuse behavior, not duplicate creation.

## AI build prompt
Implement SPEC-E3 for Epic E. Add deterministic dedup and replay safety to account discovery. Resolve canonical accounts by locked precedence: registry first, then normalized domain, then tmp hash. Make alias insertion idempotent for registry, domain, and legal-name-normalized aliases. Make evidence creation idempotent by deterministic `evidence_id`. Ensure rerunning the same discovery input or the same work item produces no duplicate surviving account, alias, or evidence rows. Do not add fuzzy merge heuristics beyond the locked precedence rules. Add unit and integration tests proving replay-safe behavior.