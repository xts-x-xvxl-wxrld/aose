# Chat Events And Run Projection

## Purpose And Scope

- Define how canonical run-scoped workflow events are projected into user-friendly chat event streams and status updates.

## Dependencies On Earlier Docs

- Depends on `docs/phase2/chat-driven-orchestrator/00-chat-driven-orchestrator-overview.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/02-chat-transport-and-thread-lifecycle.md`.
- Depends on `docs/implementation/03-orchestrator-and-run-contracts.md`.

## Decision Summary

- Canonical workflow events remain run-scoped and durable.
- Canonical stable run event names remain:
  - `run.started`
  - `agent.handoff`
  - `agent.completed`
  - `tool.started`
  - `tool.completed`
  - `run.awaiting_review`
  - `run.completed`
  - `run.failed`
- Chat streaming may project those backend events into simpler user-facing statuses.
- Chat-visible `queued`, `running`, `awaiting_review`, `completed`, and `failed` states are projection outputs for the UI and do not replace the canonical run event contract.
- `queued` is a derived chat state from queued run creation or latest run status; it is not introduced as a new canonical durable run event name in this slice.
- Any `GET /chat/events` surface is derived and not the source of truth for execution history.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes canonical `RunEventName`, `WorkflowRunStatus`, and run event persistence behavior.
- Consumes canonical `ConversationReplyMode` and `ConversationTurnResponse` semantics where workflow-backed turns already expose `workflow_run_id` and `workflow_status`.
- Introduces chat-facing SSE meta event types and translation rules as presentation-layer projections over durable run and thread state.

## Data Flow / State Transitions

- A chat turn that starts workflow execution returns or streams durable workflow linkage such as `workflow_run_id` and current workflow status.
- Immediately after run creation, the chat layer may project `queued` from durable run state before any stable run event has been emitted.
- Workflow execution emits durable run-scoped events as execution advances.
- Chat transport observes or loads the latest run status plus emitted run events.
- Chat transport translates durable status and event signals into user-facing stream updates for the active chat thread.
- On reload or reconnect, the chat layer reconstructs the visible workflow timeline from durable thread messages, latest run state, and durable run events rather than relying on prior stream memory.
- Thread and run inspection remain recoverable from durable records even if some projected stream events were missed by the client.

## Failure Modes And Edge-Case Rules

- Missing or delayed projected chat events must not imply missing durable run history.
- Projected chat states must not invent backend outcomes that were never persisted.
- Translation rules must handle awaiting-review and failure states explicitly.
- Projected chat updates must tolerate the fact that not every user-friendly state has a one-to-one canonical run event name.
- If a stream disconnects after a queued or running update, reconnect behavior must derive the latest visible status from durable run state instead of replaying guessed transient UI state.
- If tool or agent events are omitted from a particular chat render, the underlying durable run history must remain complete and inspectable.
- Cancellation, if exposed later, must also be treated as a durable run-state outcome first and only then projected into chat UX.

## Validation, Ownership, And Permission Rules

- Backend event names remain canonically owned by the implementation contracts.
- Chat-friendly statuses are presentation logic, not replacement backend semantics.
- The translation layer may simplify or group backend events for UX, but it must not rename or reinterpret canonical durable event names in storage.
- Derived chat event feeds must stay tenant-scoped and thread-safe when aggregating run and message history.

## Persistence Impact

- No new canonical execution-history source is introduced here.
- Canonical workflow execution history continues to live in `WorkflowRun` and `RunEvent` records.
- Chat-visible assistant progress or completion messages may also be persisted in conversation threads when needed for conversational continuity, but those messages do not replace durable run records.
- The projection layer may read both conversation messages and run records, but run records remain the source of truth for execution history.
- This slice does not introduce a second canonical event ledger for chat.

## API / Events / Artifact Impact

- Define the chat meta event translation table used by streaming transport:
  - queued run created or latest run status `queued` -> chat meta `queued`
  - `run.started` or latest run status `running` -> chat meta `running`
  - `agent.handoff` -> chat meta `agent_handoff`
  - `agent.completed` -> chat meta `agent_completed`
  - `tool.started` -> chat meta `tool_started`
  - `tool.completed` -> chat meta `tool_completed`
  - `run.awaiting_review` or latest run status `awaiting_review` -> chat meta `awaiting_review`
  - `run.completed` or latest run status `succeeded` -> chat meta `completed`
  - `run.failed` or latest run status `failed` -> chat meta `failed`
- Define the chat streaming payload split between assistant text chunks and workflow meta updates so the frontend can render conversational output and workflow progress independently.
- If a derived `GET /chat/events` route exists, it aggregates tenant-scoped, thread-relevant projections over durable thread, run, and run-event state for UI convenience only.
- A derived chat event feed must not require clients to abandon canonical run inspection endpoints when precise workflow history is needed.

## Implementation Acceptance Criteria

- A workflow run can be rendered in chat using projected statuses without weakening the underlying run event contract.
- Derived chat event surfaces are clearly marked as presentation layers.
- The projection rules explicitly define how `queued`, `running`, `awaiting_review`, `completed`, and `failed` are produced from durable run state and stable run events.
- No new canonical durable event names are introduced solely to satisfy chat UX terminology.
- Reconnect or reload can rebuild visible workflow progress from durable records without relying on ephemeral in-memory stream state.

## Verification

- Add runtime tests for event translation and event-driven chat status rendering.
- Add doc-contract checks that canonical run event names remain unchanged unless revised in the owning implementation doc.
- Add runtime tests covering `queued` projection from durable run state before `run.started` is emitted.
- Add runtime tests covering projection of `run.started`, `run.awaiting_review`, `run.completed`, and `run.failed` into chat meta events.
- Add runtime tests covering tool and agent event projection for active chat threads.
- Add runtime tests confirming reconnect or reload reconstructs the same visible status from durable run state and persisted events.
- Add doc-contract checks for the translation table between canonical run events or statuses and chat-facing meta events.

## Deferred Items

- Richer global activity feeds beyond chat-oriented aggregation.
- Rich step-by-step replay UX that requires more than the current stable run event minimums.
