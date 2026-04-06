# Account Search Fallback And Google Local Places

## Purpose And Scope

- Record the current account-search fallback behavior rather than the older proposed-only version of it.
- Scope this document to what is implemented, what changed since the original plan, and what remains open.

## Implemented

- Firecrawl remains the primary provider for account discovery.
- Google Local Places is an explicit backup path for account search when the primary provider fails with known provider-failure codes.
- The fallback path is visible in:
  - workflow events
  - debug bundles
  - final normalized run outcomes
  - user-facing assistant messaging

## Current Trigger Rules

- Account-search fallback is currently allowed when the primary provider reports:
  - `provider_bad_response`
  - `provider_unavailable`
  - `provider_rate_limit`
  - `provider_quota_exceeded`
- Fallback is not triggered just because account-search reasoning fails validation after usable Firecrawl evidence already exists.
- If Firecrawl produces usable evidence, the workflow stays on the primary path and uses reasoning or deterministic parsing before considering fallback.

## Current Fallback Strategy

- The fallback path builds narrower Google Local Places queries from:
  - planner output
  - seller target-market context
  - ICP industry or geography hints
- The fallback path is intentionally treated as degraded coverage rather than equivalent search breadth to the primary Firecrawl path.

## Fixed From The Original Phase 4 Plan

- The fallback policy is no longer hypothetical.
- The primary-provider outage no longer collapses into silent ordinary `no_results`.
- Degraded-success and degraded-failure account-search outcomes are now explicit.
- User-facing fallback progress messaging is implemented.

## Adjacent Improvements Since The Original Phase 4 Draft

- Account-search query planning is no longer deterministic.
- The workflow now uses an LLM-backed structured query planner for the primary path.
- That change is not a fallback feature by itself, but it removed one of the major causes of weak account-search execution that had previously been masked as search quality issues.

## Still Open

- Fallback query generation is still partially deterministic even though primary query planning is now LLM-backed.
- Final account acceptance still uses deterministic scoring and selection heuristics after reasoning normalization.
- Those are semantic-quality follow-up items rather than unresolved fallback correctness bugs.
