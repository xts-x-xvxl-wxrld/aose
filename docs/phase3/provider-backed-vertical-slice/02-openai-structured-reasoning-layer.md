# OpenAI Structured Reasoning Layer

## Purpose And Scope

- Define the Phase 3 slice that replaces skeleton reasoning and null normalization with OpenAI-backed structured workflow reasoning.
- Scope this slice to prompt ownership, schema-validated outputs, fallback behavior, and workflow integration points.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/provider-backed-vertical-slice/00-provider-backed-slice-overview.md`.
- Depends on `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`.
- Current implemented reasoning integration behavior is owned by code.

## Decision Summary

- OpenAI-backed structured reasoning is the default engine for candidate extraction, research synthesis, and contact ranking in Phase 3.
- Workflow-owned reasoning helpers should produce schema-validated outputs rather than free-form text.
- Invalid or incomplete structured outputs must degrade into explicit uncertainty or deterministic baseline behavior instead of fabricated certainty.
- The reasoning path should follow the same adapter rule as the rest of the tool layer: workflows consume internal request and response contracts, while the OpenAI-facing adapter translates model-specific payloads underneath.

## Recommended Structured Output Contracts

- Account-search reasoning should emit a schema with:
  - `query_summary`
  - `accepted_candidates[]`
  - `rejected_candidates[]`
  - `no_result_reason`
  - `confidence`
  - `missing_data_flags[]`
  - `evidence_refs[]`
- Each account-search candidate should include:
  - `name`
  - `domain`
  - `website_url`
  - `hq_location`
  - `industry`
  - `fit_summary`
  - `fit_score_0_1`
  - `why_selected`
  - `missing_fields[]`
  - `evidence_refs[]`
- Contact-search reasoning should emit a schema with:
  - `accepted_contacts[]`
  - `rejected_contacts[]`
  - `ranking_notes`
  - `confidence`
  - `missing_data_flags[]`
- Each contact candidate should include:
  - `full_name`
  - `email`
  - `linkedin_url`
  - `job_title`
  - `company_domain`
  - `source_provider`
  - `acceptance_reason`
  - `confidence_0_1`
  - `missing_fields[]`
  - `evidence_refs[]`
- Account-research reasoning should emit a schema with:
  - `overview_summary`
  - `fit_summary`
  - `key_findings[]`
  - `risks[]`
  - `uncertainty_notes[]`
  - `evidence_ref_ids[]`
  - `snapshot_quality`
  - `missing_context_flags[]`

## Prompt And Validation Defaults

- Prompt specs should remain workflow-owned and must not imply autonomous tool selection beyond the workflow logic that already exists.
- Schema validation should happen before any workflow-owned persistence decision.
- If a model response cannot be parsed into the required schema, workflows should not persist new canonical records from that output.
- Validation failure should fall back to deterministic filtering and explicit uncertainty rather than free-form interpretation of malformed output.
- Partial but schema-valid outputs may proceed only when missing fields remain explicit and do not imply fabricated certainty.

## Title And Persona Normalization Defaults

- Seller and ICP personas should be normalized into a small canonical role vocabulary before provider-facing contact-search prompts execute.
- Findymail role search should be limited to at most `3` normalized roles.
- Reasoning should collapse synonymous titles into compact role clusters such as:
  - executive
  - founder
  - sales leader
  - marketing leader
  - operations leader
- Broad or ambiguous titles should be narrowed before provider execution instead of being searched as-is.
- Tomba-oriented prompts should assume named-person or LinkedIn-driven follow-up rather than role-first search, because the available local provider resources do not expose a direct role-based search path.

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the current `content_normalizer` tool concept and specialist workflow result contracts.
- Expected additions in this slice:
  - workflow-scoped prompt specs for account search, account research, and contact search
  - schema-owned structured output shapes for candidate extraction, research synthesis, and contact ranking
  - helper interfaces for invoking OpenAI-backed structured reasoning from workflows
  - an OpenAI-facing reasoning adapter under `src/app/tools/` that converts internal reasoning requests into model calls and validated normalized outputs

## Data Flow / State Transitions

- Workflows gather provider data and public-web evidence.
- Workflow-owned reasoning helpers submit structured reasoning requests through an internal reasoning contract rather than constructing raw model payloads inline.
- The OpenAI-facing adapter translates those requests into model-specific prompts or response-format calls.
- Responses are validated against workflow-owned schemas.
- Valid outputs continue to persistence and result assembly.
- Invalid outputs fall back to uncertainty-preserving baseline behavior.
- Title and persona normalization should happen before provider-facing contact-search reasoning decides how to search or rank candidates.

## Failure Modes And Edge-Case Rules

- Prompt or model failures must not create canonical records from unvalidated output.
- A reasoning helper returning partial data should preserve uncertainty instead of filling missing fields speculatively.
- Prompt instructions should not imply autonomous handoff behavior that does not exist at runtime.
- Validation failures should degrade into deterministic baseline behavior rather than ad hoc parsing of semi-structured responses.

## Validation, Ownership, And Permission Rules

- Workflows own when reasoning is invoked and how outputs are consumed.
- Prompt specs and schemas belong to the workflow layer, not the orchestrator.
- Structured reasoning does not own persistence or authorization behavior.
- OpenAI-specific request shaping and response parsing belong in the adapter boundary, not in workflow bodies.

## Persistence Impact

- No new canonical persistence model is introduced by this slice alone.
- This slice influences the shape and confidence of persisted workflow outputs owned by downstream workflow slices.

## API / Events / Artifact Impact

- Public API shapes remain unchanged.
- This slice may clarify workflow-facing normalized payload shapes and error summaries when reasoning validation fails.
- For contact-search outputs, accepted-contact normalization should preserve workflow-judgment fields such as `confidence_0_1` and `acceptance_reason` alongside provider-origin fields.

## Implementation Acceptance Criteria

- Skeleton specialist prompt text is replaced by workflow-scoped prompt specs.
- Account search, account research, and contact search each have a schema-validated reasoning path.
- Failure handling is explicit enough that the system never claims structured certainty from invalid model output.
- Title and persona normalization behavior is explicit enough to drive provider-backed contact search deterministically.

## Verification

- Add reasoning-helper tests for schema validation, fallback behavior, and workflow-specific prompt contract expectations as implementation begins.

## Deferred Items

- Fully autonomous specialist-agent execution loops.
- Prompt-driven tool selection outside workflow-owned control flow.
