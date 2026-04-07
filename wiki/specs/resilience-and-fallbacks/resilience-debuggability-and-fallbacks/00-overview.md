# Resilience, Debuggability, And Fallbacks Overview

## Purpose And Scope

- This document is the current entrypoint for the Phase 4 resilience slice set.
- It now describes both:
  - what shipped
  - what remains open

## Current Phase 4 Status

### Implemented

- Phase 4 is correctly scoped as a resilience layer on top of the provider-backed workflows rather than a new workflow family.
- Provider failures no longer need to disappear behind ambiguous `no_results` outcomes when the system knows more.
- Developer-facing debug inspection is available from durable workflow state.
- User-facing chat summaries can distinguish normal results from degraded fallback-driven outcomes.
- Account search now supports Firecrawl-primary and Google Local Places-fallback behavior.
- Contact search already has explicit degraded/fallback handling and now also treats `provider_bad_response` as fallback-eligible.

### Partially Implemented

- Event semantics are better than they were, but they are not yet as explicit as the original Phase 4 planning target.
- The debug bundle is durable and useful, but it is still a compact explanation layer rather than a full per-attempt telemetry record.
- Successful runs can still contain degraded provider events such as rate limits or compatibility retries, and that state is not yet first-class in the standard debug and outcome story.

### No Longer Current

- The earlier proposed Phase 4 outcome model used umbrella labels such as:
  - `successful_primary_result`
  - `successful_fallback_result`
  - `partial_uncertainty`
  - `provider_degraded`
- Those labels are not the actual code-level run outcomes and should not be treated as the current contract.
- The real contracts now live in workflow result models and normalized run payloads.

## Current Outcome Model

- Account search currently uses explicit terminal outcomes such as:
  - `accounts_found`
  - `accounts_found_via_fallback`
  - `no_results`
  - `provider_failure`
  - `provider_failure_with_fallback_exhausted`
- Contact search currently uses explicit terminal outcomes such as:
  - `contacts_ranked`
  - `contacts_ranked_via_fallback`
  - `provider_failure`
  - `provider_failure_with_fallback_exhausted`
- Research currently focuses more on durable evidence and reasoning validation than on multi-provider degraded routing.

## Remaining Gaps In Scope

- Broader use of `tool.failed` and dedicated fallback lifecycle events.
- Optional expansion of debug bundle fields for status-code and timing richness.
- Standard run debug is still weaker than admin telemetry for planner and provider-call analysis.
- Smoke execution still has operational prerequisites beyond "container is running," especially migration and schema freshness in `api-test`.
- Better live verification automation.
- End-to-end smoke continuation is not guaranteed when discovery ends in real `no_results`.

## Follow-On Work

- The next important backlog is not another fallback tree first.
- It is the set of semantic workflow decisions that are still hardcoded in Python but should be owned by constrained LLM-backed services.
- That backlog is described in `05-code-backed-semantic-work.md`.
