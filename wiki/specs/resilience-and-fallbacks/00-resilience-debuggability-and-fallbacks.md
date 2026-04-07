# Phase 4: Resilience, Debuggability, And Fallbacks

## Summary

- Phase 4 is no longer just a planning set. Most of the core resilience work described here is now implemented in code.
- The main delivered outcomes are:
  - durable workflow-run debug inspection
  - truthful degraded assistant messaging
  - explicit account-search fallback from Firecrawl to Google Local Places
  - explicit contact-search degraded and fallback outcomes
- The remaining open work in this area is smaller and more specific:
  - richer event taxonomy adoption in workflows
  - optional debug-bundle enrichment such as HTTP status and timing details
  - clearer treatment of successful runs that still contain degraded provider events
  - planner observability that is first-class in standard run debug rather than mostly living in admin telemetry
  - smoke-environment readiness beyond "the container is running"
  - better live-smoke automation and rollout hygiene
- Phase 4 also exposed a follow-on problem that is not primarily a resilience bug:
  - some workflow decisions are still semantic in nature but are hardcoded in Python instead of being owned by constrained LLM-backed services

## Slice Set

Read the current Phase 4 docs in this order:

1. `docs/phase4/resilience-debuggability-and-fallbacks/00-overview.md`
2. `docs/phase4/resilience-debuggability-and-fallbacks/01-dev-facing-debugging-and-observability.md`
3. `docs/phase4/resilience-debuggability-and-fallbacks/02-user-facing-failure-and-degraded-experience.md`
4. `docs/phase4/resilience-debuggability-and-fallbacks/03-account-search-fallback-and-google-places.md`
5. `docs/phase4/resilience-debuggability-and-fallbacks/04-rollout-and-verification.md`
6. `docs/phase4/resilience-debuggability-and-fallbacks/05-code-backed-semantic-work.md`

## Current State

### Implemented

- Workflow-run debug inspection exists at `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug`.
- Debug bundles expose:
  - `provider_attempts`
  - `fallback_decisions`
  - `reasoning_validation`
  - `user_summary_snapshot`
  - `terminal_outcome_family`
  - `summary_selection_reason`
- Account search distinguishes:
  - `accounts_found`
  - `accounts_found_via_fallback`
  - `no_results`
  - `provider_failure`
  - `provider_failure_with_fallback_exhausted`
- Contact search distinguishes:
  - `contacts_ranked`
  - `contacts_ranked_via_fallback`
  - `provider_failure`
  - `provider_failure_with_fallback_exhausted`
- Account-search fallback to Google Local Places is implemented and tested.
- User-facing degraded progress and terminal summaries are implemented for fallback-driven account and contact search flows.

### Still Open

- Workflows do not yet emit the richer Phase 4 event taxonomy consistently.
  - `tool.failed` exists in the runtime contract and debug service, but current workflow code still mostly records failures through `tool.completed` plus `error_code`.
  - Dedicated `fallback.invoked`, `fallback.completed`, and `user_message.selected` events are still not part of the active workflow event stream.
- The debug bundle is useful, but it still does not include everything the original planning docs proposed.
  - `http_status` is not surfaced per provider attempt.
  - `duration_ms` is not surfaced per provider attempt.
- Successful runs can still contain degraded provider behavior such as `provider_rate_limit` events or compatibility retries, but that degraded provenance is still under-documented in the standard Phase 4 status story.
- Standard debug inspection is still weaker than admin telemetry for planner and provider-call analysis.
- Smoke execution still has operational prerequisites beyond "container is running."
  - migration and schema freshness still matter
  - stale `api-test` state can invalidate smoke conclusions until migrations are current
- Live verification is now possible, but the repo still lacks a fully owned, one-command smoke harness for the whole thread-driven path.
- End-to-end smoke continuation is still not guaranteed when account search ends in legitimate `no_results`, which can block downstream workflow continuation without reseeding or a more reliable prompt/context set.

## Core Direction

- Keep resilience ownership in code:
  - retries
  - fallback safety rules
  - run durability
  - provenance
  - user-visible outcome mapping
- Move semantic judgment out of hand-built heuristics when the task depends on context understanding instead of simple rules.
- Treat the new semantic backlog as the natural follow-on to this phase, not as unfinished Phase 4 resilience work.
