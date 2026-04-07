from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        created_by_user_id: UUID,
        full_name: str,
        status: str,
        updated_by_user_id: UUID | None = None,
        job_title: str | None = None,
        email: str | None = None,
        linkedin_url: str | None = None,
        phone: str | None = None,
        ranking_summary: str | None = None,
        person_data_json: dict[str, Any] | None = None,
    ) -> Contact:
        contact = Contact(
            tenant_id=tenant_id,
            account_id=account_id,
            created_by_user_id=created_by_user_id,
            updated_by_user_id=updated_by_user_id,
            full_name=full_name,
            job_title=job_title,
            email=email,
            linkedin_url=linkedin_url,
            phone=phone,
            status=status,
            ranking_summary=ranking_summary,
            person_data_json=person_data_json,
        )
        self._session.add(contact)
        await self._session.flush()
        return contact

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> Contact | None:
        statement = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_account(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
    ) -> Sequence[Contact]:
        statement = (
            select(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                Contact.account_id == account_id,
            )
            .order_by(Contact.created_at.asc(), Contact.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Contact]:
        statement = (
            select(Contact)
            .where(Contact.tenant_id == tenant_id)
            .order_by(
                Contact.updated_at.desc(),
                Contact.created_at.desc(),
                Contact.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        if account_id is not None:
            statement = statement.where(Contact.account_id == account_id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_for_tenant(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID | None = None,
    ) -> int:
        statement = select(func.count(Contact.id)).where(Contact.tenant_id == tenant_id)
        if account_id is not None:
            statement = statement.where(Contact.account_id == account_id)
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def update(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        updated_by_user_id: UUID,
        changes: dict[str, Any],
    ) -> Contact | None:
        contact = await self.get_for_tenant(tenant_id=tenant_id, contact_id=contact_id)
        if contact is None:
            return None

        for field_name, field_value in changes.items():
            setattr(contact, field_name, field_value)
        contact.updated_by_user_id = updated_by_user_id
        await self._session.flush()
        return contact
