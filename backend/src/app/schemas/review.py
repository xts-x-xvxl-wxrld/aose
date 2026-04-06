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


class WorkflowRunProviderAttemptResponse(BaseModel):
    provider_name: str | None
    tool_name: str
    operation: str
    attempt_number: int
    request_summary: str | None = None
    outcome: str
    error_code: str | None = None
    produced_evidence_results: bool = False


class WorkflowRunFallbackDecisionResponse(BaseModel):
    capability: str | None = None
    from_provider: str | None = None
    to_provider: str
    fallback_provider: str | None = None
    trigger_reason: str | None = None
    routing_basis: str | None = None
    allowed: bool | None = None
    decision_summary: str | None = None


class WorkflowRunReasoningValidationResponse(BaseModel):
    schema_name: str
    provider_name: str | None = None
    status: str
    failure_summary: str | None = None
    fallback_summary: str | None = None
    output_summary: str | None = None


class WorkflowRunDebugResponse(BaseModel):
    workflow_run_id: UUID
    thread_id: UUID | None
    workflow_type: str
    workflow_status: WorkflowRunStatus
    requested_payload_json: dict[str, Any]
    normalized_result_json: dict[str, Any] | None = None
    provider_attempts: list[WorkflowRunProviderAttemptResponse]
    fallback_decisions: list[WorkflowRunFallbackDecisionResponse]
    reasoning_validation: list[WorkflowRunReasoningValidationResponse]
    user_summary_snapshot: str | None = None
    terminal_outcome_family: str
    summary_selection_reason: str | None = None


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
