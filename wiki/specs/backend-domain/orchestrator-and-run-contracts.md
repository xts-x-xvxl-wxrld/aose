# Orchestrator And Run Contracts

## Purpose And Scope

This document defines the canonical orchestrator input/output contracts, workflow run contract, run events, and state transitions for the current milestone.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)

## Decision Summary

- The orchestrator is the first user-facing conversation layer for the chat-first milestone.
- The orchestrator decides whether work is inline or workflow-backed.
- The canonical user-turn transport is `POST /api/v1/tenants/{tenant_id}/chat/stream`.
- The chat route accepts a minimal streamed-turn envelope and normalizes it into canonical `OrchestratorInput`.
- Workflow-backed decisions must be specific enough that the service can persist or reject them without inventing new contract rules.
- Account search, account research, and contact search default to workflow runs.
- Seller and ICP setup may be inline or workflow-backed depending on complexity.
- Workflow runs are durable, tenant-scoped, and actor-scoped.
- Review-aware states are built into the run contract from the start.
- Chat and compatibility conversation APIs return a stable turn response whether work completes inline or continues as a workflow.
- Streaming is the primary chat transport; durable thread, message, run, and run-event records remain the recovery source of truth.
- `active_workflow` is persisted thread context plus a current-turn normalization hint.
- `missing_inputs` uses stable machine-readable codes; user-facing guidance belongs in `reply_message`.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### OrchestratorInput

```python
class OrchestratorInput(TypedDict):
    tenant_id: str
    user_id: str
    thread_id: str | None
    user_message: str
    active_workflow: str | None
    seller_profile_id: str | None
    seller_profile_status: str | None
    icp_profile_id: str | None
    icp_profile_status: str | None
    selected_account_id: str | None
    selected_contact_id: str | None
    latest_run_status: str | None
    conversation_summary: str | None
```

Rules:

- `thread_id` may be `None` only for a new conversation
- `active_workflow` is persisted thread context plus a current-turn normalization hint
- a validated explicit current-turn `active_workflow` value takes precedence over an older persisted thread value for that turn
- `active_workflow` does not authorize access and does not override tenant or resource validation
- full message history is not passed by default
- the orchestrator operates only within the provided tenant and user context

### ChatTurnStreamRequest

```python
class ChatTurnStreamRequest(TypedDict):
    user_message: str
    thread_id: str | None
    seller_profile_id: str | None
    icp_profile_id: str | None
    selected_account_id: str | None
    selected_contact_id: str | None
    active_workflow: str | None
```

Rules:

- this is the canonical request envelope for `POST /api/v1/tenants/{tenant_id}/chat/stream`
- `thread_id` may be omitted only for the first turn of a new thread
- empty threads are not created in this milestone
- the request contains only client-supplied user-turn context; `tenant_id`, `user_id`, `latest_run_status`, and `conversation_summary` remain server-owned
- `seller_profile_id`, `icp_profile_id`, `selected_account_id`, and `selected_contact_id` are optional explicit context selectors and must be validated before orchestration
- `active_workflow` is optional and, when valid, acts as current-turn workflow context that may update the thread's persisted workflow context once the turn is durably accepted

### OrchestratorDecision

```python
class OrchestratorDecision(TypedDict):
    decision_type: str
    workflow_type: str | None
    target_agent: str | None
    reply_message: str | None
    reasoning_summary: str
    requires_persistence: bool
    missing_inputs: list[str]
    handoff_payload: dict[str, Any] | None
    confidence: float
```

Allowed `decision_type` values:

- `reply_inline`
- `handoff_to_account_search`
- `handoff_to_account_research`
- `handoff_to_contact_search`
- `start_workflow_run`
- `request_user_review`

Rules:

- `reply_inline` requires `reply_message`
- `start_workflow_run` requires `workflow_type`
- handoff decisions require `target_agent`
- `handoff_to_account_search`, `handoff_to_account_research`, and `handoff_to_contact_search` are specialized workflow-start decisions; the service must normalize them into workflow creation with the corresponding workflow type and specialist target
- `start_workflow_run` is reserved for workflow-backed operations where the workflow type is known but a dedicated specialist handoff is not required or not the primary contract detail
- `request_user_review` requires `reply_message` and `handoff_payload` containing at least a `review_reason` plus the relevant `workflow_run_id` or `artifact_id`
- `confidence` is advisory and does not replace explicit validation
- `missing_inputs` contains stable machine-readable codes, not prose questions

### ConversationCreateRequest

```python
class ConversationCreateRequest(TypedDict):
    user_message: str
    seller_profile_id: str | None
    icp_profile_id: str | None
    active_workflow: str | None
```

Rules:

- this is a transitional compatibility request shape for `POST /api/v1/tenants/{tenant_id}/conversations` if that alias is retained during rollout
- the canonical user-turn request shape is `ChatTurnStreamRequest`
- compatibility conversation creation always includes the first user message
- empty threads are not created in Phase 1
- `seller_profile_id` is optional at creation time but should be supplied when already known
- `icp_profile_id` is optional at creation time but should be supplied when already known
- if both are supplied, the referenced seller and ICP must belong to the same tenant and be mutually compatible

### ConversationMessageCreateRequest

```python
class ConversationMessageCreateRequest(TypedDict):
    user_message: str
    seller_profile_id: str | None
    icp_profile_id: str | None
    selected_account_id: str | None
    selected_contact_id: str | None
    active_workflow: str | None
```

Rules:

- this is a transitional compatibility request shape for `POST /api/v1/tenants/{tenant_id}/conversations/{thread_id}/messages` if that alias is retained during rollout
- the canonical user-turn request shape is `ChatTurnStreamRequest`
- follow-up user turns must target an existing tenant-scoped thread
- selection identifiers are optional and allow the user to advance from search to research or contact workflows
- `seller_profile_id` and `icp_profile_id` may be supplied on a follow-up turn to change active context explicitly rather than forcing the service to infer context changes from free text
- `active_workflow` may be supplied on a follow-up turn as an explicit workflow-context override and is subject to the same validation and persistence rules as the chat stream request

### ConversationTurnResponse

```python
class ConversationTurnResponse(TypedDict):
    thread_id: str
    user_message_id: str
    assistant_message_id: str | None
    reply_mode: str
    reply_message: str | None
    workflow_run_id: str | None
    workflow_status: str | None
    missing_inputs: list[str]
    request_id: str
```

Allowed `reply_mode` values:

- `inline_reply`
- `workflow_queued`
- `workflow_running`
- `awaiting_review`

Rules:

- `inline_reply` returns `assistant_message_id` and `reply_message`
- workflow-backed responses return `workflow_run_id`
- `missing_inputs` may be present for either inline guidance or deferred workflow follow-up

### ChatStreamMetaEvent

```python
class ChatStreamMetaEvent(TypedDict):
    type: str
    thread_id: str
    workflow_run_id: str | None
    workflow_status: str | None
    payload: dict[str, Any]
```

Allowed `type` values:

- `queued`
- `running`
- `awaiting_review`
- `completed`
- `failed`
- `agent_handoff`
- `agent_completed`
- `tool_started`
- `tool_completed`

Rules:

- `thread_id` is always present once the durable thread exists
- `workflow_run_id` is present for workflow-backed turns and may be `None` for inline-only turns
- `workflow_status` carries the latest durable run status when a workflow run exists
- `payload` carries lightweight UI-facing metadata and must not replace canonical durable run or event records

### Chat Stream Framing

Rules:

- the canonical chat transport is line-delimited SSE only
- v1 uses `data:` frames plus blank-line separators and does not require named `event:` frames
- assistant text frames use `data: {"text":"<chunk>","thread_id":"<uuid>"}`
- workflow meta frames use `data: {"meta":<ChatStreamMetaEvent>}`
- terminal success uses `data: [DONE]`
- terminal stream errors use `data: {"error":"<message>","error_code":"<stable_code>","request_id":"<id>"}` followed by stream close

### Missing Input Codes

Phase 1 stable missing-input codes:

- `seller_profile_required`
- `icp_profile_required`
- `selected_account_required`
- `selected_contact_required`
- `review_decision_required`

Rules:

- these codes are machine-readable and stable across clients
- user-facing guidance for each code belongs in `reply_message`
- later docs may add new codes, but may not redefine the meaning of existing ones silently

### Workflow Types

Current milestone workflow types:

- `seller_profile_setup`
- `icp_profile_setup`
- `account_search`
- `account_research`
- `contact_search`

### WorkflowRun Statuses

Allowed statuses:

- `queued`
- `running`
- `awaiting_review`
- `succeeded`
- `failed`
- `cancelled`

Transition rules:

- `queued -> running`
- `running -> awaiting_review`
- `running -> succeeded`
- `running -> failed`
- `running -> cancelled`
- `awaiting_review -> succeeded`
- `awaiting_review -> failed`
- `awaiting_review -> cancelled`

No other transitions are allowed.

### Run Events

Allowed stable event names:

- `run.started`
- `agent.handoff`
- `agent.completed`
- `tool.started`
- `tool.completed`
- `run.awaiting_review`
- `run.completed`
- `run.failed`

Optional future event names may be added, but these are the stable minimum set.

#### Event Payload Minimums

Minimum payload expectations:

1. `run.started` includes `workflow_type` and `thread_id` when present.
2. `agent.handoff` includes `from_agent`, `to_agent`, and a brief `reason`.
3. `agent.completed` includes `agent_name` and `result_summary`.
4. `tool.started` includes `tool_name`, `provider_name` when relevant, `input_summary`, and a correlation key.
5. `tool.completed` includes `tool_name`, `provider_name` when relevant, `output_summary`, `error_code` when present, and whether evidence-bearing results were produced.
6. `run.awaiting_review` includes `review_reason` and the blocking `artifact_id` or `workflow_run_id`.
7. `run.completed` includes a lightweight result summary and any canonical output ids produced by the run.
8. `run.failed` includes `error_code` and failure summary text.

## Data Flow / State Transitions

### Inline Path

1. client calls `POST /api/v1/tenants/{tenant_id}/chat/stream`
2. API resolves request context
3. service validates the streamed-turn request and resolves or creates the durable tenant-scoped thread
4. service builds `OrchestratorInput`
5. orchestrator returns `reply_inline`
6. service persists conversation messages
7. API streams assistant text frames and completes with `data: [DONE]`

### Workflow Path

1. client calls `POST /api/v1/tenants/{tenant_id}/chat/stream`
2. API resolves request context
3. service validates the streamed-turn request and resolves or creates the durable tenant-scoped thread
4. service builds `OrchestratorInput`
5. orchestrator returns `start_workflow_run` or a workflow handoff decision
6. service creates `WorkflowRun` in `queued`
7. API streams workflow linkage and projected queued or running meta updates
8. worker moves run to `running`
9. worker emits durable run and tool events
10. worker persists canonical outputs
11. worker either completes, fails, or pauses for review
12. client recovers subsequent state through tenant-scoped thread, message, run, and run-event inspection surfaces

### Review Path

1. worker reaches a review gate
2. run moves to `awaiting_review`
3. `run.awaiting_review` event is emitted
4. reviewer acts on linked artifact or output
5. service resumes completion or failure handling

## Failure Modes And Edge-Case Rules

- If the orchestrator lacks required identifiers, it should prefer `reply_inline` with missing-input guidance over starting speculative workflows.
- If the worker crashes after moving a run to `running`, recovery is deferred to future infrastructure; the first implementation may rely on manual retry.
- If a user requests research for an account outside the tenant, reject before orchestration.
- If a client attempts to create an empty conversation thread, reject the request.
- If a message targets a thread outside the tenant, reject it without revealing cross-tenant existence.
- If a client retries a first turn after durable commit using the same `X-Request-ID`, the service must return or resume from the existing durable state instead of creating a duplicate thread.
- If the stream fails after durable persistence but before all frames are received, recovery must come from the durable thread, message, run, and run-event records rather than replaying guessed in-memory state.
- If a run is cancelled during execution, the worker should stop creating new downstream records as soon as practical and emit terminal run state.

## Validation, Ownership, And Permission Rules

- The service layer owns validation of tenant membership and resource access before invoking the orchestrator.
- The orchestrator does not grant permissions; it only reasons within already validated context.
- Workflow runs inherit `tenant_id` and `created_by_user_id` from the triggering request context.
- Thread reload and message-history access remain tenant-scoped and membership-checked, not creator-scoped.
- Phase 2 clients primarily use the streaming chat route for live turn delivery and use tenant-scoped thread, message, run, and run-event surfaces for reload, reconnect, and precise inspection.
- seller and ICP identifiers passed into orchestration must already be tenant-validated before the orchestrator can rely on them
- the orchestrator may request missing prerequisites, but it may not infer unauthorized access to seller, ICP, account, or contact records

## Persistence Impact

This doc defines the lifecycle semantics of `WorkflowRun` and `RunEvent`. Persistence structure remains owned by the persistence doc.

## API / Events / Artifact Impact

- Chat stream and compatibility conversation APIs produce orchestrator inputs.
- Workflow APIs inspect durable run state and events.
- Review flows depend on `awaiting_review` status and linked artifacts.
- `POST /api/v1/tenants/{tenant_id}/chat/stream` is the canonical user-turn transport.
- `GET /chat/threads/{thread_id}`, `GET /chat/threads/{thread_id}/messages`, `GET /workflow-runs/{run_id}`, and `GET /workflow-runs/{run_id}/events` are the durable reload and inspection surfaces.
- `/conversations...` routes, if retained, are transitional compatibility aliases over the same underlying services and contracts.
- `GET /chat/threads/{thread_id}/messages` and `GET /workflow-runs/{run_id}/events` are cursor-paginated append-only inspection surfaces
- `GET /workflow-runs/{run_id}` returns the latest materialized run state and does not require event replay by the client

## Implementation Acceptance Criteria

- Orchestrator input and output shapes are stable and documented.
- The canonical streamed-turn request shape and SSE framing are stable and documented.
- Workflow types are explicit and finite for the current milestone.
- Status transitions are explicit and enforceable.
- Event names and chat meta projection types are stable enough for UI streaming and inspection.

## Verification

Current automated enforcement for this document lives in:

- The current implementation includes canonical shared contract definitions in `src/app/orchestration/contracts.py` and schema validation in `src/app/schemas/orchestration.py`.
- This implementation is intentionally limited to contract code and validation helpers; conversation/workflow service execution remains owned by later slices.
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_orchestrator_contract_lists_stable_workflow_status_and_event_values`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_orchestrator_doc_freezes_chat_stream_contract_and_active_workflow_semantics`
- [tests/test_agent_contracts.py](../../tests/test_agent_contracts.py) `::test_agent_registry_description_stays_stable_for_smoke_inspection`
- [tests/test_orchestration_contracts.py](../../tests/test_orchestration_contracts.py) `::test_orchestration_enums_stay_stable`
- [tests/test_orchestration_contracts.py](../../tests/test_orchestration_contracts.py) `::test_allowed_workflow_run_transitions_match_the_spec`
- [tests/test_orchestration_contracts.py](../../tests/test_orchestration_contracts.py) `::test_conversation_turn_response_enforces_inline_shape`

## Deferred Items

- resumable worker recovery across restarts
- branching workflows
- multi-agent conversational layer separate from orchestrator
- richer transport protocols beyond the accepted line-delimited SSE contract
