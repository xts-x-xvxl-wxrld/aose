# API Auth And Request Context

## Purpose And Scope

This document defines the API-facing request context, authentication assumptions, tenant scoping, and minimum route surface for the current milestone.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)

## Decision Summary

- Production authentication uses bearer JWTs from an external identity provider.
- The acting user is resolved from the token subject.
- Development compatibility mode may use fake auth, but it must still resolve the same canonical `RequestContext` shape.
- Tenant context is explicit in tenant-scoped routes.
- The canonical tenant-selection mechanism for business routes is the `tenant_id` path parameter.
- Tenant creation is an authenticated non-tenant-scoped API operation.
- Tenant member administration is tenant-scoped and role-checked.
- Tenant selection remains explicit; the backend does not guess or persist an implicit active tenant in Phase 1.
- Tenant-scoped chat routes are the canonical user-facing conversation API surface.
- `POST /api/v1/tenants/{tenant_id}/chat/stream` is the canonical user-turn entrypoint and requires a client-supplied `X-Request-ID`.
- Supporting thread reload and message-history routes live under `/api/v1/tenants/{tenant_id}/chat/threads/...`.
- `GET /api/v1/tenants/{tenant_id}/chat/events` is not part of the required canonical route inventory for initial chat-first canonization.
- `/conversations...` routes, if retained, are transitional compatibility aliases over the same underlying services and contracts.
- Services receive resolved request context, not raw auth primitives.
- Minimum identity endpoints exist from the first implementation.
- This document owns route-level request, response, and error contracts for the API surface.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### RequestContext

```python
class RequestContext(TypedDict):
    user_id: str
    tenant_id: str | None
    membership_role: str | None
    request_id: str
```

Rules:

- `tenant_id` may be `None` only for identity-discovery or tenant-provisioning endpoints such as `/me`, `/tenants`, or `POST /api/v1/tenants`
- all business workflow endpoints require non-null `tenant_id`

### Authentication Assumption

Minimum auth behavior:

- API receives bearer token
- token is validated against configured issuer and audience
- token subject maps to `User.external_auth_subject`
- API resolves memberships before business operations

Development compatibility rule:

- the current repository may continue to use fake-auth development wiring until real JWT validation is implemented
- fake-auth mode is a bootstrap convenience only and does not change route contracts, permission rules, tenant selection semantics, or response shapes
- child docs may not treat fake-auth headers or local-dev shortcuts as canonical public API behavior

### Tenant Selection Semantics

Selection rules:

- if the user has zero active tenants, only identity-discovery and tenant-provisioning routes are available
- if the user has exactly one active tenant, clients may auto-select it, but business routes still carry explicit `tenant_id`
- if the user has multiple active tenants, clients must select one from `/api/v1/tenants` before calling tenant-scoped routes
- Phase 1 does not persist last-used tenant selection on the server; clients may remember it locally if desired
- canonical tenant selection for business APIs is path-based through `/api/v1/tenants/{tenant_id}/...`
- `X-Tenant-ID` is not part of the canonical public API contract and must not be required, documented as public behavior, or used to override a tenant path parameter

### Route Contract Ownership

Ownership rules:

- this doc owns API route paths, methods, request models, response models, and error semantics
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md) owns reusable orchestration request and turn-response types used by conversation routes
- later approval, evidence, and artifact docs may refine workflow semantics, but route payloads must still be referenced here
- child workflow docs may constrain when routes are used, but may not redefine route payloads or permission behavior

### ErrorResponse

```python
class ErrorResponse(TypedDict):
    error_code: str
    message: str
    request_id: str
    details: dict[str, Any] | None
```

Rules:

- all non-2xx API failures return `ErrorResponse`
- `error_code` is stable and machine-readable
- `message` is human-readable
- `request_id` is always echoed for traceability
- `details` is optional and may include field-level validation or policy context

### TenantCreateRequest

```python
class TenantCreateRequest(TypedDict):
    name: str
    slug: str
```

Rules:

- `name` is required
- `slug` is required and must be unique after normalization
- tenant creation is the only Phase 1 business write route allowed outside tenant context

### TenantCreateResponse

```python
class TenantCreateResponse(TypedDict):
    tenant_id: str
    name: str
    slug: str
    creator_membership_id: str
    creator_role: str
    creator_status: str
```

Rules:

- successful creation returns the created tenant and the creator membership created in the same transaction
- `creator_role` is always `owner`
- `creator_status` is always `active`

### TenantMemberResponse

```python
class TenantMemberResponse(TypedDict):
    membership_id: str
    tenant_id: str
    user_id: str
    email: str | None
    display_name: str | None
    role: str
    status: str
    created_at: str
    updated_at: str
```

### TenantMemberListResponse

```python
class TenantMemberListResponse(TypedDict):
    members: list[TenantMemberResponse]
```

Rules:

- `GET /members` returns all memberships for the tenant, including `invited` and `disabled`
- Phase 1 member listing is not paginated
- results are ordered by `created_at` ascending, then `membership_id`

### TenantMemberCreateRequest

```python
class TenantMemberCreateRequest(TypedDict):
    user_id: str | None
    email: str | None
    role: str
```

Rules:

- at least one of `user_id` or `email` must be supplied
- if `user_id` is supplied, Phase 1 direct member creation creates an `active` membership immediately after validation
- if only `email` is supplied and the user does not already exist, the request is rejected in Phase 1; email-only invite acceptance is deferred
- if `email` is supplied and exactly one existing user matches that email, the service may resolve that user and create an `active` membership
- `owner` creation through this route requires an acting owner

### TenantMemberUpdateRequest

```python
class TenantMemberUpdateRequest(TypedDict):
    role: str | None
    status: str | None
```

Rules:

- this route handles role changes, disable, and re-enable operations
- removing a member uses `DELETE`, not status mutation
- last-owner protections must be enforced before applying the change

### TenantOwnershipTransferRequest

```python
class TenantOwnershipTransferRequest(TypedDict):
    target_membership_id: str
    rationale: str | None
```

Rules:

- the target membership must already belong to the same tenant and be `active`
- the target may not already be an `owner`
- the acting owner is demoted in the same transaction that promotes the target to `owner`
- `rationale` is optional in Phase 1 but should be persisted when supplied

### TenantOwnershipTransferResponse

```python
class TenantOwnershipTransferResponse(TypedDict):
    tenant_id: str
    previous_owner_membership_id: str
    new_owner_membership_id: str
    previous_owner_role: str
    new_owner_role: str
```

### ConversationThreadResponse

```python
class ConversationThreadResponse(TypedDict):
    thread_id: str
    tenant_id: str
    created_by_user_id: str
    seller_profile_id: str | None
    active_workflow: str | None
    status: str
    current_run_id: str | None
    summary_text: str | None
    created_at: str
    updated_at: str
```

### ConversationMessageResponse

```python
class ConversationMessageResponse(TypedDict):
    message_id: str
    thread_id: str
    tenant_id: str
    run_id: str | None
    role: str
    message_type: str
    content_text: str
    created_by_user_id: str | None
    created_at: str
```

### ConversationMessageListResponse

```python
class ConversationMessageListResponse(TypedDict):
    messages: list[ConversationMessageResponse]
    next_cursor: str | None
```

Rules:

- message history is ordered by `created_at` ascending, then `message_id`
- message-history polling uses cursor pagination
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages` returns this response shape
- `GET /api/v1/tenants/{tenant_id}/conversations/{thread_id}/messages`, if retained, is a transitional compatibility alias over the same underlying service behavior

### WorkflowRunResponse

```python
class WorkflowRunResponse(TypedDict):
    workflow_run_id: str
    tenant_id: str
    thread_id: str | None
    created_by_user_id: str
    workflow_type: str
    status: str
    status_detail: str | None
    normalized_result_json: dict[str, Any] | None
    error_code: str | None
    correlation_id: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str
```

### WorkflowRunEventResponse

```python
class WorkflowRunEventResponse(TypedDict):
    event_id: str
    workflow_run_id: str
    event_name: str
    payload_json: dict[str, Any]
    created_at: str
```

### WorkflowRunEventListResponse

```python
class WorkflowRunEventListResponse(TypedDict):
    events: list[WorkflowRunEventResponse]
    next_cursor: str | None
```

Rules:

- run-event polling uses cursor pagination
- events are returned in `created_at` ascending order, then `event_id`

### SourceEvidenceResponse

```python
class SourceEvidenceResponse(TypedDict):
    evidence_id: str
    workflow_run_id: str
    account_id: str | None
    contact_id: str | None
    source_type: str
    provider_name: str | None
    source_url: str | None
    title: str | None
    snippet_text: str | None
    captured_at: str | None
    freshness_at: str | None
    confidence_score: float | None
    metadata_json: dict[str, Any] | None
    created_at: str
```

### WorkflowRunEvidenceListResponse

```python
class WorkflowRunEvidenceListResponse(TypedDict):
    evidence: list[SourceEvidenceResponse]
    next_cursor: str | None
```

### ArtifactResponse

```python
class ArtifactResponse(TypedDict):
    artifact_id: str
    tenant_id: str
    workflow_run_id: str | None
    created_by_user_id: str | None
    artifact_type: str
    format: str
    title: str
    content_markdown: str | None
    content_json: dict[str, Any] | None
    storage_url: str | None
    created_at: str
    updated_at: str
```

### SellerProfileCreateRequest

```python
class SellerProfileCreateRequest(TypedDict):
    name: str
    company_name: str
    company_domain: str | None
    product_summary: str
    value_proposition: str
    target_market_summary: str | None
    source_status: str | None
    profile_json: dict[str, Any] | None
```

### SellerProfileResponse

```python
class SellerProfileResponse(TypedDict):
    seller_profile_id: str
    tenant_id: str
    created_by_user_id: str
    updated_by_user_id: str | None
    name: str
    company_name: str
    company_domain: str | None
    product_summary: str
    value_proposition: str
    target_market_summary: str | None
    source_status: str | None
    profile_json: dict[str, Any] | None
    created_at: str
    updated_at: str
```

### SellerProfileUpdateRequest

```python
class SellerProfileUpdateRequest(TypedDict):
    name: str | None
    company_name: str | None
    company_domain: str | None
    product_summary: str | None
    value_proposition: str | None
    target_market_summary: str | None
    source_status: str | None
    profile_json: dict[str, Any] | None
```

### ICPProfileCreateRequest

```python
class ICPProfileCreateRequest(TypedDict):
    seller_profile_id: str
    name: str
    status: str | None
    criteria_json: dict[str, Any]
    exclusions_json: dict[str, Any] | None
```

### ICPProfileResponse

```python
class ICPProfileResponse(TypedDict):
    icp_profile_id: str
    tenant_id: str
    seller_profile_id: str
    created_by_user_id: str
    updated_by_user_id: str | None
    name: str
    status: str
    criteria_json: dict[str, Any]
    exclusions_json: dict[str, Any] | None
    created_at: str
    updated_at: str
```

### ICPProfileUpdateRequest

```python
class ICPProfileUpdateRequest(TypedDict):
    name: str | None
    status: str | None
    criteria_json: dict[str, Any] | None
    exclusions_json: dict[str, Any] | None
```

### Route Groups

Minimum route groups:

- `GET /api/v1/healthz`
- `GET /api/v1/agents`
- `GET /api/v1/me`
- `GET /api/v1/tenants`
- `POST /api/v1/tenants`
- `GET /api/v1/tenants/{tenant_id}/members`
- `POST /api/v1/tenants/{tenant_id}/members`
- `PATCH /api/v1/tenants/{tenant_id}/members/{membership_id}`
- `DELETE /api/v1/tenants/{tenant_id}/members/{membership_id}`
- `POST /api/v1/tenants/{tenant_id}/members/{membership_id}/transfer-ownership`
- `POST /api/v1/tenants/{tenant_id}/chat/stream`
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}`
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/events`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence`
- `GET /api/v1/tenants/{tenant_id}/artifacts/{artifact_id}`
- `POST /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals`
- `POST /api/v1/tenants/{tenant_id}/seller-profiles`
- `PATCH /api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}`
- `POST /api/v1/tenants/{tenant_id}/icp-profiles`
- `PATCH /api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}`

First-pass request modeling rule:

- create endpoints accept explicit payload models
- read endpoints return canonical structured records and linked artifact metadata when relevant
- `POST /api/v1/tenants` returns `TenantCreateResponse`
- `GET /api/v1/tenants/{tenant_id}/members` returns `TenantMemberListResponse`
- `POST /api/v1/tenants/{tenant_id}/members` returns `TenantMemberResponse`
- `PATCH /api/v1/tenants/{tenant_id}/members/{membership_id}` returns `TenantMemberResponse`
- `DELETE /api/v1/tenants/{tenant_id}/members/{membership_id}` returns `204` with no body
- `POST /api/v1/tenants/{tenant_id}/members/{membership_id}/transfer-ownership` returns `TenantOwnershipTransferResponse`
- `POST /api/v1/tenants/{tenant_id}/chat/stream` uses `ChatTurnStreamRequest` from [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- `POST /api/v1/tenants/{tenant_id}/chat/stream` requires a non-empty client-supplied `X-Request-ID` and streams frames using the chat stream framing contract from [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}` returns `ConversationThreadResponse`
- `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages` returns `ConversationMessageListResponse`
- `/conversations...` routes, if retained, use the compatibility request and response contracts from [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md) and remain explicitly secondary
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}` returns `WorkflowRunResponse`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/events` returns `WorkflowRunEventListResponse`
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence` returns `WorkflowRunEvidenceListResponse`
- `GET /api/v1/tenants/{tenant_id}/artifacts/{artifact_id}` returns `ArtifactResponse`
- `POST /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals` is a gated Phase 1 route whose request and response payloads are finalized by the dedicated approval doc; it must not be implemented before that contract is locked
- `POST /api/v1/tenants/{tenant_id}/seller-profiles` uses `SellerProfileCreateRequest`
- `PATCH /api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}` uses `SellerProfileUpdateRequest`
- seller profile create and update routes return `SellerProfileResponse`
- `POST /api/v1/tenants/{tenant_id}/icp-profiles` uses `ICPProfileCreateRequest`
- `PATCH /api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}` uses `ICPProfileUpdateRequest`
- ICP profile create and update routes return `ICPProfileResponse`

## Data Flow / State Transitions

1. request enters API
2. auth dependency validates bearer token
3. API resolves `User`
4. non-tenant-scoped provisioning routes may execute without an active tenant context
5. tenant-scoped routes resolve `TenantMembership`
6. API creates `RequestContext`
7. service layer consumes `RequestContext`

## Failure Modes And Edge-Case Rules

- invalid token returns `401`
- missing authentication for authenticated routes returns `401`
- valid user without tenant membership in the requested tenant returns `403`
- tenant creation while self-serve provisioning is disabled returns `403`
- malformed request payloads return `422`
- missing or empty `X-Request-ID` on `POST /api/v1/tenants/{tenant_id}/chat/stream` returns `422`
- membership or ownership rule violations return `409` when they conflict with current tenant state
- tenant-scoped actions without explicit tenant path selection do not exist in the canonical API; clients must call tenant-scoped routes
- tenant path mismatch with resource ownership returns `404` without leaking cross-tenant existence
- retrying a first streamed turn with the same `(tenant_id, user_id, request_id)` after durable commit must not create a duplicate thread
- inactive membership blocks workflow creation and profile edits with `403`

Stable Phase 1 error codes:

- `auth_invalid_token`
- `auth_required`
- `tenant_membership_required`
- `tenant_creation_disabled`
- `validation_error`
- `request_id_conflict`
- `ownership_conflict`
- `resource_not_found`
- `review_state_conflict`

## Validation, Ownership, And Permission Rules

- `/me` requires valid authentication but no selected tenant
- `/tenants` returns only tenants the user belongs to
- `POST /tenants` requires valid authentication, no active tenant context, and creates both the tenant and creator owner membership in one transaction
- `POST /tenants/{tenant_id}/members`, `PATCH /tenants/{tenant_id}/members/{membership_id}`, and `DELETE /tenants/{tenant_id}/members/{membership_id}` are allowed for `owner` and `admin` when the target is not an owner
- `POST /tenants/{tenant_id}/members/{membership_id}/transfer-ownership` requires acting `owner`
- all tenant-scoped routes must verify membership before calling services
- `POST /tenants/{tenant_id}/chat/stream` is the primary user-turn route and uses `X-Request-ID` as the idempotency key for chat turns scoped by tenant and acting user
- thread reload and message-history routes are visible to all active tenant members and are not limited to the thread creator
- compatibility `/conversations...` routes, if retained, are transitional aliases and must not diverge from the chat-first service behavior
- Phase 2 async interaction uses streaming for live turn delivery and durable thread, message, run, event, artifact, and evidence endpoints for reload and inspection
- review actions must verify `owner`, `admin`, or `reviewer` role
- canonical route permission checks are based on the tenant path parameter, not a separate selected-tenant header

## Persistence Impact

APIs must never create business records without tenant and actor context.

## API / Events / Artifact Impact

- workflow inspection APIs read from `WorkflowRun` and `RunEvent`
- chat thread APIs read from `ConversationThread` and `ConversationMessage`
- `GET /api/v1/tenants/{tenant_id}/chat/events`, if implemented later, is a derived convenience surface and not part of the required canonical route inventory
- artifact references may be included in workflow inspection responses
- `/workflow-runs/{run_id}/evidence` returns only evidence linked to the requested run within the tenant
- `/artifacts/{artifact_id}` returns only tenant-scoped artifacts

## Implementation Acceptance Criteria

- every tenant-scoped route has a clear tenant context resolution rule
- request context is built once and passed to services
- auth and authorization checks happen before orchestrator invocation
- tenant provisioning is explicitly modeled as an authenticated non-tenant-scoped route
- tenant selection and member-management behavior are explicit rather than deferred
- route groups are aligned with current milestone workflows

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_api_route_groups_keep_tenant_scoping_explicit`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_api_doc_freezes_chat_route_inventory_and_alias_policy`
- [tests/test_app_smoke.py](../../tests/test_app_smoke.py) `::test_openapi_smoke_exposes_current_public_routes`
- [tests/test_identity_api.py](../../tests/test_identity_api.py) `::test_me_endpoint_uses_fake_auth_request_context`
- [tests/test_identity_api.py](../../tests/test_identity_api.py) `::test_tenants_endpoint_returns_fake_membership`
- [tests/test_tenancy_api.py](../../tests/test_tenancy_api.py) `::test_tenant_creation_and_member_listing_flow`

### Post-Implementation Brief

Implemented in this slice:

- `POST /api/v1/tenants`
- `GET /api/v1/tenants/{tenant_id}/members`
- `POST /api/v1/tenants/{tenant_id}/members`
- `PATCH /api/v1/tenants/{tenant_id}/members/{membership_id}`
- `DELETE /api/v1/tenants/{tenant_id}/members/{membership_id}`
- `POST /api/v1/tenants/{tenant_id}/members/{membership_id}/transfer-ownership`
- structured `ErrorResponse` handling for service-level tenancy failures

Current implementation notes:

- canonical tenant selection for business routes now uses the `tenant_id` path parameter; the earlier `X-Tenant-ID` fallback was removed from request-context resolution
- `/me` and `/tenants` still support fake-auth bootstrap behavior for local development, but now prefer persisted user and membership state when a database session is available
- the newly implemented membership routes are backed by service-layer ownership checks instead of route-local permission logic
- the chat-first route inventory, `X-Request-ID` idempotency rule, and compatibility alias policy are canonical contract decisions in this doc even where runtime enforcement is still owned by later implementation slices
- workflow-run, evidence, artifact, approval, seller-profile, and ICP-profile routes defined here remain owned by later implementation slices

## Deferred Items

- email-based invite delivery and token acceptance UX
- refresh token flows
- external SCIM provisioning
- enterprise approval workflows before tenant activation
