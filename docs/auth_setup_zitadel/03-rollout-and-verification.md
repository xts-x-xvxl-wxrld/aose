# Rollout And Verification

## Purpose

This document describes how to land Zitadel auth safely without breaking local development or tenant-scoped backend behavior.

## Rollout Strategy

Use a staged rollout.

### Stage 1: Keep Fake Auth Available

Add the real Zitadel auth path without deleting fake auth immediately.

Why:

- local development remains unblocked
- current tests keep passing while real-auth coverage is added
- the team can compare fake and real behavior route by route

### Stage 2: Prove Core Identity Endpoints

Validate real auth against:

- `GET /api/v1/me`
- `GET /api/v1/tenants`

Why:

- they exercise identity and membership resolution
- they do not require a full frontend auth flow

### Stage 3: Prove Tenant-Scoped API Access

Validate one tenant-scoped route with a real token and real membership data.

Good candidates:

- seller profile creation
- chat entry
- member listing

### Stage 4: Make Zitadel The Preferred Dev Path

Once the real path is stable:

- switch the main local integration instructions to Zitadel mode
- keep fake auth only as an explicit fallback

## Test Matrix

Minimum backend coverage should include:

- missing bearer token returns `401`
- malformed authorization header returns `401`
- invalid token signature returns `401`
- wrong issuer returns `401`
- wrong audience returns `401`
- expired token returns `401`
- valid token resolves `AuthIdentity`
- valid token creates missing internal user
- valid token returns empty tenant list when no memberships exist
- valid token with active membership can access tenant-scoped routes
- valid token without membership gets `403` on tenant-scoped routes

## Manual Verification Checklist

### Identity

- call `GET /api/v1/me` with a valid Zitadel bearer token
- confirm the response identity maps to the token subject
- confirm the request does not depend on fake-auth env values

### Membership

- call `GET /api/v1/tenants` with a valid token
- confirm only persisted tenant memberships are returned

### Tenant Access

- call a tenant-scoped route with a user who belongs to the tenant
- confirm access succeeds
- call the same route with a user who does not belong to the tenant
- confirm access fails with `403`

## Current Project Verification Inputs

The current known values for verification are:

- issuer: `https://aose-authz-qirgym.ch1.zitadel.cloud`
- expected audience: `366874018701128501`
- required audience scope at login time: `urn:zitadel:iam:org:project:id:366874018701128501:aud`

When a real bearer token is tested against the backend, these are the first things to confirm:

- `iss` matches `https://aose-authz-qirgym.ch1.zitadel.cloud`
- `aud` includes `366874018701128501`
- `sub` is present and stable

## Logging And Debugging Expectations

The first implementation should log enough to debug auth safely without leaking secrets.

Helpful logging:

- auth mode at startup
- configured issuer
- discovery-metadata fetch failures
- JWKS fetch failures
- token validation failure category

Do not log:

- raw access tokens
- refresh tokens
- full personally sensitive token payloads

## Cutover Rule

Real-auth cutover is acceptable when:

- the backend passes auth tests in Zitadel mode
- `/api/v1/me` and `/api/v1/tenants` work with real tokens
- at least one tenant-scoped business route is verified with real auth
- fake static user identity is no longer required for real-auth mode

## Deferred Follow-Ups

These are useful, but not required for first enablement:

- refresh-token handling outside the frontend
- introspection support as a fallback mode
- SCIM provisioning
- richer role or claim mapping from Zitadel
- admin automation against Zitadel APIs
