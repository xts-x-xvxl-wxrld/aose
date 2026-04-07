---
title: Current App Overview - Review and Approvals
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - frontend/src/features/review/pages/ReviewPage.jsx
  - backend/src/app/api/v1/endpoints/review.py
  - backend/src/app/services/review.py
  - backend/src/app/services/workflow_run_debug.py
  - backend/src/app/models/approval_decision.py
  - backend/src/app/models/artifact.py
  - backend/src/app/models/source_evidence.py
  - wiki/specs/backend-domain/10-evidence-approval-and-artifacts.md
---

# Current App Overview - Review and Approvals

## Summary

The app includes a real review subsystem for inspecting workflow evidence and artifacts and submitting an approval decision. It is a visible product surface and a real backend capability, even though it is not currently the default termination path for the main workflows.

See also [[Current App Overview - Domain Model]] and [[Current App Overview - Admin Ops and Runtime Config]].

## Review Surface

The review page is route-based:

- `/workspace/review/:runId`

It shows:

- run summary and status
- visible summary and review reason
- artifacts
- evidence
- latest approval decision
- approval submission controls

This gives the user a dedicated inspection surface outside the main chat.

## Review APIs

The review backend exposes:

- evidence listing for a run
- artifact retrieval
- workflow-run debug bundle retrieval
- approval submission

The approval endpoint accepts:

- `approved`
- `needs_changes`
- `rejected`

Rationale is required for rejection and needs-changes decisions.

## Role and State Rules

Review submission requires an active tenant membership with one of:

- `owner`
- `admin`
- `reviewer`

The run must currently be in `awaiting_review`. Approval decisions then move the run into a new terminal state.

## Important Current Caveat

The review subsystem is fully implemented, but the three primary workflow implementations currently return direct terminal workflow results rather than defaulting into `awaiting_review`.

So, as of the current codebase:

- review is a real product surface
- the backend review contract is real
- the main workflows do not normally force the user through it

That is the biggest thing to keep in mind when describing the app to someone new.
