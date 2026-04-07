# Frontend Implementation Roadmap

## Goal

Turn the current frontend from a partially migrated chat shell into a production-oriented chat-first workspace that also supports user-visible data browsing and review.

## Phase A: Stabilize the frontend foundation

### Objectives

- stop building on stale frontend paths
- freeze a single active API layer
- align docs and app structure with the real backend contract

### Work

1. extend [frontend/src/lib/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\api.js) with the new setup/workspace/review resource methods
2. mark legacy API modules and old object-browser components as deprecated
3. define query keys and response mappers for:
   - tenants
   - seller profiles
   - ICP profiles
   - accounts
   - contacts
   - workflow runs
   - artifacts/evidence

### Exit criteria

- one active API client surface
- no new work landing on dead frontend paths
- stable resource map documented and implemented

## Phase B: Replace local-only setup state with server-backed reads

### Objectives

- stop relying on local storage as the only durable source for setup entities
- load seller/ICP resources from backend on tenant entry

### Work

1. add frontend query hooks for seller profiles and ICP profiles
2. refactor tenant context state so it stores selected ids, not full authoritative objects
3. rehydrate selected setup entities from backend on load
4. keep create/edit flows, but invalidate and refresh server state after mutations

### Exit criteria

- seller/ICP setup survives refresh and device changes
- active tenant context is server-backed

## Phase C: Build the tenant data browser

### Objectives

- let users inspect managed entities without leaving the chat-first product shape

### Work

1. add accounts list/detail UI
2. add contacts list/detail UI
3. add workflow runs list/detail UI
4. add navigation between entity views and chat context

### Exit criteria

- users can browse sellers, ICPs, accounts, contacts, and workflow runs from the active tenant workspace

## Phase D: Add user-facing review flows

### Objectives

- support runs that enter review-required states

### Work

1. add evidence list UI
2. add artifact viewer
3. add approval / rejection / needs changes actions
4. connect `awaiting_review` events and workflow-run entries to the review surface

### Exit criteria

- review-required runs can be completed from the frontend

## Phase E: Replace fake auth with Zitadel flow

### Objectives

- move from development-only subject input to production auth

### Work

1. implement Zitadel login/callback handling
2. replace fake-auth store behavior
3. validate session bootstrap through `/me` and `/tenants`
4. harden unauthenticated and expired-session UX

### Exit criteria

- the frontend no longer depends on fake subject entry for normal operation

## Phase F: Cleanup and hardening

### Objectives

- remove obsolete code
- reduce fragility
- make the app maintainable

### Work

1. delete archived legacy modules once replacements exist
2. split large page-level components into feature containers
3. standardize loading/error/empty states
4. add frontend tests around:
   - tenant bootstrapping
   - chat submit/rehydration
   - seller/ICP loading
   - account/contact browsing
   - review actions

### Exit criteria

- the frontend codebase matches the actual product architecture instead of carrying dead migration baggage
