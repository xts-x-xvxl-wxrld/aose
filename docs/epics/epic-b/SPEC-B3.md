# Epic B3 — SellerProfile + QueryObject

## Ticket
B3 — DB models: `SellerProfile` + `QueryObject`

## Goal
Persist the seller-side source object and the structured search intents it produces, so later discovery stages can operate on stable, stored inputs instead of ad hoc prompt text.

This ticket must make it possible to:
1. create and store a `SellerProfile`
2. deterministically generate query objects from that seller profile
3. store the generated `QueryObject` records

## Source of truth
B3 follows:
- the Epic B contract
- the Data Spine canonical shapes for `SellerProfile` and `QueryObject`
- the policy-pack touchpoint that requires `SellerProfile.policy_pack_id`
- the roadmap acceptance for B3

## Critical interpretation
- `QueryObject` means structured search intent, not prose
- generation in B3 is a deterministic local transformation, not an LLM workflow
- B3 is persistence plus minimal generation/storage, not a UI-heavy feature
- do not drag Epic D UI scope into B3

## Scope boundary

### In scope
- Alembic migration for `seller_profiles`
- Alembic migration for `query_objects`
- ORM models for `SellerProfile` and `QueryObject`
- minimal deterministic query generation service/function
- minimal verification surface sufficient to create a seller profile and generate/store query objects
- tests for schema, write/read, and generation determinism

### Out of scope
- account discovery
- adapters or external search providers
- web UI
- review screen for query objects
- editing workflow beyond minimal persistence
- scoring, contacts, drafts, approval, sending
- speculative merge logic
- LLM-based query generation

## Contract touchpoints
- canonical model names:
  - `SellerProfile` -> `seller_profiles`
  - `QueryObject` -> `query_objects`
- Data Spine shapes:
  - `SellerProfile`
  - `QueryObject`
- policy touchpoint:
  - `SellerProfile.policy_pack_id`
  - `SellerProfile.constraints.avoid_claims`

## Canonical model contract

## 1) SellerProfile

### Table name
`seller_profiles`

### ORM class
`SellerProfile`

### Required fields
Persist the seller profile as structured data with these logical fields:

- `seller_id`
- `offer.what`
- `offer.where`
- `offer.who`
- `offer.positioning`
- `constraints.avoid_claims`
- `constraints.allowed_channels`
- `constraints.languages`
- `policy_pack_id`
- `created_at`
- `v`

### Storage rules
Do not collapse the entire seller profile into one opaque JSON blob.

The persistence shape must preserve these fields in a queryable way. Acceptable storage pattern:
- scalar text columns for scalar fields
- JSONB columns for array/list fields

A practical mapping is:

- `seller_id` -> string primary key
- `offer_what` -> text
- `offer_where` -> JSONB array of strings
- `offer_who` -> JSONB array of strings
- `offer_positioning` -> JSONB array of strings
- `constraints_avoid_claims` -> JSONB array of strings
- `constraints_allowed_channels` -> JSONB array of strings
- `constraints_languages` -> JSONB array of strings
- `policy_pack_id` -> string
- `created_at` -> timezone-aware timestamp
- `v` -> integer

### SellerProfile invariants
- `seller_id` is the canonical seller identifier
- `policy_pack_id` must be stored explicitly; do not infer it later
- `constraints.avoid_claims` must be persisted explicitly
- arrays remain ordered lists of strings
- `v` is required and defaults only if the contract already standardizes that default in code

## 2) QueryObject

### Table name
`query_objects`

### ORM class
`QueryObject`

### Required fields
Persist generated query objects with these logical fields:

- `query_object_id`
- `seller_id`
- `buyer_context`
- `priority`
- `keywords`
- `exclusions`
- `rationale`
- `v`

### Storage rules
The persistence shape must preserve these fields in a queryable way. Acceptable storage pattern:
- text column for `buyer_context`
- numeric column for `priority`
- JSONB arrays for `keywords` and `exclusions`
- text column for `rationale`

A practical mapping is:

- `query_object_id` -> string primary key
- `seller_id` -> string, non-null
- `buyer_context` -> text
- `priority` -> numeric/float
- `keywords` -> JSONB array of strings
- `exclusions` -> JSONB array of strings
- `rationale` -> text
- `v` -> integer

### QueryObject invariants
- every query object belongs to one seller profile via `seller_id`
- `QueryObject` is structured intent, not freeform copy
- `keywords` and `exclusions` are lists, not comma-joined strings
- `priority` must be numeric and stable across reruns of the same generator inputs
- `v` is required

## Relationship rules
- `query_objects.seller_id` must reference `seller_profiles.seller_id`
- use a normal foreign key if it fits the current repo conventions and migration base cleanly
- at minimum, index `seller_id` on `query_objects`
- do not introduce cascading behavior beyond what the repo already standardizes

## Query generation contract

## Purpose
Generate stored query objects from a stored seller profile using deterministic local logic.

## Inputs
Generation may use only persisted seller profile fields:
- `offer.what`
- `offer.where`
- `offer.who`
- `offer.positioning`
- `constraints.avoid_claims`
- `constraints.allowed_channels`
- `constraints.languages`
- `policy_pack_id`

## Outputs
Each generated query object must contain:
- `buyer_context`
- `priority`
- `keywords`
- `exclusions`
- `rationale`
- `seller_id`
- `v`

## Hard rules
- no external network calls
- no search-provider calls
- no LLM/API calls
- no dependence on mutable runtime state
- same seller profile input must produce the same query objects in the same order
- output must be structured, not paragraph prose
- output must be storable directly in `query_objects`

## Generation behavior
B3 does not need a sophisticated generator. It needs a deterministic one.

A valid minimal strategy:
- derive one or more buyer-context combinations from `offer.where` and `offer.who`
- use `offer.what` and `offer.positioning` to seed keywords
- use a conservative static exclusion list, optionally extended from seller constraints
- produce rationale as a short audit-facing explanation, not marketing copy
- assign stable priorities based on fixed ordering logic

## Minimum output requirement
- generate at least 1 query object for a valid seller profile
- generating multiple query objects is allowed
- keep the count modest and deterministic
- do not import Epic D’s later “3–10 queries” target as a hard B3 requirement unless it already exists in code conventions

## Identifier rules
- `seller_id` follows the canonical seller ID contract
- `query_object_id` must be an application-generated string identifier
- do not invent a global cross-epic ID formula for `query_object_id` if none is frozen in the contract
- if the repo already has a standard app-level ID utility, reuse it
- if not, keep the `query_object_id` generation local to B3 and document it as an implementation detail, not a new canonical contract

## DB design rules

### Required indexes
Minimum:
- primary key on `seller_profiles.seller_id`
- primary key on `query_objects.query_object_id`
- index on `query_objects.seller_id`

Optional only if already standard in the repo:
- index on `query_objects.priority`
- index on `seller_profiles.policy_pack_id`

Do not add speculative indexes beyond these needs.

### Required constraints
- `seller_profiles.seller_id` must be unique by primary key
- `query_objects.query_object_id` must be unique by primary key
- `query_objects.seller_id` must be non-null
- `buyer_context`, `priority`, `keywords`, `exclusions`, `rationale`, and `v` must be non-null for `query_objects`
- required seller profile fields must be non-null unless the repo already models optionality explicitly

### Non-requirements for B3
- no uniqueness constraint preventing multiple query objects per seller
- no dedup engine for semantically similar query objects
- no historical versioning system beyond `v`
- no review/approval state on query objects
- no queue orchestration

## Migration requirements
Create one migration, or the minimal migration set required by repo conventions, that:
- creates `seller_profiles`
- creates `query_objects`
- creates required indexes
- creates the seller-to-query-object linkage
- is reversible
- does not create unrelated tables

Migration must be deterministic and minimal.

## ORM requirements
Create ORM models that:
- match the migration exactly
- use contract-aligned field names
- keep structured fields explicit and readable
- do not replace explicit fields with one opaque JSON blob
- do not introduce speculative base abstractions just for B3

## Verification surface
Provide one minimal create-and-generate path consistent with the existing API/admin scaffold.

Acceptable examples:
- endpoint to create a seller profile plus endpoint to generate/store query objects
- admin/debug route that does the same
- service-layer verification invoked through tests if the repo is not yet exposing these models through API routes

The minimum acceptance behavior is:
1. create one seller profile
2. persist it
3. invoke deterministic generation from that stored profile
4. persist the resulting query objects
5. read them back by `seller_id`

## Tests

### Schema/model tests
- `SellerProfile` row can be created with all required fields
- `QueryObject` row can be created with all required fields
- array/list fields round-trip correctly
- `policy_pack_id` is stored on `SellerProfile`
- `constraints_avoid_claims` is stored explicitly

### Relationship tests
- query objects are linked to the correct seller profile
- query objects can be fetched by `seller_id`

### Generation tests
- valid seller profile generates at least one query object
- repeated generation from the same input is deterministic
- repeated generation preserves output order
- generated query objects contain:
  - `buyer_context`
  - `priority`
  - `keywords`
  - `exclusions`
  - `rationale`
  - `seller_id`
  - `v`

### Storage tests
- generated query objects can be stored and read back
- `keywords` and `exclusions` remain arrays after round-trip
- `priority` persists as numeric
- seller profile fields remain readable after round-trip

### Contract guard tests
- B3 does not create account, evidence, scorecard, contact, draft, approval, or send tables
- B3 does not make external calls during generation

## Acceptance checks
B3 is complete when all of the following are true:

1. `seller_profiles` exists in Postgres
2. `query_objects` exists in Postgres
3. a seller profile can be created and stored
4. query objects can be deterministically generated from that seller profile
5. generated query objects can be stored
6. stored query objects can be read back by `seller_id`
7. `SellerProfile.policy_pack_id` is persisted
8. migration, lint, and tests pass in the Epic A toolchain

## File deliverables
Expected deliverables are limited to the minimum needed for B3, such as:
- Alembic migration for `seller_profiles` and `query_objects`
- ORM model file updates/additions
- deterministic query generation service/function
- test file(s)
- minimal verification surface if required by current scaffold

## Structure rules
- stay inside the Epic A scaffold
- do not create new root-level packages such as `shared/`, `common/`, or `core/`
- reuse existing API package layout and Alembic migration path
- avoid speculative shared abstractions
- prefer placing B3 generation logic in the API-side domain/service layer unless the repo already has a clear canonical utilities location

## Forbidden decisions
- do not use an LLM or external provider for B3 generation
- do not create a UI review flow in B3
- do not create discovery adapters in B3
- do not collapse seller profile into an opaque JSON-only record
- do not convert keywords/exclusions into plain text blobs
- do not invent new canonical IDs beyond what the contract already freezes
- do not widen scope into B4+

## Completion standard
The coding result must report:
- files changed
- migration name
- ORM fields added
- indexes added
- generation function(s) added
- verification path used
- tests added
- commands run and results
- any exact contract ambiguity encountered

## AI build prompt
Implement Epic B3 only: persist `SellerProfile` and `QueryObject`, and add deterministic query generation/storage.

Follow the Epic B contract exactly.

Important rules:
- `SellerProfile` and `QueryObject` are canonical persisted models
- `QueryObject` means structured search intent, not prose
- generation in B3 must be deterministic and local
- do not use LLMs, external APIs, web search, or discovery adapters

Scope:
- add migration(s) for `seller_profiles` and `query_objects`
- add ORM model(s) `SellerProfile` and `QueryObject`
- add minimal deterministic query generation service/function
- add minimal verification path to create seller profile and generate/store query objects
- add tests

Required `SellerProfile` logical fields:
- seller_id
- offer.what
- offer.where
- offer.who
- offer.positioning
- constraints.avoid_claims
- constraints.allowed_channels
- constraints.languages
- policy_pack_id
- created_at
- v

Required `QueryObject` logical fields:
- query_object_id
- seller_id
- buyer_context
- priority
- keywords
- exclusions
- rationale
- v

Storage rules:
- keep seller profile fields explicit and queryable
- use JSONB arrays for list fields
- do not store keywords or exclusions as comma-separated strings
- do not replace the whole seller profile with one opaque JSON blob

Relationship rules:
- every query object belongs to one seller profile via seller_id
- index `query_objects.seller_id`

Generation rules:
- same seller profile input must produce the same query objects in the same order
- generate at least one query object for a valid seller profile
- output must contain buyer_context, priority, keywords, exclusions, rationale, seller_id, and v
- rationale is short and audit-facing
- no network calls
- no provider calls
- no LLM calls

Identifier rules:
- `seller_id` follows the canonical seller ID helper contract
- `query_object_id` must be an application-generated string
- if the repo already has a standard ID utility, reuse it
- otherwise keep `query_object_id` generation local to B3 and document it as a local implementation detail, not a new global contract

Required indexes:
- primary key on `seller_profiles.seller_id`
- primary key on `query_objects.query_object_id`
- index on `query_objects.seller_id`

Tests required:
- create/store seller profile
- deterministic generation from seller profile
- store/read generated query objects
- policy_pack_id persists on seller profile
- constraints_avoid_claims persists explicitly
- keywords/exclusions round-trip as arrays
- no external calls during generation

Run only the repo-standard containerized verification commands relevant to changed files.