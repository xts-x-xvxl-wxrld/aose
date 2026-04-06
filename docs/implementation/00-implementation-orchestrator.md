# Implementation Orchestrator

## Purpose And Scope

This document is the entrypoint for the legacy implementation spec set for the Agentic OSE backend.

These documents now serve as historical reference material for an older planning model:

- multi-user and tenant-aware backend foundations
- seller and ICP setup
- account search
- account research
- contact search
- persistence, artifacts, approvals, and evidence handling
- API, orchestration, worker, and service boundaries

`resources/project-draft.md` and `resources/project-prerequisites.md` remain reference material only.
If this document set conflicts with current code or the latest active unimplemented phase doc set, code and the latest active phase doc set win.

## Authoring Conventions

All child documents in `docs/implementation/` must use the same core structure:

1. Purpose and scope
2. Dependencies on earlier docs
3. Decision summary
4. Canonical models/types/interfaces introduced or consumed
5. Data flow / state transitions
6. Failure modes and edge-case rules
7. Validation, ownership, and permission rules
8. Persistence impact
9. API/events/artifact impact, if relevant
10. Implementation acceptance criteria
11. Verification
12. Deferred items, only if intentionally out of scope

Verification sections must point to actual automated tests under `tests/` that currently enforce the document. If only doc-level verification exists for now, call that out explicitly rather than implying completed feature coverage.

Conventions used across the set:

- `tenant_id` is the primary isolation boundary for all business records
- `user_id` is the acting user identity from authentication context
- `created_by_user_id` and `updated_by_user_id` track authorship of mutable records
- structured database records are canonical
- markdown is a human-readable artifact, not the source of truth
- external evidence must be source-aware and traceable
- RAG is deferred and supporting only

## System Boundaries

In scope for the current implementation doc set:

- FastAPI control plane and request contracts
- OpenAI Agents SDK agent boundaries
- service orchestration and worker execution shape
- persistence and artifacts
- seller, ICP, account, research, and contact workflows
- review and approval metadata
- tenant and user ownership

Out of scope for the current implementation doc set:

- frontend implementation
- billing
- full enterprise RBAC
- production queue infrastructure beyond the abstraction contract
- production RAG implementation
- outreach generation workflow implementation

## Current Baseline

The current repository baseline is intentionally narrower than the full milestone described by this doc set.

Implemented and enforced today:

- FastAPI application factory and versioned API router
- public endpoints for `GET /api/v1/healthz`, `GET /api/v1/agents`, `GET /api/v1/me`, and `GET /api/v1/tenants`
- fake-auth development request resolution
- agent registry skeleton with orchestrator, account search, account research, and contact search agent definitions
- persisted identity and setup tables for `User`, `Tenant`, `TenantMembership`, `SellerProfile`, and `ICPProfile`
- repository methods for identity/setup persistence and tenant-scoped seller/ICP reads and updates
- doc-structure, doc-contract, app-smoke, and identity/setup persistence tests

Specified but not implemented yet:

- real JWT validation and production auth integration
- tenant provisioning and membership-management APIs
- conversation threads and messages
- workflow run execution, run events, and polling APIs
- evidence, artifacts, and approval persistence and routes
- provider-backed tools, connectors, and worker runtime
- account search, account research, and contact search workflow execution

Intentionally stubbed today:

- specialist agents are present as skeleton definitions only
- service package is present without workflow-coordination implementations
- worker package is present without queue-backed or in-process workflow execution
- tools package is present without product-specific tool implementations

Baseline rule:

- child docs must distinguish between behavior that is already implemented, behavior that is only specified, and behavior that is intentionally stubbed
- no child doc may imply that a stubbed capability is already runtime-enforced

## Spec Precedence

This document set no longer overrides current code or the latest active unimplemented phase doc set.

Rules:

- current code is the source of truth for implemented behavior
- the latest active unimplemented phase doc set is the source of truth for current planned behavior
- this implementation doc set is useful only as historical background unless a newer phase doc explicitly points back to it for context
- reference material in `resources/` never overrides current code or the latest active phase doc set

## Contract Freeze

Once a contract is used by code or referenced by a later child doc, that contract is frozen until it is intentionally revised in the owning document.

Frozen-contract rules:

- a contract change must update the owning document first or in the same change
- any affected child docs must be updated in the same change
- any affected runtime tests or doc-contract tests must be updated in the same change
- no implementation may silently redefine enums, route semantics, payload fields, status transitions, ownership rules, or artifact behavior outside the owning doc
- if a contract is still exploratory, the owning doc must mark it as a stub or deferred item rather than allowing implicit drift

## Verification Tiers

Verification references in this doc set must make clear what kind of enforcement currently exists.

Verification tiers:

- `doc-structure`
  tests that enforce document numbering, section order, dependency ordering, and shared authoring rules
- `doc-contract`
  tests that enforce declared contract content inside the implementation docs, such as route lists, enum values, or required acceptance bullets
- `runtime-enforced`
  tests that exercise actual application, persistence, service, worker, or API behavior in code

Rules:

- verification sections should not imply runtime enforcement when only doc-structure or doc-contract checks exist
- when a feature is specified but not implemented, the owning doc should say so plainly even if doc-contract tests already exist
- new runtime features should add or extend `runtime-enforced` coverage in addition to doc-level checks

## Cross-Cutting Invariants

The following rules apply across all child documents and may not be redefined later without updating this root doc and the owning foundational doc.

Invariants:

- `tenant_id` is the mandatory isolation boundary for every tenant-scoped business record and workflow action
- `user_id` from authenticated request context is the acting human identity for workflow triggers and mutable writes
- `created_by_user_id` is required on all user-created or workflow-triggered canonical business records unless the persistence doc explicitly defines an append-only exception
- structured persisted records are canonical; markdown and other rendered artifacts are never canonical
- artifacts, evidence, conversations, workflow runs, and downstream workflow outputs remain tenant-scoped
- services own authorization-adjacent checks and orchestration entry validation; agents, tools, and connectors do not grant permissions
- enums, status sets, workflow types, and stable event names are owned once by their designated doc and may not be redefined elsewhere
- stubbed capabilities must be marked explicitly and may not be treated as production behavior by later docs

## Slice Readiness

Development should proceed in vertical slices, but each slice must satisfy minimum readiness requirements before implementation starts.

Slice-readiness rule:

- no implementation slice may begin until its owning contracts for persistence, API shape, and service or worker boundary are explicit enough to implement without inventing new behavior in code

Minimum readiness checks for a slice:

- the owning doc names all canonical persisted models the slice creates or mutates
- the owning doc defines the route surface or invocation surface used by the slice
- the owning doc defines required statuses, events, and ownership rules for the slice
- any upstream prerequisite records or context-selection rules are explicit
- any intentionally unresolved behavior is marked as `stubbed` or `deferred`, not left implicit

## Stub Contract Rule

Stubbed behavior is allowed, but only when the stub is explicit and bounded.

Stub rules:

- a stub must name the missing runtime capability, not merely imply "future work"
- a stub must preserve the same ownership, tenant-scoping, and non-fabrication rules that the final implementation will follow
- a stub must not claim provider data, workflow completion, persisted outputs, or approvals that do not yet exist
- if a child doc depends on a stubbed upstream capability, it must state whether the downstream work is blocked, partially implementable, or limited to interface-only scaffolding

## Implementation Order Gating

The listed implementation order is not only advisory; it defines gating for later workflow work.

Gating rules:

- later workflow docs may not be implemented in full before their foundational contracts are locked in earlier docs
- conversation, workflow-run, and review flows may not be implemented ahead of the persistence and API contracts they depend on
- account search, account research, and contact search may not proceed beyond scaffolding until `WorkflowRun`, `RunEvent`, conversation, and prerequisite seller/ICP contracts are defined
- if implementation pressure reveals a missing foundational contract, the team must update the earlier owning doc rather than improvising in a later workflow doc

## Dependency Graph

Implementation documents must be read in this order:

1. [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
2. [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
3. [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
4. [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
5. [04-api-auth-and-request-context.md](./04-api-auth-and-request-context.md)
6. [05-service-worker-and-tool-boundaries.md](./05-service-worker-and-tool-boundaries.md)
7. [06-workflow-seller-and-icp-setup.md](./06-workflow-seller-and-icp-setup.md)
8. [07-workflow-account-search.md](./07-workflow-account-search.md)
9. [08-workflow-account-research.md](./08-workflow-account-research.md)
10. [09-workflow-contact-search.md](./09-workflow-contact-search.md)
11. [10-evidence-approval-and-artifacts.md](./10-evidence-approval-and-artifacts.md)
12. [11-deferred-rag-and-future-extensions.md](./11-deferred-rag-and-future-extensions.md)

Dependency rules:

- foundational docs may not depend on later workflow docs
- later docs may refine usage of earlier contracts, but may not redefine them
- if a later doc needs a foundational change, update the foundational doc and reference it explicitly

## Implementation Order

The intended development order is:

1. identity, tenant, and ownership model
2. persistence schema and artifact policy
3. orchestrator input/output and workflow run contracts
4. request context and API surface
5. service, worker, repository, and tool boundaries
6. seller and ICP setup workflow
7. account search workflow
8. account research workflow
9. contact search workflow
10. evidence, approvals, and artifacts
11. deferred RAG planning

## Decision Index

The owning document for each major decision area is:

- glossary and cross-document rules
  [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- user, tenant, membership, roles, ownership model
  [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- database models, storage rules, markdown policy, canonical persistence
  [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- orchestrator types, workflow types, run statuses, events, retries, review states
  [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- auth assumptions, tenant request context, API routes and contracts
  [04-api-auth-and-request-context.md](./04-api-auth-and-request-context.md)
- boundaries between agents, services, workers, tools, and repositories
  [05-service-worker-and-tool-boundaries.md](./05-service-worker-and-tool-boundaries.md)
- seller and ICP workflow behavior
  [06-workflow-seller-and-icp-setup.md](./06-workflow-seller-and-icp-setup.md)
- account search behavior
  [07-workflow-account-search.md](./07-workflow-account-search.md)
- account research behavior
  [08-workflow-account-research.md](./08-workflow-account-research.md)
- contact search behavior
  [09-workflow-contact-search.md](./09-workflow-contact-search.md)
- source evidence, approval decisions, and artifacts
  [10-evidence-approval-and-artifacts.md](./10-evidence-approval-and-artifacts.md)
- deferred RAG rules and future extensions
  [11-deferred-rag-and-future-extensions.md](./11-deferred-rag-and-future-extensions.md)

## Glossary

- `User`
  An authenticated human actor.
- `Tenant`
  The customer workspace and primary data isolation boundary.
- `TenantMembership`
  The relationship between a user and a tenant, including role.
- `WorkflowRun`
  A durable record of an async or reviewable workflow execution.
- `RunEvent`
  A timestamped event emitted during workflow execution.
- `Artifact`
  A human-readable output such as markdown or a review package.
- `SourceEvidence`
  A source-aware record of information gathered from an external or internal system.
- `Snapshot`
  An append-only point-in-time structured result, especially for research.

## Canonical Acceptance Checks

This implementation doc set is complete only when:

- no implementation-critical decision for the current milestone is left implicit
- every persisted record mentioned in any doc is defined by the persistence doc
- all workflow docs use the same orchestrator, workflow run, and event contracts
- auth, tenant, and actor ownership rules match across API, persistence, and workflow docs
- markdown handling matches the artifact policy
- RAG remains documented as deferred and supporting, not a replacement for live evidence gathering
- no child doc silently redefines foundational concepts from earlier docs
- every child doc contains a verification section pointing to actual tests under `tests/`

## Verification

Current automated enforcement of this orchestrator document and the doc set entrypoint lives in:

- [tests/docs/test_implementation_doc_structure.py](../../tests/docs/test_implementation_doc_structure.py) `::test_implementation_docs_are_numbered_contiguously`
- [tests/docs/test_implementation_doc_structure.py](../../tests/docs/test_implementation_doc_structure.py) `::test_root_doc_dependency_graph_lists_the_full_doc_order`
- [tests/docs/test_implementation_doc_structure.py](../../tests/docs/test_implementation_doc_structure.py) `::test_child_docs_follow_the_shared_section_template`
- [tests/test_app_smoke.py](../../tests/test_app_smoke.py) `::test_create_app_bootstraps_agent_system_and_current_routes`
- [tests/test_agent_contracts.py](../../tests/test_agent_contracts.py) `::test_agent_registry_description_stays_stable_for_smoke_inspection`

## Deferred Items

Deferred topics are allowed only when they are explicitly called out in the owning child document. Deferred topics do not grant permission to improvise during implementation.
