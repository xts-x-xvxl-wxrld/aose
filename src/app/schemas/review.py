from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.orchestration.contracts import WorkflowRunStatus


ApprovalDecisionLiteral = Literal["approved", "rejected", "needs_changes"]


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecisionLiteral
    rationale: str | None = None
    artifact_id: UUID | None = None

    @model_validator(mode="after")
    def validate_rationale_requirements(self) -> ApprovalDecisionRequest:
        if self.decision in {"rejected", "needs_changes"}:
            if self.rationale is None or not self.rationale.strip():
                raise ValueError(
                    "rationale is required when decision is rejected or needs_changes"
                )
        return self


class ApprovalDecisionResponse(BaseModel):
    approval_decision_id: UUID
    workflow_run_id: UUID
    artifact_id: UUID | None
    decision: ApprovalDecisionLiteral
    run_status_after_decision: WorkflowRunStatus
    created_at: datetime


class SourceEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: UUID
    workflow_run_id: UUID
    account_id: UUID | None
    contact_id: UUID | None
    source_type: str
    provider_name: str | None
    source_url: str | None
    title: str | None
    snippet_text: str | None
    captured_at: datetime | None
    freshness_at: datetime | None
    confidence_score: float | None
    metadata_json: dict[str, Any] | None
    created_at: datetime


class WorkflowRunEvidenceListResponse(BaseModel):
    evidence: list[SourceEvidenceResponse]
    next_cursor: str | None = None


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: UUID
    tenant_id: UUID
    workflow_run_id: UUID | None
    created_by_user_id: UUID | None
    artifact_type: str
    format: str
    title: str
    content_markdown: str | None
    content_json: dict[str, Any] | None
    storage_url: str | None
    created_at: datetime
    updated_at: datetime
