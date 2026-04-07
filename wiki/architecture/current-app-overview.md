---
title: Current App Overview
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - README.md
  - wiki/architecture/current-app-overview/auth-and-tenancy.md
  - wiki/architecture/current-app-overview/domain-model.md
  - wiki/architecture/current-app-overview/workspace-surfaces.md
  - wiki/architecture/current-app-overview/conversation-and-runtime.md
  - wiki/architecture/current-app-overview/providers-and-tools.md
  - wiki/architecture/current-app-overview/admin-ops-and-runtime-config.md
  - wiki/architecture/current-app-overview/account-search.md
  - wiki/architecture/current-app-overview/account-research.md
  - wiki/architecture/current-app-overview/contact-search.md
  - wiki/architecture/current-app-overview/review-and-approvals.md
---

# Current App Overview

## Summary

The current app is a tenant-scoped outbound research workspace built around a chat-first workflow. A signed-in user chooses a tenant, sets seller and ICP context, and then uses chat to trigger three main workflows:

- account search
- account research
- contact search

The system persists durable chat threads, workflow runs, evidence, artifacts, and admin telemetry in the backend. The frontend exposes that state through the workspace, data browser, review surface, and admin console.

This hub page is intentionally short. The detailed system description now lives in the subsystem pages below.

## Subsystem Map

- [[Current App Overview - Auth and Tenancy]]
  Authentication flow, tenant selection, explicit tenant scoping, and membership roles.
- [[Current App Overview - Domain Model]]
  Core persisted entities and how threads, runs, evidence, artifacts, and approvals relate.
- [[Current App Overview - Workspace Surfaces]]
  Frontend routes and surfaces: login, tenant entry, workspace, data browser, review, and admin.
- [[Current App Overview - Conversation and Runtime]]
  Chat orchestration, SSE transport, thread lifecycle, run dispatch, and event projection.
- [[Current App Overview - Providers and Tools]]
  Firecrawl, OpenAI, Findymail, Tomba, Google Local Places, and the tool wiring around them.
- [[Current App Overview - Admin Ops and Runtime Config]]
  Admin visibility, telemetry, config versioning, precedence, snapshots, and auditability.

## Workflow Pages

- [[Current App Overview - Account Search]]
  Seller + ICP driven target account discovery.
- [[Current App Overview - Account Research]]
  Evidence-backed research snapshots and research brief generation.
- [[Current App Overview - Contact Search]]
  Provider-backed contact discovery, ranking, and missing-data handling.
- [[Current App Overview - Review and Approvals]]
  Review UI and APIs, plus the caveat that the current main workflows do not default into review-required termination.

## Reading Order

For a quick mental model:

1. Read [[Current App Overview - Auth and Tenancy]]
2. Read [[Current App Overview - Workspace Surfaces]]
3. Read [[Current App Overview - Conversation and Runtime]]
4. Read the workflow page you care about
5. Read [[Current App Overview - Admin Ops and Runtime Config]] for observability and runtime control

## Interpretation

As implemented today, this is not a general-purpose assistant product. It is a multi-tenant sales-research workspace where chat acts as the control surface for repeatable outbound workflows, while business state remains durable, inspectable, and tenant-scoped.

The system sits at the intersection of:

- a conversational workflow runner
- a lightweight prospecting CRM surface
- an evidence-backed research store
- an operator/admin console for workflow telemetry and prompt/runtime control
