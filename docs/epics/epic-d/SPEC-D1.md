# SPEC-D1 — SellerProfile API + UI form

## Goal
Implement SellerProfile create/read/update through a minimal web form and API so a user can persist canonical seller input for downstream query generation.

## Scope
### In scope
- SellerProfile create
- SellerProfile read
- SellerProfile update
- Form rendering
- Validation
- Persistence to the canonical `seller_profiles` table

### Out of scope
- QueryObject generation
- Account discovery
- Fit/intent scoring
- People search
- Contact enrichment
- Draft generation
- Approval workflow
- Sending
- Any new canonical record families

## Contract alignment
- Canonical model: `SellerProfile`
- Canonical table: `seller_profiles`
- Allowed Epic D stage names:
  - `seller_profile_build`
  - `query_objects_generate`
- Review/edit is a UI/API capability only, not a new stage
- Stored SellerProfile shape must remain canonical:
  - `seller_id`
  - `offer`
  - `constraints`
  - `created_at`
  - `v`

## Canonical record shape
```json
{
  "seller_id": "seller:<seller_slug>",
  "offer": {
    "what": "string",
    "where": "string",
    "who": "string",
    "positioning": "string"
  },
  "constraints": {
    "avoid_claims": ["string"],
    "allowed_channels": ["string"],
    "languages": ["string"]
  },
  "created_at": "datetime",
  "v": 1
}
Requirements

The UI must support:

create seller profile

edit seller profile

load persisted seller profile

The API must preserve the nested offer and constraints structure.

The form may use individual inputs, but persistence must map back into the canonical nested structure.

seller_id must follow:

seller:<seller_slug>

v must always be stored as:

1

No extra policy fields may be introduced into the SellerProfile shape.

No flattening of offer or constraints into ad hoc API contract fields.

API behavior
Create

Accept canonical SellerProfile input

Validate required fields

Persist canonical record

Return stored SellerProfile

Read

Load persisted SellerProfile by seller_id

Return canonical nested structure

Update

Allow updates to canonical editable SellerProfile content

Preserve canonical shape

Do not mutate v away from 1

Keep seller_id format valid

Suggested deliverables

SellerProfile API routes

SellerProfile request/response schemas

Persistence wiring to Epic B canonical model

SellerProfile form UI

Validation tests

Create/read/update integration test

Acceptance criteria

User can create SellerProfile via UI.

Stored record conforms to canonical SellerProfile shape.

User can load persisted SellerProfile.

User can edit and save SellerProfile.

No new stage names, enums, or canonical record families are introduced.

Implementation constraints

Do not rename canonical fields.

Do not invent new stage names.

Do not invent new canonical models.

Do not depend on Epic E or downstream components.