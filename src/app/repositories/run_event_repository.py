from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunEvent


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
