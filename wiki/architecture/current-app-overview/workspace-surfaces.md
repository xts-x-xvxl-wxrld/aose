---
title: Current App Overview - Workspace Surfaces
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - frontend/src/app/AppRouter.jsx
  - frontend/src/pages/WorkspacePage.jsx
  - frontend/src/features/entities/pages/DataBrowserPage.jsx
  - frontend/src/features/review/pages/ReviewPage.jsx
  - frontend/src/pages/AdminPage.jsx
  - frontend/src/stores/tenantStore.js
  - frontend/src/features/entities/hooks/useWorkspaceData.js
  - frontend/src/workspace/RightSidebar.jsx
---

# Current App Overview - Workspace Surfaces

## Summary

The frontend is organized around a small number of tenant-scoped surfaces that all share the same underlying tenant context and persisted backend state.

The important routes are:

- `/login`
- `/auth/callback`
- `/workspace`
- `/workspace/data`
- `/workspace/review/:runId`
- `/admin`

See also [[Current App Overview - Auth and Tenancy]] and [[Current App Overview - Conversation and Runtime]].

## Login and Tenant Entry

The login page is a branded Zitadel entry surface. After authentication, the user lands in the workspace flow, but only after tenant selection is made explicit.

If no tenant is active, `/workspace` becomes a tenant entry page where the user can:

- choose an existing tenant membership
- create a new tenant

This keeps chat from opening without clear tenant context.

## Main Workspace

The main workspace is a three-column layout:

- left rail
  tenant switcher, active context selectors, seller/ICP setup forms, resource counts, recent runs
- center panel
  primary chat window and prompt actions
- right rail
  compact mirrored chat, projected run events, active account/contact context, recent runs

The UI assumes a "chat-first but context-aware" operating model. The workspace strongly encourages the user to pin:

- seller profile
- ICP profile
- account
- contact

depending on the workflow they want to run.

## Data Browser

The data browser is the read-and-pin surface for tenant records. It exposes:

- seller profiles
- ICP profiles
- accounts
- contacts
- workflow runs

Its main role is not only inspection. It also lets a user push a record back into active chat context with "Use in chat," which ties the browser directly into the runtime loop.

## Review Surface

The review page is a dedicated inspection surface for one workflow run. It combines:

- run summary and status
- artifacts
- evidence
- decision submission

Even though review is not currently the default termination path for the main workflows, the page is a real part of the product and is fully connected to backend review APIs.

## Admin Surface

The admin page is a real operational workspace. It provides:

- platform overview for platform admins
- tenant overview for tenant admins
- workflow run detail
- telemetry tables
- runtime config version management
- audit log visibility

Access is conditional on either platform-admin status or tenant role.

## Shared Frontend State

The tenant store is the UI glue across these surfaces. Per tenant, it keeps:

- active seller profile id
- active ICP profile id
- active account id
- active contact id
- current thread id

Because the state is shared, the app behaves like one tenant-scoped operating session rather than several disconnected pages.
