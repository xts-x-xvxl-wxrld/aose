# Build Now Vs Full Auth

## Purpose

This document separates the auth work into:

- what can be implemented immediately
- what is still missing for the full end-to-end authentication experience

This is important because the backend is already close to being able to validate real tokens, while the full browser login lifecycle still depends on later frontend work.

## What We Can Build Right Now

We can build the backend identity and authorization foundation immediately.

### Backend Config

We can add these settings now:

```dotenv
AUTH_MODE=fake
ZITADEL_ISSUER=https://aose-authz-qirgym.ch1.zitadel.cloud
ZITADEL_AUDIENCE=366874018701128501
ZITADEL_JWKS_URI=https://aose-authz-qirgym.ch1.zitadel.cloud/oauth/v2/keys
```

### Real Auth Adapter

We can add a Zitadel-specific auth adapter that:

- reads the bearer token from the request
- validates the JWT using Zitadel discovery and JWKS
- validates `iss`
- validates `aud`
- validates token expiry
- extracts `sub`, `email`, and `name`

### Dependency Wiring

We can change the backend dependency flow so that:

- `AUTH_MODE=fake` keeps current development behavior
- `AUTH_MODE=zitadel` enables real token validation

### Internal User Resolution

We can update the backend so that real-auth mode:

- resolves `User` from `external_auth_subject = token.sub`
- creates the internal user if it does not exist yet
- uses the persisted user id for downstream writes and workflow triggers

### Tenant Authorization

We can keep using the existing database-backed tenant authorization model:

- membership lookup from `TenantMembership`
- role checks from persisted membership records
- explicit tenant scoping through route path parameters

### Backend Testing

We can add backend-only tests for:

- invalid token
- wrong issuer
- wrong audience
- expired token
- valid token with no membership
- valid token with membership

### Manual Backend Verification

We can prove the first auth slice on:

- `GET /api/v1/me`
- `GET /api/v1/tenants`
- one tenant-scoped route

## What This Gives Us

If we implement the build-now slice, we will have:

- real backend authentication
- real internal user identity mapping
- real tenant authorization
- a backend that is structurally ready for production auth

Even before frontend login is complete, this is a major milestone because the core security contract becomes real.

## What Is Still Missing For Full Authentication

The build-now slice is not the entire auth story.

Full end-to-end auth still requires:

### Frontend Login Flow

- initiating login against Zitadel
- handling redirects and callbacks
- requesting the correct Zitadel audience scope
- obtaining usable access tokens in the client

### Required Audience Scope In Client Login

The login client must request:

`urn:zitadel:iam:org:project:id:366874018701128501:aud`

Without that, the backend may reject a token because it was not minted for the expected audience.

### Token Lifecycle In The Client

- token storage strategy
- token refresh behavior
- retry behavior after expiry
- logout behavior

### Browser Logout And Session UX

- logout flow
- local token/session clearing
- redirect behavior

### End-To-End Browser Verification

- real browser login
- authenticated frontend API calls
- reload behavior
- token expiry behavior

## What Is Not Required For First Enablement

These are useful, but they should not block the initial backend auth slice:

- Zitadel management SDK usage
- SCIM provisioning
- enterprise SSO admin automation
- token introspection fallback
- refresh-token support in FastAPI
- server-rendered session middleware

## Recommended Build Order

1. finish the backend auth slice
2. verify real tokens work against backend routes
3. fix frontend login so it requests the proper audience scope
4. connect frontend bearer tokens to backend API calls
5. add logout and token refresh behavior
6. add end-to-end verification

## Decision Rule

When in doubt, prioritize anything that makes the backend correctly answer these questions:

1. Is this token valid?
2. Who is this user?
3. Which tenant do they belong to?
4. What are they allowed to do?

If a task does not help answer one of those questions, it is probably not part of the first backend auth slice.
