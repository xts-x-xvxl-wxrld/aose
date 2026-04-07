# Phase 4: Frontend Enablement Backend Contract

## Goal

Phase 4 should close the backend gaps that currently prevent a reliable production frontend from being built on top of the chat-first tenant workspace.

The target product shape is now fixed:

- chat-first workflow entrypoint
- user-accessible data surfaces for managed entities and user-visible outputs
- full production Zitadel authentication
- server-side protection of internal orchestration-only messaging and operational internals

This document is intentionally backend-only. Frontend architecture, cleanup, deployment recommendations, and app rebuild notes live under `docs/frontend-development/`.

## Backend definition of "working frontend"

A frontend should be considered fully supported only when it can:

1. authenticate real users through Zitadel-backed bearer tokens
2. resolve the current user and tenant memberships
3. list and inspect user-visible tenant-scoped entities
4. create and update editable tenant-scoped entities
5. run chat workflows and rehydrate thread state durably
6. read user-visible workflow outputs, artifacts, evidence, and review state
7. avoid depending on local-only cached entity objects for rehydration

## Backend work required

### 1. Production-ready auth contract for frontend usage

The backend already has Zitadel support, but Phase 4 should explicitly finish the frontend-facing contract for production usage.

Required backend outcomes:

- finalize bearer-token validation as the supported frontend auth mode
- guarantee stable `401` error semantics for:
  - missing token
  - expired token
  - malformed token
  - invalid audience / issuer
- guarantee stable `403` semantics for tenant membership and role failures
- ensure `/api/v1/me` returns the full frontend-required identity payload
- ensure `/api/v1/tenants` reflects real persisted memberships for Zitadel users
- document required claims and issuer/audience assumptions for frontend integration

API surface involved:

- `GET /api/v1/me`
- `GET /api/v1/tenants`

Files involved:

- [backend/src/app/api/deps.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\api\deps.py)
- [backend/src/app/auth/zitadel_adapter.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\auth\zitadel_adapter.py)
- [backend/src/app/api/v1/endpoints/identity.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\api\v1\endpoints\identity.py)

### 2. Seller profile read APIs

Current gap:

- seller profiles can be created and updated
- seller profiles cannot be listed or fetched back for durable frontend rehydration

Required additions:

- `GET /api/v1/tenants/{tenant_id}/seller-profiles`
- `GET /api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}`

Required behavior:

- tenant-scoped authorization
- return only user-visible seller profile fields
- support stable ordering for list views
- support future filtering if needed, but simple list is enough for Phase 4

Files likely involved:

- [backend/src/app/api/v1/endpoints/setup.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\api\v1\endpoints\setup.py)
- [backend/src/app/services/setup.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\services\setup.py)
- [backend/src/app/repositories/seller_profile_repository.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\repositories\seller_profile_repository.py)
- [backend/src/app/schemas/setup.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\schemas\setup.py)

### 3. ICP profile read APIs

Current gap:

- ICP profiles can be created and updated
- ICP profiles cannot be listed or fetched back for durable frontend rehydration

Required additions:

- `GET /api/v1/tenants/{tenant_id}/icp-profiles`
- `GET /api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}`

Required behavior:

- tenant-scoped authorization
- seller-profile relationship preserved in responses
- only user-visible fields exposed

Files likely involved:

- [backend/src/app/api/v1/endpoints/setup.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\api\v1\endpoints\setup.py)
- [backend/src/app/services/setup.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\services\setup.py)
- [backend/src/app/repositories/icp_profile_repository.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\repositories\icp_profile_repository.py)
- [backend/src/app/schemas/setup.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\schemas\setup.py)

### 4. Account read APIs

For a chat-first frontend, users still need to access account data produced or managed inside the tenant.

Required additions:

- `GET /api/v1/tenants/{tenant_id}/accounts`
- `GET /api/v1/tenants/{tenant_id}/accounts/{account_id}`

Recommended query support:

- `seller_profile_id`
- `icp_profile_id`
- pagination parameters

Required behavior:

- return user-visible account fields only
- include enough metadata for list/detail screens
- support browsing accounts discovered by workflow execution
- do not expose internal orchestration-only summaries unless explicitly marked user-visible

This may require service/repository work if account reads are currently workflow-internal only.

### 5. Contact read APIs

Users also need to inspect discovered contacts tied to tenant data.

Required additions:

- `GET /api/v1/tenants/{tenant_id}/contacts`
- `GET /api/v1/tenants/{tenant_id}/contacts/{contact_id}`

Recommended query support:

- `account_id`
- pagination parameters

Required behavior:

- tenant-scoped authorization
- only user-visible contact fields returned
- stable filtering by account

### 6. User-visible workflow output APIs

The existing review surface is partially present, but the frontend needs a stable user-facing resource model for outputs and reviewable state.

Phase 4 should ensure the backend supports:

- listing workflow runs or user-visible run summaries for a tenant
- viewing a single user-visible run summary
- listing artifacts relevant to a tenant/user workflow view
- listing evidence relevant to a workflow run
- reading approval state when a run is awaiting review

Current partial coverage:

- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug`
- `GET /api/v1/tenants/{tenant_id}/artifacts/{artifact_id}`
- `POST /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals`

Phase 4 gaps to close:

- add user-facing run summary list/detail endpoints if chat events alone are insufficient
- add artifact list endpoint if the frontend needs artifact browsing outside a known `artifact_id`
- add approval history/read endpoint if review state must be rehydrated independently

Important rule:

- debug-only bundles and admin telemetry are not substitutes for user-facing read APIs

### 7. Clear separation between user-visible data and internal-only data

The backend needs an explicit boundary so the frontend can safely consume "all user-attributed data" without leaking server-only internals.

Phase 4 backend rules should be:

- user-visible:
  - profile/setup records
  - accounts
  - contacts
  - visible workflow outputs
  - artifacts
  - evidence
  - approval decisions
  - durable chat messages intended for the user

- internal-only by default:
  - hidden agent handoff messages
  - internal orchestration reasoning artifacts
  - raw prompt/config internals
  - debug/telemetry tables
  - operational log events not intended for user UX

This may require:

- explicit response shaping
- separate user-facing schemas vs admin/debug schemas
- review of existing endpoints that currently expose more than the frontend should depend on

### 8. Stable user-facing pagination and filtering contract

Before the frontend entity browser is built, the backend should define consistent list semantics.

Phase 4 should standardize:

- `limit`
- `offset` or cursor behavior
- stable default sort order
- consistent empty-list responses
- consistent `404` behavior for missing tenant-scoped records

This matters especially for:

- seller profiles
- ICP profiles
- accounts
- contacts
- workflow outputs/artifacts

### 9. User-facing workflow state contract

The frontend will need a predictable model for workflow visibility outside low-level admin/debug surfaces.

Phase 4 should define which workflow states are frontend-relevant:

- queued
- running
- awaiting_review
- succeeded
- failed
- cancelled

And which user-facing fields are available with those states:

- workflow type
- created/updated timestamps
- selected account/contact references when relevant
- visible completion summary
- review requirement metadata
- visible artifact/evidence references

### 10. Backend test coverage for the frontend contract

The missing APIs above should not be added without contract tests.

Phase 4 should include backend tests for:

- Zitadel-authenticated identity resolution
- tenant-scoped authorization on all new read endpoints
- seller profile list/detail
- ICP profile list/detail
- account list/detail
- contact list/detail
- user-visible workflow output endpoints
- internal-only data not leaking through user-facing endpoints

## Phase 4 implementation checklist

### Must-have

- production-stable Zitadel auth behavior for frontend bearer tokens
- seller profile list/detail APIs
- ICP profile list/detail APIs
- account list/detail APIs
- contact list/detail APIs
- stable user-facing run/output/resource contract
- tests for all of the above

### Strongly recommended

- artifact list endpoint
- approval history/read endpoint
- explicit user-facing schemas separate from debug/admin payloads
- standardized pagination/filtering conventions

## Out of scope for this doc

These are important, but they are not backend-contract items and therefore do not belong in this Phase 4 backend document:

- frontend app architecture
- frontend state management strategy
- frontend cleanup of legacy modules
- deployment topology recommendation details
- reverse proxy design
- frontend Zitadel PKCE implementation
- frontend feature/module structure

Those topics live in `docs/frontend-development/`.
