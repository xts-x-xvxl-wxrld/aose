from __future__ import annotations

from datetime import datetime
from collections.abc import Sequence
from typing import Any
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
        request_id: str | None = None,
        request_payload_json: dict[str, Any] | None = None,
        created_by_user_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            message_type=message_type,
            content_text=content_text,
            request_id=request_id,
            request_payload_json=request_payload_json,
            created_by_user_id=created_by_user_id,
            created_at=created_at,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def get_user_turn_by_request_id(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        request_id: str,
    ) -> ConversationMessage | None:
        statement = select(ConversationMessage).where(
            ConversationMessage.tenant_id == tenant_id,
            ConversationMessage.created_by_user_id == created_by_user_id,
            ConversationMessage.request_id == request_id,
            ConversationMessage.message_type == "user_turn",
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

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

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> Sequence[ConversationMessage]:
        statement = (
            select(ConversationMessage)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.run_id == run_id,
            )
            .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
