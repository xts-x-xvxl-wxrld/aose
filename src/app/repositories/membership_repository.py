from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TenantMembership


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role: str,
        status: str = "active",
    ) -> TenantMembership:
        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            status=status,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def get_by_tenant_and_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> TenantMembership | None:
        statement = select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
