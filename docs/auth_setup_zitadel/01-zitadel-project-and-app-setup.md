# Zitadel Project And App Setup

## Purpose

This document explains what must exist in Zitadel before the backend can validate real bearer tokens.

## High-Level Model

A single Zitadel project can back both:

- the user-facing sign-in experience
- the backend API audience

That is fine.

What matters for the backend is not just "can a user log in?" but also "was this token issued for our API?"

## The Two Important App Concerns

### 1. User-Facing OIDC Application

This is the application used by the browser or frontend login flow.

It is responsible for:

- redirecting users to Zitadel
- completing the login flow
- obtaining tokens after successful authentication

Even though the backend is API-first, this user-facing app still matters because it is often the source of the bearer token eventually sent to the backend.

### 2. Backend API Audience / API Application

This represents the backend as a resource server.

It is responsible for:

- giving the token a backend-specific audience
- making it possible for the backend to reject tokens meant for some other app

Without this, the backend cannot safely answer the question:

"Was this token actually minted for Agentic OSE's API?"

## Values We Need From Zitadel

At minimum we need these values:

- `issuer`
- `audience` for the backend API

Usually we also want:

- frontend OIDC client id
- backend API app identifier or audience value
- discovery metadata URL
- JWKS URL

Optional later values:

- introspection client id
- introspection client secret or private-key JWT config

## Current Known Project Values

The current Zitadel project details confirmed so far are:

- issuer: `https://aose-authz-qirgym.ch1.zitadel.cloud`
- project id: `366874018701128501`

Important clarification:

- `https://aose-authz-qirgym.ch1.zitadel.cloud/oauth/v2/authorize` is the authorization endpoint
- it is not the issuer value the backend should validate against
- the backend issuer should remain the base Zitadel instance URL

For the current project, the backend should initially treat the project id as the expected audience value:

- backend audience: `366874018701128501`

This follows the Zitadel project-audience pattern where the token audience for a backend API is tied to the project id.

## How The Backend Will Use These Values

The backend will:

1. receive `Authorization: Bearer <token>`
2. load Zitadel discovery metadata from the issuer
3. load signing keys from JWKS
4. validate token signature
5. validate `iss`
6. validate `aud`
7. validate expiry-related claims
8. extract user claims such as `sub`, `email`, and `name`

## Practical Zitadel Checklist

Before backend work starts, confirm the following in Zitadel:

- a Zitadel project exists for the product
- the user-facing login app exists
- the backend audience or API app exists
- the token intended for the backend includes the correct audience
- the project issuer URL is known
- discovery metadata is reachable at `/.well-known/openid-configuration`

For the current project, the discovery URL should therefore be:

- `https://aose-authz-qirgym.ch1.zitadel.cloud/.well-known/openid-configuration`

## Claims We Expect To Consume

The backend should plan around these standard claims:

- `sub`
- `iss`
- `aud`
- `exp`
- `iat`
- `nbf` if present
- `email` if present
- `name` or a similar display-name claim if present

The most important claim for product identity is:

- `sub`

That should map to `User.external_auth_subject`.

## Important Boundary

Zitadel authentication does not replace our internal tenant model.

Zitadel tells us:

- the token is real
- which external identity it belongs to

Our database still decides:

- whether that identity has a `User` row
- which `TenantMembership` rows exist
- which role applies in a given tenant

## Recommended First Backend Mode

Use local JWT validation first:

- simpler runtime model
- no per-request dependency on Zitadel introspection
- easier to test in FastAPI dependencies

Keep introspection as a fallback option, not the primary implementation path.

## Required Audience Scope

For the backend to receive tokens that include the expected project audience, the login client must request the reserved Zitadel audience scope:

`urn:zitadel:iam:org:project:id:366874018701128501:aud`

This matters because backend JWT validation should enforce `aud`.

If the client does not request the audience scope, the backend may reject an otherwise valid token because it was not minted for the expected API audience.

## Setup Output

When Zitadel setup is "ready for backend integration", we should be able to fill these environment variables:

```dotenv
AUTH_MODE=zitadel
ZITADEL_ISSUER=https://aose-authz-qirgym.ch1.zitadel.cloud
ZITADEL_AUDIENCE=366874018701128501
```

Optional:

```dotenv
ZITADEL_JWKS_URI=https://aose-authz-qirgym.ch1.zitadel.cloud/oauth/v2/keys
```

If discovery is working correctly, the backend should be able to derive JWKS from the issuer and discovery document rather than requiring it manually.
