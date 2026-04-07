# Frontend Chat Entry And UX Migration

## Purpose And Scope

- Define the frontend transition to a chat-first workflow initiation model while preserving necessary setup forms in v1.

## Dependencies On Earlier Docs

- Depends on `docs/phase2/chat-driven-orchestrator/00-chat-driven-orchestrator-overview.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/01-chat-api-and-tenant-entry.md`.
- Depends on `docs/phase2/chat-driven-orchestrator/02-chat-transport-and-thread-lifecycle.md`.

## Decision Summary

- Chat becomes the primary visible workflow entrypoint.
- The primary visible frontend entry path is:
  - tenant selection in the dashboard
  - entry into the chat workspace
  - workflow initiation through chat input or chat-injected prompt actions
- Seller and ICP setup remain form-based in v1.
- Existing direct workflow-launch controls for account search, account research, account crawl, and contact search are demoted, hidden, or treated as temporary compatibility surfaces rather than peer product entrypoints.
- Existing context-aware action buttons may remain only when they inject prompts into chat rather than directly calling workflow-start APIs.
- The existing chat workspace and sidebar chat surfaces continue to share one underlying chat session model during the migration.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes tenant selection, thread lifecycle, and chat event projection behavior from earlier slices.
- Consumes the streamed chat-turn request envelope and tenant-scoped chat routes from earlier slices.
- Consumes chat-facing projected workflow meta updates for rendering pipeline and progress UI.
- Introduces frontend-only view-model groupings for entry prompts, setup nudges, and chat status presentation where needed.

## Data Flow / State Transitions

- User discovers or selects tenant from the dashboard before entering the chat workspace.
- If seller or ICP setup is incomplete, the user is guided to the existing form-based setup surfaces before or alongside chat usage.
- Once the required setup exists, the user initiates account search, account research, or contact search through chat input or context-aware prompt injection into chat.
- The chat surface submits the tenant-scoped streamed turn, renders assistant text plus workflow meta updates, and remains the visible progress surface for workflow initiation.
- Full chat and compact sidebar chat continue to share the same underlying session or thread state rather than diverging into separate user-visible conversations.
- Page-level account and contact views may still expose object inspection and setup context, but they should route workflow initiation intent into chat rather than directly executing workflow APIs.

## Failure Modes And Edge-Case Rules

- Transitional controls must not present conflicting entrypoints without clear product intent.
- UX must remain usable when streaming reconnect or fallback behavior occurs.
- Setup prerequisites must remain visible when chat cannot proceed without them.
- Direct workflow-start controls must not remain visible beside equivalent chat-first controls indefinitely, or the product will have two competing control surfaces.
- Prompt-injection actions must not imply that the frontend has already selected unauthorized seller, ICP, account, or contact context unless that context is actually present and valid in the UI state.
- If chat is temporarily unavailable, the UI may expose compatibility or fallback affordances, but those must be clearly secondary rather than presented as the main workflow path.
- The shared chat session must survive panel transitions between full chat, sidebar chat, and object-viewer flows without losing visible user context.

## Validation, Ownership, And Permission Rules

- Frontend convenience behavior must stay within explicit backend contracts.
- Chat UX must not imply silent tenant, seller, ICP, account, or contact selection.
- Frontend prompt actions may package current explicit UI context into chat payload fields, but they must not bypass backend normalization or authorization.
- Seller and ICP setup forms remain the authoritative source of those records in v1 even when chat references them conversationally.
- Frontend routing and state management should treat tenant-scoped chat threads as durable backend state, not as purely local ephemeral conversation state.

## Persistence Impact

- Frontend-only view state such as whether the chat is shown in full mode or sidebar mode remains local UI state.
- Durable chat continuity should come from backend thread, message, run, and run-event records rather than from frontend-only stores.
- Client-local convenience state may still include the last selected tenant or active workspace pane, but it must not become a hidden server-side active-context contract.
- The shared frontend chat store may cache messages and projected activity for responsiveness, but it is a client cache over durable backend records rather than the canonical source of truth.

## API / Events / Artifact Impact

- Frontend chat submission should migrate from legacy non-tenant-scoped `/chat/...` helpers toward the tenant-scoped `POST /api/v1/tenants/{tenant_id}/chat/stream` transport and supporting tenant-scoped thread routes.
- Frontend event refresh behavior should treat any `GET /chat/events` style feed as a derived convenience surface rather than the canonical execution history.
- Existing direct workflow API helpers used by pages such as account discovery, crawl, or contact search may remain internally during migration, but user-facing workflow initiation should move behind chat-oriented flows.
- Context-aware action bars should prefer prompt injection into chat over direct workflow execution so the chat remains the visible control surface.

## Implementation Acceptance Criteria

- Users can initiate account search, account research, and contact search from chat without relying on peer visible controls.
- Seller and ICP setup remain accessible and coherent in the same product flow.
- The frontend has an explicit tenant-selection step before entering tenant-scoped chat when multiple tenants exist.
- Shared chat state works consistently across the full chat window and compact sidebar surface.
- Existing action buttons either open setup dialogs or inject prompts into chat; they do not remain as peer direct workflow launchers for the same user goals.
- Legacy direct workflow buttons on pages such as account discovery are either removed, hidden, or clearly marked as transitional compatibility behavior.
- The frontend no longer depends on non-tenant-scoped chat endpoints as the canonical workflow initiation path.

## Verification

- Add frontend integration or end-to-end tests for tenant entry, chat initiation, and migration away from direct workflow controls.
- Add frontend tests covering tenant selection before chat entry and single-tenant auto-entry behavior.
- Add frontend tests covering prompt-injection actions that open or drive chat rather than calling direct workflow-start APIs.
- Add frontend tests covering shared chat-session continuity between full chat and sidebar chat.
- Add end-to-end tests covering workflow initiation from chat for account search, account research, and contact search after required setup exists.
- Add migration tests or assertions ensuring legacy direct workflow controls are absent, hidden, or explicitly transitional in the intended surfaces.

## Deferred Items

- Final removal timing for temporary compatibility controls during rollout.
- Broader redesign of workspace information architecture beyond the minimum chat-first migration needed for this phase.
