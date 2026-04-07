# Backend API Auth Implementation

## Purpose

This document describes the code changes required to replace fake auth with real Zitadel-backed bearer-token validation in the FastAPI backend.

## Current Backend Reality

The current codebase already has:

- bearer-token parsing in the API dependency layer
- an `AuthIdentity` model
- user lookup by `external_auth_subject`
- tenant membership lookup and authorization checks

The missing piece is the real token validator.

## Files Expected To Change

The first implementation should likely touch these areas:

- `src/app/config.py`
- `src/app/api/deps.py`
- `src/app/auth/types.py`
- `src/app/auth/`
- auth-related tests under `tests/`

## Configuration Changes

Add backend auth settings to `src/app/config.py`.

Recommended first-pass variables:

```dotenv
AUTH_MODE=fake
ZITADEL_ISSUER=https://aose-authz-qirgym.ch1.zitadel.cloud
ZITADEL_AUDIENCE=366874018701128501
ZITADEL_JWKS_URI=https://aose-authz-qirgym.ch1.zitadel.cloud/oauth/v2/keys
```

Suggested behavior:

- `AUTH_MODE=fake` preserves the current local-development path
- `AUTH_MODE=zitadel` enables real token validation
- `ZITADEL_JWKS_URI` is optional if discovery metadata is used

## What We Can Build Right Now

Based on the current Zitadel inputs already confirmed, we can build the backend auth slice immediately.

Confirmed values:

- issuer: `https://aose-authz-qirgym.ch1.zitadel.cloud`
- audience: `366874018701128501`
- validation strategy: JWT verification through discovery and JWKS

That means the backend implementation does not need to wait for:

- the frontend auth flow to be fixed
- introspection credentials
- a Zitadel Python SDK

The backend can proceed using standard OIDC discovery plus JWT validation.

## Adapter Structure

Introduce a real auth adapter next to the fake one.

Suggested shape:

- `FakeAuthAdapter`
- `ZitadelAuthAdapter`
- shared adapter protocol or interface

The adapter contract should remain simple:

- input: bearer token string
- output: `AuthIdentity`
- failures: auth-specific exceptions or translated HTTP errors

## ZitadelAuthAdapter Responsibilities

The real adapter should:

1. require a non-empty bearer token
2. load Zitadel discovery metadata from the issuer
3. resolve JWKS URI
4. fetch or cache signing keys
5. validate token signature
6. validate `iss`
7. validate `aud`
8. validate token expiry and timing claims
9. extract claims into `AuthIdentity`

Suggested `AuthIdentity` mapping:

- `external_auth_subject <- sub`
- `email <- email`
- `display_name <- name`

If `email` or `name` is missing, the backend should still authenticate successfully as long as the core token validation and `sub` are valid.

The first implementation should also assume that the caller has obtained a token that includes the reserved Zitadel audience scope:

`urn:zitadel:iam:org:project:id:366874018701128501:aud`

Without that scope, the validated token may not contain the backend audience and should be rejected by the API auth layer.

## Dependency Wiring Changes

`src/app/api/deps.py` should stop assuming fake auth is the only adapter.

The new dependency flow should be:

1. parse bearer token from `Authorization`
2. choose auth adapter based on config
3. resolve `AuthIdentity`
4. resolve or create internal user
5. resolve memberships from the database
6. build request context

## Important Current Bug To Remove

The fake-auth path currently leaks a fake static user id into request resolution.

In real-auth mode, the backend should not use a fake `user_dev` style identity.

Instead it should:

- resolve the internal user by `external_auth_subject`
- create that user if missing
- use the persisted user id for downstream operations

This keeps workflow runs, profile writes, and approvals tied to durable product users instead of a development placeholder.

## What Stays The Same

The following product behavior should stay unchanged:

- `User.external_auth_subject` remains the durable external identity key
- tenant membership checks still come from the database
- role checks remain product-owned authorization rules
- tenant scoping stays explicit through path parameters

In other words:

- auth provider validates identity
- the Agentic OSE backend authorizes product access

## Why We Are Not Using The Browser Example Directly

The Zitadel example in `resources/example-auth-fastapi` is useful reference material, but it is a browser-session application:

- it uses redirect-based login
- it stores tokens in a server session
- it protects pages with session guards

Our backend needs something different:

- accept bearer tokens from callers
- validate them per request
- return API responses instead of redirecting to sign-in pages

That means we should borrow:

- discovery metadata patterns
- issuer and claim expectations

But not:

- `SessionMiddleware`
- callback routes
- sign-in redirect handlers
- server-session refresh flow

## Suggested Implementation Order

1. add config fields for Zitadel auth
2. add a shared auth adapter contract
3. implement `ZitadelAuthAdapter`
4. update `get_auth_adapter()` and `get_auth_identity()`
5. remove fake static user resolution in real-auth mode
6. add tests for valid and invalid tokens
7. test `/api/v1/me`
8. test tenant-scoped routes with real memberships

## Immediate Build Scope

The first code slice should stay intentionally narrow:

1. add config and env support for `AUTH_MODE`, `ZITADEL_ISSUER`, `ZITADEL_AUDIENCE`, and optional `ZITADEL_JWKS_URI`
2. add a `ZitadelAuthAdapter`
3. switch `get_auth_adapter()` to select fake vs Zitadel
4. make `get_auth_identity()` use real bearer-token validation when `AUTH_MODE=zitadel`
5. ensure real-auth mode no longer relies on fake static user ids
6. prove the path with `/api/v1/me`

This is enough to establish real backend auth without coupling the work to frontend login UX.

## First Endpoint To Prove Out

The first real-auth target should be:

- `GET /api/v1/me`

Why:

- simple route
- no tenant path required
- proves token validation and user resolution first

After that:

- `GET /api/v1/tenants`

After that:

- one tenant-scoped route such as seller setup or chat

## Non-Goals For The First Auth Slice

Do not block first implementation on:

- refresh tokens
- logout
- frontend login UX
- SCIM
- enterprise IdP onboarding automation
- provider-specific management SDK usage

Those can come later.
