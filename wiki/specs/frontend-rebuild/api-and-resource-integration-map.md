# API And Resource Integration Map

## Purpose

This document translates the current backend contract into frontend-facing resources, query responsibilities, and integration points.

It is the bridge between:

- the backend contract in [docs/phase4/01-frontend-enablement-backend-contract.md](c:\Users\ravil\Desktop\Agentic-OSE\docs\phase4\01-frontend-enablement-backend-contract.md)
- the frontend rebuild plan in [docs/frontend-development/02-frontend-rebuild-and-cleanup-plan.md](c:\Users\ravil\Desktop\Agentic-OSE\docs\frontend-development\02-frontend-rebuild-and-cleanup-plan.md)

## Resource groups

### Auth + identity

Backend routes:

- `GET /api/v1/me`
- `GET /api/v1/tenants`

Frontend responsibility:

- bootstrap authenticated user
- load memberships
- decide whether user can enter workspace
- establish active tenant selection

Recommended frontend module:

- `features/auth/api`
- `features/auth/session`
- `features/tenants/api`

### Setup resources

Backend routes:

- `POST /api/v1/tenants/{tenant_id}/seller-profiles`
- `GET /api/v1/tenants/{tenant_id}/seller-profiles`
- `GET /api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}`
- `PATCH /api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}`
- `POST /api/v1/tenants/{tenant_id}/icp-profiles`
- `GET /api/v1/tenants/{tenant_id}/icp-profiles`
- `GET /api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}`
- `PATCH /api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}`

Frontend responsibility:

- seller profile browser
- ICP browser
- create/edit forms
- active context selection for chat

Important change from the earlier state:

- setup data no longer needs to live only in local storage
- frontend should rehydrate these resources from backend reads on load

### Workspace entity resources

Backend routes:

- `GET /api/v1/tenants/{tenant_id}/accounts`
- `GET /api/v1/tenants/{tenant_id}/accounts/{account_id}`
- `GET /api/v1/tenants/{tenant_id}/contacts`
- `GET /api/v1/tenants/{tenant_id}/contacts/{contact_id}`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}`

Frontend responsibility:

- account list/detail
- contact list/detail
- workflow runs list/detail
- connecting chat outcomes to durable entities and outputs

Recommended query patterns:

- accounts filtered by `seller_profile_id` and `icp_profile_id`
- contacts filtered by `account_id`
- workflow runs filtered client-side by status/type until server filtering is needed

### Chat resources

Backend routes:

- `POST /api/v1/tenants/{tenant_id}/chat/stream`
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}`
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages`
- `GET /api/v1/tenants/{tenant_id}/chat/events`

Frontend responsibility:

- streaming assistant replies
- durable thread rehydration
- projected run event timeline
- preserving current thread context per tenant

This remains the primary workflow surface.

### Review resources

Backend routes:

- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug`
- `GET /api/v1/tenants/{tenant_id}/artifacts/{artifact_id}`
- `POST /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals`

Frontend responsibility:

- evidence browsing
- artifact viewing
- approval / rejection / needs changes actions

Frontend constraint:

- `debug` should not become a general-purpose user-facing data dependency
- use it only if the product explicitly wants a debug surface

### Admin resources

Backend routes:

- current `/api/v1/admin/...` surface

Frontend responsibility:

- platform/tenant operations UX
- agent config management
- logs and telemetry inspection for authorized users

This remains a separate concern from the main end-user workspace.

## Recommended frontend API client shape

The current [frontend/src/lib/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\api.js) should evolve to expose grouped resource clients like:

- `auth`
- `identity`
- `tenancy`
- `setup`
- `workspace`
- `chat`
- `review`
- `admin`

Recommended additions not yet present in the active client:

- `setup.listSellerProfiles`
- `setup.getSellerProfile`
- `setup.listIcpProfiles`
- `setup.getIcpProfile`
- `workspace.listAccounts`
- `workspace.getAccount`
- `workspace.listContacts`
- `workspace.getContact`
- `workspace.listWorkflowRuns`
- `workspace.getWorkflowRun`
- `review.listEvidence`
- `review.getArtifact`
- `review.submitApproval`

## Server-state ownership guidance

These resources should be treated as backend-owned state:

- tenants
- seller profiles
- ICP profiles
- accounts
- contacts
- workflow runs
- artifacts
- evidence
- approval state

These values may still be mirrored locally for UX, but the backend remains the source of truth.

## Local UI state guidance

The following values are still good candidates for local client state:

- active tenant id
- active thread id
- selected seller profile id
- selected ICP profile id
- selected account id
- selected contact id
- panel open/close state
- transient draft form values
