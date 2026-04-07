# Chat And Frontend Completion

## Purpose And Scope

- Define the Phase 3 slice that completes the usable product path on top of the provider-backed backend workflows.
- Scope this slice to chat-triggered workflow continuity, final assistant summaries, provider-aware progress reporting, and minimum frontend compatibility work.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/provider-backed-vertical-slice/03-account-search-provider-slice.md`.
- Depends on `docs/phase3/provider-backed-vertical-slice/04-account-research-provider-slice.md`.
- Depends on `docs/phase3/provider-backed-vertical-slice/05-contact-search-findymail-slice.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/06-frontend-chat-entry-and-ux-migration.md`.

## Decision Summary

- Chat remains the only user-facing trigger for account search, account research, and contact search.
- The Phase 3 frontend goal is compatibility completion, not a major chat redesign.
- The existing chat flow must be able to launch all three workflows end to end and surface progress, failures, and final summaries cleanly.

## Chat Summary Contract

- Final assistant summaries should always resolve into one of these workflow-visible outcome families:
  - `accounts_found`
  - `no_results`
  - `research_completed`
  - `contacts_found`
  - `partial_uncertainty`
  - `provider_failure`
- Each final summary should include:
  - result count or outcome
  - top accepted entities when present
  - the biggest remaining uncertainty or failure reason
- User-visible provider messaging should stay human-readable and avoid raw API detail except when needed to explain a failure clearly.

## Run-Event Taxonomy Defaults

- Standard event categories should include:
  - `workflow.started`
  - `tool.started`
  - `tool.completed`
  - `tool.failed`
  - `reasoning.validated`
  - `reasoning.failed_validation`
  - `candidate.accepted`
  - `candidate.rejected`
  - `provider.routing_decision`
  - `workflow.completed`
- Event payloads should carry provider-aware metadata and enough context to explain summary outcomes later in chat.
- The durable run-event projection model remains stable; the taxonomy above is an additive Phase 3 expansion rather than a replacement for the existing event foundation.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the current tenant-scoped chat routes, chat thread state, and run-event projection model.
- This slice may refine frontend-facing expectations for provider-aware progress messages and final assistant summaries.

## Data Flow / State Transitions

- User starts the workflow from chat with the required context selected.
- Required chat-start prerequisites should be explicit per workflow:
  - account search requires seller context and ICP context
  - account research requires a selected account and seller context, with ICP context optional
  - contact search requires a selected account and seller context, with ICP context optional and latest research context allowed
- Backend launches a provider-backed workflow run.
- Chat surfaces tool activity, provider-aware run progress, and final assistant summaries tied to the durable run.
- The user can continue from account search to research to contact search without switching to direct workflow controls.

## Failure Modes And Edge-Case Rules

- Frontend compatibility work must not introduce a second primary workflow-start path beside chat.
- Provider or reasoning failures must surface in the chat-visible failure path rather than disappearing behind background execution.
- Shared chat continuity must continue to rely on durable thread and run state rather than transient client-only assumptions.

## Validation, Ownership, And Permission Rules

- Backend remains the source of truth for workflow state, validation, and provider-error shaping.
- Frontend remains a rendering and context-selection layer for the chat-first product flow.
- Missing prerequisite handling should remain backend-validated and should surface human-readable guidance in chat rather than relying on frontend-only rules.

## Persistence Impact

- No new persistence model is introduced in this slice.
- This slice depends on the durability of existing thread, message, run, and run-event records.

## API / Events / Artifact Impact

- Public route families remain the current tenant-scoped chat and workflow surfaces.
- Chat-facing event projection should expose provider-aware progress and final workflow outcomes cleanly enough for the current frontend experience.

## Implementation Acceptance Criteria

- A user can trigger account search, account research, and contact search from chat in the intended product flow.
- Final summaries and failure states are visible in chat without requiring direct workflow pages to explain what happened.
- Frontend changes remain limited to compatibility work needed for the provider-backed vertical slice.
- Chat-visible event and summary behavior is explicit enough to verify end to end without inventing frontend-only state rules.

## Verification

- Add end-to-end or integration coverage for the full chat-first path across all three workflows.

## Deferred Items

- Major information-architecture redesign.
- New non-chat workflow entry models.
