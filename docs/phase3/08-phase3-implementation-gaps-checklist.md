# Phase 3 Consistency And Contract-Closure Checklist

## Purpose

- Capture the concrete inconsistencies and instruction mismatches still present in the Phase 3 doc set.
- Propose explicit resolutions so implementers do not have to guess which Phase 3 statement is authoritative.
- Treat this document as a contract-closure checklist for `docs/phase3/...`, not as a parallel long-term spec once the owning slice docs are updated.

## How To Use This Document

- If this document identifies a contradiction, the contradiction should be resolved in the active Phase 3 slice docs before implementation depends on the area.
- The "Proposed Resolution" sections below are the recommended decisions unless the team intentionally chooses a different explicit contract.
- After a resolution is adopted in the owning slice docs, the corresponding checklist item should be marked complete or removed.

## Current Assessment

- The Phase 3 direction is now coherent at a high level:
  - Firecrawl is the primary provider for account discovery and account research evidence.
  - Google Local Places is an optional account-search supplement for place-centric companies.
  - Findymail is the primary contact-search provider.
  - Tomba is a constrained fallback contact-search provider.
  - OpenAI is the structured reasoning and synthesis layer.
- The main remaining risk is no longer "missing direction" in the abstract.
- The main remaining risk is that some Phase 3 slice docs still define the same contract in incompatible ways.
- The preferred implementation interpretation for Phase 3 is now also clearer:
  - the tool layer should speak one internal system contract
  - each external provider should translate to and from that internal contract at the adapter boundary
  - workflows should not consume raw vendor-specific payloads directly

## Status Update

- The highest-priority inconsistencies from this checklist have now been routed into the active Phase 3 slice docs.
- Items 1 through 6 below should now be treated as resolution records and audit notes unless later edits reintroduce drift.
- The remaining work in this checklist is to keep the active Phase 3 doc set aligned with itself and close any secondary gaps that still need stronger wording.

## Highest-Priority Inconsistencies That Were Resolved In The Owning Slice Docs

### 1. Account Research Output Schema Mismatch

Issue:
- The reasoning-layer doc and the account-research slice define different field names for what should be the same research output contract.

Conflicting docs:
- `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`
- `docs/phase3/provider-backed-vertical-slice/04-account-research-provider-slice.md`

What currently conflicts:
- reasoning layer uses:
  - `account_overview`
  - `icp_fit_summary`
  - `evidence_refs[]`
  - `snapshot_quality`
- account-research slice uses:
  - `overview_summary`
  - `fit_summary`
  - `evidence_ref_ids[]`
- the account-research slice does not currently carry `snapshot_quality`

Why this matters:
- One implementation cannot satisfy both docs without inventing field aliases or hidden translation rules.
- This will create avoidable bugs in schema validation, persistence mapping, tests, and frontend summary rendering.

Proposed resolution:
- Freeze one canonical account-research snapshot shape and use it in both docs.
- Recommended canonical schema:
  - `overview_summary`
  - `fit_summary`
  - `key_findings[]`
  - `risks[]`
  - `uncertainty_notes[]`
  - `evidence_ref_ids[]`
  - `snapshot_quality`
  - `missing_context_flags[]`
- Use snapshot-oriented naming rather than reasoning-oriented naming.
- Update the reasoning-layer doc to match the workflow-owned snapshot contract instead of defining alternate names.
- Keep `snapshot_quality` because it is useful for downstream UX, verification, and uncertainty handling.

Recommended completion action:
- Update `02-openai-structured-reasoning-layer.md` and `04-account-research-provider-slice.md` so they define the exact same schema.

### 2. Run-Event Contract Mismatch

Issue:
- Some Phase 3 docs describe the run-event model as mostly unchanged except for richer provider metadata.
- The chat/frontend slice defines a broader event taxonomy with new categories such as reasoning validation, candidate acceptance, and provider-routing decisions.

Conflicting docs:
- `docs/phase3/00-provider-backed-vertical-slice.md`
- `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`
- `docs/phase3/provider-backed-vertical-slice/06-chat-and-frontend-completion.md`

What currently conflicts:
- high-level docs imply metadata enrichment only
- chat/frontend doc implies additive event-category expansion

Why this matters:
- Implementation teams will not know whether they are allowed to introduce new event categories or only enrich existing ones.
- Verification and frontend projection logic depend on this distinction.

Proposed resolution:
- Make the contract explicit:
  - the run-event envelope remains stable
  - the event taxonomy expands additively in Phase 3
  - provider metadata enrichment is part of that expansion, not a substitute for it
- Recommended Phase 3 standard categories:
  - `workflow.started`
  - `tool.started`
  - `tool.completed`
  - `tool.failed`
  - `reasoning.validated`
  - `reasoning.failed_validation`
  - `candidate.accepted`
  - `candidate.rejected`
  - `provider.routing_decision`
  - `workflow.completed`
- Clarify that "existing run/event plumbing remains stable" means the durable projection model stays in place, not that the category set is frozen.

Recommended completion action:
- Update the overview and runtime-wiring docs so they explicitly allow additive event-category expansion.

### 3. Contact Provider Routing Ambiguity

Issue:
- The contact-search docs say Findymail is the required primary provider for Phase 3.
- The same doc also phrases routing as "prefer Findymail for EU contact search," which leaves the non-EU default path ambiguous.

Conflicting docs:
- `docs/phase3/00-provider-backed-vertical-slice.md`
- `docs/phase3/provider-backed-vertical-slice/00-provider-backed-slice-overview.md`
- `docs/phase3/provider-backed-vertical-slice/05-contact-search-findymail-slice.md`

Why this matters:
- The provider default determines adapter wiring, test cases, fallback behavior, and completion criteria.
- An ambiguous default will create inconsistent implementations across environments.

Proposed resolution:
- Freeze the Phase 3 routing policy as:
  - Findymail is the default primary provider for all contact search
  - EU-sensitive routing is the strongest reason to keep Findymail as primary
  - Tomba is fallback-only in Phase 3
- Allow fallback to Tomba only for:
  - missing credentials
  - provider unavailable
  - quota or credit exhaustion
  - unsupported input shape
  - explicit no-results from the primary provider path
- Do not use geography to switch the default provider away from Findymail in normal operation.
- Preserve the routing basis in run metadata when region-sensitive reasoning is used.

Recommended completion action:
- Rewrite the routing language in `05-contact-search-findymail-slice.md` so "prefer Findymail for EU" does not sound like "Findymail is only primary for EU."

### 4. Google Local Places Invocation Rule Drift

Issue:
- The account-search slice uses two different standards for when Google Local Places may run.

Conflicting doc:
- `docs/phase3/provider-backed-vertical-slice/03-account-search-provider-slice.md`

What currently conflicts:
- one section requires all of:
  - local-business intent
  - geographic targeting
  - place-centric vertical
- another section says Places may be used whenever the target is place-centric or location-bound

Why this matters:
- This changes query volume, search budget, and result quality.
- It also changes whether Google Local Places is a narrowly targeted supplement or a broad secondary search engine.

Proposed resolution:
- Freeze one invocation rule:
  - Google Local Places may run when the target is place-centric or location-bound
  - and there is either explicit geographic targeting or strong location evidence in seller, ICP, or user instructions
- Keep Firecrawl as the default first-pass source.
- Use Google Local Places as:
  - first-pass only when the user request is clearly local from the start
  - otherwise a second-pass supplement when Firecrawl results are weak or ambiguous for a place-centric search
- Keep the per-run budget small:
  - max `2` Google Local Places lookups

Recommended completion action:
- Update the query-budget section and the workflow flow section in `03-account-search-provider-slice.md` so they use the same trigger rule.

### 5. Contact Candidate Shape Mismatch

Issue:
- The reasoning-layer doc defines `acceptance_reason` in normalized contact outputs.
- The contact-provider request and response section does not include `acceptance_reason` in its normalized candidate shape.

Conflicting docs:
- `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`
- `docs/phase3/provider-backed-vertical-slice/05-contact-search-findymail-slice.md`

Why this matters:
- Ranking, persistence review, and chat summaries all benefit from a compact acceptance rationale.
- If the field is real, it should be in the normalized contract.
- If the field is reasoning-only, the docs should say that clearly.

Proposed resolution:
- Keep `acceptance_reason` in the reasoning output schema.
- Add `acceptance_reason` to the normalized accepted-contact shape that exits ranking and flows into persistence and summaries.
- Keep provider-origin fields separate from workflow-judgment fields:
  - provider-origin fields:
    - `full_name`
    - `email`
    - `linkedin_url`
    - `job_title`
    - `company_domain`
    - `source_provider`
    - `missing_fields[]`
    - `evidence_refs[]`
  - workflow-judgment fields:
    - `confidence_0_1`
    - `acceptance_reason`

Recommended completion action:
- Update the contact slice so the normalized candidate contract matches the reasoning output that the workflow actually consumes.

### 6. Deferred-Item Wording Mismatch For Routing

Issue:
- The rollout doc says multi-provider routing and fallback strategy is deferred.
- The contact-search slice already treats Findymail-primary and Tomba-fallback routing as a required Phase 3 behavior.

Conflicting docs:
- `docs/phase3/provider-backed-vertical-slice/05-contact-search-findymail-slice.md`
- `docs/phase3/provider-backed-vertical-slice/07-rollout-and-verification.md`

Why this matters:
- It makes "done" ambiguous.
- A reader could reasonably conclude that routing is both required and deferred.

Proposed resolution:
- Narrow the deferred-item wording.
- Recommended wording:
  - deferred:
    - broader multi-provider routing beyond the explicit Findymail-primary and Tomba-fallback policy for Phase 3
    - tenant-specific provider strategy
    - dynamic optimization across multiple contact providers
- Do not describe the explicit Phase 3 routing policy itself as deferred.

Recommended completion action:
- Update the deferred-items section in `07-rollout-and-verification.md`.

## Important Secondary Gaps Still Worth Freezing

These are no longer the biggest contradictions, but they still need explicit closure before implementation is smooth.

### 7. Chat Trigger Preconditions Need To Be Made Explicit

Current problem:
- The chat/frontend slice says workflows begin with the required context selected, but it does not freeze the exact required context for each workflow.

Proposed resolution:
- Freeze per-workflow prerequisites:
  - account search:
    - seller context required
    - ICP context required
  - account research:
    - selected account required
    - seller context required
    - ICP context optional
  - contact search:
    - selected account required
    - seller context required
    - ICP context optional
    - latest research context optional but allowed
- Require backend validation to remain the source of truth.
- Require chat summaries to explain missing prerequisites in human-readable language.

### 8. Runtime Contract Should Freeze One Adapter Pattern

Current problem:
- The runtime-wiring doc suggests a narrow adapter surface, but "where applicable" still leaves too much room for per-provider improvisation.
- Without a stronger statement, implementers could still let provider-specific payloads leak upward into workflows and tool orchestration.

Proposed resolution:
- Freeze one adapter interpretation for the tool layer:
  - the system should expose a small set of internal request, response, and error contracts
  - workflows and tool orchestration should use those internal contracts only
  - each provider adapter should translate:
    - internal request shape -> provider request shape
    - provider response shape -> internal normalized response shape
    - provider-specific errors -> internal normalized error shape
- Freeze one provider-adapter convention by capability:
  - account-search and account-research web adapters:
    - `search(...)`
    - `fetch(...)`
    - `scrape(...)`
    - `map(...)` when supported
    - `healthcheck(...)`
  - contact-search adapters:
    - `search(...)`
    - `lookup_person(...)`
    - `lookup_profile(...)`
    - `enrich(...)`
    - `verify(...)`
    - `healthcheck(...)`
- Keep adapter names capability-oriented rather than forcing every provider into identical fake verbs.
- Treat adapters as translators, not as places where workflow policy is invented.
- Do not let raw Findymail, Tomba, Firecrawl, or Google Local Places payloads become the workflow-facing contract.

### 9. Evidence Shape Should Be Identical Across Workflow Slices

Current problem:
- The account-search, account-research, and contact-search docs all point toward the same evidence shape, but they currently restate it separately.

Proposed resolution:
- Freeze one provider-evidence contract used by all three workflows:
  - `provider_name`
  - `provider_object_id`
  - `source_url`
  - `provider_request_summary`
  - `captured_fields`
  - `captured_at`
  - `confidence_note`
  - `uncertainty_note`
- Keep workflow-specific fields outside the shared evidence envelope.

### 10. Canonical Mapping Rules Should Be Upgraded From Guidance To Contract

Current problem:
- Several slices say existing non-empty canonical values should generally win unless new evidence is stronger and identity-safe.
- That is good guidance, but it is still too soft for deterministic tests.

Proposed resolution:
- Freeze the following defaults:
  - never overwrite canonical fields with empty values
  - exact identity match is required before destructive canonical replacement
  - provider metadata and supporting alternates may still persist as evidence even when canonical overwrite is rejected
  - same-domain plus weak-name similarity is never enough for destructive contact merge

## Proposed Canonical Phase 3 Decisions

If the team wants one compact view of the recommended contract state, use this:

### Research Schema

- Canonical research snapshot fields:
  - `overview_summary`
  - `fit_summary`
  - `key_findings[]`
  - `risks[]`
  - `uncertainty_notes[]`
  - `evidence_ref_ids[]`
  - `snapshot_quality`
  - `missing_context_flags[]`

### Event Model

- Keep the existing durable run-event plumbing.
- Allow additive Phase 3 categories.
- Treat event taxonomy expansion as intentional contract evolution, not accidental drift.

### Contact Routing

- Findymail is the default primary provider for Phase 3 contact search.
- Tomba is fallback-only in Phase 3.
- EU-sensitive routing strengthens the case for Findymail; it does not redefine the default provider away from Findymail.

### Google Local Places

- Firecrawl remains the default discovery provider.
- Google Local Places is used only for place-centric or location-bound searches with actual geographic grounding.
- Google Local Places is usually a second-pass supplement unless the user request is clearly local from the beginning.

### Normalized Contact Shape

- Recommended accepted-contact shape:
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

### Adapter Interpretation

- The tool layer should have one internal language, not one language per provider.
- Provider adapters should be translation boundaries.
- Each adapter should translate:
  - our internal request types into vendor-specific calls
  - vendor-specific responses into our normalized result types
  - vendor-specific failures into our normalized error categories
- Workflow code should make provider-routing decisions when needed, but should not parse raw vendor payloads directly.
- "Universal adapter mechanism" should mean universal internal contracts with provider-specific translation, not fake provider uniformity.

## Definition Of Ready For Implementation

Phase 3 should be treated as ready for coding only when:
- the account-research schema is frozen in one form across the reasoning and workflow docs
- the run-event taxonomy is explicitly described as additive, not merely metadata enrichment
- Findymail and Tomba routing language is unambiguous
- Google Local Places trigger rules are defined in one consistent way
- the normalized contact candidate shape is consistent across reasoning and workflow docs
- the adapter boundary is explicitly defined as internal-contract-first with provider-specific translation underneath
- chat-trigger prerequisites are explicit per workflow
- the active Phase 3 docs stay aligned while behavior is still unimplemented
- implemented behavior is then treated as owned by code

## Recommended Doc Update Order

Recommended order:
1. `docs/phase3/provider-backed-vertical-slice/04-account-research-provider-slice.md`
2. `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`
3. `docs/phase3/provider-backed-vertical-slice/05-contact-search-findymail-slice.md`
4. `docs/phase3/provider-backed-vertical-slice/03-account-search-provider-slice.md`
5. `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`
6. `docs/phase3/provider-backed-vertical-slice/06-chat-and-frontend-completion.md`
7. `docs/phase3/provider-backed-vertical-slice/07-rollout-and-verification.md`

## Final Recommendation

- Use this checklist to resolve the remaining Phase 3 doc contradictions before implementation accelerates.
- The strongest near-term move is to stop treating the biggest gaps as open-ended "missing specs" and instead adopt a small set of explicit canonical resolutions.
- Build the runtime slice around a universal internal tool contract and provider-specific translation adapters so later workflow slices can plug into one system language.
- Once those are reflected in the owning slice docs, this checklist should shrink substantially or be removed.
