# Frontend Rebuild And Cleanup Plan

## Current assessment

The existing frontend contains useful working pieces, but it also contains redundant API layers, dead code paths, and logic that no longer matches the backend contract.

The goal should not be to keep patching the current app indefinitely. The goal should be a controlled rebuild around the working chat-first surface and a stable API layer.

## Pieces to keep as the starting foundation

- [frontend/src/lib/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\api.js)
- [frontend/src/lib/sse.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\sse.js)
- [frontend/src/pages/WorkspacePage.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\pages\WorkspacePage.jsx)
- [frontend/src/pages/AdminPage.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\pages\AdminPage.jsx)
- [frontend/src/workspace/hooks/useChat.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\hooks\useChat.js)

## Pieces to treat as unreliable or legacy

- [frontend/src/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\api.js)
- old seller/account/contact object-browser modules under `frontend/src/workspace/views/`
- websocket task notification path in [frontend/src/lib/ws.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\ws.js)
- fake-auth login assumptions in the current login/store flow

## Recommended rebuild direction

### 1. Freeze the active API layer

All active requests should flow through:

- [frontend/src/lib/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\api.js)
- [frontend/src/lib/sse.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\sse.js)

### 2. Remove or archive dead frontend modules

The legacy modules should be removed from the active build path so new work does not accidentally target deleted APIs.

### 3. Reorganize frontend by feature

Recommended shape:

- `features/auth`
- `features/tenants`
- `features/chat`
- `features/entities`
- `features/review`
- `features/admin`

### 4. Narrow what Zustand owns

Good Zustand responsibilities:

- auth session shell state
- active tenant id
- selected entity ids
- current thread id
- local UI toggles

Bad Zustand responsibilities:

- authoritative copies of server entities
- long-lived cached setup objects as the only rehydration source

### 5. Introduce a proper server-state layer

A query/cache layer should manage:

- sellers
- ICPs
- accounts
- contacts
- artifacts
- evidence
- review state

This is a cleaner fit than hand-written fetch logic inside many components.

## Implementation order

1. stabilize API contracts
2. delete/archive dead code paths
3. introduce feature-based structure
4. migrate server-state reads into query hooks
5. rebuild entity browsing around the new contract
