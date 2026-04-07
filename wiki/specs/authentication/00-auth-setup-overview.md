# Auth Setup With Zitadel

## Purpose

This doc set explains how to enable real authentication for the Agentic OSE backend using Zitadel.

The intended architecture in this set is:

- the product may have a browser frontend
- the backend is still treated as an API-first resource server
- clients send bearer access tokens to the backend
- the backend validates those tokens and resolves internal user and tenant context

## Why This Doc Set Exists

The repository already has:

- a fake-auth development mode
- tenant and membership persistence
- request-context dependencies
- API routes that expect authenticated callers

The repository does not yet have:

- real bearer-token validation
- Zitadel-specific backend configuration
- a production-ready auth adapter

This doc set is meant to close that gap in a practical way.

## Current Backend Shape

Today the backend behaves like an API resource server, not a server-rendered auth app:

- routes are JSON and tenant-scoped
- auth is resolved in request dependencies
- downstream services expect resolved identity and membership context
- fake auth currently stands in for real token verification

Because of that, the recommended first implementation is:

- keep FastAPI as a bearer-token API
- validate Zitadel-issued tokens on the backend
- continue to use the database as the source of truth for tenant membership and role checks

## Core Rule

Zitadel proves who the user is.

The Agentic OSE database proves:

- whether that user exists in our product
- which tenants they belong to
- what role they have in each tenant

## Required Pieces

The full auth path has these moving parts:

1. Zitadel project
2. Zitadel user-facing OIDC application
3. Zitadel backend API audience or API application
4. bearer access token sent to FastAPI
5. backend token validation against issuer, audience, and signing keys
6. internal user resolution from token `sub`
7. tenant membership lookup from the database
8. role-based authorization in services and route dependencies

## Recommended Reading Order

1. [01-zitadel-project-and-app-setup.md](./01-zitadel-project-and-app-setup.md)
2. [02-backend-api-auth-implementation.md](./02-backend-api-auth-implementation.md)
3. [03-rollout-and-verification.md](./03-rollout-and-verification.md)
4. [04-build-now-vs-full-auth.md](./04-build-now-vs-full-auth.md)

## Decisions Frozen By This Doc Set

- FastAPI is treated as an API-first backend for auth purposes.
- The backend accepts bearer tokens rather than relying on server-side login sessions.
- Zitadel is the external identity provider.
- The backend should prefer JWT validation via discovery and JWKS before considering token introspection.
- The internal user key remains `User.external_auth_subject`, populated from the validated token `sub`.
- Tenant and role checks remain product-owned database behavior, not provider-owned authorization behavior.

## Out Of Scope

This doc set does not define:

- frontend UX details for login screens
- session-cookie auth for server-rendered pages
- SCIM provisioning
- enterprise SSO onboarding workflows beyond the backend contract shape
- billing, subscription, or org lifecycle behavior

## Success Criteria

This auth setup is considered complete when:

- fake auth can be disabled in local development
- the backend accepts valid Zitadel bearer tokens
- invalid, expired, wrong-issuer, and wrong-audience tokens are rejected
- `/api/v1/me` resolves identity from a real token
- tenant-scoped routes authorize based on persisted memberships, not fake bootstrap values
- the backend no longer depends on a fake static acting user id for real-auth mode

## Immediate Delivery Goal

The first delivery target for this auth set is not "full user login UX."

The first delivery target is:

- a backend that can trust real Zitadel bearer tokens
- a backend that can resolve real internal users from those tokens
- a backend that can authorize tenant-scoped routes using persisted memberships

That is the narrowest slice that moves the system from fake auth toward production auth without blocking on frontend auth cleanup.
