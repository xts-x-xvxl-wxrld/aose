---
title: Current App Overview - Auth and Tenancy
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - frontend/src/features/auth/AuthProvider.jsx
  - frontend/src/features/auth/pages/LoginPage.jsx
  - frontend/src/features/tenants/hooks/useTenantMemberships.js
  - frontend/src/stores/tenantStore.js
  - backend/src/app/api/v1/endpoints/identity.py
  - backend/src/app/api/v1/endpoints/tenancy.py
  - backend/src/app/services/tenancy.py
  - backend/src/app/models/tenant_membership.py
  - wiki/specs/authentication/00-auth-setup-overview.md
  - wiki/specs/backend-domain/01-core-domain-and-ownership.md
---

# Current App Overview - Auth and Tenancy

## Summary

The app uses Zitadel-backed authentication plus a database-backed tenant membership model. Authentication proves who the user is; the app's own tenant tables decide which workspaces and tenant-scoped routes that user can access.

This is a deliberate split:

- Zitadel handles identity and session restoration
- the backend database remains the source of truth for tenant membership and role checks
- business routes require explicit tenant scope in the URL

See also [[Current App Overview]], [[Current App Overview - Workspace Surfaces]], and [[Current App Overview - Domain Model]].

## Authentication Flow

The frontend auth flow is an OIDC redirect flow:

- the login page sends the user through Zitadel
- `AuthProvider` restores the browser session from the OIDC client
- once a token is available, the frontend calls `/api/v1/me`
- the backend resolves the persisted user and returns identity fields including `is_platform_admin`

If the frontend is not configured with the `VITE_ZITADEL_*` variables, the production auth flow is intentionally unavailable.

## Tenant Discovery and Selection

After auth, the frontend loads `/api/v1/tenants` and stores the returned memberships in the tenant store. This determines:

- which tenants the user can enter
- which tenant is currently active in the UI
- which tenant id is used in every business request

The product does not use hidden server-side "active tenant" state. Tenant choice is explicit in the client and explicit again in every business route path.

The workspace entry behavior is:

- if no tenant is selected, the user sees a tenant entry screen
- existing memberships can be selected
- a new tenant can be created through `POST /api/v1/tenants`

## Roles and Access Model

The data model supports the roles:

- `owner`
- `admin`
- `member`
- `reviewer`

Practical behavior in the current app:

- any active member can use normal tenant-scoped workspace surfaces
- `owner` and `admin` unlock the tenant admin entry in the UI
- `reviewer`, `admin`, and `owner` can submit review decisions
- platform admins additionally get cross-tenant admin visibility

## Explicit Tenant Scoping

Identity routes sit outside tenant scope:

- `/api/v1/me`
- `/api/v1/tenants`
- `/api/v1/tenants` for self-serve tenant creation

Business routes are tenant-scoped:

- chat routes
- seller/ICP setup routes
- account/contact/workflow read routes
- review routes
- tenant-scoped admin routes

This explicit path scoping is one of the central architectural rules of the app. It prevents ambiguous server behavior and keeps ownership boundaries obvious.

## Frontend Tenant State

The tenant store persists two distinct ideas:

- the active tenant id
- tenant-specific workspace context

The active tenant id is global UI state. The tenant-specific context includes the currently pinned seller, ICP, account, contact, and thread for that tenant.

This lets the app feel stateful and session-like without relying on implicit backend tenant context.
