# Rollout And Verification

## Purpose And Scope

- Define the implementation order, rollout expectations, and verification requirements for the chat-driven orchestration slice set.

## Dependencies On Earlier Docs

- Depends on all earlier chat-driven orchestrator phase slices.
- Depends on the owning implementation docs that will be revised as accepted contracts are upstreamed.

## Decision Summary

- Chat-driven orchestration should be implemented in vertical slices with explicit contract updates.
- The recommended rollout order for this phase is:
  - upstream foundational contract changes into the owning implementation docs
  - mount tenant-scoped chat routes and transport lifecycle
  - implement chat payload normalization and decision mapping
  - implement runtime executor wiring and workflow dispatch
  - implement chat event projection and reconnect or reload behavior
  - migrate frontend entrypoints so chat becomes the primary visible workflow surface
- Implementation docs remain the canonical baseline and must be revised as accepted phase decisions are adopted.
- Verification must distinguish doc scaffolding, doc-contract coverage, and runtime-enforced behavior.
- The chat-first path should not be declared canonical until both backend and frontend compatibility surfaces are reconciled and secondary or transitional paths are clearly identified.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the accepted route, orchestration, event, and runtime contracts from the earlier slices.
- Consumes the implementation-doc ownership model, verification tiers, and contract-freeze rules from `docs/implementation/00-implementation-orchestrator.md`.

## Data Flow / State Transitions

- Phase proposal is split into slices.
- Each accepted slice decision is upstreamed into its owning implementation document before or alongside code changes that depend on it.
- Backend code and tests are updated against the revised implementation docs for tenant-scoped chat routes, transport behavior, orchestration contracts, event projection support, and runtime wiring.
- Frontend code and tests are updated so tenant selection, chat submission, prompt injection, and shared chat state align with the revised backend contracts.
- Transitional compatibility surfaces remain only while they are explicitly documented and tested as secondary behavior.
- Once the chat-first path is stable, legacy or secondary entrypoints are removed or clearly demoted so the repository returns to one coherent canonical product flow.

## Failure Modes And Edge-Case Rules

- No slice should imply runtime behavior that is still stubbed.
- No accepted contract change should remain only in a phase doc after implementation begins.
- Rollout staging must avoid shipping two equally authoritative workflow entry models indefinitely.
- Foundational contract updates must not be implemented partially across docs; route, payload, event, and own ership changes need synchronized updates in the owning implementation docs.
- Frontend migration must not switch visible entrypoints to chat before the tenant-scoped backend chat path, durable thread lifecycle, and workflow dispatch path are actually available.
- Compatibility aliases such as `/conversations...` or legacy frontend direct workflow controls must not silently become permanent second systems.

## Validation, Ownership, And Permission Rules

- Contract ownership must remain explicit at each stage of rollout.
- Verification claims must accurately reflect whether enforcement is doc-level or runtime-level.
- The expected owning implementation docs to revise for this phase are:
  - `docs/implementation/03-orchestrator-and-run-contracts.md`
  - `docs/implementation/04-api-auth-and-request-context.md`
  - `docs/implementation/05-service-worker-and-tool-boundaries.md`
  - `docs/implementation/00-implementation-orchestrator.md` when dependency order, baseline wording, or verification guidance needs to reflect the accepted chat-first direction
- Child phase slices may refine or stage these changes, but the owning implementation docs must become the canonical resting place for accepted contracts.

## Persistence Impact

- Summarize any migration or compatibility implications caused by accepted chat-driven changes.
- No new hidden active-tenant persistence should be introduced during rollout.
- Durable thread, message, run, and run-event records remain the continuity mechanism across all rollout stages.
- Compatibility surfaces must continue to read or write the same canonical tenant-scoped conversation and workflow records rather than creating parallel persistence models.

## API / Events / Artifact Impact

- Track which routes, events, and artifacts are newly mounted, revised, or deprecated during rollout.
- Newly mounted or revised surfaces in this phase include:
  - tenant-scoped `/api/v1/tenants/{tenant_id}/chat/...` routes
  - streamed chat transport behavior
  - chat-facing projection of durable run and event state
- Compatibility or deprecation tracking should explicitly cover:
  - tenant-scoped `/conversations...` compatibility aliases if retained
  - legacy non-tenant-scoped frontend chat helpers
  - direct workflow-launch UI controls that are no longer primary product surfaces
- Canonical durable run events remain unchanged unless revised in the owning implementation doc, even when chat-facing projection terms are added for UX.

## Implementation Acceptance Criteria

- Each slice names its upstream doc changes, runtime tasks, and verification additions.
- The repository returns to one coherent canonical contract set after accepted changes are upstreamed.
- The owning implementation docs reflect the accepted tenant-scoped chat route family, streaming-first transport, canonical orchestration boundary, run-event projection model, and runtime wiring expectations.
- Backend runtime tests exist for tenant-scoped chat entry, streamed turn handling, normalization, dispatch, and recovery behavior.
- Frontend integration or end-to-end tests exist for tenant selection, chat-first workflow initiation, and migration away from peer visible workflow buttons.
- Compatibility paths that remain are explicitly documented as secondary and have an exit path or deferred-removal note.
- Minimum build decisions for chat-turn idempotency and rules-first orchestrator routing are explicit in the owning phase slice docs rather than left to implementation guesswork.

## Verification

- Add a checklist of required doc updates, runtime tests, and integration coverage before declaring the chat-driven path canonical.
- Implementation-doc upstreaming status:
  - `docs/implementation/04-api-auth-and-request-context.md` now carries tenant-scoped chat route ownership, route semantics, compatibility alias policy, and `X-Request-ID` requirements
  - `docs/implementation/03-orchestrator-and-run-contracts.md` now carries the streaming-first transport contract, canonical chat-turn request shape, `active_workflow` semantics, and accepted SSE framing
  - `docs/implementation/05-service-worker-and-tool-boundaries.md` now carries the accepted runtime wiring, chat-turn idempotency ownership, and stream-projection ownership
  - `docs/implementation/00-implementation-orchestrator.md` may still be revised later if baseline wording, dependency order, or verification guidance needs to reflect the accepted chat-first milestone direction
- Required backend runtime coverage before canonization:
  - tenant entry and tenant-scoped authorization checks
  - implicit thread creation and follow-up turn handling over streaming chat
  - canonical input normalization and `missing_inputs` behavior
  - workflow dispatch, missing-handler failure, and reconnect or reload recovery
  - event projection from durable run state into chat-facing meta updates
- Required idempotency coverage before canonization:
  - retrying the same first turn after thread creation does not create a duplicate thread
  - retrying the same workflow-start turn does not create a duplicate run
  - retrying with the same `request_id` but a different payload returns `request_id_conflict`
  - retry after stream interruption resumes durable state rather than creating duplicate records
- Required orchestrator-policy coverage before canonization:
  - account-search missing-ICP requests clarify instead of starting a run
  - account-research missing-account requests clarify instead of starting a run
  - follow-up clarification answers resume the intended active workflow path
  - explicit workflow switch requests override stale `active_workflow`
  - status questions on queued or running threads return inline status and do not queue another run
- Required frontend or end-to-end coverage before canonization:
  - tenant selection before chat entry
  - chat submission through the tenant-scoped streaming path
  - shared chat continuity across full chat and sidebar chat
  - workflow initiation from chat for account search, account research, and contact search
  - clarification-follow-up flow from missing context to workflow start
  - removal, hiding, or clear demotion of direct workflow-launch controls on intended product surfaces
- Required rollout readiness checks before canonization:
  - no contract-critical behavior remains only in `docs/phase2/...`
  - no primary product flow depends on legacy non-tenant-scoped chat endpoints
  - no user-facing workflow path bypasses chat unintentionally for the targeted workflows
  - compatibility surfaces that remain are explicitly secondary and documented as such

## Deferred Items

- Follow-on work that depends on the chat-first foundation, such as a dedicated chat agent or broader activity-feed designs.
- Final retirement timing for compatibility aliases and transitional frontend controls once the chat-first path is fully enforced.
