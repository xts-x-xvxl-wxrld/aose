from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApprovalDecision


class ApprovalDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        workflow_run_id: UUID,
        reviewed_by_user_id: UUID,
        decision: str,
        artifact_id: UUID | None = None,
        rationale: str | None = None,
        reviewed_at: datetime | None = None,
    ) -> ApprovalDecision:
        approval_kwargs = {
            "tenant_id": tenant_id,
            "workflow_run_id": workflow_run_id,
            "artifact_id": artifact_id,
            "reviewed_by_user_id": reviewed_by_user_id,
            "decision": decision,
            "rationale": rationale,
        }
        if reviewed_at is not None:
            approval_kwargs["reviewed_at"] = reviewed_at

        approval = ApprovalDecision(
            **approval_kwargs,
        )
        self._session.add(approval)
        await self._session.flush()
        return approval

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        workflow_run_id: UUID,
    ) -> Sequence[ApprovalDecision]:
        statement = (
            select(ApprovalDecision)
            .where(
                ApprovalDecision.tenant_id == tenant_id,
                ApprovalDecision.workflow_run_id == workflow_run_id,
            )
            .order_by(ApprovalDecision.created_at.asc(), ApprovalDecision.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_for_artifact(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID,
    ) -> Sequence[ApprovalDecision]:
        statement = (
            select(ApprovalDecision)
            .where(
                ApprovalDecision.tenant_id == tenant_id,
                ApprovalDecision.artifact_id == artifact_id,
            )
            .order_by(ApprovalDecision.created_at.asc(), ApprovalDecision.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
