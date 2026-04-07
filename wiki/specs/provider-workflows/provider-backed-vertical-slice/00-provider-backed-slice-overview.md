# Provider-Backed Slice Overview

## Purpose And Scope

- This document is the entrypoint for the current Phase 3 provider-backed vertical-slice set.
- It splits the current Phase 3 reference direction into narrower implementation slices that can be built and verified incrementally.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/00-provider-backed-vertical-slice.md`.
- Current implemented behavior is owned by code.
- Older `docs/implementation/...` files may still provide historical context, but they are not the source of truth for current or planned Phase 3 behavior.

## Decision Summary

- Phase 3 is implemented as a provider-backed vertical slice, not as a free-form agent-runtime rewrite.
- The current chat, thread, workflow-run, and run-event plumbing remains the foundation.
- Firecrawl is the first provider for account discovery and public research gathering.
- Google Local Places is an optional local-business discovery source for account search when the workflow targets place-centric companies.
- Findymail is the required primary provider for contact search completion in this phase.
- Tomba is an allowed fallback provider for contact search, using only the provider features that fit the precision-first workflow.
- Findymail is the default primary provider for Phase 3 contact search.
- For GDPR-sensitive routing defaults, Findymail remains the preferred primary path because it documents EU-only processing.
- Tomba is the fallback provider because it is an American company even though it documents EU-hosted processing.
- OpenAI-backed structured reasoning is the default normalization and synthesis engine.
- The tool layer should speak one internal system contract, while provider adapters translate vendor-specific requests, responses, and failures at the adapter boundary.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the existing chat, workflow-run, run-event, and workflow result contracts as currently represented in code.
- Child slices may introduce provider-facing request and response shapes, runtime builder interfaces, and prompt-owned structured output schemas.

## Data Flow / State Transitions

- Runtime wiring resolves provider-backed tool instances.
- Chat-triggered workflows execute against real tools instead of null toolsets.
- Account search produces accepted accounts.
- Account research produces evidence, snapshot, and optional artifact outputs.
- Contact search produces canonical contacts and evidence through the provider-backed path, with Findymail as the default provider and Tomba as a scoped fallback.

## Failure Modes And Edge-Case Rules

- No Phase 3 slice should weaken the current tenant, persistence, or workflow-run guarantees.
- Provider failures must surface as explicit workflow failures or uncertainty-preserving partial results, not as silent fallback behavior.
- The durable run/event model remains stable in Phase 3, but event categories may expand additively where provider routing, reasoning validation, and candidate decisions need to be explained.
- If a slice changes a foundational planned contract that is not yet implemented, the latest unimplemented Phase 3 doc set should be updated in the same change.
- If a slice changes an implemented runtime contract, code remains the source of truth and the active Phase 3 docs should be brought back into alignment.

## Validation, Ownership, And Permission Rules

- Services and workflows continue to own validation, persistence decisions, and workflow state transitions.
- Tools and provider adapters remain narrow execution surfaces and do not write canonical records directly.
- Workflows should consume normalized internal tool contracts rather than raw provider payloads.
- The current rules-based orchestrator remains in place for this phase unless a later accepted slice explicitly revises that decision.

## Persistence Impact

- No new persistence contract is defined in this overview.
- Child slices must name any new config surfaces, structured result schemas, or stored provider metadata they require.

## API / Events / Artifact Impact

- Existing tenant-scoped chat and workflow interfaces remain stable unless a later slice explicitly revises them.
- Child slices define provider configuration, runtime wiring, prompt-owned schemas, and any workflow-specific result enrichments.

## Implementation Acceptance Criteria

- All Phase 3 child slices exist with narrow scope boundaries and explicit implementation intent.
- The slice order is clear enough that Phase 3 can be built incrementally without re-deciding the provider strategy.

## Verification

- Doc-only scaffold in this change.
- Runtime and doc-contract verification should be attached in the owning child slices as implementation begins.

## Deferred Items

- Autonomous multi-agent runtime orchestration.
- Broad multi-provider routing beyond the explicit Findymail-primary and Tomba-fallback contact-search policy defined for this phase.
- Broader frontend redesign beyond compatibility fixes needed for the Phase 3 vertical slice.
