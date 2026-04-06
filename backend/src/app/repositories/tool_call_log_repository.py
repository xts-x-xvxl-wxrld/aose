from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ToolCallLog


class ToolCallLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> ToolCallLog:
        row = ToolCallLog(**kwargs)
        self._session.add(row)
        await self._session.flush()
        return row

    async def find_latest_open_call(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        tool_name: str,
        provider_name: str | None,
        correlation_key: str | None,
    ) -> ToolCallLog | None:
        statement = (
            select(ToolCallLog)
            .where(
                ToolCallLog.tenant_id == tenant_id,
                ToolCallLog.run_id == run_id,
                ToolCallLog.tool_name == tool_name,
                ToolCallLog.status == "started",
            )
            .order_by(ToolCallLog.created_at.desc(), ToolCallLog.id.desc())
        )
        if provider_name is None:
            statement = statement.where(ToolCallLog.provider_name.is_(None))
        else:
            statement = statement.where(ToolCallLog.provider_name == provider_name)
        if correlation_key is not None:
            statement = statement.where(ToolCallLog.correlation_key == correlation_key)
        result = await self._session.execute(statement.limit(1))
        return result.scalar_one_or_none()

    async def mark_finished(
        self,
        *,
        row: ToolCallLog,
        status: str,
        output_excerpt: str | None,
        output_hash: str | None,
        error_code: str | None,
        raw_metadata_json: dict,
        finished_at: datetime,
        latency_ms: int | None,
    ) -> ToolCallLog:
        row.status = status
        row.output_excerpt = output_excerpt
        row.output_hash = output_hash
        row.error_code = error_code
        row.raw_metadata_json = raw_metadata_json
        row.updated_at = finished_at
        row.latency_ms = latency_ms
        await self._session.flush()
        return row

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ToolCallLog]:
        statement = (
            select(ToolCallLog)
            .where(ToolCallLog.tenant_id == tenant_id)
            .order_by(ToolCallLog.created_at.desc(), ToolCallLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if run_id is not None:
            statement = statement.where(ToolCallLog.run_id == run_id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
