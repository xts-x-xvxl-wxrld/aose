from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LlmCallLog


class LlmCallLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> LlmCallLog:
        row = LlmCallLog(**kwargs)
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[LlmCallLog]:
        statement = (
            select(LlmCallLog)
            .where(LlmCallLog.tenant_id == tenant_id)
            .order_by(LlmCallLog.created_at.desc(), LlmCallLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if run_id is not None:
            statement = statement.where(LlmCallLog.run_id == run_id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
