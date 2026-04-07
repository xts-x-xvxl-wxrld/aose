# Chat-Driven Orchestration MVP

## Summary

Build a single chat-first workflow entrypoint where the user talks to the orchestrator, the orchestrator decides whether to reply, ask for missing context, or launch a specialized workflow, and the thread then receives async status/result updates. Keep seller/ICP editing as forms in v1, but make chat the only user-facing way to start account search, account research, and contact search.

## Implementation Changes

- Add canonical chat APIs:
  - `POST /chat/stream` as the primary entrypoint for a user turn, streaming assistant text and typed meta events.
  - `POST /chat/threads` and `POST /chat/threads/{thread_id}/messages` only if needed to support non-stream fallback cleanly; otherwise keep the streaming route as the main interface.
  - `GET /chat/threads/{thread_id}` and `GET /chat/threads/{thread_id}/messages` for reload/resume.
  - `GET /chat/events` for recent workflow/activity events used by the existing frontend event panel.
- Implement a real orchestrator service on top of the existing conversation models/contracts:
  - Input = user text + UI context (`active_seller_id`, selected record ids, pipeline session/thread id).
  - Output = one of: inline reply, request for missing context, start workflow run.
  - Use UI context first; never auto-pick ICP/account silently when required context is missing or ambiguous.
  - Seller/ICP setup stays hybrid: forms remain the source of truth, chat reads them and can guide the user to complete missing setup.
- Make chat the only user-facing workflow trigger:
  - Do not add visible "start account search/research/contact search" buttons.
  - Keep existing workflow services as internal orchestration helpers.
  - Direct workflow-start APIs may exist internally/admin-only if useful for tests, but not as the product UX.
- Wire the executor into the running app:
  - Register an `InProcessWorkflowExecutor` at app startup.
  - Register handlers for account search, account research, and contact search.
  - When the orchestrator chooses `START_WORKFLOW_RUN`, create the run, attach it to the thread, dispatch it immediately, and return chat meta showing the queued/running state.
  - Use queue + status updates UX in v1, not "hold the request open until the workflow finishes".
- Add thread/run update behavior:
  - Persist the user turn, assistant reply, workflow-status messages, and final completion/failure messages into the conversation thread.
  - Stream meta events for run queued, run started, tool activity, run completed, run failed, and review-required states.
  - On workflow completion, append a concise assistant summary tied to the run so the chat reads like one continuous conversation.
- Build provider abstractions first, then concrete adapters:
  - Keep universal tool/connector interfaces for `web_search`, `page_fetch`, `page_scrape`, `company_enrichment`, `contact_enrichment`, `content_normalizer`.
  - Implement Firecrawl-backed adapters first for account search/research web discovery and page crawl/scrape.
  - Implement one concrete contact-provider adapter first for contact search using company/account context plus target roles/personas.
  - Design provider registration so later fallback/routing is possible, but do not implement multi-provider routing logic in v1.
- Define v1 orchestration rules explicitly:
  - "Find companies matching my ICP" requires seller + explicit ICP context; if absent, ask a follow-up in chat.
  - "Research this account" requires selected account + seller; optional ICP if available.
  - "Find contacts for this account" requires selected account + seller; use latest research snapshot when present.
  - Review gating remains off by default for these workflows unless a later requirement turns it on.
- Align frontend to the canonical backend shape:
  - Reuse the existing chat window, SSE stream, and event panel expectations already present in the frontend.
  - Update frontend context payload and event handling to match the new chat/thread/run contracts.
  - Preserve seller/ICP forms/pages for setup in v1.

## Public Interfaces

- New canonical user API is chat-based, with `POST /chat/stream` as the primary workflow control surface.
- Thread/message responses should carry `thread_id`, message ids, reply mode, optional `workflow_run_id`, and current workflow status.
- SSE event payloads should have stable event types for text chunks and workflow meta updates so the frontend can render pipeline progress without polling the workflow services directly.
- Provider connectors must implement the existing tool contracts, with Firecrawl and one contact provider as the first concrete backends.

## Test Plan

- Conversation tests:
  - New thread creation from chat.
  - Existing thread continuation.
  - Missing seller/ICP/account context produces clarifying assistant reply instead of starting the wrong workflow.
- Orchestrator tests:
  - Correctly maps natural-language intents to account search, account research, contact search, or inline reply.
  - Respects UI context first and refuses silent default ICP/account selection.
- Runtime tests:
  - Chat turn that launches a workflow creates a run, attaches it to the thread, dispatches it, and appends workflow-status messages.
  - Completed workflows append final assistant summaries to the thread.
  - Failed workflows surface an assistant-visible error/status update.
- Provider/tool tests:
  - Firecrawl adapters produce valid tool-contract responses for search/fetch/scrape flows.
  - Contact provider adapter produces valid contact enrichment responses.
- Frontend integration tests:
  - Chat stream renders assistant text and activity meta.
  - A user can complete seller/ICP setup in forms, then trigger account search from chat, then research an account, then find contacts, all without workflow buttons.

## Assumptions And Defaults

- Canonical v1 UX is chat only for workflow starts.
- Seller/ICP setup remains form-based in v1, with chat reading and referencing that state.
- Executor is in-process for v1; external queueing is deferred until after the chat-driven loop works.
- Orchestrator is user-facing in v1; no separate dedicated chat agent is introduced yet.
- UI context is treated as a hint/source of explicit selection, not as permission to invent defaults.
- Firecrawl is the first account-search/research provider, and one contact provider is the first contact-search provider.

## Conflicts With Current System

This proposal conflicts with the current canonical implementation docs and current runtime in several important ways.

- API surface conflict:
  - This document makes `/chat/*` the canonical public API.
  - The current canonical API contract uses tenant-scoped routes under `/api/v1/tenants/{tenant_id}/...` for conversations and workflow inspection.
  - See `docs/implementation/04-api-auth-and-request-context.md`.

- Tenant selection conflict:
  - This document implies chat context can be routed without an explicit tenant path.
  - The current canonical API requires tenant selection in the route path and explicitly rejects a hidden or implicit active-tenant server contract in Phase 1.
  - See `docs/implementation/04-api-auth-and-request-context.md`.

- Streaming versus polling conflict:
  - This document makes `POST /chat/stream` and SSE the primary transport.
  - The current orchestrator/run contract explicitly says Phase 1 uses polling-based conversation and workflow inspection, and lists streaming as deferred.
  - See `docs/implementation/03-orchestrator-and-run-contracts.md`.

- Orchestrator input contract conflict:
  - This document describes input as user text plus UI context such as `active_seller_id`, selected record ids, and pipeline session id.
  - The current typed `OrchestratorInput` contract uses `thread_id`, `seller_profile_id`, `icp_profile_id`, `selected_account_id`, `selected_contact_id`, `latest_run_status`, and `conversation_summary`.
  - See `docs/implementation/03-orchestrator-and-run-contracts.md` and `src/app/services/conversation.py`.

- Orchestrator decision contract conflict:
  - This document reduces orchestrator output to inline reply, missing-context request, or workflow start.
  - The current canonical decision model includes `reply_inline`, specialized workflow handoffs, `start_workflow_run`, and `request_user_review`, with `missing_inputs` represented as stable machine-readable codes rather than a separate decision family.
  - See `docs/implementation/03-orchestrator-and-run-contracts.md` and `src/app/orchestration/contracts.py`.

- Event contract conflict:
  - This document proposes streamed meta updates including queued/running/completed states and a global `GET /chat/events` feed.
  - The current canonical event model is run-scoped and freezes the stable event names as `run.started`, `agent.handoff`, `agent.completed`, `tool.started`, `tool.completed`, `run.awaiting_review`, `run.completed`, and `run.failed`.
  - There is no canonical `run.queued` event or canonical global chat-events route in the implementation docs.
  - See `docs/implementation/03-orchestrator-and-run-contracts.md`.

- Contract-ownership conflict:
  - This document effectively redefines foundational API and orchestrator contracts from inside `docs/phase2/`.
  - The current doc set says foundational contracts are owned by `docs/implementation/03-orchestrator-and-run-contracts.md` and `docs/implementation/04-api-auth-and-request-context.md`, and later work must update those owning docs rather than silently redefining them elsewhere.
  - See `docs/implementation/00-implementation-orchestrator.md`.

- Current runtime wiring conflict:
  - This document says to register an `InProcessWorkflowExecutor` and workflow handlers at app startup.
  - The current app startup only builds the agent registry and includes the current API router; it does not register workflow executor handlers in `create_app()`.
  - See `src/app/main.py`.

- Current public-router conflict:
  - This document assumes chat routes are part of the active backend surface.
  - The current API router exposes health, agents, identity, tenancy, setup, and review route groups; there are no chat or conversation routes currently mounted.
  - See `src/app/api/v1/router.py` and `tests/test_app_smoke.py`.

- Current frontend-UX conflict:
  - This document says chat should be the only user-facing way to start account search, account research, and contact search.
  - The current frontend still exposes direct workflow-style controls such as `Search accounts`, account crawl controls, and direct contact-search API helpers.
  - See `frontend/src/pages/AccountsPage.jsx` and `frontend/src/lib/api.js`.

## Conflict Resolutions

- Resolve the API surface conflict by making chat routes tenant-scoped instead of introducing a tenantless public `/chat/*` surface:
  - Treat every `/chat/*` route in this document as shorthand for `/api/v1/tenants/{tenant_id}/chat/*`.
  - Keep the chat-first product UX, but preserve the canonical public API rule that business routes remain under `/api/v1/tenants/{tenant_id}/...`.
  - Do not introduce a hidden server-side active-tenant contract, `X-Tenant-ID` override, or tenant inference based on session state.
- Resolve the tenant selection conflict by moving tenant choice into the dashboard entry flow before chat is opened:
  - If the user has multiple active tenants, the dashboard must require explicit tenant selection before allowing access to the orchestrator chat entrypoint.
  - If the user has exactly one active tenant, the client may auto-select it for convenience, but all business requests still carry that tenant explicitly in the route path.
  - The frontend may remember the last tenant locally for UX, but the backend must continue to require explicit tenant-scoped routes and must not persist or guess an implicit active tenant.
  - The selected tenant defines the chat thread namespace, workflow launches, conversation reload/resume behavior, and workflow/event inspection routes for that session.
- Resolve the streaming versus polling conflict by making streaming the primary user transport for chat-driven orchestration:
  - Treat tenant-scoped `POST /api/v1/tenants/{tenant_id}/chat/stream` plus SSE as the canonical user-facing transport for orchestrator turns in this phase.
  - Use streaming for assistant text, workflow-status/meta events, and final run outcome updates so the chat behaves like a live conversation rather than a polling-driven dashboard.
  - Preserve durable thread, message, run, and event records behind the scenes so reload/resume, auditing, and recovery do not depend on the stream connection remaining open.
  - Polling endpoints may remain available as compatibility or recovery surfaces, but they are no longer the primary UX contract for chat.
  - This resolution requires the owning implementation docs to be updated so streaming is promoted from deferred transport to canonical chat transport for this phase.
- Resolve the orchestrator input contract conflict by separating the chat payload from the canonical orchestration contract:
  - The chat UI may remain a minimal chat-first surface that sends the user message, optional `thread_id`, and optional explicit UI selections such as `seller_profile_id`, `icp_profile_id`, `selected_account_id`, and `selected_contact_id`.
  - The user-facing responder in v1 remains the orchestrator, not a separate dedicated chat agent.
  - A backend conversation/chat service is responsible for resolving durable context before orchestration runs, including `tenant_id` from the tenant-scoped route, `user_id` from auth, `latest_run_status` from workflow state, `conversation_summary` from thread state, and any previously established explicit selections stored for the thread or dashboard session.
  - That backend service must validate and normalize the incoming chat payload into the canonical typed `OrchestratorInput` contract before calling the orchestrator.
  - The orchestrator must receive only normalized canonical input and must not consume an untyped UI-context bag directly.
- Resolve the orchestrator decision contract conflict by preserving the canonical typed decision model and treating the simpler chat outcomes as UX-level groupings:
  - The canonical backend contract remains `OrchestratorDecision` with explicit decision types such as `reply_inline`, workflow handoff/start decisions, and `request_user_review`.
  - "Request for missing context" is not introduced as a separate canonical decision type.
  - Instead, missing context is represented through stable machine-readable `missing_inputs` codes attached to the orchestrator decision, together with a user-facing reply that asks the clarifying question.
  - The chat UI may present simplified user-facing categories such as inline reply, clarification needed, workflow started, or review required, but the backend contract remains the typed decision model.
  - This preserves deterministic backend routing and testability while still allowing the product UX to feel like a simple conversational flow.
- Resolve the event contract conflict by keeping canonical workflow events run-scoped while allowing the chat transport to project them into a friendlier stream for the UI:
  - The canonical durable event model remains the run-scoped event contract defined in the implementation docs.
  - The backend must continue to persist stable workflow events such as `run.started`, `agent.handoff`, `agent.completed`, `tool.started`, `tool.completed`, `run.awaiting_review`, `run.completed`, and `run.failed` against the workflow run.
  - The chat streaming layer may translate those durable run-scoped events into user-facing SSE meta updates such as queued, running, awaiting review, completed, or failed for rendering in the chat UI.
  - Any chat-level event feed is a presentation or aggregation surface over canonical run and thread records, not a replacement for the underlying run-scoped event contract.
  - If a `GET /chat/events` route is introduced, it should be documented as a derived UI convenience surface rather than the source of truth for workflow execution history.
- Resolve the contract-ownership conflict by treating the implementation docs as the current canonical baseline, while allowing later phase design work to revise them when product requirements become clearer:
  - The implementation docs are not immutable truth; they are the best current backend contract baseline and may be updated when later design work identifies a better-informed direction.
  - Phase docs may propose refinements, corrections, or contract changes when earlier implementation assumptions were made before the full product shape was known.
  - Such changes must be explicit and intentional: once accepted, they must be reconciled back into the owning documents in `docs/implementation/` so the repository returns to a single canonical contract source.
  - Until that reconciliation happens, this document should be read as a proposed evolution of the current baseline rather than a silent replacement of it.
  - The goal is not to discard the implementation docs, but to refine and integrate them so the backend contract evolves toward the intended product shape without losing continuity or prior design work.
- Resolve the current runtime wiring conflict by explicitly wiring workflow execution at app startup and keeping per-run state durable:
  - App startup should create one shared `InProcessWorkflowExecutor` per backend process and register handlers for `account_search`, `account_research`, and `contact_search`.
  - Request-time services that create workflow runs must receive that shared executor instance so queued runs can actually be dispatched.
  - The executor should remain a stateless workflow-type-to-handler registry; it must not hold tenant-specific, user-specific, or thread-specific mutable state.
  - Multi-user correctness should come from durable per-run records in the database, with `tenant_id`, `created_by_user_id`, `thread_id`, and `run_id` carried explicitly through workflow execution requests.
  - Each workflow execution should use a fresh database session inside its handler so concurrent users and concurrent runs remain isolated.
  - This in-process executor model is acceptable for v1 runtime wiring; a later queue-backed worker model may replace the dispatch mechanism without changing the durable run and event contract.
- Resolve the current public-router conflict by making tenant-scoped chat routes part of the active mounted backend surface for this phase:
  - The backend must add and mount tenant-scoped chat/conversation routes under `/api/v1/tenants/{tenant_id}/chat/...` rather than leaving chat behavior as an unmounted design-only concept.
  - These routes should become the user-facing entrypoint for orchestrator-driven chat turns, thread resume/reload behavior, and any chat-oriented event inspection surfaces introduced in this phase.
  - The mounted router surface must follow the same explicit tenant-scoping, orchestration-input normalization, streaming, and durable run/event rules defined in the conflict resolutions above.
  - Until those routes are mounted, this document describes intended backend surface evolution rather than behavior available in the running application.
- Resolve the current frontend-UX conflict by making chat the primary visible workflow entrypoint while demoting direct workflow-launch controls from the product UI:
  - The user-facing frontend should guide account search, account research, and contact search initiation through the chat entrypoint rather than exposing parallel visible workflow-start controls.
  - Existing direct workflow helpers or lower-level API utilities may remain as internal implementation details, test helpers, or admin/developer surfaces, but they should not remain peer user-facing entrypoints for the same actions.
  - Seller and ICP setup may remain form-based in v1, but workflow initiation after setup should route through chat so the product presents a single conversational control surface.
  - If transitional UI is needed during rollout, direct controls should be clearly treated as temporary compatibility surfaces rather than the intended long-term product interaction model.

## Notes On Partial Alignment

- Seller and ICP setup remaining form-based is compatible with the current setup workflow docs.
- The workflow prerequisite rules in this document are broadly compatible with the current workflow docs:
  - account search requires explicit ICP context
  - account research may run without an ICP
  - contact search may use latest research context opportunistically
- The current frontend chat code already expects `/chat/stream` and `/chat/events`, so this proposal is closer to current frontend chat assumptions than to the current canonical backend spec.
