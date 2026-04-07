# Workflow Contact Search

## Purpose And Scope

This document defines the workflow for identifying and ranking contact candidates within a selected account.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- [05-service-worker-and-tool-boundaries.md](./05-service-worker-and-tool-boundaries.md)
- [06-workflow-seller-and-icp-setup.md](./06-workflow-seller-and-icp-setup.md)
- [08-workflow-account-research.md](./08-workflow-account-research.md)

## Decision Summary

- Contact search is workflow-backed by default.
- The contact search agent owns persona and ranking reasoning.
- The service/tool layer owns provider lookups, normalization, dedupe, and persistence.
- Contact confidence is limited; the system must preserve missing-data flags.
- Latest account research context is optional in Phase 1 and is consumed opportunistically when present.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### Contact Search Inputs

- account context
- seller profile
- optional ICP profile
- optional account research snapshot
- optional contact objective

### Contact Search Agent Output

- `target_personas`
- `selection_criteria`
- `ranked_contact_rationale`
- `missing_data_flags`

### Canonical Saved Records

- `Contact`
- optional `SourceEvidence`
- `WorkflowRun`
- `RunEvent`

### Missing Data Flags

Stable Phase 1 `missing_data_flags` values:

- `missing_email`
- `missing_linkedin`
- `missing_job_title`
- `low_source_confidence`
- `role_match_uncertain`

### Contact Search Run Result

Minimum `WorkflowRun.normalized_result_json` shape:

- `outcome`
- `contact_ids`
- `missing_data_flags`
- `used_research_snapshot_id`
- `reason_summary`

Rules:

- successful contact-search runs use `outcome = contacts_ranked`
- `contact_ids` is always present, including `[]` for zero-result runs
- `used_research_snapshot_id` may be `null` when no research snapshot was available

## Data Flow / State Transitions

1. orchestrator or service starts contact search for a selected account
2. worker loads account context and latest research context when available
3. worker calls `contact_search_agent`
4. tools/connectors query contact providers or public research sources
5. service normalizes person records
6. dedupe logic merges or inserts canonical contacts
7. ranking summaries and missing-data flags are persisted
8. workflow completes

## Failure Modes And Edge-Case Rules

- If no credible people are found, the run may succeed with zero results and explicit missing-data notes.
- If partial contact data exists without enough evidence for strong ranking, keep the candidate with low-confidence or missing-data flags instead of inflating confidence.
- If the same person appears from multiple sources, merge into one canonical contact within the tenant/account boundary.
- automatic merge precedence is exact email match within the tenant/account, then exact LinkedIn URL within the tenant/account
- name-plus-title similarity alone is not enough for automatic merge in Phase 1

## Validation, Ownership, And Permission Rules

- contact search requires a tenant-owned account
- actor must have access to the relevant seller and account context
- only `owner`, `admin`, and `member` may trigger contact search
- reviewers may inspect outputs and artifacts later, but do not create contacts

## Persistence Impact

- canonical people records persist in `Contact`
- evidence may persist in `SourceEvidence`
- contact search does not create research snapshots
- missing-data flags persist as machine-readable values in canonical contact data and run results

## API / Events / Artifact Impact

- workflow inspection should expose resulting contact ids
- markdown artifacts are optional and deferred for contact search

## Implementation Acceptance Criteria

- contact search stores normalized contacts rather than only transient ranked text
- missing-data flags are supported
- contact ranking remains tied to account and seller context

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_workflow_doc_expectations.py](../../tests/docs/test_workflow_doc_expectations.py) `::test_contact_search_doc_keeps_normalization_and_missing_data_contract`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_contact_search_doc_freezes_dedupe_precedence_and_missing_data_flags`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_workflow_docs_only_reference_defined_persisted_models`

## Deferred Items

- email verification workflows
- contact sequencing and outreach generation
