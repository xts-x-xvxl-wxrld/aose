# Core Domain And Ownership

## Purpose And Scope

This document defines the canonical domain ownership model for users, tenants, roles, and tenant-scoped business entities.

It establishes the ownership rules that all later docs must follow.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)

## Decision Summary

- Every business record belongs to exactly one tenant.
- Every workflow action is attributable to an acting user.
- Users may belong to many tenants.
- Tenants may contain many users.
- Tenant creation is self-serve by default for authenticated users.
- Creating a tenant automatically creates an active `owner` membership for the creator.
- Deployments may disable self-serve tenant creation and provision tenants out-of-band for controlled enterprise rollouts.
- Tenant member management is tenant-scoped and explicit.
- `owner` and `admin` may manage non-owner memberships in Phase 1, but only `owner` may manage owners or transfer ownership.
- Phase 1 uses direct membership creation for authenticated users; external invite-acceptance UX is deferred.
- Tenant isolation is enforced at the application, persistence, and worker layers.
- The first pass uses simple role-based membership, not full fine-grained RBAC.
- Identity-discovery and tenant-provisioning routes may execute without an active tenant; business routes require explicit tenant context in the API contract.
- Membership lifecycle and ownership-transfer semantics must remain aligned with the API contract.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### User

Conceptual fields:

- `id`
- `external_auth_subject`
- `email`
- `display_name`
- `status`
- `created_at`
- `updated_at`

Rules:

- `external_auth_subject` is unique
- `status` is one of `active`, `disabled`

### Tenant

Conceptual fields:

- `id`
- `name`
- `slug`
- `status`
- `created_at`
- `updated_at`

Rules:

- `slug` is unique
- `status` is one of `active`, `suspended`

### TenantMembership

Conceptual fields:

- `id`
- `tenant_id`
- `user_id`
- `role`
- `status`
- `created_at`
- `updated_at`

Rules:

- unique by `tenant_id + user_id`
- `role` is one of `owner`, `admin`, `member`, `reviewer`
- `status` is one of `active`, `invited`, `disabled`
- the tenant creator receives the first active membership with role `owner`
- direct member creation in Phase 1 creates an `active` membership immediately
- `invited` is reserved for later invite-acceptance flows and is not required for Phase 1 membership creation
- each tenant must retain at least one active `owner`

Phase 1 lifecycle rules:

- the normal Phase 1 API may create `active` memberships directly
- the normal Phase 1 API may transition `active -> disabled`
- the normal Phase 1 API may transition `disabled -> active`
- member removal uses deletion rather than a new terminal membership status
- `invited` is reserved for future invite-acceptance flows and should not be emitted by the normal Phase 1 direct-member-management API

### Tenant Provisioning

Provisioning rules:

- the default production path is authenticated self-serve tenant creation
- tenant creation happens outside an existing tenant context
- tenant creation must create the `Tenant` row and creator `TenantMembership` row atomically
- controlled deployments may disable self-serve creation and provision tenants before users join them
- the self-serve gate is a deployment-level policy switch, not an inferred runtime heuristic
- Phase 1 does not define plan-based, domain-based, or per-user exception logic unless a later owning doc introduces it explicitly

### Membership Management

Membership management rules:

- member management happens only inside an explicit tenant context
- `owner` and `admin` may add, disable, re-enable, update, and remove non-owner memberships
- only `owner` may create, demote, disable, or remove another `owner`
- ownership transfer must promote an existing active member to `owner` and demote the acting owner in the same transaction
- recovery for a tenant that has lost access to every owner is an out-of-band platform-admin action, not a normal tenant workflow
- the ownership-transfer target must already belong to the same tenant with `active` status
- the ownership-transfer target may not already be an `owner`
- the acting owner is demoted to `admin` as part of the transfer transaction
- membership deletion in Phase 1 is a hard removal of the membership row, not a soft-delete status
- email-only invite creation for unknown users is out of scope for Phase 1 direct member management

### Ownership Rules For Business Records

Every business record must include:

- `tenant_id`
- `created_at`
- `updated_at`

Every user-created or user-triggered record must include:

- `created_by_user_id`

Every mutable business record should include:

- `updated_by_user_id`

Every review decision must include:

- `reviewed_by_user_id`
- `reviewed_at`

### Core Business Entities

This doc defines the conceptual entity set. Storage details are owned by the persistence doc.

- `SellerProfile`
- `ICPProfile`
- `ConversationThread`
- `ConversationMessage`
- `WorkflowRun`
- `RunEvent`
- `Account`
- `AccountResearchSnapshot`
- `Contact`
- `SourceEvidence`
- `Artifact`
- `ApprovalDecision`

## Data Flow / State Transitions

Identity flow:

1. user authenticates with an external identity provider
2. backend resolves `User` from the auth subject
3. backend resolves active `TenantMembership`
4. request is executed in a single active tenant context

Provisioning flow:

1. authenticated user requests tenant creation outside any active tenant context
2. service validates creation policy, tenancy limits, and tenant naming constraints
3. service creates `Tenant`
4. service creates creator `TenantMembership` with role `owner` and status `active`
5. future requests may execute in the newly created tenant context

Membership management flow:

1. authorized tenant member requests a membership change inside a tenant
2. service validates actor role, target membership role, and last-owner protections
3. service creates, updates, disables, re-enables, removes, or transfers membership as requested
4. future tenant access checks resolve against the updated membership set

Ownership flow:

1. user performs action inside a tenant
2. service validates membership and role
3. created records receive tenant and actor ownership fields
4. downstream async workers carry the same tenant and actor context

## Failure Modes And Edge-Case Rules

- If the user is authenticated but has no active membership in the requested tenant, return authorization failure.
- If the user has memberships in multiple tenants and no tenant is selected, the API must require tenant selection rather than guessing.
- If self-serve tenant creation is disabled for the deployment, reject self-serve provisioning attempts instead of silently creating tenants.
- If a membership change would leave the tenant without an active `owner`, reject it.
- If an `admin` attempts to modify an `owner` membership, reject it.
- If a record exists but belongs to a different tenant, treat it as inaccessible; do not reveal cross-tenant existence.
- Disabled users and suspended tenants may not trigger workflows.

## Validation, Ownership, And Permission Rules

Role expectations for the first milestone:

- `owner`
  Full tenant access, including membership administration and approvals.
- `admin`
  Full workflow and profile management access, excluding tenant ownership transfer.
- `member`
  Can create and edit seller/ICP context and trigger workflows.
- `reviewer`
  Can view artifacts and approve or reject review-gated outputs.

First-pass capability matrix:

- seller and ICP edit
  `owner`, `admin`, `member`
- workflow trigger
  `owner`, `admin`, `member`
- artifact view
  `owner`, `admin`, `member`, `reviewer`
- approval / review actions
  `owner`, `admin`, `reviewer`
- tenant creation
  authenticated user outside tenant context, subject to deployment policy
- membership administration
  `owner`, `admin` for non-owner memberships
- owner management and ownership transfer
  `owner`

## Persistence Impact

All persistence models described later must implement these ownership fields and rules.

## API / Events / Artifact Impact

- business-route request context must include the active tenant
- identity-discovery and tenant-provisioning routes may carry `tenant_id = None` in the API contract
- APIs returning business records must return only tenant-scoped data
- emitted events must remain tenant-scoped
- artifacts must remain tenant-scoped

## Implementation Acceptance Criteria

- Every business record in the system can be assigned to exactly one tenant.
- Every workflow trigger can be tied to a user and a tenant.
- The role model is consistent across API, services, and approvals.
- Tenant provisioning is explicit, including who may create a tenant and how the first owner membership is assigned.
- No later doc introduces a business record without tenant ownership.

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_implementation_doc_structure.py](../../tests/docs/test_implementation_doc_structure.py) `::test_child_doc_dependencies_only_point_to_existing_earlier_docs`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_core_business_entities_have_canonical_persistence_models`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_phase_1_tables_are_registered_in_metadata`
- [tests/db/test_repositories.py](../../tests/db/test_repositories.py) `::test_identity_repositories_lookup_expected_records`
- [tests/db/test_tenancy_service.py](../../tests/db/test_tenancy_service.py) `::test_create_tenant_provisions_owner_membership`
- [tests/db/test_tenancy_service.py](../../tests/db/test_tenancy_service.py) `::test_owner_can_create_member_from_existing_email`
- [tests/db/test_tenancy_service.py](../../tests/db/test_tenancy_service.py) `::test_admin_cannot_disable_owner_membership`
- [tests/db/test_tenancy_service.py](../../tests/db/test_tenancy_service.py) `::test_transfer_ownership_demotes_actor_and_promotes_target`

### Post-Implementation Brief

Implemented in this slice:

- canonical `User`, `Tenant`, and `TenantMembership` persistence models with status and role constraints
- tenant provisioning that creates the tenant and first active `owner` membership atomically
- direct Phase 1 member creation, update, disable, re-enable, deletion, and ownership transfer service logic
- last-owner protection and owner-only enforcement for owner-management operations
- Docker-backed app and test Postgres databases so runtime verification can execute against a real tenant-aware database

Current implementation notes:

- Phase 1 direct member management resolves existing users by `user_id` or by an existing unique email match; email-only invite acceptance remains deferred
- fake-auth bootstrap mode still exists for local identity discovery routes, but the runtime path now prefers persisted tenant and membership data when a database session is available
- recovery for tenants that lose all owner access remains out-of-band, as specified
- broader business-record tenant ownership beyond identity, seller, and ICP setup remains gated on later docs

## Deferred Items

- email invite delivery and invite acceptance UX
- enterprise RBAC
- SCIM / SSO provisioning
- tenant billing and plan management
