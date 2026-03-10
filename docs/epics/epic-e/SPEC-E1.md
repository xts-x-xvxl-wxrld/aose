# SPEC-E1 — AccountDiscoveryAdapter interface + dummy adapter

## Goal
Define the canonical account discovery adapter contract for Epic E and implement a deterministic test adapter that returns predictable normalized candidates without external network access.

## Scope boundary
In scope:
- Adapter interface definition for account discovery.
- Normalized result and candidate shapes.
- Dummy adapter implementation (`dummy_predictable`).
- Unit tests for interface compatibility and deterministic output.
- No-op safe integration point for the Epic E handler to call adapters through one stable interface.

Out of scope:
- Real external provider calls.
- Canonical Account/Evidence database writes.
- Run caps, stop rules, and downstream enqueue behavior.
- Scoring, contact discovery, enrichment, copy, approval, or sending.
- Any provider-specific assumptions for PH-EPIC-E-001.

## Contract touchpoints
Consumes:
- `WorkItem.stage = account_discovery`
- `payload.v = 1`
- `payload.data.query_object_id`

Reads:
- `QueryObject`
- `SellerProfile` via `QueryObject.seller_id`

Produces at this ticket level:
- In-memory `AccountDiscoveryResult`
- In-memory normalized candidate list
- No canonical writes required in E1

Must align with:
- Epic E adapter contract and candidate shape supplied by the human
- Data Spine rule that modules exchange stable, versioned shapes and do not bypass canonical routing or queue handoff
- Epic B normalization and ID helper rules for domain handling and deterministic downstream IDs
- Policy pack requirement that provider-derived fields carry `source_provider`, `source_ref`, `observed_at`, and `confidence` :contentReference[oaicite:4]{index=4} :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6}

## Required behavior
1. Create an interface named `AccountDiscoveryAdapter`.
2. Expose one method:

   `search_accounts(query_object, limits, context) -> AccountDiscoveryResult`

3. `AccountDiscoveryResult` must contain:
   - `query_object_id`
   - `adapter_name`
   - `adapter_version`
   - `observed_at`
   - `candidates`

4. Each candidate must contain required fields:
   - `source_provider`
   - `source_ref`
   - `observed_at`
   - `confidence`
   - `legal_name`
   - `country`
   - `provenance`
   - `evidence`

5. Optional candidate fields:
   - `registry_id`
   - `domain`
   - `legal_name_normalized`
   - `raw_payload_ref`

6. Normalization rules in the adapter boundary:
   - `domain` normalized using Epic B domain normalization.
   - `country` uppercased ISO-like code when present.
   - `registry_id` passed through provider-specific helper or left absent.
   - `confidence` bounded to `0.0..1.0`.
   - No prose-only evidence. Evidence objects must contain structured pointer fields suitable for later canonical `Evidence` mapping. :contentReference[oaicite:7]{index=7}

7. The dummy adapter must:
   - require no network access
   - return deterministic candidates for the same `QueryObject`
   - include stable provenance and evidence fields
   - make tests independent of external provider availability

## Deliverables
- `worker/.../adapters/account_discovery/base.py` or equivalent
- `worker/.../adapters/account_discovery/types.py` or equivalent
- `worker/.../adapters/account_discovery/dummy_predictable.py`
- unit tests for adapter interface and deterministic output
- optional fixture file with deterministic dummy outputs

## Implementation notes
- Keep the interface source-agnostic. Do not encode AJPES or any other real source into the base contract.
- Keep normalization at the adapter boundary so downstream canonical write logic receives clean candidate objects.
- Do not allow adapters to write directly to `accounts`, `account_aliases`, `evidence`, or `work_items`.
- Do not decrement attempt budgets in the adapter itself; budget accounting belongs to orchestration/handler flow. The Data Spine and roadmap both separate module logic from orchestration and replay policy. :contentReference[oaicite:8]{index=8} :contentReference[oaicite:9]{index=9}

## Acceptance checks
- A unit test calls `dummy_predictable.search_accounts(...)` and gets a valid `AccountDiscoveryResult`.
- Repeating the same call with the same input returns structurally identical normalized candidates.
- Returned candidates satisfy required fields and normalization expectations.
- No external network access occurs during tests.

## Tests required
- unit: result object matches interface schema
- unit: dummy adapter returns predictable normalized candidates
- unit: domain normalization is applied at adapter output boundary
- unit: confidence remains within `0.0..1.0`
- unit: evidence objects are structured, not prose-only

## Failure handling
- Invalid or malformed adapter output must raise a contract-level error to the caller.
- The adapter itself should not park work items or enqueue downstream items.

## AI build prompt
Implement SPEC-E1 for Epic E account discovery. Create a source-agnostic `AccountDiscoveryAdapter` interface with `search_accounts(query_object, limits, context) -> AccountDiscoveryResult`. Add typed result/candidate models that enforce the required fields from the Epic E contract. Implement a `dummy_predictable` adapter with no network calls and deterministic normalized output. Normalize domains using the existing Epic B helper, uppercase country codes, clamp confidence to 0..1, and require structured evidence pointers. Do not write to canonical DB tables from the adapter. Add unit tests proving interface compatibility and deterministic output.