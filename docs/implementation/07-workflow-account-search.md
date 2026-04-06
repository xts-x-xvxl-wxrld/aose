# Workflow Account Search

## Purpose And Scope

This document defines the canonical account search workflow, including iterative search behavior, shortlist creation, and transition into account research.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- [05-service-worker-and-tool-boundaries.md](./05-service-worker-and-tool-boundaries.md)
- [06-workflow-seller-and-icp-setup.md](./06-workflow-seller-and-icp-setup.md)

## Decision Summary

- Account search is a workflow-backed operation by default.
- The orchestrator starts account search only when seller and ICP context are sufficiently clear.
- The account search agent owns strategy and fit reasoning.
- The service and tool layer owns search execution, normalization, and persistence.
- Search is explicitly iterative; the first pass is not assumed to be final.
- Account search requires an explicit `icp_profile_id` in Phase 1.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### Account Search Inputs

- tenant-scoped seller profile
- tenant-scoped ICP profile
- optional search objective text
- optional user targeting constraints

### Account Search Agent Output

- `search_strategy`
- `query_ideas`
- `fit_criteria`
- `clarification_questions`

### Canonical Saved Records

- `WorkflowRun`
- `RunEvent`
- `Account`
- optional `SourceEvidence`

### Account Search Run Result

Minimum `WorkflowRun.normalized_result_json` shape:

- `outcome`
- `accepted_account_ids`
- `reason_summary`
- `search_attempt_count`

Rules:

- successful no-results runs use `outcome = no_results`
- successful result-bearing runs use `outcome = accounts_found`
- `accepted_account_ids` is always present, including `[]` for no-results outcomes
- `search_attempt_count` records the completed search/refine cycles for the run

## Data Flow / State Transitions

1. orchestrator determines account search intent
2. service validates seller and ICP availability
3. workflow run is created
4. worker loads seller, ICP, and current constraints
5. worker calls `account_search_agent`
6. tools perform external search or provider lookup
7. service normalizes account candidates
8. worker may call `account_search_agent` again to score or filter results
9. accepted accounts are persisted
10. workflow completes or pauses for review if configured later

Iterative rule:

- the workflow may perform multiple search-and-refine cycles inside one run
- each cycle must be grounded in prior results and stable fit criteria
- the system should not rewrite accepted accounts destructively when refining
- Phase 1 allows at most 2 completed search/refine cycles per run
- the worker should stop early when credible search space is exhausted or enough acceptable accounts have been accepted

## Failure Modes And Edge-Case Rules

- If seller or ICP context is too thin, return clarification guidance instead of weak search.
- If external search returns noisy or sparse results, preserve uncertainty and partial evidence rather than over-normalizing weak matches.
- If a domain collides with an existing tenant-scoped account, update that canonical account instead of inserting a duplicate.
- Domain-collision updates preserve existing canonical field values unless the current run provides a non-empty replacement value.
- If no credible candidates are found, the run may still succeed with an explicit no-results outcome.

## Validation, Ownership, And Permission Rules

- account search requires tenant-owned seller and ICP records
- only `owner`, `admin`, and `member` may trigger search
- all accepted accounts must belong to the same tenant as the workflow run

## Persistence Impact

- accepted accounts persist to `Account`
- search evidence may persist to `SourceEvidence`
- run outcome persists to `WorkflowRun.normalized_result_json`
- no-results outcomes persist `accepted_account_ids = []` instead of using a missing field

## API / Events / Artifact Impact

- workflow inspection must expose accepted account ids
- events should show handoff, tool usage, and completion
- account search does not require markdown artifact generation in the first pass

## Implementation Acceptance Criteria

- account search cannot run without seller and ICP context
- the iterative refinement loop is allowed by design
- accepted accounts become tenant-scoped canonical records
- downstream account research can start from persisted account ids

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_workflow_doc_expectations.py](../../tests/docs/test_workflow_doc_expectations.py) `::test_account_search_doc_keeps_prerequisite_iteration_and_persistence_contract`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_account_search_doc_freezes_result_shape_merge_policy_and_iteration_limit`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_workflow_docs_only_reference_defined_persisted_models`

## Deferred Items

- manual shortlist curation UI
- automatic account suppression lists beyond ICP exclusions
