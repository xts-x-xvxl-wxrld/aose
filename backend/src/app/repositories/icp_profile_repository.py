from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ICPProfile


class ICPProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID,
        created_by_user_id: UUID,
        name: str,
        criteria_json: dict[str, Any],
        exclusions_json: dict[str, Any] | None = None,
        status: str = "draft",
    ) -> ICPProfile:
        icp_profile = ICPProfile(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
            created_by_user_id=created_by_user_id,
            name=name,
            status=status,
            criteria_json=criteria_json,
            exclusions_json=exclusions_json,
        )
        self._session.add(icp_profile)
        await self._session.flush()
        return icp_profile

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        icp_profile_id: UUID,
    ) -> ICPProfile | None:
        statement = select(ICPProfile).where(
            ICPProfile.tenant_id == tenant_id,
            ICPProfile.id == icp_profile_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ICPProfile]:
        statement = (
            select(ICPProfile)
            .where(ICPProfile.tenant_id == tenant_id)
            .order_by(
                ICPProfile.updated_at.desc(),
                ICPProfile.created_at.desc(),
                ICPProfile.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_for_tenant(
        self,
        *,
        tenant_id: UUID,
    ) -> int:
        statement = select(func.count(ICPProfile.id)).where(
            ICPProfile.tenant_id == tenant_id
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def update(
        self,
        *,
        tenant_id: UUID,
        icp_profile_id: UUID,
        updated_by_user_id: UUID,
        changes: dict[str, Any],
    ) -> ICPProfile | None:
        icp_profile = await self.get_for_tenant(
            tenant_id=tenant_id,
            icp_profile_id=icp_profile_id,
        )
        if icp_profile is None:
            return None

        for field_name, field_value in changes.items():
            setattr(icp_profile, field_name, field_value)
        icp_profile.updated_by_user_id = updated_by_user_id
        await self._session.flush()
        return icp_profile
