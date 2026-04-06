# Workflow Seller And ICP Setup

## Purpose And Scope

This document defines the seller profile and ICP profile setup workflows that establish the context required by all downstream account and contact workflows.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- [04-api-auth-and-request-context.md](./04-api-auth-and-request-context.md)
- [05-service-worker-and-tool-boundaries.md](./05-service-worker-and-tool-boundaries.md)

## Decision Summary

- Seller and ICP setup are first-class workflows.
- They do not require dedicated specialist agents in the first pass.
- Services and the orchestrator may handle them inline or as a workflow run.
- Seller and ICP context must exist before high-quality search and research can proceed.
- Normal seller and ICP create/update routes are inline-only in Phase 1.
- Downstream workflows require an explicit `icp_profile_id`; Phase 1 does not infer a default ICP.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### SellerProfile Minimum Shape

- `id`
- `tenant_id`
- `name`
- `company_name`
- `company_domain`
- `product_summary`
- `value_proposition`
- `target_market_summary`
- `profile_json`

Expected `profile_json` topics:

- products or services
- buyer pains
- differentiators
- notable customer segments
- optional geography or industry emphasis

### ICPProfile Minimum Shape

- `id`
- `tenant_id`
- `seller_profile_id`
- `name`
- `status`
- `criteria_json`
- `exclusions_json`

Expected `criteria_json` topics:

- target industries
- company size guidance
- geography guidance
- buying triggers
- role or persona relevance

## Data Flow / State Transitions

Seller setup flow:

1. user creates or edits seller context
2. service validates ownership and required fields
3. service persists canonical `SellerProfile`
4. service optionally emits summary artifact
5. conversation summary may reference the active seller profile

ICP setup flow:

1. user creates or edits ICP criteria linked to a seller profile
2. service validates seller ownership within tenant
3. service persists canonical `ICPProfile`
4. service optionally emits summary artifact
5. downstream workflows consume seller + ICP context together

## Failure Modes And Edge-Case Rules

- If seller profile is incomplete, account search may proceed only if the missing data does not block useful search reasoning; otherwise the orchestrator should request clarification.
- If an ICP references invalid or missing seller context, reject the write.
- Multiple ICPs per seller are allowed, but downstream workflows must supply an explicit `icp_profile_id`.

## Validation, Ownership, And Permission Rules

Required fields for initial seller profile creation:

- `name`
- `company_name`
- `product_summary`
- `value_proposition`

Required fields for initial ICP creation:

- `seller_profile_id`
- `name`
- at least one meaningful targeting criterion

Permission rules:

- `owner`, `admin`, `member` may create and edit seller/ICP context
- `reviewer` may view but not edit

## Persistence Impact

- seller and ICP are mutable canonical records
- each update should set `updated_by_user_id`
- optional human-readable summaries belong in `Artifact`

## API / Events / Artifact Impact

- seller and ICP create/update endpoints are required
- setup workflows may emit normal run events when executed as workflow runs
- artifact types may include `seller_summary` and `icp_summary`
- normal seller and ICP create/update routes do not create `WorkflowRun` rows in Phase 1

## Implementation Acceptance Criteria

- downstream workflows can rely on stable seller and ICP records
- missing setup context is surfaced explicitly instead of inferred or fabricated
- seller and ICP writes are tenant-scoped and actor-scoped

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_workflow_doc_expectations.py](../../tests/docs/test_workflow_doc_expectations.py) `::test_setup_workflow_doc_keeps_stable_prerequisite_contract`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_setup_doc_freezes_inline_mode_and_explicit_icp_selection`
- [tests/docs/test_implementation_doc_structure.py](../../tests/docs/test_implementation_doc_structure.py) `::test_child_doc_dependencies_only_point_to_existing_earlier_docs`

## Deferred Items

- multi-step guided onboarding conversation UX
- imported seller data from CRM or uploaded docs
