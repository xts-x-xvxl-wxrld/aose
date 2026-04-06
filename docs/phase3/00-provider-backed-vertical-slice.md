# Phase 3: Provider-Backed Outbound Research Vertical Slice

## Summary

- Deliver a working chat-triggered vertical slice for account search, account research, and contact search.
- Keep the current chat/thread/run/event plumbing and the rules-based orchestrator. Do not build autonomous agent-to-agent runtime in this phase.
- Make the workflows real by wiring provider-backed tools: Firecrawl as the primary provider for account discovery/research, Google Local Places as an optional local-business discovery source for account search, OpenAI for normalization and synthesis, Findymail as the primary contact-search provider, and Tomba as a constrained fallback for contact search.
- Optimize for precision over recall: fewer defensible results with explicit evidence and missing-data flags.

## Slice Set

Read the Phase 3 implementation slices in this order:

1. `docs/phase3/provider-backed-vertical-slice/00-provider-backed-slice-overview.md`
2. `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`
3. `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`
4. `docs/phase3/provider-backed-vertical-slice/03-account-search-provider-slice.md`
5. `docs/phase3/provider-backed-vertical-slice/04-account-research-provider-slice.md`
6. `docs/phase3/provider-backed-vertical-slice/05-contact-search-findymail-slice.md`
7. `docs/phase3/provider-backed-vertical-slice/06-chat-and-frontend-completion.md`
8. `docs/phase3/provider-backed-vertical-slice/07-rollout-and-verification.md`

Post-implementation correction document:

- `docs/phase3/09-post-implementation-fixes.md`

## Implementation Changes

### Runtime and wiring

- Add provider settings and runtime wiring for Firecrawl, Google Local Places, Findymail, Tomba, and OpenAI-backed normalization.
- Replace the null workflow toolsets with concrete tool instances built from a centralized tool factory and injected through runtime wiring.
- Keep `ConversationService`, `WorkflowRunService`, `RulesBasedChatOrchestrator`, and the current durable run/event projection model in place. Phase 3 may add provider-aware event categories and richer `provider_name` metadata, but it should not replace the current run/event foundation.

### Workflow behavior

- Account search:
  - Use seller + ICP context to generate search queries and fit criteria.
  - Run Firecrawl-backed web search/fetch/scrape against public company sources.
  - Allow Google Local Places as an optional discovery source when the search target is a local business, location-bound provider, franchise, clinic, office, storefront, or other place-centric company type.
  - Use Google Local Places fields such as place title, category, address, phone, website, coordinates, ratings, reviews, `place_id`, and `extensions` as structured evidence for company identity and fit, but do not treat it as a replacement for broader public-web evidence.
  - Use OpenAI structured normalization to extract candidate accounts, fit summaries, and evidence.
  - Add a public-web company enrichment step backed by Firecrawl + OpenAI to fill canonical company fields before persistence.
  - Persist only accepted candidates with evidence; preserve no-results as successful runs.
- Account research:
  - Gather a small, high-signal evidence set for the selected account with Firecrawl.
  - Use OpenAI structured synthesis to build the research record, snapshot, and research brief with explicit uncertainty.
  - Persist evidence, snapshot versioning, and artifacts through the existing contracts.
- Contact search:
  - Add a Findymail-backed primary candidate retrieval step using account domain/name plus target personas/titles.
  - Add a Tomba-backed fallback path for contact search using only the features that fit the slice: domain search, named-person email lookup, LinkedIn-based lookup, accepted-email enrichment, verification, and evidence-source lookup.
  - Use Findymail as the default primary provider for contact search in Phase 3, including EU-sensitive routing where its documented EU-only processing strengthens that default.
  - Treat Tomba as a fallback provider because it is an American company even though it documents EU-hosted processing.
  - Use OpenAI ranking/normalization to convert provider results into canonical contact candidates with rationale and missing-data flags.
  - Use Firecrawl only as optional corroborating evidence, not as the primary contact source.
  - Persist merged canonical contacts and source evidence using the existing precision-first merge rules.

### Prompt and agent layer

- Replace the current skeleton specialist instructions with concrete workflow-scoped prompt specs for:
  - account search planning and candidate acceptance,
  - account research synthesis,
  - contact persona targeting and ranking.
- Invoke these prompts from workflows or helper services; do not switch to free-form SDK handoffs or autonomous agent loops in Phase 3.
- Require structured OpenAI outputs with schema validation. If validation fails, fall back to deterministic baseline behavior and explicit uncertainty instead of fabricating results.

### Chat and frontend completion

- Keep chat as the only user-facing workflow trigger.
- Ensure the existing chat flow can launch all three workflows end-to-end and surface final summaries, tool activity, failures, and persisted outputs.
- Limit frontend work to compatibility fixes needed for the vertical slice; no major UX redesign in this phase.

## Public APIs and Interfaces

- Existing tenant-scoped chat, thread, workflow-run, and run-event interfaces remain stable in this phase.
- Add configuration for Firecrawl, Google Local Places, Findymail, Tomba, and OpenAI normalization/synthesis settings.
- Add a centralized tool-builder interface used by runtime wiring to construct workflow toolsets.
- Extend the contact tool layer with a primary provider-search interface for candidate retrieval:
  `ContactSearchProviderRequest/Response` keyed by account identity plus target personas/titles.
- Keep `contact_enrichment` optional and use it only when the provider exposes a distinct single-person enrichment step worth calling after provider search.

## Test Plan

- Tool contract tests for Firecrawl search/fetch/scrape, Google Local Places result normalization, OpenAI normalization, public-web company enrichment, Findymail candidate retrieval, and Tomba fallback retrieval or enrichment paths.
- Workflow integration tests for:
  - account search with accepted accounts and no-results outcomes,
  - account research snapshot creation with evidence and uncertainty,
  - contact search persistence, merge behavior, and missing-data flags.
- Chat API end-to-end tests covering:
  - seller/ICP setup -> account search from chat,
  - selected account -> account research from chat,
  - selected account -> contact search from chat,
  - provider/configuration failures surfaced as assistant-visible run failures.
- Precision tests ensuring weak or ambiguous candidates are filtered rather than promoted and invalid structured outputs do not create bad canonical records.

## Assumptions And Defaults

- Phase 3 is not complete unless Findymail-backed contact search works in an environment where you provide the necessary reference materials and credentials.
- Tomba is an allowed fallback provider for contact search, but it should not replace Findymail as the default provider for EU contact search.
- Firecrawl is the default source for account discovery and public research, while Google Local Places is an optional local-business discovery source for account search; no separate paid company enrichment provider is introduced in this phase.
- OpenAI-backed structured normalization and synthesis is the default reasoning engine inside workflows.
- Precision is favored over recall across all workflows.
- The current rules-based orchestrator remains in place for Phase 3; true autonomous agent runtime is deferred until after the vertical slice works.
