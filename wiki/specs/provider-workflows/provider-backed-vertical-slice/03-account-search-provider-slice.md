# Account Search Provider Slice

## Purpose And Scope

- Define the Phase 3 slice that turns account search into a functioning provider-backed workflow.
- Scope this slice to Firecrawl-backed discovery, OpenAI-backed candidate extraction, and precision-first account persistence.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`.
- Depends on `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`.
- Current implemented account-search behavior is owned by code.

## Decision Summary

- Account search uses seller and ICP context to produce high-signal search queries and fit criteria.
- Firecrawl-backed search, fetch, and scrape flows are the evidence-gathering path for public company discovery.
- Google Local Places is an allowed optional discovery source when the target company type is place-centric, local, franchise-like, or otherwise strongly location-bound.
- OpenAI-backed structured reasoning extracts, filters, and scores candidate accounts.
- Precision is preferred over recall, and successful no-results runs remain valid outcomes.

## Firecrawl Feature Fit For ICP-Driven Target Account Search

- `firecrawl search` is the primary natural-language company-discovery primitive for Phase 3.
- The workflow should translate seller profile context, ICP criteria, and optional user targeting constraints into a small set of precision-focused search queries, then run them through Firecrawl search.
- `firecrawl search --scrape` is the preferred extension of that discovery step when the workflow needs immediate page-level evidence from result pages without first building a broader crawl.
- `firecrawl map` is the best follow-on tool once a plausible company site is identified, because it can quickly expose high-signal pages such as `/about`, `/pricing`, `/careers`, `/customers`, `/security`, or documentation pages that support fit evaluation.
- `firecrawl crawl` is allowed for narrow follow-up evidence gathering on shortlisted companies, but it should not be the default discovery primitive because the account-search path favors precision-first evidence collection over broad recall.
- `firecrawl agent` may be used as an optional structured extraction layer after a likely company or company site is already known, especially when the workflow needs normalized company facts from a bounded set of URLs; it is not the primary mechanism for broad target-account discovery.
- Experimental workflow wrappers such as company-directory scraping or browser-driven lead-generation flows may inform future higher-level search experiences, but they are not the canonical Phase 3 provider contract for account search.

## Google Local Places Feature Fit For Local-Business Account Search

- Google Local Places should be used only when the target is place-centric or location-bound and there is explicit geographic targeting or strong location evidence in seller context, ICP context, or user instructions.
- Google Local Places should not replace Firecrawl as the default broad company-discovery source for account search.
- The most useful Google Local Places result fields for this slice are:
  - `title` for candidate company or place name
  - `type` for business category
  - `address` for locality evidence
  - `phone` for business identity evidence
  - `links.website` for canonical-domain extraction
  - `gps_coordinates` for geographic grounding
  - `rating` and `reviews` as lightweight quality or popularity signals
  - `place_id` as provider-stable place identity metadata
  - `extensions` as structured fit hints such as service availability, accessibility, pricing, care options, or vertical-specific traits
- When Google Local Places returns a website, the workflow should prefer extracting and normalizing the canonical domain from `links.website` before merging or enriching a candidate account.
- Place results should still be treated as advisory evidence until OpenAI-backed normalization and workflow-owned acceptance logic decide whether the result maps cleanly to a canonical account.
- Google Local Places is most valuable as a supplement to Firecrawl when location, storefront, or service-area relevance is part of the fit decision.

## Query Budget And Invocation Defaults

- Firecrawl remains the default first-pass provider for account discovery unless the user request is clearly local from the start.
- Google Local Places should be invoked only when:
  - the target is place-centric or location-bound
  - and there is explicit geographic targeting or strong location evidence in seller context, ICP context, or user instructions
- Google Local Places is preferred as a second-pass supplement when Firecrawl returns weak or ambiguous results for place-centric searches, unless the user request is clearly local from the start.
- Default per-run account-search budget should be:
  - max `3` Firecrawl searches
  - max `2` Firecrawl map or fetch cycles per shortlisted domain
  - max `2` Google Local Places lookups

## Canonical Mapping And Evidence Defaults

- Firecrawl and Google Local Places both map into canonical `Account` candidates.
- Firecrawl and Google Local Places adapters should translate vendor payloads into shared internal account-search tool results before workflow-owned normalization begins.
- Google Local Places fields should be mapped conservatively:
  - `title` -> candidate company or place name
  - `links.website` -> canonical-domain extraction candidate
  - `type` -> category evidence
  - `address`, `phone`, and `gps_coordinates` -> locality and identity evidence
  - `rating`, `reviews`, and `extensions` -> fit-supporting signals, not canonical business facts by default
- Existing non-empty canonical account fields should generally win unless new evidence is clearly stronger and identity-safe.
- Accepted evidence should preserve:
  - `provider_name`
  - `provider_object_id`
  - `source_url`
  - `provider_request_summary`
  - `captured_fields`
  - `captured_at`
  - `confidence_note`
  - `uncertainty_note`
- For Google Local Places, `place_id` should be preserved when available.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the current account-search workflow input, result, and persistence contracts.
- Expected additions in this slice:
  - Firecrawl-backed `web_search`, `page_fetch`, `page_scrape`, and public-web company-enrichment behavior for account search
  - account-search-specific structured candidate extraction schema
  - clearer fit-evidence expectations for persisted accepted accounts
  - account-search-facing internal tool result types consumed from `src/app/tools/contracts.py`

## Data Flow / State Transitions

- Workflow loads seller and ICP context.
- Workflow builds one or more precision-focused search queries.
- Firecrawl-backed search and page collection gathers candidate evidence through normalized tool interfaces rather than raw Firecrawl payload parsing in the workflow.
- If the search target is place-centric or location-bound and the workflow has actual geographic grounding, it may also query Google Local Places for additional structured discovery evidence.
- Initial discovery should start with natural-language Firecrawl search, then selectively use map, fetch, scrape, and only narrow crawl behavior for shortlisted domains.
- Google Local Places results should be translated by the adapter into internal discovery evidence and then feed identity clues such as title, category, address, phone, and website into normalization before candidate acceptance.
- OpenAI-backed structured reasoning extracts and filters candidate accounts.
- Optional public-web enrichment fills missing canonical company fields.
- Accepted candidates and evidence persist through the existing account-search contracts.

## Failure Modes And Edge-Case Rules

- Sparse or noisy public-web evidence should produce explicit no-results or uncertainty, not weak accepted accounts.
- Duplicate-domain matches should continue to merge into existing canonical accounts rather than duplicating records.
- Search or extraction failures should not create partial accepted accounts without defensible evidence.
- Google Local Places results without a trustworthy website or strong identity match should not be promoted into accepted canonical accounts on their own.
- Google Local Places should not be allowed to widen query scope into broad generic company discovery that Firecrawl already owns better in this phase.

## Validation, Ownership, And Permission Rules

- Account search still requires seller and ICP context.
- Workflow-owned scoring and acceptance logic remains responsible for final promotion into canonical accounts.
- Tool outputs remain advisory until normalized and validated by the workflow.
- Vendor-specific response parsing belongs in adapters under `src/app/tools/`, not in account-search workflow logic.

## Persistence Impact

- Accepted accounts persist to the existing `Account` model.
- Evidence persists through the existing `SourceEvidence` path.
- No-results outcomes continue to persist as successful account-search runs.

## API / Events / Artifact Impact

- No new public route surface is required.
- Run events should reflect real Firecrawl-backed search and enrichment activity.
- When used, Google Local Places lookups should appear in run events with correct provider metadata and enough result context to explain later normalization decisions.

## Implementation Acceptance Criteria

- Account search no longer depends on null tooling in the Phase 3 path.
- Accepted accounts are grounded in public-web evidence plus structured fit reasoning.
- The slice allows Google Local Places as an optional local-business discovery source without replacing Firecrawl as the default account-search provider.
- No-results behavior remains explicit and non-error.

## Verification

- Add workflow tests for accepted results, no-results outcomes, enrichment behavior, duplicate-domain merge behavior, and Google Local Places normalization behavior for place-centric account searches.

## Deferred Items

- Multi-provider company discovery.
- Broad Google Local Places usage outside the explicit local-business and place-centric search fit described in this slice.
- Manual shortlist curation UX beyond current workflow outputs.
