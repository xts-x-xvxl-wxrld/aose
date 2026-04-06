# Runtime Wiring And Workflow Dispatch

## Purpose And Scope

- Define how chat-driven workflow runs are dispatched at runtime and how the in-process executor is wired for v1.

## Dependencies On Earlier Docs

- Depends on `docs/phase2/chat-driven-orchestrator/00-chat-driven-orchestrator-overview.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/03-orchestrator-chat-contracts.md`.
- Depends on `docs/implementation/05-service-worker-and-tool-boundaries.md`.

## Decision Summary

- App startup creates one shared `InProcessWorkflowExecutor` per backend process.
- The shared executor should be attached to application runtime state, for example `app.state.workflow_executor`, so request-time services can receive the same instance consistently.
- Workflow handlers are registered for account search, account research, and contact search.
- Each registered handler is a thin runtime adapter that:
  - opens a fresh database session from the shared session factory
  - constructs the workflow implementation and any required workflow-run service dependencies for that execution
  - delegates execution through the worker runtime wrapper so run state transitions and terminal updates are handled consistently
- Per-run correctness comes from durable database records, not executor-held mutable state.
- Each execution uses a fresh database session.
- Chat request handlers create and commit queued workflow runs first, then dispatch them through the shared executor using the durable `WorkflowExecutionRequest`.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes canonical `WorkflowExecutionRequest`, workflow run statuses, run events, and workflow handler boundaries.
- Consumes `InProcessWorkflowExecutor`, `WorkflowRunService.dispatch_queued_run`, `execute_workflow_request`, and the shared async session factory from the current runtime and database modules.
- Introduces startup wiring and dependency-injection conventions for the chat-driven path rather than new execution primitives.

## Data Flow / State Transitions

- Orchestrator decides to start a workflow run.
- Request-time service creates a queued `WorkflowRun` record and commits it before dispatch.
- Request-time service builds or reuses `WorkflowRunService` with the shared executor instance attached.
- Request-time service dispatches the queued run using `dispatch_queued_run`, which builds a durable `WorkflowExecutionRequest`.
- Shared executor looks up the handler registered for the requested `WorkflowType`.
- The handler opens a fresh database session using the application session factory and constructs the workflow implementation for that execution.
- The handler delegates to the worker runtime wrapper, which marks the run `running`, invokes the workflow, and applies terminal or review-state transitions.
- Durable run state and run events then drive chat projection, reload, and reconnect behavior.

## Failure Modes And Edge-Case Rules

- If no handler is registered for a workflow type, dispatch fails explicitly.
- Executor state must not leak user-specific or tenant-specific context across runs.
- Concurrent runs must remain isolated even when served by the same app process.
- If queued-run creation succeeds but dispatch fails, the run remains durably visible in `queued` unless later recovery or retry rules are added; the system must not pretend execution started when it did not.
- If a handler raises `WorkflowExecutionError`, failure is recorded through canonical run-failure transitions rather than ad hoc chat-only error handling.
- If a handler raises an unexpected exception, the worker runtime marks the run failed before the exception escapes.
- Handlers must not reuse the request-scoped database session from the chat API request for long-running workflow execution.

## Validation, Ownership, And Permission Rules

- Authorization-adjacent checks remain in services before workflow execution begins.
- Workflow handlers execute only against explicitly provided tenant, user, thread, and run identifiers.
- The executor registry owns only workflow-type-to-handler dispatch and must not perform authorization, tenant lookup, or context inference.
- `WorkflowExecutionRequest` is the handoff boundary between request-time orchestration services and runtime execution handlers.
- Request-time services remain responsible for validating that the queued run belongs to the acting tenant and user context before dispatch.

## Persistence Impact

- Chat-launched workflow execution must always create a durable queued run before dispatch.
- `queued -> running -> terminal-or-review` transitions continue to be recorded through canonical `WorkflowRunService` methods.
- Stable run events such as `run.started`, `run.awaiting_review`, `run.completed`, and `run.failed` continue to be emitted through the workflow-run service and remain the durable execution history.
- No executor-local in-memory job ledger becomes a substitute for the database-backed run and event records.

## API / Events / Artifact Impact

- Chat-facing routes should receive workflow linkage immediately after queued-run creation and dispatch attempt, typically through `workflow_run_id` plus projected queued or running status.
- Chat transport and derived chat event projection continue to observe execution state through durable run and event records rather than direct callbacks from the executor.
- Request correlation identifiers may be carried through `WorkflowExecutionRequest.request_id` for tracing, but correlation does not replace tenant-scoped durable run identity.

## Implementation Acceptance Criteria

- Startup wiring registers the shared executor and workflow handlers.
- The shared executor is created during app startup and is reachable from request-time service construction without rebuilding a new executor per request.
- Registered handlers exist for `account_search`, `account_research`, and `contact_search`.
- Request-time services can dispatch queued runs through the shared executor.
- Registered handlers open fresh database sessions for execution and delegate status transitions through the worker runtime wrapper.
- The request-time path creates and commits queued runs before execution starts.
- Concurrent users and concurrent runs remain isolated by durable state and fresh execution sessions.
- The executor remains stateless with respect to tenant, user, and thread mutable context.

## Verification

- Add runtime tests covering startup wiring, dispatch success, missing-handler failure, and concurrent isolation.
- Add doc-contract checks for the registered workflow types and runtime wiring invariants.
- Add runtime tests confirming `create_app()` or equivalent startup wiring exposes a shared workflow executor on application state.
- Add runtime tests confirming `WorkflowRunService` dispatch fails clearly when no executor or no handler is configured.
- Add runtime tests confirming handlers use fresh sessions rather than the originating request session.
- Add runtime tests covering queued-run creation followed by successful dispatch for each registered workflow type.
- Add runtime tests covering dispatch failure after queued-run creation and verifying the durable run remains inspectable.

## Deferred Items

- Queue-backed execution and worker-process separation beyond the in-process abstraction.
- Retry and recovery infrastructure for runs left queued or interrupted by process failure.
