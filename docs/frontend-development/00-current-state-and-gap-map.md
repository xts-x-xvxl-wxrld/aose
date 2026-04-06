# Current State And Gap Map

## Current top-level architecture

- Backend app: [backend/src/app/main.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\main.py)
- Backend route registry: [backend/src/app/api/v1/router.py](c:\Users\ravil\Desktop\Agentic-OSE\backend\src\app\api\v1\router.py)
- Active frontend API client: [frontend/src/lib/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\api.js)
- Active chat streaming client: [frontend/src/lib/sse.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\sse.js)
- Active workspace shell: [frontend/src/pages/WorkspacePage.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\pages\WorkspacePage.jsx)
- Active admin surface: [frontend/src/pages/AdminPage.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\pages\AdminPage.jsx)

## What is already working

- fake-auth bootstrap through the current shell
- tenant selection and tenant creation
- seller/ICP creation and update flows
- tenant-scoped chat streaming and thread rehydration
- admin/ops surfaces

## Main integration gaps

- no durable seller profile list/detail rehydration
- no durable ICP profile list/detail rehydration
- no account list/detail browse flow in active frontend
- no contact list/detail browse flow in active frontend
- no production Zitadel frontend auth flow
- no finished user-facing review workflow UI

## Legacy frontend modules that should not be treated as the foundation

- [frontend/src/api.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\api.js)
- [frontend/src/workspace/LeftSidebar.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\LeftSidebar.jsx)
- [frontend/src/workspace/views/ObjectTable.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\views\ObjectTable.jsx)
- [frontend/src/workspace/views/RecordDetail.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\views\RecordDetail.jsx)
- [frontend/src/workspace/views/SellerOverview.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\views\SellerOverview.jsx)
- [frontend/src/workspace/views/SellersTable.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\views\SellersTable.jsx)
- [frontend/src/workspace/actions/dialogs/AddSellerDialog.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\actions\dialogs\AddSellerDialog.jsx)
- [frontend/src/workspace/actions/dialogs/AddICPDialog.jsx](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\actions\dialogs\AddICPDialog.jsx)
- [frontend/src/lib/ws.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\lib\ws.js)
- [frontend/src/workspace/hooks/useTaskNotifications.js](c:\Users\ravil\Desktop\Agentic-OSE\frontend\src\workspace\hooks\useTaskNotifications.js)

## Primary frontend risk areas

- mixed API generations
- fake-auth assumptions in active routes and stores
- local storage used as a source of truth for server entities
- large page-level components holding too much logic
- stale websocket assumptions coexisting with the active SSE model
