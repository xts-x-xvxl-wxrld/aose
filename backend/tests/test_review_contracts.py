from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.orchestration.contracts import WorkflowRunStatus
from app.schemas.review import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ArtifactResponse,
    SourceEvidenceResponse,
    WorkflowRunEvidenceListResponse,
)


def test_approval_decision_request_requires_rationale_for_negative_decisions() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        ApprovalDecisionRequest(decision="rejected")

    with pytest.raises(ValidationError, match="rationale"):
        ApprovalDecisionRequest(decision="needs_changes", rationale="   ")

    request = ApprovalDecisionRequest(decision="approved")

    assert request.rationale is None


def test_review_response_models_match_phase_1_contract_shapes() -> None:
    created_at = datetime.now(timezone.utc)
    evidence = SourceEvidenceResponse(
        evidence_id=uuid4(),
        workflow_run_id=uuid4(),
        account_id=uuid4(),
        contact_id=None,
        source_type="web",
        provider_name="example-search",
        source_url="https://example.com",
        title="Example Source",
        snippet_text="Summary",
        captured_at=created_at,
        freshness_at=None,
        confidence_score=0.75,
        metadata_json={"rank": 1},
        created_at=created_at,
    )
    evidence_list = WorkflowRunEvidenceListResponse(evidence=[evidence], next_cursor=None)
    artifact = ArtifactResponse(
        artifact_id=uuid4(),
        tenant_id=uuid4(),
        workflow_run_id=uuid4(),
        created_by_user_id=uuid4(),
        artifact_type="review_packet",
        format="json",
        title="Review Packet",
        content_markdown=None,
        content_json={"status": "awaiting_review"},
        storage_url=None,
        created_at=created_at,
        updated_at=created_at,
    )
    approval = ApprovalDecisionResponse(
        approval_decision_id=uuid4(),
        workflow_run_id=uuid4(),
        artifact_id=artifact.artifact_id,
        decision="approved",
        run_status_after_decision=WorkflowRunStatus.SUCCEEDED,
        created_at=created_at,
    )

    assert evidence_list.next_cursor is None
    assert artifact.artifact_type == "review_packet"
    assert approval.run_status_after_decision is WorkflowRunStatus.SUCCEEDED
