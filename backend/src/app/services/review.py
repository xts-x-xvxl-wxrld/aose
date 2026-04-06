from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import AuthIdentity
from app.models import (
    ApprovalDecision,
    Artifact,
    SourceEvidence,
    TenantMembership,
    User,
    WorkflowRun,
)
from app.orchestration.contracts import WorkflowRunStatus
from app.repositories.approval_decision_repository import ApprovalDecisionRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.workflow_runs import WorkflowRunService

REVIEWER_ROLES = {"owner", "admin", "reviewer"}
APPROVAL_DECISIONS = {"approved", "rejected", "needs_changes"}


class ReviewService:
    def __init__(
        self,
        session: AsyncSession,
        run_service: WorkflowRunService | None = None,
    ) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)
        self._evidence = SourceEvidenceRepository(session)
        self._artifacts = ArtifactRepository(session)
        self._approvals = ApprovalDecisionRepository(session)
        self._run_service = run_service or WorkflowRunService(session)

    async def list_evidence_for_run(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        run_id: UUID,
    ) -> list[SourceEvidence]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        run = await self._run_service.get_run_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        return list(
            await self._evidence.list_for_run(
                tenant_id=tenant_id,
                workflow_run_id=run.id,
            )
        )

    async def get_artifact(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        artifact_id: UUID,
    ) -> Artifact:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        artifact = await self._artifacts.get_for_tenant(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
        )
        if artifact is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Artifact was not found in the requested tenant.",
            )
        return artifact

    async def submit_approval(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        run_id: UUID,
        decision: str,
        rationale: str | None = None,
        artifact_id: UUID | None = None,
    ) -> tuple[ApprovalDecision, WorkflowRun]:
        actor_user, _membership = await self._require_active_membership(
            identity=identity,
            tenant_id=tenant_id,
            allowed_roles=REVIEWER_ROLES,
            missing_membership_message=(
                "User does not have permission to review workflow results in this tenant."
            ),
        )
        run = await self._run_service.get_run_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        if run.status != WorkflowRunStatus.AWAITING_REVIEW.value:
            raise ServiceError(
                status_code=409,
                error_code="review_state_conflict",
                message="Workflow run is not awaiting review.",
            )

        artifact = None
        if artifact_id is not None:
            artifact = await self._artifacts.get_for_tenant(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
            )
            if artifact is None:
                raise ServiceError(
                    status_code=404,
                    error_code="resource_not_found",
                    message="Artifact was not found in the requested tenant.",
                )
            if artifact.workflow_run_id != run.id:
                raise ServiceError(
                    status_code=409,
                    error_code="review_state_conflict",
                    message="Artifact does not belong to the reviewed workflow run.",
                )

        normalized_rationale = _normalize_optional_text(rationale)
        if decision not in APPROVAL_DECISIONS:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="decision must be one of approved, rejected, or needs_changes.",
                details={"field": "decision"},
            )
        if decision in {"rejected", "needs_changes"} and normalized_rationale is None:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="rationale is required when decision is rejected or needs_changes.",
                details={"field": "rationale"},
            )
        approval = await self._approvals.create(
            tenant_id=tenant_id,
            workflow_run_id=run.id,
            artifact_id=artifact.id if artifact is not None else None,
            reviewed_by_user_id=actor_user.id,
            decision=decision,
            rationale=normalized_rationale,
        )

        if decision == "approved":
            updated_run = await self._run_service.mark_succeeded(
                tenant_id=tenant_id,
                run_id=run.id,
                result_summary=normalized_rationale or "Workflow run approved after review.",
                normalized_result_json=run.normalized_result_json,
                status_detail="Approval decision recorded: approved.",
            )
        elif decision == "rejected":
            updated_run = await self._run_service.mark_failed(
                tenant_id=tenant_id,
                run_id=run.id,
                error_code="review_rejected",
                failure_summary=normalized_rationale or "Workflow run was rejected during review.",
                normalized_result_json=run.normalized_result_json,
                status_detail="Approval decision recorded: rejected.",
            )
        else:
            updated_run = await self._run_service.mark_failed(
                tenant_id=tenant_id,
                run_id=run.id,
                error_code="review_needs_changes",
                failure_summary=(
                    normalized_rationale or "Workflow run requires changes before resubmission."
                ),
                normalized_result_json=run.normalized_result_json,
                status_detail="Approval decision recorded: needs_changes.",
            )

        await self._session.refresh(approval)
        return approval, updated_run

    async def _require_active_membership(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        allowed_roles: set[str] | None = None,
        missing_membership_message: str = "User does not have an active membership in the requested tenant.",
    ) -> tuple[User, TenantMembership]:
        user = await self._users.get_by_external_auth_subject(
            external_auth_subject=identity.external_auth_subject
        )
        if user is None:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message=missing_membership_message,
            )

        membership = await self._memberships.get_by_tenant_and_user(
            tenant_id=tenant_id,
            user_id=user.id,
        )
        if membership is None or membership.status != "active":
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message=missing_membership_message,
            )
        if allowed_roles is not None and membership.role not in allowed_roles:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message=missing_membership_message,
            )
        return user, membership


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
