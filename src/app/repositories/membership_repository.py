from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant, TenantMembership, User


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

    async def get_by_id_for_tenant(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> TenantMembership | None:
        statement = select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.id == membership_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        *,
        user_id: UUID,
    ) -> Sequence[tuple[TenantMembership, Tenant]]:
        statement = (
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user_id)
            .order_by(TenantMembership.created_at.asc(), TenantMembership.id.asc())
        )
        result = await self._session.execute(statement)
        return [(membership, tenant) for membership, tenant in result.all()]

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
    ) -> Sequence[tuple[TenantMembership, User]]:
        statement = (
            select(TenantMembership, User)
            .join(User, User.id == TenantMembership.user_id)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.created_at.asc(), TenantMembership.id.asc())
        )
        result = await self._session.execute(statement)
        return [(membership, user) for membership, user in result.all()]

    async def count_active_owners(self, *, tenant_id: UUID) -> int:
        statement = select(func.count()).select_from(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.role == "owner",
            TenantMembership.status == "active",
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def delete(self, membership: TenantMembership) -> None:
        await self._session.delete(membership)
