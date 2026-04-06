# User-Facing Failure And Degraded Experience

## Purpose And Scope

- Record the current product behavior for degraded workflow messaging.
- Remove the older Phase 4 planning language that no longer matches the implemented outcome contracts.

## Implemented Behavior

- Users are no longer forced into one of two misleading extremes:
  - fake-normal completion language
  - raw provider or infrastructure detail
- The current pattern is:
  - progress update when fallback begins
  - degraded success summary when fallback produces accepted results
  - degraded failure summary when fallback also fails to confirm reliable candidates
  - ordinary `no_results` language only when there is no known upstream provider failure

## Current User-Visible Outcome Families

### Account Search

- `accounts_found`
- `accounts_found_via_fallback`
- `no_results`
- `provider_failure`
- `provider_failure_with_fallback_exhausted`

### Contact Search

- `contacts_ranked`
- `contacts_ranked_via_fallback`
- `provider_failure`
- `provider_failure_with_fallback_exhausted`

## Fixed From The Original Phase 4 Plan

- Account search now has real degraded progress and terminal summaries.
- Contact search also has degraded progress and terminal summaries.
- True no-results behavior remains distinct from provider-driven degraded behavior.
- Summary-selection provenance is now persisted in `summary_selection_reason`.

## No Longer Current

- Earlier planning-only labels such as `provider_degraded` are not the active workflow contract.
- The product currently uses concrete workflow outcomes rather than umbrella Phase 4 labels.

## Messaging Rules That Still Hold

- User-visible copy should not leak raw values such as:
  - `provider_unavailable`
  - `provider_bad_response`
  - `reasoning_failed_validation`
- User-visible copy should continue to explain degradation at the product level, for example:
  - a source failed
  - a backup source was used
  - the backup path was narrower than usual
  - the system could not verify enough evidence for a reliable result

## Still Open

- Account research does not yet have the same kind of explicit degraded multi-provider outcome model because it is not using the same fallback pattern.
- Phase 4 currently handles terminal degraded outcomes well, but it does not yet define a user-facing policy for runs that succeed overall while still encountering upstream provider degradation internally.
- There is still room to standardize phrasing further across workflows, but the core Phase 4 user-facing failure goal is already met.
