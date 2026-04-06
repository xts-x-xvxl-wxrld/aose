# Rollout And Verification

## Purpose And Scope

- Record what Phase 4 verification has already proved.
- Separate completed resilience verification from the remaining rollout hygiene backlog.

## What Has Been Verified

- Durable debug inspection exists and is exercised by tests.
- Account-search degraded summaries and fallback outcomes are covered by workflow tests.
- Contact-search degraded summaries and fallback outcomes are covered by workflow tests.
- The account-search Firecrawl-to-Google-Local-Places fallback path is covered by workflow tests.
- The chat API surface exposes the workflow-run debug endpoint.
- Live smoke verification has already shown:
  - account-search provider failure and degraded handling
  - account-research healthy execution
  - contact-search healthy execution
  - post-fix account-search runs that no longer crash after reasoning validation

## What Is No Longer An Open Phase 4 Issue

- The debug-bundle contract is no longer missing.
- The degraded-summary rules are no longer missing.
- The Firecrawl-to-Google-Local-Places fallback triggers are no longer missing.
- The system no longer needs Phase 4 defined as "ready for coding."

## Remaining Verification Work

- Add an environment-readiness prerequisite to smoke verification so migrations and schema freshness are verified before drawing conclusions from `api-test`.
- Acknowledge explicitly that stale schema in `api-test` can invalidate smoke conclusions until migrations are applied.
- Add or automate a one-command local smoke harness for the full chat-thread path.
- Expand live verification to make planner observability part of the standard smoke-readout, not just admin inspection.
- Call out explicitly that planner observability may still require admin endpoints today.
- Call out explicitly that the three-workflow path is not guaranteed to continue naturally when account search ends in real `no_results`.
- A complete smoke harness should either:
  - seed a known accepted account for downstream verification
  - or use a curated prompt and context set that is expected to produce an accepted account
- Optionally add explicit tests for richer event taxonomy if `tool.failed` and dedicated fallback lifecycle events are adopted in workflows.

## Current Recommendation

- Treat Phase 4 resilience work as largely implemented.
- Keep this doc set as a status-and-gap reference, not as an active greenfield spec.
- Track the next major improvement area separately:
  - code-backed semantic work that should move into constrained LLM-backed services
