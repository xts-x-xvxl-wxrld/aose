from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, WorkflowRun


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        source_workflow_run_id: UUID,
        name: str,
        status: str,
        updated_by_user_id: UUID | None = None,
        domain: str | None = None,
        normalized_domain: str | None = None,
        linkedin_url: str | None = None,
        hq_location: str | None = None,
        employee_range: str | None = None,
        industry: str | None = None,
        fit_summary: str | None = None,
        fit_signals_json: dict[str, Any] | None = None,
        canonical_data_json: dict[str, Any] | None = None,
    ) -> Account:
        account = Account(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            updated_by_user_id=updated_by_user_id,
            source_workflow_run_id=source_workflow_run_id,
            name=name,
            domain=domain,
            normalized_domain=normalized_domain,
            linkedin_url=linkedin_url,
            hq_location=hq_location,
            employee_range=employee_range,
            industry=industry,
            status=status,
            fit_summary=fit_summary,
            fit_signals_json=fit_signals_json,
            canonical_data_json=canonical_data_json,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
    ) -> Account | None:
        statement = select(Account).where(
            Account.tenant_id == tenant_id,
            Account.id == account_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_normalized_domain(
        self,
        *,
        tenant_id: UUID,
        normalized_domain: str,
    ) -> Account | None:
        statement = select(Account).where(
            Account.tenant_id == tenant_id,
            Account.normalized_domain == normalized_domain,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID | None = None,
        icp_profile_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Account]:
        statement = (
            select(Account)
            .join(WorkflowRun, WorkflowRun.id == Account.source_workflow_run_id)
            .where(
                Account.tenant_id == tenant_id,
                WorkflowRun.tenant_id == tenant_id,
            )
            .order_by(
                Account.updated_at.desc(),
                Account.created_at.desc(),
                Account.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        if seller_profile_id is not None:
            statement = statement.where(
                WorkflowRun.requested_payload_json["seller_profile_id"].astext
                == str(seller_profile_id)
            )
        if icp_profile_id is not None:
            statement = statement.where(
                WorkflowRun.requested_payload_json["icp_profile_id"].astext == str(icp_profile_id)
            )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_for_tenant(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID | None = None,
        icp_profile_id: UUID | None = None,
    ) -> int:
        statement = (
            select(func.count(Account.id))
            .select_from(Account)
            .join(WorkflowRun, WorkflowRun.id == Account.source_workflow_run_id)
            .where(
                Account.tenant_id == tenant_id,
                WorkflowRun.tenant_id == tenant_id,
            )
        )
        if seller_profile_id is not None:
            statement = statement.where(
                WorkflowRun.requested_payload_json["seller_profile_id"].astext
                == str(seller_profile_id)
            )
        if icp_profile_id is not None:
            statement = statement.where(
                WorkflowRun.requested_payload_json["icp_profile_id"].astext == str(icp_profile_id)
            )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def update(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        updated_by_user_id: UUID,
        changes: dict[str, Any],
    ) -> Account | None:
        account = await self.get_for_tenant(tenant_id=tenant_id, account_id=account_id)
        if account is None:
            return None

        for field_name, field_value in changes.items():
            setattr(account, field_name, field_value)
        account.updated_by_user_id = updated_by_user_id
        await self._session.flush()
        return account
