# Account Research Provider Slice

## Purpose And Scope

- Define the Phase 3 slice that turns account research into a functioning provider-backed workflow.
- Scope this slice to Firecrawl-backed evidence gathering, OpenAI-backed synthesis, and snapshot-quality research persistence.

## Dependencies On Earlier Docs

- Depends on `docs/phase3/provider-backed-vertical-slice/01-provider-config-and-runtime-wiring.md`.
- Depends on `docs/phase3/provider-backed-vertical-slice/02-openai-structured-reasoning-layer.md`.
- Current implemented account-research behavior is owned by code.

## Decision Summary

- Account research gathers a compact, high-signal evidence set rather than maximizing raw source count.
- Firecrawl is the public-web evidence path for selected-account research.
- OpenAI-backed structured synthesis builds the research record, fit analysis, uncertainty notes, and optional research brief content.
- Research output should remain source-aware and explicit about uncertainty.

## Recommended Research Snapshot Contract

- Research snapshots should include:
  - `overview_summary`
  - `fit_summary`
  - `key_findings[]`
  - `risks[]`
  - `uncertainty_notes[]`
  - `evidence_ref_ids[]`
  - `snapshot_quality`
  - `missing_context_flags[]`
- Optional artifact sections should be derived from the same canonical research snapshot rather than becoming a second source of truth.
- If ICP context is missing, the snapshot should include explicit `missing_context_flags[]` markers instead of implying fit certainty.

## Evidence And Fetch Budget Defaults

- Account research should prefer a compact evidence set over a large dossier in this phase.
- Default research collection budget should remain small and bounded, using only the pages needed to support a defensible snapshot.
- Firecrawl evidence collection should reach the workflow as normalized internal tool outputs rather than raw provider payloads.
- Evidence persisted from provider-backed research should preserve:
  - `provider_name`
  - `provider_object_id` when available
  - `source_url`
  - `provider_request_summary`
  - `captured_fields`
  - `captured_at`
  - `confidence_note`
  - `uncertainty_note`

## Canonical Models / Types / Interfaces Introduced Or Consumed

- Consumes the existing account-research workflow, snapshot, evidence, and artifact contracts.
- Expected additions in this slice:
  - Firecrawl-backed search and page-collection behavior used by account research
  - account-research-specific synthesis schema and structured output expectations
  - optional artifact rendering rules refined for provider-backed research output
  - account-research-facing internal evidence-collection tool contracts consumed from `src/app/tools/contracts.py`

## Data Flow / State Transitions

- Workflow loads selected account, seller context, and optional ICP context.
- Firecrawl-backed collection gathers public-web evidence for a narrow set of relevant sources through normalized tool interfaces owned by the runtime slice.
- OpenAI-backed synthesis produces structured research summaries and uncertainty notes.
- Evidence persists first, then snapshot and optional artifact outputs persist through current contracts.

## Failure Modes And Edge-Case Rules

- Limited evidence should reduce certainty rather than block snapshot creation by default.
- Invalid synthesis output should not create malformed snapshots.
- Account research should not imply ICP-fit certainty when ICP context is missing.
- Research output should remain append-only and source-aware even when only a compact evidence set is available.

## Validation, Ownership, And Permission Rules

- Account research remains a workflow-owned synthesis and persistence path.
- Structured reasoning remains subordinate to evidence and validation.
- Research snapshots remain append-only.
- Provider-specific fetch and scrape response parsing belongs in adapters under `src/app/tools/`, not in account-research workflow bodies.

## Persistence Impact

- Evidence persists to `SourceEvidence`.
- Research snapshots persist to the current account-research snapshot model.
- Optional research artifacts persist through the current artifact path when generated.

## API / Events / Artifact Impact

- No new route surface is required.
- Run events should reflect real search, fetch, scrape, and synthesis steps.

## Implementation Acceptance Criteria

- Account research can execute end to end with real provider-backed evidence gathering.
- Snapshot creation remains source-aware, uncertainty-preserving, and append-only.
- Optional artifact generation stays aligned with the canonical research snapshot rather than becoming a second source of truth.
- Snapshot schema, evidence shape, and missing-context behavior are explicit enough to support deterministic tests.

## Verification

- Add workflow tests for evidence persistence, snapshot creation, ICP-optional behavior, and synthesis fallback handling.

## Deferred Items

- Deep multi-source dossier generation beyond the compact Phase 3 evidence set.
- RAG-backed augmentation.
