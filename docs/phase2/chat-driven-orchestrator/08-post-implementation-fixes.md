# Post-Implementation Fixes

## Purpose And Scope

- Record the concrete mismatches found after implementing the Phase 2 chat-driven orchestration slice.
- Replace the earlier ambiguity-tracking document with a fix list grounded in the current runtime behavior.
- Make the remaining work explicit before declaring the chat-first path canonically complete.

## Status

- The Phase 2 chat surface, persistence changes, event projection layer, and runtime wiring now exist in code.
- The implementation exists, but Phase 2 is not complete yet.
- The current implementation is partially aligned with the accepted Phase 2 direction, but several contract-critical behaviors still need correction.
- The remaining work is concentrated in backend lifecycle correctness and conversational continuity.
- This file is now the Phase 2 closure and correction document for the implemented slice set.

## Decision Lock

- This fix pass is full closure for the remaining Phase 2 post-implementation backend and thread-continuity issues.
- Workflow-backed chat remains status-aware. Durable `workflow_status` messages stay in the thread for progress visibility, and terminal assistant summary messages are added for conversational continuity.
- Workflow-backed chat threads will keep durable workflow status messages and also append a final assistant summary message tied to the run.
- The target UX is not assistant-only and not status-log-only; it is progress records plus final assistant summaries.
- The target thread style is conversational continuity plus progress visibility, not pure status-log output and not assistant-only replacement of status records.

## Implemented Areas That Are In Good Shape

- Tenant-scoped chat routes are mounted under `/api/v1/tenants/{tenant_id}/chat/...`.
- `X-Request-ID` is required on `POST /chat/stream`.
- Durable user-turn idempotency is partially implemented through persisted `request_id` storage on `ConversationMessage`.
- The backend creates and wires a shared `InProcessWorkflowExecutor` at app startup.
- Workflow handlers use fresh database sessions through the runtime wiring layer.
- Chat event projection exists for queued, running, awaiting-review, completed, failed, agent, and tool states.

## Post-Implementation Findings

### 1. Streaming Route Still Behaves Like A Synchronous Request

- The current `POST /api/v1/tenants/{tenant_id}/chat/stream` route computes nearly all work before returning the SSE response.
- The workflow-backed path currently creates the run, dispatches it, refreshes current run state, projects run events, and only then returns the stream response.
- This means the request can remain open until the workflow has already advanced or finished, instead of immediately yielding a queued or running chat response.
- That behavior conflicts with the accepted transport and runtime contract:
  - use queue plus status updates UX in v1
  - do not hold the request open until the workflow finishes
  - allow workflow completion to occur after the initial stream ends

### 2. Workflow-Start Retries Do Not Yet Guarantee Resumable Accepted-Turn Recovery

- Idempotency is correctly designed around the durable accepted user turn, but the workflow-start path still has a partial-materialization recovery gap.
- A queued workflow run can exist before the initial assistant-visible workflow response is guaranteed to exist on the thread.
- If the process fails or the request is interrupted after run creation but before the initial assistant/status messages are fully persisted, a retry with the same `(tenant_id, user_id, request_id)` can find the accepted user turn, fail to find the expected response message, and not yet guarantee reuse or repair of the already accepted workflow-start outcome.
- The current implementation therefore protects the common happy-path retry case, but not the full interrupted workflow-start recovery case required by the Phase 2 contract.

### 3. Workflow Completion Does Not Yet Append A Final Assistant Summary

- The current workflow-backed chat path persists `workflow_status` messages such as queued, running, succeeded, or failed.
- It does not currently append a concise assistant summary tied to the run after completion or failure.
- As a result, the thread reads like status-log output rather than one continuous assistant conversation.
- This conflicts with the accepted Phase 2 requirement that completed workflows append a final assistant-visible summary so the chat remains conversational.

### 4. Workflow Start Does Not Yet Distinguish Status Messaging From Conversational Messaging

- The current response path for workflow-backed turns returns the latest `workflow_status` message text as the main chat reply.
- This compresses two separate concerns into one surface:
  - conversational assistant response for the user turn
  - machine-driven workflow status updates for progress rendering
- The accepted Phase 2 design expects both durable workflow status visibility and assistant continuity, not only system-style status messages.

## Required Fixes

### Backend Fixes

- Refactor `POST /chat/stream` so it can return SSE frames promptly after durable turn acceptance and queued-run creation.
- Stop awaiting full in-request workflow progression before beginning stream output.
- Treat the initial stream as the place to return accepted thread linkage plus queued or running meta, not as a synchronous completion transport.
- The `/chat/stream` refactor must be completed together with terminal assistant-summary persistence for workflow-backed turns.
- Close the workflow-start retry gap by treating run creation, thread linkage, and the first assistant/status messages as one resumable accepted-turn outcome.
- Ensure a retry can reuse or repair existing run linkage when the first stream died after queued-run creation but before the initial workflow response was fully materialized.
- Persist the initial accepted workflow outcome durably before dispatch so retries recover accepted state instead of attempting to recreate it.
- Keep `workflow_status` messages as durable progress records, but stop relying on them as the only assistant-visible workflow response.
- Every workflow-backed turn must persist an initial assistant reply when the workflow is accepted.
- Every workflow-backed turn must append a terminal assistant reply on `succeeded`, `failed`, or `awaiting_review`.
- Append a final assistant summary message on workflow completion and workflow failure, tied to the corresponding run.

## Acceptance Criteria For Closure

- A workflow-start turn returns a usable stream immediately after durable turn acceptance and queued-run dispatch attempt.
- Workflow completion may happen after the initial stream ends, with reload and event routes recovering the latest durable state correctly.
- Retrying an interrupted workflow-start turn with the same `X-Request-ID` reuses or repairs the accepted workflow-start outcome instead of attempting to recreate it.
- Backend behavior is fixed for prompt-returning stream behavior and idempotent workflow start.
- Workflow-backed turns append both progress/status records and a final assistant summary message.

## Verification Additions Required

- Add a runtime test proving that the workflow-start stream returns before full workflow completion is required.
- Add a runtime or service test covering interruption after queued-run creation but before the initial assistant/status workflow response is fully persisted, and prove that retry repairs or reuses the accepted outcome instead of attempting to recreate it.
- Add runtime tests proving that workflow-backed turns persist an initial assistant reply plus queued `workflow_status` message.
- Add runtime tests proving that completed workflows append a final assistant summary message tied to the run.
- Add runtime tests proving that failed workflows also append an assistant-visible failure summary.
- Add runtime tests proving that review-required workflows append an assistant-visible summary if review states are surfaced.

## Owning Follow-Up Docs

- Reconcile the fixes above back into:
  - `docs/implementation/03-orchestrator-and-run-contracts.md`
  - `docs/implementation/04-api-auth-and-request-context.md`
  - `docs/implementation/05-service-worker-and-tool-boundaries.md`
  - `docs/implementation/00-implementation-orchestrator.md` if the rollout baseline or verification guidance changes

## Closure Rule

- Do not declare the Phase 2 chat-first path complete while any item above remains unresolved.
- Once the implementation matches the accepted Phase 2 behavior, this file may be reduced to a short closure note or removed in favor of the updated implementation docs.

## Assumptions And Defaults

- Full closure is the implementation target for this pass.
- No public API shape change is required for the fix pass.
- No SSE wire-shape change is required for the fix pass.
- Keep `workflow_status` messages.
- Add final assistant summaries rather than replacing status messages entirely.
