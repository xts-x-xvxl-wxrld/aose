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
- seller/ICP list/detail backend support now exists
- workspace account/contact/workflow-run backend support now exists
- tenant-scoped chat streaming and thread rehydration
- admin/ops surfaces

## Main integration gaps

- active frontend does not yet consume the new seller/ICP list/detail APIs
- active frontend does not yet consume the new account/contact/workflow-run APIs
- active frontend still treats local storage as the main source of setup context
- no production Zitadel frontend auth flow
- no finished user-facing review workflow UI

## Backend contract now available for frontend work

The backend now exposes user-facing read surfaces beyond chat:

- seller profiles list/detail
- ICP profiles list/detail
- accounts list/detail
- contacts list/detail
- workflow runs list/detail

That means the frontend docs can now shift from "waiting on backend gaps" to "planning real feature integration against a stable resource model."

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
- the current active API client does not yet expose the new workspace/setup read methods
