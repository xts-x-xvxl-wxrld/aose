# Chat Transport And Thread Lifecycle

## Purpose And Scope

- Define the streaming-first transport model for chat turns and the lifecycle rules for chat threads.

## Dependencies On Earlier Docs

- Depends on `docs/phase2/chat-driven-orchestrator/00-chat-driven-orchestrator-overview.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/01-chat-api-and-tenant-entry.md`.
- Depends on `docs/implementation/03-orchestrator-and-run-contracts.md`.

## Decision Summary

- Streaming is the primary transport for chat-driven orchestration.
- The primary transport route is `POST /api/v1/tenants/{tenant_id}/chat/stream`.
- `POST /api/v1/tenants/{tenant_id}/chat/stream` requires a client-supplied `X-Request-ID` for turn idempotency.
- The stream carries two top-level categories of output:
  - assistant text output for conversational rendering
  - workflow meta updates projected from durable run and thread state
- The first streamed user turn may create a thread implicitly and return or stream its durable `thread_id`.
- Durable thread and message state remains authoritative underneath the stream.
- Polling may remain as a recovery or compatibility surface, but not the primary chat UX contract.
- Reload and reconnect rebuild the visible chat state from durable thread, message, run, and run-event records rather than from prior stream memory.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes canonical conversation, message, workflow run, and run event contracts.
- Consumes the tenant-scoped chat route family and implicit-thread-creation rule from `01-chat-api-and-tenant-entry.md`.
- Consumes the streamed chat-turn request envelope from `03-orchestrator-chat-contracts.md`.
- Consumes the chat meta event projection rules from `04-chat-events-and-run-projection.md`.
- Introduces line-delimited SSE framing rules, stream envelope categories, and thread lifecycle rules for the chat transport layer.

## Accepted Turn Idempotency

- The persistence boundary for chat-turn idempotency is the durable `user_turn` record.
- The accepted `request_id` is stored on the durable user-turn record for chat turns accepted through `POST /api/v1/tenants/{tenant_id}/chat/stream`.
- Enforce uniqueness for accepted user turns within `(tenant_id, created_by_user_id, request_id)`.
- Recommended implementation shape for this phase:
  - store `request_id` on `ConversationMessage`
  - persist it only for `message_type = 'user_turn'`
  - back it with a partial unique index for accepted user-turn rows
- On retry after durable commit, the backend looks up the existing accepted user turn by `(tenant_id, created_by_user_id, request_id)` and resumes from that durable state rather than creating new records.
- If the original accepted turn created a new thread, the retry returns the original `thread_id`.
- If the original accepted turn created a workflow run, the retry returns the original `workflow_run_id` plus the latest durable workflow status.
- If the stream died after durable persistence, recovery comes from durable thread, message, run, and run-event records rather than from replaying guessed in-memory output.
- Idempotency applies to all accepted `/chat/stream` turns in this phase, with first-turn duplicate-thread prevention called out as the critical case.
- Conflict rule:
  - same `(tenant_id, user_id, request_id)` plus the same accepted turn resumes existing durable state
  - same `(tenant_id, user_id, request_id)` plus a different `user_message`, different explicit selectors, or different `thread_id` is rejected as `409 request_id_conflict`

## Data Flow / State Transitions

- Client opens `POST /api/v1/tenants/{tenant_id}/chat/stream` with the minimal chat-turn payload.
- The request includes `X-Request-ID`, which is the idempotency key scoped by tenant and acting user for the turn.
- If `thread_id` is absent, the backend treats the request as the first turn of a new thread and creates the durable tenant-scoped thread as part of processing the turn.
- If `thread_id` is present, the backend loads and validates the existing tenant-scoped thread before processing the turn.
- Backend persists the user turn and any durable thread context needed for follow-up turns before or alongside orchestration.
- Backend begins streaming assistant text chunks and projected workflow meta updates as soon as they are available.
- If the orchestrator replies inline, the stream completes after the assistant reply and any associated persisted message records are finalized.
- If the orchestrator starts a workflow, the stream includes workflow linkage such as `thread_id`, `workflow_run_id`, and projected queued or running status before the request completes.
- Later thread reload or message-history routes reconstruct the conversation from durable thread and message records.
- Reconnect after interruption uses the durable thread, run, and run-event state to recover the latest visible status rather than replaying ephemeral in-memory stream state.
- A retry with the same accepted request id resolves durable user-turn state before any new thread, message, or workflow creation is attempted.

## Failure Modes And Edge-Case Rules

- Stream interruption must not lose durable thread or run state.
- Duplicate reconnect logic must not create duplicate user turns.
- Thread resume must remain tenant-scoped, membership-checked, and available to active tenant members rather than only to the thread creator.
- A dropped stream after durable user-turn persistence but before the client receives all streamed output must still allow the client to recover the turn result from thread and run inspection surfaces.
- A client retry after network interruption with the same `X-Request-ID` must not blindly create a second first-turn thread when the original turn was already durably committed.
- The idempotency scope for a streamed chat turn is `(tenant_id, user_id, request_id)`.
- Reload behavior must remain correct whether the interrupted turn was inline-only, workflow-backed, awaiting review, or failed.
- The transport must tolerate the fact that workflow completion may occur after the initial stream ends; later state is observed through durable thread and run records plus any derived chat event surfaces.
- A conflicting retry that reuses the same request id with a changed payload must fail deterministically rather than being treated as a new turn.

## Validation, Ownership, And Permission Rules

- Transport choice does not weaken tenant validation or message ownership rules.
- Durable thread state, not client memory, remains the recovery source of truth.
- Thread creation, reload, resume, and message-history access all remain tenant-scoped and membership-checked.
- In v1, tenant-member visibility is the access model for chat threads; creator-only or participant-only thread ACLs are deferred.
- The stream transport is responsible only for delivery and presentation timing; canonical validation, orchestration, persistence, and workflow execution remain owned by backend services.
- Compatibility polling or reload surfaces must not redefine the thread, message, or run ownership rules already established elsewhere.

## Persistence Impact

- Before or during stream startup, the backend persists the tenant-scoped thread when needed and persists the user message for the turn.
- The durable user-turn record carries the accepted `request_id` for chat-turn idempotency in this phase.
- The recommended persistence enforcement is a partial unique index over accepted user-turn rows scoped by tenant, actor, and request id.
- During inline reply handling, the backend persists assistant reply messages according to canonical conversation rules while streaming user-visible text.
- During workflow-backed turns, the backend persists workflow-linked conversation messages, queued runs, and later run status or completion records according to the canonical run and event model.
- Stream delivery itself is not a persistence layer; missing client receipt of stream chunks does not imply missing durable records.
- Thread reload and message-history routes read from durable persisted records, not from stream-session memory.

## API / Events / Artifact Impact

- The primary transport route is `POST /api/v1/tenants/{tenant_id}/chat/stream`.
- Supporting lifecycle routes remain:
  - `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}`
  - `GET /api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages`
  - non-required derived `GET /api/v1/tenants/{tenant_id}/chat/events` only if a convenience feed is later implemented
- The canonical stream framing is line-delimited SSE only using `data:` frames plus blank-line separators.
- Assistant text frames use `data: {"text":"<chunk>","thread_id":"<uuid>"}`.
- Workflow meta frames use `data: {"meta":{"type":"queued|running|awaiting_review|completed|failed|agent_handoff|agent_completed|tool_started|tool_completed","thread_id":"<uuid>","workflow_run_id":"<uuid|null>","workflow_status":"queued|running|awaiting_review|succeeded|failed|cancelled|null","payload":{...}}}`.
- Terminal success uses `data: [DONE]`.
- Terminal stream errors use `data: {"error":"<message>","error_code":"<stable_code>","request_id":"<id>"}` followed by stream close.
- Polling-oriented or compatibility surfaces may remain available for operational recovery, reload, or rollout compatibility, but they are secondary to the streaming chat UX.
- A reconnecting client should recover by reading durable thread, message, and run state rather than by requiring resumable low-level stream cursors in this phase.

## Implementation Acceptance Criteria

- A tenant-scoped chat turn can stream assistant output without losing durable persistence guarantees.
- First-turn streamed requests can create durable threads implicitly and return usable `thread_id` linkage.
- Follow-up streamed requests target existing tenant-scoped threads and do not create duplicate threads.
- Thread reload and resume rules are explicit.
- `X-Request-ID` idempotency rules are explicit for first-turn and follow-up retries.
- Accepted-turn idempotency is defined in terms of durable user-turn storage rather than transient stream state.
- The docs specify where `request_id` is stored, how uniqueness is enforced, and how durable retry resume works.
- Stream interruption and reconnect behavior are defined for both inline and workflow-backed turns.
- Polling fallback, if retained, is documented as secondary.
- The stream contract distinguishes assistant text delivery from workflow meta delivery.

## Verification

- Add runtime tests for stream start, reconnect, and reload behavior.
- Add doc-contract checks for the streaming route and thread lifecycle surface.
- Add runtime tests covering first-turn implicit thread creation over `POST /chat/stream`.
- Add runtime tests covering first-turn retry with the same `X-Request-ID` and proving that no duplicate thread is created.
- Add runtime tests covering retry of the same workflow-start turn and proving that no duplicate workflow run is created.
- Add runtime tests covering retry with the same `request_id` but different payload and proving that `request_id_conflict` is returned.
- Add runtime tests covering follow-up streamed turns against an existing `thread_id`.
- Add runtime tests covering interrupted inline-reply streams and recovery through thread reload.
- Add runtime tests covering interrupted workflow-backed streams and recovery through durable run and message state.
- Add doc-contract checks that reload and message-history routes remain explicit supporting surfaces for the streaming chat contract.

## Deferred Items

- Multi-transport parity guarantees beyond the minimal fallback surface.
- Low-level resumable stream cursor protocols beyond reload-from-durable-state behavior.
