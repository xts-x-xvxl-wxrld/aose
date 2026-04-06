from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunEvent, WorkflowRun


class RunEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        event_name: str,
        payload_json: dict[str, Any],
    ) -> RunEvent:
        event = RunEvent(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=event_name,
            payload_json=payload_json,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> Sequence[RunEvent]:
        statement = (
            select(RunEvent)
            .where(
                RunEvent.tenant_id == tenant_id,
                RunEvent.run_id == run_id,
            )
            .order_by(RunEvent.created_at.asc(), RunEvent.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_recent_for_tenant(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[RunEvent]:
        statement = (
            select(RunEvent)
            .join(WorkflowRun, WorkflowRun.id == RunEvent.run_id)
            .where(RunEvent.tenant_id == tenant_id, WorkflowRun.tenant_id == tenant_id)
            .order_by(RunEvent.created_at.desc(), RunEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if thread_id is not None:
            statement = statement.where(WorkflowRun.thread_id == thread_id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
