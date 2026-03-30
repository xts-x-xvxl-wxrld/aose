from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversationThread


class ConversationThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        status: str = "active",
        seller_profile_id: UUID | None = None,
        active_workflow: str | None = None,
        current_run_id: UUID | None = None,
        summary_text: str | None = None,
    ) -> ConversationThread:
        thread = ConversationThread(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            seller_profile_id=seller_profile_id,
            active_workflow=active_workflow,
            status=status,
            current_run_id=current_run_id,
            summary_text=summary_text,
        )
        self._session.add(thread)
        await self._session.flush()
        return thread

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> ConversationThread | None:
        statement = select(ConversationThread).where(
            ConversationThread.tenant_id == tenant_id,
            ConversationThread.id == thread_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        changes: dict[str, Any],
    ) -> ConversationThread | None:
        thread = await self.get_for_tenant(tenant_id=tenant_id, thread_id=thread_id)
        if thread is None:
            return None

        for field_name, field_value in changes.items():
            setattr(thread, field_name, field_value)
        await self._session.flush()
        return thread
