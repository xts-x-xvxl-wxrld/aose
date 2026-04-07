---
title: Current App Overview - Contact Search
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - backend/src/app/workflows/contact_search.py
  - backend/src/app/workflows/contracts.py
  - backend/src/app/tools/provider_factory.py
  - backend/src/app/services/chat_orchestrator.py
  - backend/src/app/models/contact.py
  - wiki/specs/backend-domain/09-workflow-contact-search.md
---

# Current App Overview - Contact Search

## Summary

Contact search is the workflow that turns seller context plus a selected account into ranked contact candidates, using provider-backed search and missing-data-aware normalization.

See also [[Current App Overview - Account Research]] and [[Current App Overview - Providers and Tools]].

## Trigger Conditions

The rules-based orchestrator routes a turn into contact search when the user asks to find contacts, buyers, champions, or similar people for the selected account.

Required context:

- seller profile
- selected account

Optional context:

- ICP profile
- latest account research snapshot

If the account is missing, the assistant replies with a clarification instead of starting the workflow.

## Core Behavior

The workflow:

- builds provider search inputs from seller/account/optional ICP context
- searches contacts through a primary provider
- can fall back to a secondary provider if needed
- combines provider-backed results with supporting reasoning
- enriches and finalizes candidates
- preserves missing-data flags instead of overstating certainty
- persists contacts and evidence

## Output and Persistence

The main durable outputs are:

- `Contact` records
- `SourceEvidence`
- `WorkflowRun` normalized result payload

The result payload includes:

- contact ids
- missing data flags
- used research snapshot id when available
- provider/fallback markers
- assistant summary

## Provider Behavior

The current default routing is:

- Findymail primary
- Tomba fallback

This is one of the most explicit fallback-aware workflows in the system and is also where provider routing decisions are surfaced most clearly.

## Current Caveats

- The workflow is careful about uncertainty and missing fields, so some returned contacts are intentionally incomplete.
- Like the other main workflows, it currently completes as a normal terminal result rather than defaulting into review-required status.
