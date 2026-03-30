from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkflowRun


class WorkflowRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        workflow_type: str,
        status: str,
        requested_payload_json: dict[str, Any],
        thread_id: UUID | None = None,
        status_detail: str | None = None,
        normalized_result_json: dict[str, Any] | None = None,
        error_code: str | None = None,
        correlation_id: str | None = None,
        started_at: Any | None = None,
        finished_at: Any | None = None,
    ) -> WorkflowRun:
        workflow_run = WorkflowRun(
            tenant_id=tenant_id,
            thread_id=thread_id,
            created_by_user_id=created_by_user_id,
            workflow_type=workflow_type,
            status=status,
            status_detail=status_detail,
            requested_payload_json=requested_payload_json,
            normalized_result_json=normalized_result_json,
            error_code=error_code,
            correlation_id=correlation_id,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._session.add(workflow_run)
        await self._session.flush()
        return workflow_run

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> WorkflowRun | None:
        statement = select(WorkflowRun).where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.id == run_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_correlation_id(
        self,
        *,
        tenant_id: UUID,
        correlation_id: str,
    ) -> WorkflowRun | None:
        statement = select(WorkflowRun).where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.correlation_id == correlation_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        changes: dict[str, Any],
    ) -> WorkflowRun | None:
        workflow_run = await self.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if workflow_run is None:
            return None

        for field_name, field_value in changes.items():
            setattr(workflow_run, field_name, field_value)
        await self._session.flush()
        return workflow_run
