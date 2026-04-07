---
title: Current App Overview - Account Search
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - backend/src/app/workflows/account_search.py
  - backend/src/app/workflows/contracts.py
  - backend/src/app/services/chat_orchestrator.py
  - backend/src/app/services/workflow_runs.py
  - backend/src/app/api/v1/endpoints/workspace.py
  - wiki/specs/backend-domain/07-workflow-account-search.md
---

# Current App Overview - Account Search

## Summary

Account search is the workflow that turns seller context plus ICP context into accepted target account candidates. It is the main entry workflow for expanding the tenant’s account dataset.

See also [[Current App Overview - Conversation and Runtime]] and [[Current App Overview - Providers and Tools]].

## Trigger Conditions

The rules-based orchestrator routes a turn into account search when the user asks to find or search for companies/accounts matching the ICP.

Required context:

- seller profile
- ICP profile

If either is missing, the assistant replies inline with a clarification rather than starting the run.

## Core Behavior

The workflow:

- plans search strategy and query ideas
- searches for candidate accounts
- evaluates candidates against seller + ICP context
- accepts defensible candidates conservatively
- persists accepted accounts and evidence
- emits a terminal assistant summary

It supports degraded operation and fallback behavior if the primary discovery path is impaired.

## Output and Persistence

The main durable outputs are:

- `Account` records
- `SourceEvidence` records
- `WorkflowRun` normalized result payload
- run events for planning, tool activity, and candidate decisions

The result payload includes:

- accepted account ids
- outcome
- attempt counts
- assistant summary
- provider/fallback fields

## User-Facing Meaning

In the workspace, account search is the workflow that fills the "Accounts" part of the tenant’s data browser and gives the user the first real prospecting set to work with.

## Current Caveats

- It is deliberately precision-first rather than recall-first.
- It relies on explicit seller and ICP context rather than inferring the target market from chat alone.
- It currently terminates as a normal terminal workflow result rather than defaulting into review-required status.
