# SPEC-D2 — QueryObject generator (simple heuristic v0)

## Goal
Generate and persist 3 to 10 structured QueryObjects from SellerProfile input using a deterministic local heuristic with no external search or discovery side effects.

## Scope
### In scope
- QueryObject generation
- QueryObject persistence
- Generate action from stored SellerProfile
- Generate action from submitted SellerProfile data
- Deterministic local heuristic logic

### Out of scope
- External search calls
- Account discovery
- Discovery adapters
- Fit/intent scoring
- People search
- Contact enrichment
- Draft generation
- Approval workflow
- Sending

## Contract alignment
- Canonical model: `QueryObject`
- Canonical table: `query_objects`
- Generator version:
  - `simple_heuristic_v0`
- Input source:
  - SellerProfile fields only
- Allowed generation inputs:
  - `offer.what`
  - `offer.where`
  - `offer.who`
  - `offer.positioning`
  - `constraints.avoid_claims`
  - `constraints.allowed_channels`
  - `constraints.languages`

## Canonical QueryObject shape
```json
{
  "query_object_id": "string",
  "seller_id": "seller:<seller_slug>",
  "buyer_context": "string",
  "priority": 1,
  "keywords": ["string"],
  "exclusions": ["string"],
  "rationale": "string",
  "v": 1
}
Output contract

Minimum generated count:

3

Maximum generated count:

10

Output format:

structured QueryObjects only

Prose blobs are forbidden

Requirements

A user can click a generate action from a stored SellerProfile or freshly submitted SellerProfile data.

Generation must store between 3 and 10 QueryObjects.

QueryObject.seller_id must reference an existing SellerProfile.seller_id.

Each QueryObject must include:

query_object_id

seller_id

buyer_context

priority

keywords

exclusions

rationale

v

priority must be numeric.

keywords must be an array of strings.

exclusions must be an array of strings.

rationale must be structured and concise.

Output must be deterministic for the same SellerProfile input.

Output ordering must be stable.

Generation must not perform external calls.

Heuristic behavior

The heuristic may derive QueryObjects by:

combining offer.who and offer.where into buyer contexts

translating offer.what and offer.positioning into search keywords

applying constraints.avoid_claims into exclusions or query phrasing constraints

using explicit ranking rules to assign deterministic priority

Forbidden behavior

No external search calls

No account discovery during generation

No scoring side effects

No enrichment side effects

No prose output instead of structured records

No detached QueryObjects without valid seller_id

No fewer than 3 or more than 10 QueryObjects

Replay and persistence rules

Generate action must persist QueryObjects.

Re-running generation must not invent new schema variants.

If work items are used internally, idempotency and trace behavior must follow Epic B rules.

No duplicate unintended side effects beyond the intended stored QueryObject set.

Suggested deliverables

QueryObject generator service

QueryObject persistence service

Generate queries API/action handler

Determinism unit tests

Count and shape tests

Integration test for SellerProfile → generated QueryObjects

Acceptance criteria

Clicking generate queries stores 3 to 10 QueryObjects.

Each stored QueryObject contains:

buyer_context

priority

keywords

exclusions

rationale

Generated QueryObjects are linked to the correct seller_id.

Re-running generation does not invent schema drift or broken linkage.

No external discovery or search side effects occur.

Implementation constraints

Use only canonical model names.

Use only canonical field names.

Do not add discovery-specific fields into QueryObject.

Do not depend on Epic E adapter infrastructure.