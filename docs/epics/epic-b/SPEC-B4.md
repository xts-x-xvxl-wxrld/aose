# Epic B4 — Account + AccountAlias

## Ticket
B4 — DB models: `Account` + `AccountAlias`

## Goal
Persist canonical account records and their alias set so discovery results can be stored under stable identities, deduplicated deterministically, and upgraded later without rewriting history.

This ticket must make it possible to:
1. create and store an `Account`
2. create and store aliases for that account
3. read an account back together with its aliases

## Source of truth
B4 follows:
- the Epic B contract
- the Data Spine canonical shape for `Account`
- the locked account ID precedence
- the locked account alias types
- the roadmap acceptance for B4

## Critical interpretation
- B4 is about canonical account persistence and alias storage
- merge logic is explicitly deferred
- alias storage must work now even if later identity upgrades/merges are not implemented yet
- the account ID formula is already frozen by B1 / Epic B contract and must not be reinvented here

## Scope boundary

### In scope
- Alembic migration for `accounts`
- Alembic migration for `account_aliases`
- ORM models for `Account` and `AccountAlias`
- minimal create/read verification surface sufficient to insert an account with aliases
- tests for schema, write/read, alias persistence, and deterministic identity behavior at the storage boundary

### Out of scope
- merge engine
- account consolidation workflow
- discovery adapters
- evidence extraction
- scorecards
- contacts
- account promotion logic beyond storing `status`
- address-based merge logic
- UI-heavy admin workflows

## Contract touchpoints
- canonical model names:
  - `Account` -> `accounts`
  - `AccountAlias` -> `account_aliases`
- account canonical ID precedence:
  - `account:<COUNTRY>-<REGISTRY_ID>`
  - `account:<normalized_domain>`
  - `account:tmp:<sha256(country|legal_name_normalized|source_provider|source_ref)>`
- account alias types:
  - `registry`
  - `domain`
  - `legal_name_normalized`
- deferred alias type:
  - `address_normalized`
- account dedup semantics:
  - primary: `country + registry_id`
  - secondary: `normalized_domain`
  - tertiary name/address logic deferred

## Canonical model contract

## 1) Account

### Table name
`accounts`

### ORM class
`Account`

### Required logical fields
Persist the account with these logical fields:

- `account_id`
- `name`
- `domain`
- `country`
- `provenance`
- `evidence_ids`
- `confidence`
- `status`
- `v`

### Storage rules
Do not collapse the account into one opaque JSON blob.

The persistence shape must preserve these fields in a queryable way. Acceptable storage pattern:
- scalar columns for scalar fields
- JSONB for structured collections

A practical mapping is:

- `account_id` -> string primary key
- `name` -> text
- `domain` -> text, nullable when canonical ID is registry- or tmp-based and no canonical domain is known
- `country` -> text
- `provenance` -> JSONB array
- `evidence_ids` -> JSONB array of strings
- `confidence` -> numeric/float
- `status` -> text
- `v` -> integer

### Account invariants
- `account_id` is the canonical account identifier
- `domain` must already be normalized if present
- `country` must be uppercase ISO-like code if present
- `provenance` is persisted explicitly; do not drop source lineage
- `evidence_ids` is persisted explicitly as a list of evidence references
- `status` is stored but B4 does not implement promotion rules
- `v` is required

## 2) AccountAlias

### Table name
`account_aliases`

### ORM class
`AccountAlias`

### Required logical fields
Persist aliases as first-class rows, not embedded only on the account record.

Required logical fields:

- `account_alias_id`
- `account_id`
- `alias_type`
- `alias_value`
- `source_provider`
- `source_ref`
- `created_at`
- `v`

### Alias type semantics
Allowed alias types for B4:
- `registry`
- `domain`
- `legal_name_normalized`

Forbidden in B4:
- `address_normalized` as an implemented alias type
- any invented alias type not frozen by the contract

### Alias value shape rules
Because alias types have different logical shapes, storage must remain explicit but practical.

A valid B4 storage rule is:
- `alias_type` stores the frozen type label
- `alias_value` stores the canonical string value for the alias
- `source_provider` and `source_ref` capture provenance needed to reconstruct trust and origin

Per-type expectations:
- `registry`
  - `alias_value` stores the registry ID string
  - `source_provider` stores registry source such as `AJPES`
  - `source_ref` stores provider-specific reference when available
- `domain`
  - `alias_value` stores normalized domain string
- `legal_name_normalized`
  - `alias_value` stores normalized legal name string

### AccountAlias invariants
- every alias belongs to one `Account`
- alias rows are appendable and durable
- alias storage must support future identity upgrade without losing prior identifiers
- aliases are not a substitute for the canonical `account_id`
- alias values must already be normalized before persistence where normalization rules exist

## Relationship rules
- `account_aliases.account_id` must reference `accounts.account_id`
- use a normal foreign key if that fits the current repo conventions and migration base cleanly
- at minimum, index `account_id` on `account_aliases`
- do not introduce cascade behavior beyond what the repo already standardizes

## Identity and dedup rules at B4 boundary

### Canonical ID
`account_id` must already be produced using the frozen Epic B precedence. B4 does not define a new formula.

### Required storage behavior
B4 must support storing:
1. registry-based canonical accounts
2. domain-based canonical accounts
3. tmp-hash canonical accounts when neither registry nor domain exists

### Deferred behavior
B4 does not need to implement:
- deterministic merge of domain-based account into registry-based account
- identity upgrade workflow
- alias backfill migration
- address-normalized dedup
- trust-ranked field conflict resolution

But B4 must not block those future behaviors. Alias persistence must preserve enough data for later upgrade/merge work.

## Account field semantics

### Name
- human-readable canonical name for the account
- may reflect the best current canonical name
- B4 does not implement multi-source name conflict resolution

### Domain
- canonical normalized domain when known
- may be null for registry-only or tmp cases
- storing a domain on the account does not remove the need for a `domain` alias row when alias persistence is part of the source record

### Country
- uppercase ISO-like code when known
- required if the canonical account ID is registry-based
- may be nullable only if current repo conventions and upstream data shape truly require it

### Provenance
- structured lineage for how the account was observed
- preserve as JSONB array or equivalent practical structure
- B4 does not need a separate provenance table

### Evidence IDs
- list of evidence references grounding the account record
- stored as string references only in B4
- B4 does not require evidence table integration beyond referential shape

### Confidence
- numeric confidence for the current account record
- B4 does not define a scoring algorithm

### Status
Expected values at this stage are account lifecycle labels already implied by the Data Spine, such as:
- `candidate`
- `target`

Do not invent a wider status taxonomy in B4.

## DB design rules

### Required indexes
Minimum:
- primary key on `accounts.account_id`
- primary key on `account_aliases.account_alias_id`
- index on `account_aliases.account_id`
- index on `accounts.domain`
- composite index on `account_aliases (alias_type, alias_value)`

Optional only if already standard in the repo:
- index on `accounts.country`
- index on `accounts.status`
- composite index on `account_aliases (account_id, alias_type)`

Do not add speculative indexes beyond these needs.

### Required constraints
- `accounts.account_id` must be unique by primary key
- `account_aliases.account_alias_id` must be unique by primary key
- `account_aliases.account_id` must be non-null
- `account_aliases.alias_type` must be non-null
- `account_aliases.alias_value` must be non-null
- `accounts.name`, `provenance`, `evidence_ids`, `confidence`, `status`, and `v` must be non-null unless the repo already models optionality explicitly
- `accounts.domain` may be nullable
- `accounts.country` should be non-null unless tmp-fallback cases require nullability in the current implementation path

### Uniqueness policy for aliases
B4 should prevent obvious duplicate alias rows within the same account, but should not prematurely encode global merge semantics.

Recommended minimum:
- unique constraint on (`account_id`, `alias_type`, `alias_value`)

Optional only if clearly safe for current source diversity:
- unique constraint on (`alias_type`, `alias_value`) for alias types that are expected to map to one canonical account
- do not add this broader uniqueness rule unless you are certain it will not block legitimate current data ingestion

### Non-requirements for B4
- no global alias conflict resolver
- no account merge table
- no winner/loser merge markers
- no history rewrite of existing account IDs
- no source-trust reconciliation engine
- no address-normalized alias type
- no score-driven promotion logic

## Migration requirements
Create one migration, or the minimal migration set required by repo conventions, that:
- creates `accounts`
- creates `account_aliases`
- creates required indexes
- creates the account-to-alias linkage
- is reversible
- does not create unrelated tables

Migration must be deterministic and minimal.

## ORM requirements
Create ORM models that:
- match the migration exactly
- use contract-aligned field names
- keep canonical account fields explicit and readable
- keep aliases as first-class rows
- do not hide alias persistence inside one serialized account blob
- do not introduce speculative inheritance or base abstractions just for B4

## Verification surface
Provide one minimal create/read path consistent with the existing API/admin scaffold.

Acceptable examples:
- endpoint to create an account plus aliases and fetch it back
- admin/debug route that does the same
- service-layer verification invoked through tests if the repo is not yet exposing these models through API routes

The minimum acceptance behavior is:
1. create one account
2. persist it
3. create aliases for that account
4. persist them
5. read the account back together with its aliases

## Tests

### Schema/model tests
- `Account` row can be created with all required fields
- `AccountAlias` row can be created with all required fields
- `provenance` round-trips correctly
- `evidence_ids` round-trips correctly
- `domain` can be null for appropriate cases
- `alias_type` accepts only allowed B4 types if validation is implemented at model level

### Relationship tests
- aliases are linked to the correct account
- aliases can be fetched by `account_id`
- account can be read back with all aliases attached

### Alias storage tests
- registry alias persists with provider provenance
- domain alias persists as normalized string
- legal-name-normalized alias persists as normalized string
- duplicate alias row for the same account is rejected if the uniqueness rule is implemented
- multiple alias types for the same account are allowed

### Identity boundary tests
- registry-based canonical account can be inserted
- domain-based canonical account can be inserted
- tmp-hash canonical account can be inserted
- B4 does not require merge when a later registry alias appears
- alias storage preserves data needed for future upgrade/merge work

### Contract guard tests
- B4 does not create evidence, scorecard, contact, draft, approval, or send tables
- B4 does not implement merge workflow side effects
- B4 does not implement `address_normalized` alias type

## Acceptance checks
B4 is complete when all of the following are true:

1. `accounts` exists in Postgres
2. `account_aliases` exists in Postgres
3. an account can be inserted and stored
4. aliases can be inserted and stored for that account
5. stored aliases can be read back with the account
6. alias storage works for:
   - `registry`
   - `domain`
   - `legal_name_normalized`
7. merge logic remains deferred
8. migration, lint, and tests pass in the Epic A toolchain

## File deliverables
Expected deliverables are limited to the minimum needed for B4, such as:
- Alembic migration for `accounts` and `account_aliases`
- ORM model file updates/additions
- test file(s)
- minimal verification surface if required by current scaffold

## Structure rules
- stay inside the Epic A scaffold
- do not create new root-level packages such as `shared/`, `common/`, or `core/`
- reuse existing API package layout and Alembic migration path
- avoid speculative shared abstractions
- prefer placing account persistence logic in the API-side domain/model layer unless the repo already has a clear canonical persistence location

## Forbidden decisions
- do not implement merge engine in B4
- do not invent new account ID formulas
- do not invent new alias types
- do not implement `address_normalized` alias storage in B4
- do not collapse aliases into one opaque JSON-only column as the sole storage form
- do not widen scope into evidence, scoring, contacts, drafts, approval, or send
- do not encode speculative global uniqueness rules that could block future merge handling without contract support

## Completion standard
The coding result must report:
- files changed
- migration name
- ORM fields added
- indexes added
- constraints added
- verification path used
- tests added
- commands run and results
- any exact contract ambiguity encountered

## AI build prompt
Implement Epic B4 only: persist `Account` and `AccountAlias`.

Follow the Epic B contract exactly.

Important rules:
- `Account` and `AccountAlias` are canonical persisted models
- alias storage must work now
- merge logic is deferred
- canonical account ID precedence is already frozen and must not be redefined here

Scope:
- add migration(s) for `accounts` and `account_aliases`
- add ORM model(s) `Account` and `AccountAlias`
- add minimal verification path to insert an account with aliases and fetch it back
- add tests

Required `Account` logical fields:
- account_id
- name
- domain
- country
- provenance
- evidence_ids
- confidence
- status
- v

Required `AccountAlias` logical fields:
- account_alias_id
- account_id
- alias_type
- alias_value
- source_provider
- source_ref
- created_at
- v

Allowed alias types:
- registry
- domain
- legal_name_normalized

Not allowed in B4:
- address_normalized
- invented alias types

Storage rules:
- keep account fields explicit and queryable
- keep aliases as first-class rows
- use JSONB for structured list fields such as provenance and evidence_ids
- do not replace accounts with one opaque blob
- do not store aliases only inside one JSON column on accounts

Relationship rules:
- every alias belongs to one account via `account_id`
- index `account_aliases.account_id`
- add a practical uniqueness rule to prevent duplicate alias rows within the same account

Identity rules:
- `account_id` follows the canonical account ID helper contract already frozen in Epic B
- support storage for registry-based, domain-based, and tmp-hash accounts
- do not implement merge or identity-upgrade workflow in this ticket

Required indexes:
- primary key on `accounts.account_id`
- primary key on `account_aliases.account_alias_id`
- index on `account_aliases.account_id`
- index on `accounts.domain`
- composite index on `account_aliases (alias_type, alias_value)`

Tests required:
- create/store account
- create/store aliases
- read account with aliases
- provenance round-trip
- evidence_ids round-trip
- registry/domain/legal_name_normalized aliases persist correctly
- merge remains unimplemented
- address_normalized alias type is not implemented

Run only the repo-standard containerized verification commands relevant to changed files.