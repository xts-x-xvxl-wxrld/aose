---
title: Current App Overview - Providers and Tools
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - backend/src/app/tools/provider_factory.py
  - backend/src/app/tools/provider_adapters.py
  - backend/src/app/tools/contracts.py
  - backend/src/app/tools/provider_errors.py
  - backend/src/app/workflows/account_search.py
  - backend/src/app/workflows/account_research.py
  - backend/src/app/workflows/contact_search.py
  - wiki/specs/provider-workflows/00-provider-backed-vertical-slice.md
  - wiki/specs/resilience-and-fallbacks/00-resilience-debuggability-and-fallbacks.md
---

# Current App Overview - Providers and Tools

## Summary

The workflows are provider-backed, not mocked. The app uses a tool factory to compose search, fetch, scrape, enrichment, and structured-normalization tools into each workflow type.

See also [[Current App Overview - Account Search]], [[Current App Overview - Account Research]], [[Current App Overview - Contact Search]], and [[Current App Overview - Admin Ops and Runtime Config]].

## Current Provider Stack

The live provider set is:

- Firecrawl
  web search, page fetch, page scrape, company enrichment
- OpenAI
  structured normalization and reasoning output generation
- Findymail
  primary provider-backed contact search and contact enrichment
- Tomba
  fallback contact provider
- Google Local Places
  fallback local-business discovery path for account search

## Factory and Toolset Model

The tool factory creates workflow-specific bundles:

- account search toolset
- account research toolset
- contact search toolset

This lets each workflow depend on capability contracts rather than directly hard-coding API calls everywhere.

## Provider Behavior Patterns

The provider layer already includes operational behavior beyond simple request forwarding:

- retry loops
- compatibility request profiles for some providers
- normalized provider error codes
- fallback routing
- structured result normalization
- evidence/source reference capture

This is especially visible in:

- Firecrawl search compatibility fallbacks
- OpenAI structured-output compatibility handling
- Findymail -> Tomba fallback routing for contact search

## Workflow Use by Capability

High-level capability mapping:

- account search
  Firecrawl search as primary, Google Local Places as fallback, OpenAI for planning/selection
- account research
  Firecrawl search/fetch/scrape/enrichment, OpenAI for structured synthesis
- contact search
  Findymail as primary provider search and enrichment, Tomba as fallback provider search, Firecrawl web search as supporting public-source signal, OpenAI for candidate reasoning

## Why This Matters

The product’s value is not just that it calls providers. It captures provider-backed work into durable business state:

- accepted accounts
- research snapshots
- contacts
- source evidence
- terminal assistant summaries

That means provider behavior directly affects the tenant’s long-lived workspace data, not just one chat response.
