from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog


class AdminAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID | None,
        action: str,
        target_type: str,
        target_id: UUID | None,
        request_id: str | None,
        before_json: dict | None,
        after_json: dict | None,
    ) -> AdminAuditLog:
        row = AdminAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            before_json=before_json,
            after_json=after_json,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_logs(
        self,
        *,
        tenant_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AdminAuditLog]:
        statement = (
            select(AdminAuditLog)
            .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if tenant_id is not None:
            statement = statement.where(AdminAuditLog.tenant_id == tenant_id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
