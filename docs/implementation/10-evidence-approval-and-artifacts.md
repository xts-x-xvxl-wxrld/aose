# Evidence Approval And Artifacts

## Purpose And Scope

This document defines source evidence handling, approval decisions, and human-readable artifacts for the current milestone.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- [04-api-auth-and-request-context.md](./04-api-auth-and-request-context.md)
- [08-workflow-account-research.md](./08-workflow-account-research.md)
- [09-workflow-contact-search.md](./09-workflow-contact-search.md)

## Decision Summary

- Source-aware evidence is required for external-information workflows.
- Evidence must be linkable to workflow runs and downstream outputs.
- Approval is modeled as a durable decision, not just a transient UI action.
- Artifacts are human-readable renderings of canonical records.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### SourceEvidence

Required concepts:

- source type
- provider name
- source url or provider reference
- title or source label
- captured timestamp
- freshness timestamp when meaningful
- confidence score
- snippet or summary text
- metadata json

Evidence use rules:

- evidence supports research, qualification, and contact reasoning
- evidence does not replace canonical entity records
- evidence may exist even if a workflow fails

### ApprovalDecision

Required concepts:

- linked workflow run
- optional linked artifact
- reviewer identity
- decision
- rationale
- timestamp

### ApprovalDecisionRequest

```python
class ApprovalDecisionRequest(TypedDict):
    decision: str
    rationale: str | None
    artifact_id: str | None
```

Rules:

- `decision` is one of `approved`, `rejected`, `needs_changes`
- `artifact_id` is optional when the review applies to the run as a whole rather than one artifact
- `rationale` is required for `rejected` and `needs_changes`
- `rationale` is optional for `approved`

### ApprovalDecisionResponse

```python
class ApprovalDecisionResponse(TypedDict):
    approval_decision_id: str
    workflow_run_id: str
    artifact_id: str | None
    decision: str
    run_status_after_decision: str
    created_at: str
```

### Artifact

Allowed first-pass artifact types:

- `research_brief`
- `seller_summary`
- `icp_summary`
- `run_summary`
- `review_packet`
- `outreach_draft`

Allowed first-pass formats:

- `markdown`
- `json`
- `external_pointer`

## Data Flow / State Transitions

Evidence flow:

1. worker gathers source-aware external information
2. normalized evidence is persisted
3. canonical workflow outputs reference evidence ids

Artifact flow:

1. canonical data is persisted
2. service optionally renders markdown or structured artifact
3. artifact is linked to workflow run

Approval flow:

1. run reaches review gate or artifact is submitted for review
2. reviewer loads linked artifact and evidence through tenant-scoped read endpoints
3. reviewer submits `POST /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals`
4. service validates reviewer role, artifact linkage, and current run state
5. service stores `ApprovalDecision`
6. run continues or fails based on decision outcome

## Failure Modes And Edge-Case Rules

- If a source lacks sufficient attribution, it may not be used as strong evidence.
- If evidence conflicts, preserve both the conflict and the uncertainty rather than selecting one silently.
- If a markdown artifact cannot be generated, canonical structured outputs remain valid.
- If an approval request references an artifact outside the reviewed run, reject it.
- If a review decision is submitted when the run is not in `awaiting_review`, reject it unless the route explicitly supports artifact-only review.
- If a review decision is changed later, create a new approval record rather than editing history destructively.

## Validation, Ownership, And Permission Rules

- only tenant members may view tenant evidence and artifacts
- only `owner`, `admin`, and `reviewer` may issue approval decisions
- `approved` maps the reviewed run to `succeeded`
- `rejected` maps the reviewed run to `failed`
- `needs_changes` maps the reviewed run to `failed` in Phase 1 and requires a new run for resubmission
- artifacts must not be generated from unvalidated fabricated content

## Persistence Impact

- `SourceEvidence`, `Artifact`, and `ApprovalDecision` are canonical persisted models
- artifacts may store markdown inline or point to external storage
- approval history must remain durable

## API / Events / Artifact Impact

- workflow inspection responses may include evidence summaries, artifact references, and approval summaries
- review-related actions should emit stable run events when tied to a workflow run
- `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence` and `GET /api/v1/tenants/{tenant_id}/artifacts/{artifact_id}` are the reviewer read surface in Phase 1
- `approved` decisions should lead to `run.completed`; `rejected` and `needs_changes` decisions should lead to `run.failed`

## Implementation Acceptance Criteria

- research outputs can be traced back to evidence
- approval decisions are durable and actor-attributed
- markdown is clearly treated as an artifact layer over canonical data

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_workflow_doc_expectations.py](../../tests/docs/test_workflow_doc_expectations.py) `::test_evidence_doc_keeps_traceability_and_approval_contract`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_workflow_docs_only_reference_defined_persisted_models`

## Deferred Items

- automated evidence scoring heuristics
- redlining artifacts in-place
- external reviewer sharing
- in-place revision loops for `needs_changes`
