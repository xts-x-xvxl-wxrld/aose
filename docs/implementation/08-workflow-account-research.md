# Workflow Account Research

## Purpose And Scope

This document defines the account research workflow that turns a selected account into a structured, source-aware research snapshot.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- [05-service-worker-and-tool-boundaries.md](./05-service-worker-and-tool-boundaries.md)
- [06-workflow-seller-and-icp-setup.md](./06-workflow-seller-and-icp-setup.md)
- [07-workflow-account-search.md](./07-workflow-account-search.md)

## Decision Summary

- Account research is workflow-backed by default.
- Research evaluates a selected account against seller and ICP context, not raw company facts alone.
- Deeper enrichment belongs here, not in account search.
- Research output is append-only via `AccountResearchSnapshot`.
- Uncertainty and source provenance are required parts of the output.
- Account research may run without an ICP in Phase 1, but the output must explicitly record whether ICP context was present.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### Account Research Inputs

- `account_id`
- seller profile
- optional ICP profile
- optional user research objective

### Account Research Agent Output

- `research_plan`
- `evidence_categories`
- `structured_research_summary`
- `uncertainty_notes`

### Research Snapshot Minimum Topics

- account overview
- fit to seller proposition
- fit to ICP
- buying relevance signals
- risks or disqualifiers
- uncertainty notes
- linked evidence ids

### Account Research Run Result

Minimum `WorkflowRun.normalized_result_json` shape:

- `outcome`
- `snapshot_id`
- `snapshot_version`
- `icp_context_present`
- `reason_summary`

Rules:

- successful research runs use `outcome = research_completed`
- `icp_context_present` is required and is `false` when research ran without an ICP
- when `icp_context_present = false`, the research output must omit unsupported ICP-fit claims rather than fabricate them

## Data Flow / State Transitions

1. orchestrator or service starts research for a selected account
2. worker loads account, seller, and ICP context
3. worker calls `account_research_agent` to decide what matters
4. tools and connectors gather evidence and enrichment
5. service validates normalized evidence
6. research snapshot is persisted append-only
7. optional research brief artifact is generated
8. workflow completes or pauses for review if review gating is enabled later

## Failure Modes And Edge-Case Rules

- If the selected account is missing or inaccessible, fail before tool execution.
- If evidence is weak or contradictory, preserve uncertainty rather than flattening to a confident conclusion.
- If enrichment succeeds partially, persist the valid evidence and snapshot what can be defended.
- If a later run re-researches the same account, create a new snapshot version rather than overwriting the prior one.
- snapshot versions increment monotonically per account using the latest persisted version plus one at write time

## Validation, Ownership, And Permission Rules

- account research requires a tenant-owned account
- actor must also have access to the referenced seller and ICP context
- only `owner`, `admin`, and `member` may trigger research
- research outputs remain tenant-scoped and may be reviewed by `reviewer`

## Persistence Impact

- canonical record: `AccountResearchSnapshot`
- supporting records: `SourceEvidence`, optional `Artifact`
- snapshot must link to `workflow_run_id`
- `snapshot_version` is assigned per account as a monotonic integer sequence

## API / Events / Artifact Impact

- workflow inspection should expose latest snapshot id
- artifact type may be `research_brief`
- events should reflect tool usage and review pauses when present

## Implementation Acceptance Criteria

- research output is seller-aware and ICP-aware
- deeper enrichment belongs to research, not search
- snapshots are append-only
- uncertainty notes are persisted when evidence is incomplete

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_workflow_doc_expectations.py](../../tests/docs/test_workflow_doc_expectations.py) `::test_account_research_doc_keeps_snapshot_and_uncertainty_contract`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_account_research_doc_freezes_optional_icp_result_shape_and_versioning`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_workflow_docs_only_reference_defined_persisted_models`

## Deferred Items

- automated qualification scoring beyond structured summary
- outreach generation from research output
