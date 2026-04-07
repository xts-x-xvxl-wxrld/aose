# Wiki Index

A catalog of all pages in this wiki. Agents update this on every ingest or significant change.

---

## Specs — active build instructions

### frontend-rebuild
- [Overview](specs/frontend-rebuild/overview.md) — directory overview and reading order
- [Current State and Gap Map](specs/frontend-rebuild/current-state-and-gap-map.md) — active frontend/backend shape, gaps, and integration surface
- [Product and UX Direction](specs/frontend-rebuild/product-and-ux-direction.md) — target product flow and information architecture
- [Rebuild and Cleanup Plan](specs/frontend-rebuild/rebuild-and-cleanup-plan.md) — recommended rebuild path and unreliable pieces to replace
- [Auth and Deployment Direction](specs/frontend-rebuild/auth-and-deployment-direction.md) — frontend auth direction and same-origin deployment
- [API and Resource Integration Map](specs/frontend-rebuild/api-and-resource-integration-map.md) — frontend-facing resource map for all surfaces
- [Screen and Navigation Spec](specs/frontend-rebuild/screen-and-navigation-spec.md) — chat-first app shell, screens, and route responsibilities
- [Implementation Roadmap](specs/frontend-rebuild/implementation-roadmap.md) — phased implementation order against current backend contract
- [Frontend Enablement Backend Contract](specs/frontend-rebuild/frontend-enablement-backend-contract.md) — backend gaps to close before a reliable frontend can be built

---

## Specs — reference (what was built)

### backend-domain
- [Overview](specs/backend-domain/overview.md) — entrypoint, authoring conventions, and reading order
- [Core Domain and Ownership](specs/backend-domain/core-domain-and-ownership.md)
- [Persistence and Artifacts](specs/backend-domain/persistence-and-artifacts.md)
- [Orchestrator and Run Contracts](specs/backend-domain/orchestrator-and-run-contracts.md)
- [API Auth and Request Context](specs/backend-domain/api-auth-and-request-context.md)
- [Service Worker and Tool Boundaries](specs/backend-domain/service-worker-and-tool-boundaries.md)
- [Workflow: Seller and ICP Setup](specs/backend-domain/workflow-seller-and-icp-setup.md)
- [Workflow: Account Search](specs/backend-domain/workflow-account-search.md)
- [Workflow: Account Research](specs/backend-domain/workflow-account-research.md)
- [Workflow: Contact Search](specs/backend-domain/workflow-contact-search.md)
- [Evidence Approval and Artifacts](specs/backend-domain/evidence-approval-and-artifacts.md)
- [Deferred RAG and Future Extensions](specs/backend-domain/deferred-rag-and-future-extensions.md)

### chat-orchestration (complete)
- [Spec](specs/chat-orchestration/spec.md) — full design spec, conflicts identified, and resolutions
- [Overview](specs/chat-orchestration/overview.md) — slice set entrypoint, decision summary, and acceptance criteria
- [Chat API and Tenant Entry](specs/chat-orchestration/chat-api-and-tenant-entry.md)
- [Chat Transport and Thread Lifecycle](specs/chat-orchestration/chat-transport-and-thread-lifecycle.md)
- [Orchestrator Contracts](specs/chat-orchestration/orchestrator-contracts.md)
- [Chat Events and Run Projection](specs/chat-orchestration/chat-events-and-run-projection.md)
- [Runtime Wiring and Workflow Dispatch](specs/chat-orchestration/runtime-wiring-and-workflow-dispatch.md)
- [Frontend Chat Migration](specs/chat-orchestration/frontend-chat-migration.md)
- [Post-Implementation Fixes](specs/chat-orchestration/post-implementation-fixes.md)

### provider-workflows (complete)
- [Spec](specs/provider-workflows/spec.md) — high-level summary, provider stack, and test plan
- [Overview](specs/provider-workflows/overview.md) — slice set entrypoint and acceptance criteria
- [Provider Config and Runtime Wiring](specs/provider-workflows/provider-config-and-runtime-wiring.md)
- [OpenAI Reasoning Layer](specs/provider-workflows/openai-reasoning-layer.md)
- [Account Search](specs/provider-workflows/account-search.md)
- [Account Research](specs/provider-workflows/account-research.md)
- [Contact Search](specs/provider-workflows/contact-search.md)
- [Chat and Frontend Completion](specs/provider-workflows/chat-and-frontend-completion.md)
- [Contract Decisions](specs/provider-workflows/contract-decisions.md) — resolved inconsistencies and canonical decisions for this phase
- [Post-Implementation Fixes](specs/provider-workflows/post-implementation-fixes.md)

### resilience-and-fallbacks (mostly complete)
- [Spec](specs/resilience-and-fallbacks/spec.md) — delivered outcomes and remaining open work
- [Overview](specs/resilience-and-fallbacks/overview.md) — slice set entrypoint and acceptance criteria
- [Dev Debugging and Observability](specs/resilience-and-fallbacks/dev-debugging-and-observability.md)
- [User-Facing Failure](specs/resilience-and-fallbacks/user-facing-failure.md)
- [Account Search Fallback](specs/resilience-and-fallbacks/account-search-fallback.md)
- [Semantic Work](specs/resilience-and-fallbacks/semantic-work.md)

### authentication
- [Overview](specs/authentication/overview.md) — purpose, architecture, and reading order
- [Zitadel Project Setup](specs/authentication/zitadel-project-setup.md)
- [Backend Auth Implementation](specs/authentication/backend-auth-implementation.md)
- [Build Now vs Full Auth](specs/authentication/build-now-vs-full-auth.md)

### admin-system
- [Overview](specs/admin-system/overview.md) — platform ops, telemetry, agent config versioning, audit logs

---

## Architecture — current-state reference (agent-maintained)

- [Current App Overview](architecture/current-app-overview.md) — top-level description of the app as it stands today
- [Auth and Tenancy](architecture/current-app-overview/auth-and-tenancy.md)
- [Domain Model](architecture/current-app-overview/domain-model.md)
- [Workspace Surfaces](architecture/current-app-overview/workspace-surfaces.md)
- [Conversation and Runtime](architecture/current-app-overview/conversation-and-runtime.md)
- [Providers and Tools](architecture/current-app-overview/providers-and-tools.md)
- [Admin Ops and Runtime Config](architecture/current-app-overview/admin-ops-and-runtime-config.md)
- [Account Search](architecture/current-app-overview/account-search.md)
- [Account Research](architecture/current-app-overview/account-research.md)
- [Contact Search](architecture/current-app-overview/contact-search.md)
- [Review and Approvals](architecture/current-app-overview/review-and-approvals.md)

---

## Features — agent-written summaries of completed work
- [Wiki Current App Overview Restructure](features/wiki-current-app-overview-restructure.md) — split the current-app reference page into subsystem pages under `wiki/architecture/`

## Decisions — agent-written technical decision records
<!-- Agents add entries here as significant decisions are made -->

## In Progress
<!-- Agents add entries here for work currently being planned or executed -->
