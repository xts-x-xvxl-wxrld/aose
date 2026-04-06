# Auth And Deployment Direction

## Auth direction

The target auth mode is full production Zitadel.

Recommended frontend auth flow:

1. frontend uses Zitadel OIDC Authorization Code + PKCE
2. frontend receives bearer token(s) through the OIDC flow
3. backend validates Zitadel JWTs
4. backend remains the source of truth for tenant membership and authorization

This means the current fake-auth login flow is only a temporary development fallback and should not be treated as the product auth design.

## Backend/frontend contract expectations

- frontend should depend on `/api/v1/me` for resolved identity
- frontend should depend on `/api/v1/tenants` for real memberships
- backend should return stable `401` and `403` semantics for auth failures

## Deployment recommendation

Recommended best-practice default:

- serve frontend and backend from the same origin
- mount backend under `/api/v1`
- use a reverse proxy in front of both apps

Recommended shape:

- frontend: `https://app.example.com/`
- backend: `https://app.example.com/api/v1/...`

## Why same-origin is preferred here

- simpler browser security model
- avoids broad CORS complexity
- easier local/prod parity
- cleaner frontend API base setup

## Local and Docker guidance

- root `.env` should remain the shared Compose env
- `backend/.env` can support backend-only direct runs
- `frontend/.env.local` should remain frontend-local override space
- frontend should continue using `/api/v1` as its default base path

## Follow-up frontend work implied by this choice

- replace fake-auth login page with Zitadel login/callback flow
- remove ad hoc fake subject handling from auth state
- keep the API base same-origin by default
