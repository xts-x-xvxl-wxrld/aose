from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str, slug: str, status: str = "active") -> Tenant:
        tenant = Tenant(name=name, slug=slug, status=status)
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def get_by_slug(self, *, slug: str) -> Tenant | None:
        statement = select(Tenant).where(Tenant.slug == slug)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
