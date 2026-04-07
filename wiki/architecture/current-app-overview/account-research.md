---
title: Current App Overview - Account Research
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - backend/src/app/workflows/account_research.py
  - backend/src/app/workflows/contracts.py
  - backend/src/app/services/chat_orchestrator.py
  - backend/src/app/models/account_research_snapshot.py
  - backend/src/app/models/artifact.py
  - wiki/specs/backend-domain/08-workflow-account-research.md
---

# Current App Overview - Account Research

## Summary

Account research is the workflow that gathers public evidence and synthesizes a seller-aware account snapshot for one selected account.

See also [[Current App Overview - Account Search]], [[Current App Overview - Review and Approvals]], and [[Current App Overview - Providers and Tools]].

## Trigger Conditions

The rules-based orchestrator routes a turn into account research when the user asks to research or analyze the currently selected account.

Required context:

- seller profile
- selected account

Optional context:

- ICP profile

If the account is missing, the assistant responds with a clarification instead of starting research.

## Core Behavior

The workflow:

- loads the selected account plus seller and optional ICP context
- gathers public evidence through search/fetch/scrape/enrichment
- synthesizes a structured research record
- persists evidence
- creates an account research snapshot
- may create a markdown research brief artifact

The output is designed to be durable and reusable, not just a one-off reply.

## Output and Persistence

The main durable outputs are:

- `AccountResearchSnapshot`
- `SourceEvidence`
- optional `Artifact` for a research brief
- `WorkflowRun` normalized result payload

The result payload includes:

- snapshot id
- snapshot version
- whether ICP context was present
- reason summary

## User-Facing Meaning

This workflow is the bridge between initial account discovery and deeper operator judgment. It turns a selected account into a structured piece of tenant knowledge that later flows, especially contact search, can reuse.

## Current Caveats

- ICP context is optional, so some research outputs are seller-aware but not fully ICP-evaluated.
- The workflow produces durable research state, but it does not currently default into review-required termination.
