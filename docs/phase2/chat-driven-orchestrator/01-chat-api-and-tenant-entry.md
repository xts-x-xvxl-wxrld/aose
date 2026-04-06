# Chat API And Tenant Entry

## Purpose And Scope

- Define the tenant-scoped chat API surface and the tenant-selection entry rules that gate access to chat.

## Dependencies On Earlier Docs

- Depends on `docs/phase2/chat-driven-orchestrator/00-chat-driven-orchestrator-overview.md`.
- Depends on `docs/implementation/04-api-auth-and-request-context.md`.

## Decision Summary

- Chat routes are tenant-scoped under `/api/v1/tenants/{tenant_id}/chat/...`.
- The mounted primary chat route family is:
  - `POST /api/v1/tenants/{tenant_id}/chat/stream`
  - `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}`
  - `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages`
  - non-required derived `GET /api/v1/tenants/{tenant_id}/chat/events` only if a convenience feed is later implemented
- New thread creation is implicit on the first streamed user turn rather than a separate required create-thread route.
- The dashboard requires explicit tenant selection before chat is entered when the user has multiple active tenants.
- The backend does not infer or persist a hidden active tenant.
- `/chat/...` is the primary user-facing route family for this phase, while existing tenant-scoped `/conversations...` routes may remain only as transitional compatibility aliases during rollout.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes request auth context and tenant-scoped route rules from the implementation docs.
- Consumes canonical conversation thread, conversation message, and turn-response contracts from the implementation docs.
- Introduces a tenant-scoped chat route family that reuses canonical conversation and orchestration contracts rather than redefining them.

## Chat Turn Idempotency Header Contract

- `POST /api/v1/tenants/{tenant_id}/chat/stream` requires a non-empty `X-Request-ID` on every request.
- Idempotency scope is `(tenant_id, user_id, request_id)`.
- `request_id` identifies one accepted user turn, not one transport connection or one client retry attempt.
- Retrying the same accepted turn with the same `(tenant_id, user_id, request_id)` must return or resume the existing durable result rather than creating a duplicate thread, message, or workflow run.
- Reusing the same `(tenant_id, user_id, request_id)` with a materially different request payload or a conflicting `thread_id` must return `409` using a stable `request_id_conflict` error code.
- This section is route-facing only; durable storage, lookup, and resume mechanics are owned by the thread-lifecycle slice.

## Data Flow / State Transitions

- User discovers active tenants through the existing identity or tenancy surfaces.
- If the user has zero active tenants, chat entry is blocked and the product routes them to tenant provisioning or discovery flow.
- If the user has exactly one active tenant, the client may auto-select it and enter the tenant-scoped chat route family directly.
- If the user has multiple active tenants, the dashboard requires explicit tenant selection before the chat surface is opened.
- Frontend enters the tenant-scoped chat surface using the selected `tenant_id` in the route.
- Backend derives tenant authority from the route path, derives acting user identity from auth context, and validates membership before serving the request.
- The first streamed user turn may create a new thread implicitly; later turns and reload flows target an existing tenant-scoped thread.

## Failure Modes And Edge-Case Rules

- No chat entry without an explicit tenant when multiple tenants exist.
- Single-tenant users may be auto-selected by the client, but business requests still carry tenant-scoped routes.
- Tenant mismatches between route context and request state are rejected.
- Requests from users without active membership in the route tenant are rejected.
- Disabled or inactive memberships must not be allowed to open or resume tenant-scoped chat threads.
- Cross-tenant thread access is rejected even if the thread identifier exists.
- Client-supplied tenant hints, headers, or local UI state must not override the route tenant.
- Missing or empty `X-Request-ID` on `POST /chat/stream` is rejected.
- Reuse of a request id with a conflicting payload or conflicting `thread_id` is rejected with `409 request_id_conflict`.

## Validation, Ownership, And Permission Rules

- Tenant selection is explicit in product UX and in API shape.
- Auth and tenant-validation behavior remains backend-owned.
- Frontend convenience state must not override tenant-scoped backend rules.
- `tenant_id` is authoritative only when supplied in the route path.
- `user_id` is authoritative only when supplied by authenticated request context.
- `X-Tenant-ID` is not part of the public contract and must not be accepted as an override mechanism.
- In v1, chat thread lookup, message history lookup, and any derived event inspection route are visible to all active tenant members and are not limited to the thread creator.
- Thread access remains tenant-scoped and membership-checked rather than creator-scoped.
- This slice defines the chat route family, but canonical request and response payload shapes continue to be owned by the implementation docs until they are revised there.

## Persistence Impact

- Tenant selection as dashboard convenience remains client-local and is not persisted as hidden server-side active-tenant state.
- Chat threads and messages remain durable tenant-scoped records and are the canonical persisted context for reload and resume behavior.
- This slice does not require a new persisted "active tenant" record.

## API / Events / Artifact Impact

- Define mounted chat route group under `/api/v1/tenants/{tenant_id}/chat/...`.
- Treat `/chat/...` as the primary user-facing route family for chat-driven orchestration.
- `GET /api/v1/tenants/{tenant_id}/chat/events`, if implemented, is a derived convenience surface only and is not required for initial chat-first canonization.
- Retain existing tenant-scoped `/conversations...` routes only as transitional compatibility aliases during rollout, reusing the same underlying conversation and orchestration services.
- Route-level ownership for path, method, request, response, and error semantics remains explicit and must be reconciled back into `docs/implementation/04-api-auth-and-request-context.md` when accepted.
- Thread creation is implicit on the first streamed turn; thread reload and message-history routes target existing tenant-scoped thread identifiers.
- `POST /chat/stream` owns the header-level requirement that `X-Request-ID` be present and stable across retries for the same accepted turn.

## Implementation Acceptance Criteria

- Tenant-scoped chat routes are mounted in the active API router.
- The primary mounted chat surface includes `POST /chat/stream`, `GET /chat/threads/{thread_id}`, and `GET /chat/threads/{thread_id}/messages` under the tenant-scoped API prefix.
- Thread creation does not require a separate mandatory create-thread call before the first user turn.
- Dashboard entry rules for tenant selection are explicit.
- Zero-tenant, one-tenant, and multi-tenant entry behavior is specified and implemented consistently.
- Backend authorization rejects cross-tenant thread access and tenant override attempts.
- `/conversations...` compatibility behavior, if retained, is explicitly documented as a transitional alias secondary to `/chat/...`.
- `GET /chat/events`, if implemented, is explicitly documented as non-required and derived.
- No hidden active-tenant server contract is introduced.
- The route contract explicitly requires `X-Request-ID` and defines request-id conflict behavior at the API boundary.

## Verification

- Add doc-contract checks for the exact tenant-scoped chat route inventory and compatibility alias policy.
- Add runtime tests covering zero-tenant, one-tenant, and multi-tenant entry behavior.
- Add runtime tests covering rejection of cross-tenant thread lookup and cross-tenant message-history access.
- Add runtime tests confirming that client-side tenant hints or headers cannot override the route tenant.
- Add contract tests covering required `X-Request-ID`, idempotency scope, and `request_id_conflict` behavior for conflicting retries.

## Deferred Items

- Cross-device remembered tenant selection beyond local client convenience.
- Exact calendar timing for removing compatibility `/conversations...` routes after the frontend no longer depends on them and the chat-first path is declared canonical.
