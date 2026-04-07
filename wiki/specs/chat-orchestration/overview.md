# Chat-Driven Orchestrator Overview

## Purpose And Scope

- This document is the entrypoint for the chat-driven orchestration phase slice set.
- It scopes the chat-first product direction, the slice boundaries, and the order in which the downstream slice docs should be read and implemented.

## Dependencies On Earlier Docs

- Depends on `docs/implementation/00-implementation-orchestrator.md`.
- Depends on `docs/implementation/03-orchestrator-and-run-contracts.md`.
- Depends on `docs/implementation/04-api-auth-and-request-context.md`.
- Depends on `docs/implementation/05-service-worker-and-tool-boundaries.md`.

## Decision Summary

- Chat becomes the primary user-facing workflow entrypoint for account search, account research, and contact search.
- Tenant selection remains explicit and happens before chat is entered.
- Streaming becomes the primary chat transport.
- Canonical backend contracts remain typed and durable even when the frontend presents simplified chat UX.
- Accepted phase refinements must be reconciled back into the owning implementation docs.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the canonical `OrchestratorInput`, `OrchestratorDecision`, `WorkflowRun`, and `RunEvent` contracts from the implementation docs.
- Child slices may introduce chat-facing request and response shapes, but should not bypass the canonical orchestration and workflow contracts.

## Data Flow / State Transitions

- Dashboard selects tenant.
- Chat route accepts a tenant-scoped user turn.
- Backend normalizes chat payload into canonical orchestration input.
- Orchestrator replies inline or starts a workflow run.
- Streaming projects backend state into chat-friendly updates.

## Failure Modes And Edge-Case Rules

- If the user has multiple tenants and none is selected, chat entry is blocked.
- If a slice changes a foundational contract, the owning implementation doc must be updated.
- If runtime support is stubbed, the slice must say so explicitly.

## Validation, Ownership, And Permission Rules

- `tenant_id` remains the isolation boundary for all chat, thread, run, and artifact behavior.
- The backend, not the frontend, owns normalization and validation of orchestration input.
- Later child slices may refine product behavior, but foundational contract ownership still belongs in the implementation docs until revised there.

## Persistence Impact

- No new persistence contract is defined here.
- Child slices must name any new tables, fields, or durable records they require.

## API / Events / Artifact Impact

- Child slices define the tenant-scoped chat route surface, streaming transport behavior, event projection rules, and frontend migration effects.

## Implementation Acceptance Criteria

- All downstream slice docs exist and have explicit scope boundaries.
- Each child slice is narrow enough to implement without inventing new cross-cutting behavior in code.

## Verification

- Doc-only scaffold in this change.
- Runtime and doc-contract verification must be attached in the owning child slices.

## Deferred Items

- Dedicated chat agent beyond the orchestrator.
- Queue-backed worker replacement for the in-process executor.
- Any non-chat workflow entrypoints intended only for transitional rollout.
