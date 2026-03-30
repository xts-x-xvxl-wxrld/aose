from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SellerProfile


class SellerProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        name: str,
        company_name: str,
        product_summary: str,
        value_proposition: str,
        company_domain: str | None = None,
        target_market_summary: str | None = None,
        source_status: str | None = "manual",
        profile_json: dict[str, Any] | None = None,
    ) -> SellerProfile:
        seller_profile = SellerProfile(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            name=name,
            company_name=company_name,
            company_domain=company_domain,
            product_summary=product_summary,
            value_proposition=value_proposition,
            target_market_summary=target_market_summary,
            source_status=source_status,
            profile_json=profile_json,
        )
        self._session.add(seller_profile)
        await self._session.flush()
        return seller_profile

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID,
    ) -> SellerProfile | None:
        statement = select(SellerProfile).where(
            SellerProfile.tenant_id == tenant_id,
            SellerProfile.id == seller_profile_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID,
        updated_by_user_id: UUID,
        changes: dict[str, Any],
    ) -> SellerProfile | None:
        seller_profile = await self.get_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
        )
        if seller_profile is None:
            return None

        for field_name, field_value in changes.items():
            setattr(seller_profile, field_name, field_value)
        seller_profile.updated_by_user_id = updated_by_user_id
        await self._session.flush()
        return seller_profile
