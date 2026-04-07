# Orchestrator Chat Contracts

## Purpose And Scope

- Define how minimal chat payloads are normalized into canonical orchestration contracts and how canonical orchestrator decisions are exposed through chat UX.

## Dependencies On Earlier Docs

- Depends on `docs/phase2/chat-driven-orchestrator/00-chat-driven-orchestrator-overview.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/01-chat-api-and-tenant-entry.md`.
- Depends on `docs/implementation/03-orchestrator-and-run-contracts.md`.

## Decision Summary

- The chat UI sends a minimal payload.
- The chat-facing request envelope for a streamed user turn includes:
  - `user_message`
  - optional `thread_id`
  - optional `seller_profile_id`
  - optional `icp_profile_id`
  - optional `selected_account_id`
  - optional `selected_contact_id`
  - optional `active_workflow`
- A backend conversation or chat service resolves durable context and builds canonical `OrchestratorInput`.
- `active_workflow` is persisted thread context plus a current-turn normalization hint.
- The orchestrator remains the user-facing responder in v1.
- Missing context remains represented by canonical `missing_inputs` codes rather than a new decision family.
- The chat layer may present simplified reply groupings such as inline reply, clarification needed, workflow started, or review required, but the backend boundary remains canonical `OrchestratorDecision`.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes canonical `OrchestratorInput`, `OrchestratorDecision`, decision types, and `missing_inputs` codes.
- Consumes canonical conversation create/message fields and `ConversationTurnResponse` semantics from the implementation docs.
- Introduces a chat-facing streamed-turn envelope that is a thin transport wrapper around the canonical conversation and orchestration contracts rather than a replacement for them.

## Decision Policy

### Precedence Ladder

- Validated explicit current-turn selectors win over persisted thread context for the current turn.
- Persisted thread context wins over free-text implication when the two are in tension.
- `active_workflow` is a hint for follow-up interpretation, not permission and not an override of explicit validated selectors.
- The orchestrator must never silently invent seller, ICP, account, or contact identifiers.

### Workflow Prerequisites

- `account_search` requires `seller_profile_id` and `icp_profile_id`.
- `account_research` requires `seller_profile_id` and `selected_account_id`; `icp_profile_id` is optional.
- `contact_search` requires `seller_profile_id` and `selected_account_id`; `icp_profile_id` is optional.
- `contact_search` may use the latest research snapshot when present, but absence of a snapshot does not block workflow start in this phase.

### Routing Behavior

- Requests to find, discover, or search for target companies route to `account_search`.
- Requests to research, analyze, or profile a specific selected account route to `account_research`.
- Requests to find people, contacts, buyers, champions, or stakeholders for a selected account route to `contact_search`.
- Status questions, clarifications, setup guidance, unsupported requests, and ambiguous requests route to `reply_inline`.
- Missing required context never causes speculative workflow start; it returns `reply_inline` plus stable `missing_inputs`.

### Follow-Up Turn Behavior

- If the thread has unresolved missing context for an active workflow and the new turn plausibly supplies that missing context, continue in that workflow context rather than treating it as a fresh unrelated task.
- If the user explicitly asks to switch tasks, the explicit current-turn request overrides the prior `active_workflow`.
- If a thread already has a queued or running run and the new turn is a status or progress question, respond inline from durable run state and do not create a duplicate run.
- If a thread already has a queued or running run and the new turn explicitly asks to start a different workflow, start the new workflow only when its prerequisites are satisfied and the runtime allows it.
- Phase 2 defaults to one active run per thread unless a later accepted doc revision explicitly relaxes that rule.
- Under the one-active-run-per-thread default, an explicit request to start a different workflow while a run is already queued or running yields an inline explanation of the active run state rather than a duplicate or concurrent run.

## Decision Table Examples

- "Find companies matching my ICP" with seller plus ICP present => `start_workflow_run` for `account_search`.
- "Find companies matching my ICP" with seller present but ICP missing => `reply_inline` plus `icp_profile_required`.
- "Research this account" with selected account plus seller present => `start_workflow_run` for `account_research`.
- "Research this account" with seller present but selected account missing => `reply_inline` plus `selected_account_required`.
- "Find contacts for this account" with seller plus selected account present => `start_workflow_run` for `contact_search`.
- "Find contacts for this account" with selected account present but seller missing => `reply_inline` plus `seller_profile_required`.
- Follow-up turn that answers the prior clarification for the active workflow => continue that active workflow path if the missing context is now satisfied.
- "What's happening with this run?" while the thread has a queued or running run => `reply_inline` using durable run status and no new run.
- Explicit switch from an account-search thread to "research this account" with selected account present => current-turn explicit request takes precedence and starts `account_research`.
- Ambiguous prompts such as "go ahead" without enough durable or explicit context => `reply_inline` asking for clarification and no workflow start.

## Data Flow / State Transitions

- Chat payload arrives with `user_message`, optional `thread_id`, and optional explicit selection overrides or context selections.
- The backend derives `tenant_id` from the tenant-scoped route and `user_id` from authenticated request context rather than from the client payload.
- If `thread_id` is present, the backend loads the tenant-scoped thread, its latest summary state, and any previously established explicit context carried by that thread.
- The backend loads latest workflow state relevant to the thread, including `latest_run_status` when present.
- Explicit client-supplied selections are validated and, when valid, take precedence over older persisted thread context for the current turn.
- A validated explicit `active_workflow` value takes precedence over any older persisted thread workflow context for the current turn.
- The backend normalizes the combined request and durable context into canonical `OrchestratorInput` and calls the orchestrator.
- The chat layer translates the canonical decision into persisted thread/message effects plus streamed user-facing output.
- Handoff decisions such as `handoff_to_account_search`, `handoff_to_account_research`, and `handoff_to_contact_search` are normalized by backend services into workflow creation and dispatch rather than being exposed as ad hoc frontend-only control paths.
- If the thread already has a queued or running run, the backend consults durable run state before deciding whether the new turn is status-oriented, clarification-oriented, or an explicit workflow switch request.

## Failure Modes And Edge-Case Rules

- Ambiguous or missing required context must produce clarifying chat behavior without fabricating defaults.
- Raw UI context bags must not be passed directly into the orchestrator.
- Backend normalization failures must be explicit and tenant-safe.
- Invalid or cross-tenant `seller_profile_id`, `icp_profile_id`, `selected_account_id`, or `selected_contact_id` values are rejected during normalization rather than silently dropped into orchestration.
- A follow-up turn targeting a nonexistent or cross-tenant `thread_id` is rejected before orchestration runs.
- The backend must not infer seller, ICP, account, or contact context from unrelated client-local UI state unless that context is explicitly supplied or already durably associated with the thread.
- `missing_inputs` must remain stable machine-readable codes even when the streamed assistant wording changes.
- A running or queued workflow must not cause duplicate run creation merely because the user asks for progress or status in chat.
- Under the phase-default one-active-run-per-thread rule, a new workflow request during an active run must not silently create concurrent work.

## Validation, Ownership, And Permission Rules

- Backend services own normalization and validation before orchestration.
- Orchestrator input must remain typed and canonical.
- UI convenience state is advisory unless validated and normalized server-side.
- `tenant_id` and `user_id` are server-owned fields and are never accepted from the chat payload.
- `active_workflow` is advisory workflow context, not an authorization mechanism and not a hard execution constraint by itself.
- Canonical `OrchestratorDecision` ownership remains with the implementation docs; this slice may define only how chat transport presents those decisions.
- "Clarification needed" in chat UX is derived from a canonical decision plus `missing_inputs`, not a new backend decision type.
- Any normalization helper used by the chat route should remain in a backend conversation or chat service boundary rather than inside the orchestrator itself.
- Routing policy is rules-first in this phase: prompts may shape reply wording, but workflow selection, context precedence, and missing-input behavior must remain deterministic.

## Persistence Impact

- Persist the user turn before or alongside orchestration so the thread remains durable even when a later workflow path is chosen.
- Persist assistant replies, workflow-linked assistant messages, or clarification messages according to canonical conversation rules rather than ephemeral stream-only output.
- Persist any thread summary or latest durable context fields needed to rebuild `conversation_summary` and follow-up-turn context without replaying the full message history into the orchestrator.
- Once a turn is durably accepted, the validated `active_workflow` becomes the thread's latest persisted workflow context.
- Do not persist a separate hidden "active context" record that can override explicit tenant-scoped thread and selection validation rules.

## API / Events / Artifact Impact

- Define the streamed chat-turn request shape as the minimal payload listed above.
- Define the normalization boundary between the chat route and canonical `OrchestratorInput`.
- Define the mapping from canonical `OrchestratorDecision` to chat-facing reply groupings:
  - `reply_inline` -> inline reply or clarification-needed chat response
  - handoff or workflow-start decisions -> workflow-started chat response with workflow linkage
  - `request_user_review` -> review-required chat response with durable review linkage
- Keep `missing_inputs` and workflow identifiers in the canonical response shape even when the frontend renders simplified messaging.
- Keep decision examples and precedence rules explicit enough that backend routing does not depend on prompt interpretation alone.

## Implementation Acceptance Criteria

- The chat route can accept a minimal payload and always call the orchestrator with canonical `OrchestratorInput`.
- The streamed chat-turn request shape is explicit and limited to `user_message`, optional `thread_id`, and optional explicit context selections.
- Server-owned fields such as `tenant_id`, `user_id`, `latest_run_status`, and `conversation_summary` are always resolved server-side.
- Explicit client selections are validated against tenant-scoped durable records before being included in canonical orchestration input.
- The orchestrator decision model remains typed and unchanged at the backend boundary unless revised in the owning implementation doc.
- Backend services, not the frontend, normalize handoff and workflow-start decisions into workflow creation behavior.
- Chat-facing simplified statuses do not replace or weaken the canonical `missing_inputs` and decision semantics.
- Workflow prerequisites, routing targets, and context-precedence rules are explicit enough to implement without ad hoc policy decisions.
- Phase 2 defaults to one active run per thread and requires inline status handling instead of duplicate-run creation for status questions.

## Verification

- Add runtime tests for input normalization and `missing_inputs` behavior.
- Add doc-contract checks that the chat layer does not redefine canonical decision types silently.
- Add runtime tests covering first-turn normalization, follow-up turn normalization with `thread_id`, and explicit context override behavior.
- Add runtime tests covering rejection of cross-tenant or invalid selection identifiers before orchestration.
- Add runtime tests confirming that clarification responses still expose canonical `missing_inputs` codes.
- Add doc-contract checks for the streamed chat-turn request shape and the decision-to-chat grouping rules.
- Add orchestrator-policy tests covering account-search missing-ICP clarification, account-research missing-account clarification, follow-up clarification completion, explicit workflow switch precedence, and inline status replies during active runs.

## Deferred Items

- Dedicated chat agent that replaces or sits in front of the orchestrator.
- Passing full message history into the orchestrator rather than summary-oriented durable context.
