# Rollout And Verification

## Purpose And Scope

- Define the implementation order and verification expectations for the Phase 3 provider-backed slice set.
- Scope this slice to build order, active-doc alignment expectations, and completion checks for declaring Phase 3 done.

## Dependencies On Earlier Docs

- Depends on all earlier Phase 3 provider-backed slices.
- Current implemented behavior is owned by code.
- The latest unimplemented Phase 3 doc set is the planning source of truth for work that has not landed yet.

## Decision Summary

- Phase 3 should be implemented in narrow slices that preserve the current chat/run foundation while swapping in real provider-backed behavior.
- The recommended build order for this phase is:
  - provider config and runtime wiring
  - OpenAI structured reasoning layer
  - account search provider slice
  - account research provider slice
  - contact search Findymail slice
  - chat and frontend completion
- Accepted foundational contract changes should be reflected in the active Phase 3 slice docs while the work remains unimplemented.
- Once behavior is implemented, code becomes the source of truth.

## Environment And Credential Defaults

- In local development:
  - OpenAI should be the only provider assumed required for reasoning-path work
  - Firecrawl, Google Local Places, Findymail, and Tomba may be optional depending on the slice under active development
- In staging and end-to-end verification:
  - all providers required by the relevant Phase 3 workflows should be configured
- Missing credentials must fail clearly and predictably instead of silently downgrading into null behavior.

## Test Fixture Strategy Defaults

- Provider contract and normalization tests should use checked-in fixtures by default.
- Live smoke tests should run only behind explicit opt-in environment flags.
- Deterministic fixture coverage should include:
  - no-results cases
  - malformed provider payloads
  - quota or credit failures
  - sparse but valid results

## Slice-Level Done Criteria

- A slice is done only when:
  - the runtime path is wired
  - at least one integration path passes
  - contract or fixture tests pass
  - provider-aware events are emitted
  - owning docs are updated if contracts changed

## Active-Doc Alignment Defaults

- While a contract remains unimplemented, keep the active Phase 3 slice docs aligned around:
  - provider settings and runtime factory contracts
  - workflow result schemas
  - merge and persistence rules
  - event taxonomy
  - chat summary expectations

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the provider, workflow, and chat-facing decisions accepted in the earlier Phase 3 slices.
- Uses code as the source of truth for implemented behavior and this Phase 3 doc set as the source of truth for current unimplemented planning.

## Data Flow / State Transitions

- Phase 3 reference direction is split into slices.
- Each slice is implemented with runtime tests and any necessary updates to the active Phase 3 docs while the work is still in flight.
- The repository stays coherent by keeping code aligned with implemented behavior and the latest unimplemented Phase 3 docs aligned with planned behavior.
- The vertical slice is complete only when the chat-first path works end to end with real provider-backed workflows.

## Failure Modes And Edge-Case Rules

- No slice should leave a hidden dependency on null toolsets in the main Phase 3 path.
- No accepted provider or workflow contract should remain specified only in Phase 3 docs after implementation depends on it.
- Phase 3 should not be declared complete if Findymail-backed contact search is still stubbed.

## Validation, Ownership, And Permission Rules

- Foundational ownership for implemented behavior remains in code.
- Planning ownership for unimplemented Phase 3 behavior remains in the latest active Phase 3 doc set.
- Verification claims must continue to distinguish doc scaffolding, doc-contract coverage, and runtime-enforced behavior.

## Persistence Impact

- Rollout must continue to use the canonical tenant-scoped persistence model for threads, runs, evidence, snapshots, contacts, and artifacts.
- No compatibility step should create a parallel persistence path for provider-backed results.

## API / Events / Artifact Impact

- Track any active Phase 3 doc updates required for provider-facing interfaces, prompt-owned schema behavior, or run-event metadata changes while the work is still unimplemented.
- Public chat and workflow APIs should remain stable while the underlying workflow execution becomes provider-backed.

## Implementation Acceptance Criteria

- Firecrawl-backed account search works end to end through chat.
- Firecrawl-backed account research works end to end through chat.
- Findymail-backed contact search works end to end through chat in an environment with provided credentials and reference materials.
- OpenAI-backed structured reasoning is active in all three workflows with explicit fallback behavior.
- The Phase 3 path no longer depends on skeleton prompts and null toolsets as its primary runtime behavior.

## Verification

- Required runtime coverage before Phase 3 is considered complete:
  - provider configuration and runtime wiring behavior
  - schema validation and fallback behavior in structured reasoning
  - account-search provider-backed persistence behavior
  - account-research snapshot and artifact behavior
  - contact-search provider-backed merge and missing-data behavior
  - chat-first end-to-end flow across all three workflows
- Required documentation completion before Phase 3 is considered complete:
  - the latest unimplemented Phase 3 docs stayed aligned while the phase was being built
  - code and active Phase 3 docs are no longer in conflict for implemented behavior

## Deferred Items

- Broader multi-provider routing and fallback strategy beyond the explicit Findymail-primary and Tomba-fallback Phase 3 policy.
- Autonomous agent-runtime redesign after the provider-backed vertical slice is working.
