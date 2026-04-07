# Wiki Index

A catalog of all pages in this wiki. Agents update this on every ingest or significant change.

---

## Specs - active build instructions

- [Frontend: Current State and Gap Map](specs/frontend-rebuild/00-current-state-and-gap-map.md) - active frontend/backend shape, gaps, and integration surface
- [Frontend: Product and UX Direction](specs/frontend-rebuild/01-product-and-ux-direction.md) - target product flow and information architecture
- [Frontend: Rebuild and Cleanup Plan](specs/frontend-rebuild/02-frontend-rebuild-and-cleanup-plan.md) - recommended rebuild path and unreliable pieces to replace
- [Frontend: Auth and Deployment Direction](specs/frontend-rebuild/03-auth-and-deployment-direction.md) - frontend auth direction and same-origin deployment
- [Frontend: API and Resource Integration Map](specs/frontend-rebuild/04-api-and-resource-integration-map.md) - frontend-facing resource map for all surfaces
- [Frontend: Screen and Navigation Spec](specs/frontend-rebuild/05-screen-and-navigation-spec.md) - chat-first app shell, screens, and route responsibilities
- [Frontend: Implementation Roadmap](specs/frontend-rebuild/06-implementation-roadmap.md) - phased implementation order against current backend contract
- [Frontend Enablement Backend Contract](specs/frontend-enablement-backend-contract.md) - backend gaps to close before a reliable frontend can be built

## Architecture - reference (what exists today)

- [Current App Overview](architecture/current-app-overview.md) - high-level description of the app as it stands today

### current-app-overview
- [Auth and Tenancy](architecture/current-app-overview/auth-and-tenancy.md) - auth flow, tenant entry, explicit tenant scoping, and membership model
- [Domain Model](architecture/current-app-overview/domain-model.md) - durable records for threads, runs, evidence, artifacts, and approvals
- [Workspace Surfaces](architecture/current-app-overview/workspace-surfaces.md) - login, workspace, data browser, review, admin, and shared tenant context
- [Conversation and Runtime](architecture/current-app-overview/conversation-and-runtime.md) - chat transport, orchestration, run dispatch, and projected event flow
- [Providers and Tools](architecture/current-app-overview/providers-and-tools.md) - provider stack, tool factory, fallbacks, and reasoning layer
- [Admin Ops and Runtime Config](architecture/current-app-overview/admin-ops-and-runtime-config.md) - ops visibility, telemetry, config precedence, and frozen run snapshots
- [Account Search](architecture/current-app-overview/account-search.md) - current workflow behavior for account discovery and acceptance
- [Account Research](architecture/current-app-overview/account-research.md) - current workflow behavior for evidence-backed account research and snapshots
- [Contact Search](architecture/current-app-overview/contact-search.md) - current workflow behavior for provider-backed contact discovery and ranking
- [Review and Approvals](architecture/current-app-overview/review-and-approvals.md) - current review surface, approval contract, and caveats

### backend-domain
- [Implementation Orchestrator](specs/backend-domain/00-implementation-orchestrator.md) - entrypoint and conventions for the backend spec set
- [Core Domain and Ownership](specs/backend-domain/01-core-domain-and-ownership.md)
- [Persistence and Artifacts](specs/backend-domain/02-persistence-and-artifacts.md)
- [Orchestrator and Run Contracts](specs/backend-domain/03-orchestrator-and-run-contracts.md)
- [API Auth and Request Context](specs/backend-domain/04-api-auth-and-request-context.md)
- [Service Worker and Tool Boundaries](specs/backend-domain/05-service-worker-and-tool-boundaries.md)
- [Workflow: Seller and ICP Setup](specs/backend-domain/06-workflow-seller-and-icp-setup.md)
- [Workflow: Account Search](specs/backend-domain/07-workflow-account-search.md)
- [Workflow: Account Research](specs/backend-domain/08-workflow-account-research.md)
- [Workflow: Contact Search](specs/backend-domain/09-workflow-contact-search.md)
- [Evidence Approval and Artifacts](specs/backend-domain/10-evidence-approval-and-artifacts.md)
- [Deferred RAG and Future Extensions](specs/backend-domain/11-deferred-rag-and-future-extensions.md)

### chat-orchestration (Phase 2 - complete)
- [Overview](specs/chat-orchestration/chat-driven-orchestrator.md)
- [Chat API and Tenant Entry](specs/chat-orchestration/chat-driven-orchestrator/01-chat-api-and-tenant-entry.md)
- [Chat Transport and Thread Lifecycle](specs/chat-orchestration/chat-driven-orchestrator/02-chat-transport-and-thread-lifecycle.md)
- [Orchestrator Chat Contracts](specs/chat-orchestration/chat-driven-orchestrator/03-orchestrator-chat-contracts.md)
- [Chat Events and Run Projection](specs/chat-orchestration/chat-driven-orchestrator/04-chat-events-and-run-projection.md)
- [Runtime Wiring and Workflow Dispatch](specs/chat-orchestration/chat-driven-orchestrator/05-runtime-wiring-and-workflow-dispatch.md)
- [Frontend Chat Entry and UX Migration](specs/chat-orchestration/chat-driven-orchestrator/06-frontend-chat-entry-and-ux-migration.md)

### provider-workflows (Phase 3 - complete)
- [Overview](specs/provider-workflows/00-provider-backed-vertical-slice.md)
- [Provider Config and Runtime Wiring](specs/provider-workflows/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md)
- [OpenAI Structured Reasoning Layer](specs/provider-workflows/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md)
- [Account Search Provider Slice](specs/provider-workflows/provider-backed-vertical-slice/03-account-search-provider-slice.md)
- [Account Research Provider Slice](specs/provider-workflows/provider-backed-vertical-slice/04-account-research-provider-slice.md)
- [Contact Search Findymail Slice](specs/provider-workflows/provider-backed-vertical-slice/05-contact-search-findymail-slice.md)
- [Chat and Frontend Completion](specs/provider-workflows/provider-backed-vertical-slice/06-chat-and-frontend-completion.md)

### resilience-and-fallbacks (Phase 4 - mostly complete)
- [Overview](specs/resilience-and-fallbacks/00-resilience-debuggability-and-fallbacks.md)
- [Dev-Facing Debugging and Observability](specs/resilience-and-fallbacks/resilience-debuggability-and-fallbacks/01-dev-facing-debugging-and-observability.md)
- [User-Facing Failure and Degraded Experience](specs/resilience-and-fallbacks/resilience-debuggability-and-fallbacks/02-user-facing-failure-and-degraded-experience.md)
- [Account Search Fallback and Google Places](specs/resilience-and-fallbacks/resilience-debuggability-and-fallbacks/03-account-search-fallback-and-google-places.md)
- [Code-Backed Semantic Work](specs/resilience-and-fallbacks/resilience-debuggability-and-fallbacks/05-code-backed-semantic-work.md)

### authentication
- [Auth Setup Overview](specs/authentication/00-auth-setup-overview.md)
- [Zitadel Project and App Setup](specs/authentication/01-zitadel-project-and-app-setup.md)
- [Backend API Auth Implementation](specs/authentication/02-backend-api-auth-implementation.md)
- [Build Now vs Full Auth](specs/authentication/04-build-now-vs-full-auth.md)

### admin-system
- [Admin System](specs/admin-system/README.md) - platform ops, telemetry, agent config versioning, audit logs

---

## Features - agent-written summaries of completed work
- [Wiki Current App Overview Restructure](features/wiki-current-app-overview-restructure.md) - split the current-app reference page into subsystem pages and move it into `wiki/architecture/`

## Decisions - agent-written technical decision records
<!-- Agents add entries here as significant decisions are made -->

## In Progress
<!-- Agents add entries here for work currently being planned or executed -->
