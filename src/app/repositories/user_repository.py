from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        external_auth_subject: str,
        email: str | None = None,
        display_name: str | None = None,
        status: str = "active",
    ) -> User:
        user = User(
            external_auth_subject=external_auth_subject,
            email=email,
            display_name=display_name,
            status=status,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, *, user_id: UUID) -> User | None:
        statement = select(User).where(User.id == user_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_external_auth_subject(self, *, external_auth_subject: str) -> User | None:
        statement = select(User).where(User.external_auth_subject == external_auth_subject)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_email(self, *, email: str) -> Sequence[User]:
        statement = select(User).where(func.lower(User.email) == email.strip().lower())
        result = await self._session.execute(statement)
        return result.scalars().all()
