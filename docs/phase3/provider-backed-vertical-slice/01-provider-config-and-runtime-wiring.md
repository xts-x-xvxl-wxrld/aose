# Provider Config And Runtime Wiring

## Purpose And Scope

- Define the Phase 3 slice that replaces null workflow toolsets with provider-backed runtime wiring.
- Scope this slice to configuration, tool construction, dependency injection, and failure-shape expectations.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/provider-backed-vertical-slice/00-provider-backed-slice-overview.md`.
- Current implemented runtime boundaries are owned by code.
- Older `docs/implementation/...` files may still provide background context, but they are not authoritative for this Phase 3 slice.

## Decision Summary

- Runtime wiring should construct concrete Firecrawl, Google Local Places, Findymail, Tomba, and OpenAI-backed tool instances from centralized configuration.
- Workflows should receive real toolsets through a shared builder or factory boundary instead of instantiating provider implementations inline.
- The current run lifecycle, dispatch, and chat projection services remain on the same durable foundation. Phase 3 may add provider-aware event categories, richer provider metadata, and clearer failure summaries without replacing the existing run/event model.

## Recommended Provider Runtime Contract

- Runtime wiring should expose one settings object per provider:
  - `firecrawl`
  - `google_local_places`
  - `findymail`
  - `tomba`
  - `openai`
- The tool layer should expose a small set of internal request, response, and error contracts rather than passing vendor-specific payloads into workflows.
- Each provider adapter should translate:
  - internal request shape -> provider request shape
  - provider response shape -> internal normalized response shape
  - provider-specific failures -> internal normalized error shape
- Provider adapters should stay narrow and consistent, using `search(...)`, `enrich(...)`, `verify(...)`, and `healthcheck(...)` where applicable.
- Provider adapter conventions should be capability-oriented and explicit:
  - account-search and account-research web adapters should expose `search(...)`, `fetch(...)`, `scrape(...)`, `map(...)` when supported, and `healthcheck(...)`
  - contact-search adapters should expose `search(...)`, `lookup_person(...)`, `lookup_profile(...)`, `enrich(...)`, `verify(...)`, and `healthcheck(...)`
- Runtime wiring should centralize provider construction and routing helpers rather than letting workflows instantiate provider clients directly.
- Adapters should be translators, not owners of workflow policy, persistence, or fallback decisions.

## Recommended Code Ownership For Adapter Logic

- Shared internal tool contracts should live in `src/app/tools/contracts.py`.
- Provider adapter implementations should live under `src/app/tools/` or a provider-oriented subpackage rooted there.
- Runtime construction and dependency injection should live in `src/app/services/runtime_wiring.py`.
- Provider configuration should live in `src/app/config.py`.
- Workflows in `src/app/workflows/` should consume only normalized internal tool interfaces and should not parse raw vendor payloads directly.

## Recommended Timeout, Retry, And Error Defaults

- Default request timeouts should be:
  - `10s` for search
  - `15s` for enrichment
  - `20s` for research fetch
- Retries should be limited to `2` attempts for transient `429` and `5xx` failures with exponential backoff.
- Provider-specific exceptions should be normalized into workflow-safe categories:
  - `ProviderAuthError`
  - `ProviderRateLimitError`
  - `ProviderQuotaError`
  - `ProviderUnavailableError`
  - `ProviderBadResponseError`

## Routing And Credential Defaults

- Contact-search runtime wiring should support explicit provider-routing decisions instead of implicit provider fallback hidden inside adapters.
- Region-sensitive routing should support a Findymail-primary and Tomba-fallback policy without changing the overall Phase 3 default away from Findymail.
- The routing basis should be preserved in provider metadata when geography influences provider choice.
- In local development, OpenAI should be the only provider assumed required for reasoning-path work.
- Firecrawl, Google Local Places, Findymail, and Tomba may be optional in local development depending on the slice under active development.
- In staging and end-to-end verification environments, all providers needed for the relevant Phase 3 workflow should be configured.
- Missing credentials must fail clearly at construction or execution time instead of silently downgrading into null behavior.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the current workflow tool contracts in `src/app/tools/contracts.py`.
- Expected additions in this slice:
  - provider configuration settings for Firecrawl, Google Local Places, Findymail, Tomba, and OpenAI-backed structured reasoning
  - a centralized tool-builder or runtime-factory interface used by workflow runtime wiring
  - provider-specific adapter boundaries under `src/app/tools/` or adjacent runtime-owned packages
  - normalized provider request, response, and error contracts owned by the tool layer

## Data Flow / State Transitions

- App startup resolves shared settings.
- Runtime wiring builds provider-backed toolsets for account search, account research, and contact search from normalized internal contracts plus provider-specific adapters.
- Account-search runtime wiring may expose Google Local Places as an optional tool path for local-business or location-bound discovery without replacing Firecrawl as the default web-discovery provider.
- Contact-search runtime wiring must support a Findymail-primary and Tomba-fallback policy without requiring workflows to instantiate provider clients directly.
- Workflow handlers receive those toolsets through injected construction rather than defaulting to null implementations or consuming raw provider clients directly.
- Tool execution emits stable run events with provider-aware metadata.
- The durable run-event envelope remains stable, but Phase 3 may add event categories needed for provider-backed execution such as reasoning validation, candidate decisions, and provider-routing decisions.
- Provider-aware event metadata should include:
  - `provider_name`
  - `operation`
  - `attempt`
  - `duration_ms`
  - normalized error code when failed

## Failure Modes And Edge-Case Rules

- Missing provider configuration must fail clearly at tool-construction or workflow-execution time rather than producing silent null behavior.
- Runtime wiring must not create separate hidden tool graphs per request when shared stateless adapters are sufficient.
- Provider-specific exceptions should be normalized into workflow-friendly failures with explicit error summaries.
- Fallback routing decisions must be visible to workflows and run events rather than being hidden inside provider adapters.
- Raw provider payloads must not leak upward into workflow-owned contracts.

## Validation, Ownership, And Permission Rules

- Runtime wiring owns provider construction.
- Workflows own the decision to treat provider failures as terminal errors or uncertainty-preserving partial results.
- Tools and adapters do not gain permission or persistence responsibilities.
- Tool contracts own the normalized system-facing language; adapters own translation to and from provider-specific shapes.

## Persistence Impact

- No canonical business-record changes are owned by this slice.
- This slice may add config surfaces and provider-name metadata usage in run events.

## API / Events / Artifact Impact

- Existing public chat and workflow APIs remain stable.
- `tool.started` and `tool.completed` should carry accurate `provider_name` values when provider-backed tools execute.
- Additive event-category expansion in Phase 3 is allowed as long as the existing run-event projection model remains the durable source of truth.

## Implementation Acceptance Criteria

- Null workflow toolsets are no longer the default runtime path for Phase 3-targeted workflows.
- Firecrawl, Google Local Places, Findymail, Tomba, and OpenAI-backed reasoning are all constructible from central settings.
- Workflow runtime wiring is explicit enough to test without patching application globals ad hoc.
- Provider settings, adapter boundaries, retry policy, timeout policy, and normalized error behavior are explicit enough to test deterministically.
- Adapter placement is explicit enough that provider translation logic lands in `src/app/tools/` and not inside workflow implementations.

## Verification

- Add runtime tests for tool construction, missing-config behavior, and provider-aware run-event emission as this slice is implemented.

## Deferred Items

- Dynamic provider routing beyond the explicit contact-search fallback policy for this phase.
- Per-tenant provider selection policies.
