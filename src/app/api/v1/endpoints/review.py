from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import AuthIdentityDep, DbSessionDep
from app.models import ApprovalDecision, Artifact, SourceEvidence, WorkflowRun
from app.schemas.review import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ArtifactResponse,
    SourceEvidenceResponse,
    WorkflowRunEvidenceListResponse,
)
from app.services.review import ReviewService

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/workflow-runs/{run_id}/evidence",
    response_model=WorkflowRunEvidenceListResponse,
)
async def list_workflow_run_evidence(
    tenant_id: UUID,
    run_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> WorkflowRunEvidenceListResponse:
    evidence = await ReviewService(db_session).list_evidence_for_run(
        identity=identity,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return WorkflowRunEvidenceListResponse(
        evidence=[_to_source_evidence_response(row) for row in evidence],
        next_cursor=None,
    )


@router.get(
    "/tenants/{tenant_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def get_artifact(
    tenant_id: UUID,
    artifact_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> ArtifactResponse:
    artifact = await ReviewService(db_session).get_artifact(
        identity=identity,
        tenant_id=tenant_id,
        artifact_id=artifact_id,
    )
    return _to_artifact_response(artifact)


@router.post(
    "/tenants/{tenant_id}/workflow-runs/{run_id}/approvals",
    response_model=ApprovalDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_approval(
    tenant_id: UUID,
    run_id: UUID,
    payload: ApprovalDecisionRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> ApprovalDecisionResponse:
    approval, updated_run = await ReviewService(db_session).submit_approval(
        identity=identity,
        tenant_id=tenant_id,
        run_id=run_id,
        **payload.model_dump(),
    )
    return _to_approval_response(approval, updated_run)


def _to_source_evidence_response(row: SourceEvidence) -> SourceEvidenceResponse:
    return SourceEvidenceResponse(
        evidence_id=row.id,
        workflow_run_id=row.workflow_run_id,
        account_id=row.account_id,
        contact_id=row.contact_id,
        source_type=row.source_type,
        provider_name=row.provider_name,
        source_url=row.source_url,
        title=row.title,
        snippet_text=row.snippet_text,
        captured_at=row.captured_at,
        freshness_at=row.freshness_at,
        confidence_score=row.confidence_score,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


def _to_artifact_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        artifact_id=artifact.id,
        tenant_id=artifact.tenant_id,
        workflow_run_id=artifact.workflow_run_id,
        created_by_user_id=artifact.created_by_user_id,
        artifact_type=artifact.artifact_type,
        format=artifact.format,
        title=artifact.title,
        content_markdown=artifact.content_markdown,
        content_json=artifact.content_json,
        storage_url=artifact.storage_url,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def _to_approval_response(
    approval: ApprovalDecision,
    updated_run: WorkflowRun,
) -> ApprovalDecisionResponse:
    return ApprovalDecisionResponse(
        approval_decision_id=approval.id,
        workflow_run_id=approval.workflow_run_id,
        artifact_id=approval.artifact_id,
        decision=approval.decision,
        run_status_after_decision=updated_run.status,
        created_at=approval.created_at,
    )
