# SPEC-D3 — QueryObject review screen

## Goal
Provide a review/edit screen where a human can inspect generated QueryObjects and modify allowed fields before any future discovery work.

## Scope
### In scope
- List generated QueryObjects
- View generated QueryObjects
- Edit allowed QueryObject fields
- Save QueryObject edits
- Persist edits to canonical storage

### Out of scope
- Account discovery
- Adapter execution
- Fit/intent scoring
- People search
- Contact enrichment
- Draft generation
- Approval workflow
- Sending
- Any new stage names
- Any new canonical record families

## Contract alignment
- Review is not a queue stage.
- Epic D in-scope stages remain:
  - `seller_profile_build`
  - `query_objects_generate`
- Canonical model:
  - `QueryObject`
- Canonical table:
  - `query_objects`

## Editable fields
The review UI/API may allow edits to:
- `buyer_context`
- `priority`
- `keywords`
- `exclusions`
- `rationale`

## Non-editable fields
The review UI/API must not allow edits to:
- `query_object_id`
- `seller_id`
- `v`

## Requirements
- The review screen must list generated QueryObjects for a selected SellerProfile.
- The user must be able to edit:
  - `keywords`
  - `exclusions`
- The user may also edit:
  - `buyer_context`
  - `priority`
  - `rationale`
- Save must persist edits to stored QueryObjects.
- Save must not trigger account discovery automatically.
- The screen must not require Epic E components for acceptance.
- Immutable fields must be read-only or excluded from edit controls.
- Validation must preserve canonical types.

## Validation rules
- `keywords` must remain an array of strings.
- `exclusions` must remain an array of strings.
- `priority` must remain numeric.
- `seller_id` must not change.
- `query_object_id` must not change.
- `v` must not change.

## API behavior
### List
- Return generated QueryObjects for a selected `seller_id`

### Update
- Accept edits only for allowed fields
- Reject attempts to mutate immutable fields
- Persist valid edits to canonical storage
- Return updated QueryObject records

## UI behavior
- Show generated QueryObjects in a review list or table
- Allow inline or form-based editing of editable fields
- Save changes explicitly
- Do not auto-run discovery on save
- Do not create a new stage for review

## Suggested deliverables
- QueryObject review screen UI
- QueryObject update API endpoint
- Editable vs immutable field schema enforcement
- Persistence tests
- Immutable field protection tests

## Acceptance criteria
- User can edit keywords before discovery.
- User can edit exclusions before discovery.
- Edits persist to stored QueryObjects.
- Saving does not trigger discovery.
- `query_object_id`, `seller_id`, and `v` cannot be edited.
- No new stage name is introduced for review/edit.

## Implementation constraints
- Review/edit is UI/API capability only.
- Do not invent a review stage.
- Do not add new canonical enums.
- Do not add new canonical models.
- Do not require Epic E components.