# Contact Search Findymail Slice

## Purpose And Scope

- Define the Phase 3 slice that turns contact search into a functioning Findymail-backed workflow.
- Scope this slice to provider-backed candidate retrieval, OpenAI-backed ranking, and precision-first contact persistence.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`.
- Depends on `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`.
- Current implemented contact-search behavior is owned by code.

## Decision Summary

- Findymail is the required provider-backed path for contact search completion in Phase 3.
- Findymail is the default primary provider-backed path for contact search in this slice.
- Tomba is an allowed fallback provider for contact search, but only for the narrower set of features that fit this workflow.
- Provider routing should keep Findymail as the default primary path for Phase 3 contact search. EU-sensitive routing strengthens that default because Findymail documents EU-only processing, while Tomba should be treated as a fallback provider because it is an American company even though it documents EU-hosted processing.
- Contact retrieval uses account identity plus target personas, role hints, or titles.
- OpenAI-backed structured reasoning ranks and normalizes provider results into canonical contact candidates.
- Firecrawl may be used only as optional corroborating evidence, not as the primary contact source.
- Missing-data flags and confidence limits are preserved rather than hidden.

## Provider Features To Implement

- Primary retrieval uses `POST /api/search/domain` with canonical account `domain` plus normalized target `roles`.
- The workflow should treat `/api/search/domain` as the default first-pass provider search because it returns contacts only when Findymail found a valid email.
- Role inputs must be normalized down to a small precision-first set before calling Findymail; the provider allows a maximum of `3` roles per request.
- Secondary targeted resolution uses `POST /api/search/name` when the workflow already has a likely person name plus account domain or company name.
- Secondary targeted resolution uses `POST /api/search/business-profile` when the workflow already has a likely LinkedIn URL or username for a candidate.
- Optional post-retrieval enrichment uses `POST /api/search/reverse-email` after a candidate email has been accepted and the workflow wants stronger identity data such as LinkedIn URL, `jobTitle`, and company-profile fields.
- Optional supporting verification uses `POST /api/verify` only for uncertain imported or manually entered emails; it is not required on the standard happy path immediately after Findymail retrieval.
- Provider diagnostics and failure surfacing should use `GET /api/credits` where helpful for clearer credit-related run failures.
- `POST /api/search/employees` may be used only as a lower-priority discovery fallback because it does not return email and therefore cannot serve as the main terminal provider result for this slice.
- Do not rely on Findymail lists, saved contacts, Intellimatch, Signals, exclusion lists, or phone lookup as core contact-search workflow steps in this slice.

## Tomba Fallback Features To Implement

- Tomba fallback retrieval may use domain-based candidate discovery through `Domain.domain_search(domain, page=None, limit=None, department=None, country=None)`.
- Tomba fallback targeted resolution may use `Finder.email_finder(domain, first_name, last_name)` when the workflow already has a likely person name.
- Tomba fallback targeted resolution may use `Finder.linkedin_finder(url)` when the workflow already has a likely LinkedIn profile URL.
- Tomba fallback post-acceptance enrichment may use `Enrichment.person(email)` or `Enrichment.combined(email)` after a candidate email has been accepted and the workflow wants stronger person or company identity fields.
- Tomba fallback verification may use `Verifier.email_verifier(email)` for uncertain imported or manually entered emails, or for defensive verification when the workflow needs a second provider signal.
- Tomba fallback evidence capture may use `Sources.email_sources(email)` after an accepted email is found.
- Tomba `Status.auto_complete(query)` and `Status.domain_status(domain)` may be used only as supporting normalization helpers when account identity is incomplete or the workflow needs a domain sanity check before provider search.
- Tomba `Count.email_count(domain)` may be used only as an optional supporting signal to estimate likely domain coverage before broad domain-based search.
- Tomba `Finder.author_finder`, phone features, and company-only enrichment are not core contact-search steps for this slice.
- Tomba should not be treated as feature-equivalent to Findymail for title-driven primary retrieval because the local provider resources do not expose a direct domain-plus-role search path.

## Provider Request, Routing, And Budget Defaults

- `ContactSearchProviderRequest` should include:
  - `account_id`
  - `account_name`
  - `account_domain`
  - `account_country`
  - `persona_hints[]`
  - `title_hints[]`
  - `region_hint`
  - `selected_people[]`
  - `linkedin_urls[]`
- `ContactSearchProviderResponse` should include:
  - `provider_name`
  - `candidates[]`
  - `raw_result_summary`
  - `quota_state`
  - `errors[]`
- Each normalized provider candidate should include:
  - `full_name`
  - `email`
  - `linkedin_url`
  - `job_title`
  - `company_domain`
  - `source_provider`
  - `confidence_0_1`
  - `acceptance_reason`
  - `missing_fields[]`
  - `evidence_refs[]`
- Findymail and Tomba adapters should translate provider-specific payloads into this shared contact-search contract before workflow-owned ranking and persistence logic runs.
- Default routing should determine EU-sensitive contact search in this order:
  - `account_country`
  - HQ country
  - website TLD or location evidence
  - explicit user override
- Findymail remains the Phase 3 default primary provider regardless of geography.
- Prefer Findymail when the best available account geography indicates EU.
- If geography is ambiguous, do not assume EU automatically, but do not switch the default provider away from Findymail on ambiguity alone.
- Allow provider fallback only for:
  - missing credentials
  - provider unavailable
  - quota or credit exhaustion
  - unsupported input shape
  - explicit no-results from the primary provider path
- Record region-sensitive provider selection and fallback as explicit run events rather than hiding them inside provider adapters.
- Default per-run contact-search budget should be:
  - max `2` provider retrieval calls
  - max `3` targeted follow-up lookups
  - max `1` enrichment call per accepted contact

## Canonical Mapping, Evidence, And Merge Defaults

- Findymail and Tomba both map into canonical `Contact` candidates.
- All provider-backed contact workflows may persist `SourceEvidence`.
- Existing non-empty canonical contact values should generally win unless new evidence is clearly stronger and identity-safe.
- Accepted provider evidence should preserve:
  - `provider_name`
  - `provider_object_id`
  - `source_url`
  - `provider_request_summary`
  - `captured_fields`
  - `captured_at`
  - `confidence_note`
  - `uncertainty_note`
- Merge priority should be:
  - exact email first
  - exact LinkedIn URL second
  - same domain plus strong name match only for non-destructive update, not canonical merge by default
- Same LinkedIn with different email should prefer one canonical contact and keep alternate email in evidence until stronger merge-safe logic says otherwise.
- Same name and same domain without exact email remains insufficient for merge-safe persistence.
- Sparse accepted emails without LinkedIn or title may persist only when exact email identity is strong and missing-data flags remain explicit.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the existing contact-search workflow, missing-data flag, and contact persistence contracts.
- Expected additions in this slice:
  - `ContactSearchProviderRequest` and `ContactSearchProviderResponse`
  - Findymail-backed provider adapter behavior
  - contact-search-specific structured ranking schema
  - contact-search-facing internal tool contracts in `src/app/tools/contracts.py` consumed by the workflow regardless of which provider is selected

## Data Flow / State Transitions

- Workflow loads account, seller context, optional ICP context, and optional latest research context.
- Workflow derives a small normalized title or persona set and maps it to at most `3` Findymail roles for the primary provider request.
- Provider routing chooses the contact-search provider path, keeping Findymail as the default primary provider and using Tomba only as a scoped fallback when the explicit fallback triggers are met.
- Provider search first calls `POST /api/search/domain` with account identity plus normalized target roles when Findymail is selected.
- When Tomba is selected, provider search first calls `Domain.domain_search(...)` for domain-based candidate retrieval.
- In both cases, the workflow should consume the same normalized internal provider response shape rather than branching over raw vendor payload formats.
- If the workflow already knows a likely person identity, it may instead or additionally call `POST /api/search/name`.
- If the workflow already knows a likely LinkedIn profile, it may instead or additionally call `POST /api/search/business-profile`.
- If Tomba is selected and the workflow already knows a likely person identity, it may instead or additionally call `Finder.email_finder(...)`.
- If Tomba is selected and the workflow already knows a likely LinkedIn profile, it may instead or additionally call `Finder.linkedin_finder(...)`.
- OpenAI-backed structured reasoning ranks and normalizes provider results.
- Accepted email candidates may optionally call `POST /api/search/reverse-email` to attach stronger identity fields before persistence.
- Accepted Tomba email candidates may optionally call `Enrichment.person(...)` or `Enrichment.combined(...)` and may attach `Sources.email_sources(...)` as supporting evidence before persistence.
- Optional corroborating web evidence may be attached without replacing the provider-backed path.
- Canonical contacts and evidence persist using the existing merge-safe rules.

## Failure Modes And Edge-Case Rules

- Phase 3 contact search is not considered complete if Findymail cannot be integrated in an environment with provided credentials and references.
- Weak or partial provider matches should preserve low-confidence or missing-data flags instead of inflating certainty.
- Name similarity alone remains insufficient for merge-safe contact persistence.
- Sparse provider payloads are expected from the main retrieval endpoints, especially `name`, `email`, and `domain` without job title or LinkedIn URL, so normalization must preserve missing-data flags instead of guessing.
- Synchronous provider execution should stay small-batch and precision-first because `/api/search/domain` is limited to `5` concurrent requests and `/api/search/business-profile` is limited to `30` concurrent requests.
- Async webhook mode should be deferred unless needed; the preferred Phase 3 path is synchronous provider execution inside the existing chat-triggered workflow.
- Credit-related failures such as `402` not enough credits and `423` subscription paused must surface as clear provider-backed run failures.
- Tomba fallback should not silently widen search behavior beyond the workflow intent; domain-wide candidate retrieval from Tomba must still be filtered through precision-first ranking and missing-data preservation.
- Weak accepted candidates should be rejected by normalization rather than triggering automatic fallback to a second provider.

## Validation, Ownership, And Permission Rules

- Contact search continues to require tenant-owned account context and appropriate actor access.
- Workflow-owned normalization and merge logic remains the gate before canonical contact persistence.
- Provider-backed data remains untrusted until normalized and validated.
- Vendor-specific request shaping and response parsing belong in adapters under `src/app/tools/`, not in contact-search workflow bodies.

## Persistence Impact

- Canonical contacts persist to the existing `Contact` model.
- Supporting source evidence persists through the existing `SourceEvidence` path.
- Missing-data flags remain machine-readable in canonical contact data and run results.

## API / Events / Artifact Impact

- No new public route surface is required.
- Contact-provider search and enrichment activity should be visible through stable run events with correct provider metadata.
- Run events should distinguish at least:
  - primary provider retrieval by domain
  - targeted resolution by name or business profile
  - optional reverse-email enrichment
  - Tomba domain search, named-person lookup, LinkedIn lookup, and enrichment when Tomba is used
  - credit or subscription-related provider failures

## Implementation Acceptance Criteria

- Contact search runs end to end through a Findymail-backed retrieval path.
- The default retrieval path uses `POST /api/search/domain` with normalized account-domain role search.
- The slice defines a clear targeted follow-up path for `POST /api/search/name` and `POST /api/search/business-profile` when person identity evidence is already available.
- The slice defines optional post-acceptance enrichment through `POST /api/search/reverse-email`.
- The slice defines a Tomba fallback path using only the provider features that fit contact search: `Domain.domain_search`, `Finder.email_finder`, `Finder.linkedin_finder`, `Enrichment.person` or `Enrichment.combined`, `Verifier.email_verifier`, and `Sources.email_sources`.
- The provider-selection default keeps Findymail as the primary provider and uses Tomba as fallback only when the explicit Phase 3 fallback triggers apply.
- Ranked contacts preserve missing-data flags and confidence limits.
- Persisted contacts follow the existing exact-email and exact-LinkedIn precedence rules.
- Request shape, response shape, fallback triggers, evidence shape, merge policy, and search budgets are explicit enough to support deterministic workflow tests.

## Verification

- Add workflow and tool tests for:
  - `POST /api/search/domain` primary retrieval behavior
  - `POST /api/search/name` targeted resolution behavior
  - `POST /api/search/business-profile` targeted resolution behavior
  - optional `POST /api/search/reverse-email` enrichment behavior
  - Tomba `Domain.domain_search` fallback retrieval behavior
  - Tomba `Finder.email_finder` targeted resolution behavior
  - Tomba `Finder.linkedin_finder` targeted resolution behavior
  - optional Tomba `Enrichment.person` or `Enrichment.combined` behavior
  - optional Tomba `Verifier.email_verifier` and `Sources.email_sources` behavior
  - provider credit and paused-subscription failure handling
  - normalization, merge precedence, and missing-data flag preservation

## Deferred Items

- Broader multi-provider contact routing beyond the explicit Findymail-primary and Tomba-fallback policy defined in this slice.
- Async webhook-based Findymail orchestration.
- Broader Tomba usage outside the explicit fallback feature set listed in this slice.
- Outreach sequencing and downstream messaging workflows.
