# Epic B2 — WorkItem persistence contract

## Ticket
B2 — DB model: WorkItem with embedded trace fields

## Goal
Persist the universal WorkItem envelope in Postgres as the database truth, so stage-based processing can be stored, read back, and replayed safely.

## Source of truth
This ticket must follow the locked Epic B contract and the Data Spine envelope.

Critical interpretation:
- The roadmap label “WorkItem + Trace” is shorthand.
- Epic B lock explicitly forbids a separate `Trace` table in Epic B.
- Trace must be stored as fields on `work_items`.

## Scope boundary
In scope:
- Alembic migration for `work_items`
- SQLAlchemy ORM model for `WorkItem`
- required columns from the locked contract
- indexes required for stage-driven reads and replay/debug lookup
- minimal create/read surface sufficient for verification
- unit tests for model creation/read and schema expectations

Out of scope:
- separate `Trace` table
- `StructuredEvent` table
- queue consumer logic
- stage router
- replay endpoint
- canonical record tables from B3+
- merge logic
- business-stage execution logic

## Contract touchpoints
- Universal envelope: `WorkItem`
- Stage vocabulary
- Replay-safety support fields
- Trace shape embedded into `WorkItem`
- Epic B explicit non-goals

## Canonical table contract

### Table name
`work_items`

### ORM class
`WorkItem`

### Required columns
The model must include these persisted fields:

- `work_item_id`
- `entity_ref_type`
- `entity_ref_id`
- `stage`
- `payload_json`
- `payload_version`
- `attempt_budget_remaining`
- `attempt_budget_policy`
- `idempotency_key`
- `trace_run_id`
- `trace_parent_work_item_id`
- `trace_correlation_id`
- `trace_policy_pack_id`
- `created_at`

## Column semantics

### Identity
- `work_item_id`: canonical primary identifier for the row
- Must be the primary key
- String-based, not DB auto-increment

### Entity anchor
- `entity_ref_type`: extracted from envelope `entity_ref.type`
- `entity_ref_id`: extracted from envelope `entity_ref.id`
- These are stored as first-class columns, not buried only inside JSON

### Routing
- `stage`: canonical stage label from the locked enum pack
- No stage invention outside the locked stage vocabulary

### Payload
- `payload_json`: JSON/JSONB storage of stage-specific payload data
- `payload_version`: integer or small integer extracted from `payload.v`

### Attempt budget
- `attempt_budget_remaining`: remaining budget count
- `attempt_budget_policy`: policy label such as `standard`

### Replay and trace
- `idempotency_key`: stored exactly as provided by the originating layer
- `trace_run_id`
- `trace_parent_work_item_id` nullable
- `trace_correlation_id`
- `trace_policy_pack_id`

### Timestamps
- `created_at`: persisted creation timestamp from the envelope
- Timezone-aware timestamp preferred

## Storage mapping rules
The DB model should flatten the envelope into columns while preserving the original payload body in JSON form.

Expected mapping from envelope shape:

```json
{
  "work_item_id": "wi_...",
  "entity_ref": { "type": "account", "id": "account:SI-1234567" },
  "stage": "account_discovery",
  "payload": { "v": 1, "data": { "query_object_id": "q_87f1" } },
  "attempt_budget": { "remaining": 3, "policy": "standard" },
  "idempotency_key": "acctdisc:account:SI-1234567:q_87f1:v1",
  "trace": {
    "run_id": "run_...",
    "parent_work_item_id": "wi_...",
    "correlation_id": "corr_account:SI-1234567"
  },
  "created_at": "2026-02-25T10:12:33Z"
}

Flattening target:

entity_ref.type -> entity_ref_type

entity_ref.id -> entity_ref_id

payload.data or full payload body -> payload_json

payload.v -> payload_version

attempt_budget.remaining -> attempt_budget_remaining

attempt_budget.policy -> attempt_budget_policy

trace.run_id -> trace_run_id

trace.parent_work_item_id -> trace_parent_work_item_id

trace.correlation_id -> trace_correlation_id

policy_pack_id for Epic B defaults to safe_v0_1, stored in trace_policy_pack_id

DB design rules

Use Postgres-compatible types

Prefer JSONB for payload_json

Use explicit nullable/non-nullable constraints matching the contract

trace_parent_work_item_id is nullable

work_item_id must be unique by primary key

Do not add foreign keys to future tables in this ticket

Do not introduce generic “metadata” blobs as a substitute for explicit trace columns

Required indexes

Add indexes for the access patterns already named in the roadmap and contract.

Minimum required indexes:

index on stage

index on idempotency_key

composite index on (entity_ref_type, entity_ref_id)

Recommended but optional only if already standard in the repo:

index on trace_correlation_id

index on created_at

Do not add speculative indexes beyond clear replay/debug or stage-routing needs.

Constraints and non-constraints

Required:

primary key on work_item_id

Not required for B2 unless already explicitly locked elsewhere:

uniqueness on idempotency_key

foreign keys to future canonical tables

enum DB types for stage values

Reason:

roadmap requires indexes on stage, idempotency_key, and entity_ref

the locked Epic B contract does not require a DB uniqueness rule on work_items.idempotency_key

uniqueness for side-effect idempotency is primarily a later concern on side-effect tables

Migration requirements

Create one Alembic migration that:

creates work_items

creates the required indexes

is reversible with downgrade

does not create unrelated tables

Migration must be deterministic and minimal.

ORM requirements

Create an ORM model that:

matches the migration exactly

exposes all required fields

uses clear names aligned to the contract

does not split trace into a separate model

does not hide contract fields behind convenience-only wrappers

Verification surface

Provide one minimal create/read path for acceptance. Either is acceptable:

a simple API endpoint under the existing API scaffold for create/read of WorkItem

or an admin/debug route already consistent with the repo structure

This ticket does not require a full CRUD system.

Minimum acceptance behavior:

can insert one WorkItem

can fetch that same WorkItem

fetched row preserves all required fields

JSON payload is readable back without shape drift

Tests

Add focused tests for:

Schema/model tests

WorkItem row can be created with all required fields

trace_parent_work_item_id accepts null

payload is stored and read back correctly

payload_version persists separately from the JSON body

Migration tests

migration creates work_items

migration creates required indexes

Read/write behavior

insert and retrieve a representative row

representative row includes:

entity_ref_type

entity_ref_id

stage

idempotency_key

trace_*

created_at

Contract guard tests

no separate trace table is created by this ticket

no structured_events table is created by this ticket

Acceptance checks

B2 is complete when all of the following are true:

work_items exists in Postgres

the table contains all required contract fields

indexes exist on:

stage

idempotency_key

(entity_ref_type, entity_ref_id)

one WorkItem can be created and read through the chosen verification surface

no separate Trace table exists

migration, lint, and tests pass in the Epic A toolchain

File deliverables

Expected deliverables are limited to the minimum needed for B2, such as:

Alembic migration for work_items

ORM model file update/addition

test file(s)

minimal API/admin verification surface if not already present

Structure rules

stay inside the Epic A repo scaffold

do not create new root packages

reuse existing API package and migration layout

avoid speculative shared abstractions

Forbidden decisions

do not create a trace table

do not create a structured_events table

do not implement queue handlers

do not add B3+ canonical tables

do not invent new stage labels

do not rename contract fields into “nicer” alternatives

do not replace explicit columns with one opaque envelope blob

Completion standard

The coding result must report:

files changed

migration name

ORM fields added

indexes added

verification path used

tests added

commands run and results

any exact contract ambiguity encountered

AI build prompt

Implement Epic B2 only: persist the Data Spine WorkItem envelope in Postgres.

Follow the locked Epic B contract exactly.

Important contract interpretation:

The roadmap phrase “WorkItem + Trace” does NOT mean a separate Trace table.

Trace must be embedded as columns on the work_items table.

Epic B explicitly forbids a separate Trace table and forbids StructuredEvent in this ticket.

Scope:

add Alembic migration for work_items

add ORM model WorkItem

add required indexes

add a minimal create/read verification surface

add tests

Required table:

table name: work_items

model name: WorkItem

Required fields:

work_item_id

entity_ref_type

entity_ref_id

stage

payload_json

payload_version

attempt_budget_remaining

attempt_budget_policy

idempotency_key

trace_run_id

trace_parent_work_item_id

trace_correlation_id

trace_policy_pack_id

created_at

Mapping rules:

flatten entity_ref.type to entity_ref_type

flatten entity_ref.id to entity_ref_id

flatten payload.v to payload_version

store payload body in payload_json

flatten attempt budget and trace fields into explicit columns

trace_parent_work_item_id is nullable

DB rules:

work_item_id is the primary key

use Postgres-compatible types

prefer JSONB for payload_json

do not add foreign keys to future tables

do not add a separate Trace model/table

Required indexes:

index on stage

index on idempotency_key

composite index on (entity_ref_type, entity_ref_id)

Do not assume uniqueness on idempotency_key unless already explicitly required by code you are integrating with. For B2, the roadmap requires indexing, not a new uniqueness policy.

Verification surface:

provide one minimal create/read path in the existing API/admin structure

enough to create one WorkItem and fetch it back

Tests required:

create/read WorkItem succeeds

payload round-trips correctly

null parent trace works

required indexes exist

no separate trace table is created

no structured_events table is created

Structure rules:

stay inside the Epic A scaffold

reuse existing API package layout and Alembic migration path

do not create new root-level shared packages

Run repo-standard verification commands relevant to changed files, using the Epic A containerized workflow.


One correction to carry forward into every B2 prompt: never say “Trace table” again for Epic B. The correct phrase is “embedded trace fields on WorkItem.”