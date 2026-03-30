from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversationMessage


class ConversationMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        role: str,
        message_type: str,
        content_text: str,
        run_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            message_type=message_type,
            content_text=content_text,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_for_thread(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> Sequence[ConversationMessage]:
        statement = (
            select(ConversationMessage)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.thread_id == thread_id,
            )
            .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
