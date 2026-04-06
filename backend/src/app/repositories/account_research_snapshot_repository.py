from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountResearchSnapshot


class AccountResearchSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        workflow_run_id: UUID,
        created_by_user_id: UUID,
        snapshot_version: int,
        research_json: dict[str, Any],
        research_summary: str | None = None,
        qualification_summary: str | None = None,
        uncertainty_notes: str | None = None,
    ) -> AccountResearchSnapshot:
        snapshot = AccountResearchSnapshot(
            tenant_id=tenant_id,
            account_id=account_id,
            workflow_run_id=workflow_run_id,
            created_by_user_id=created_by_user_id,
            snapshot_version=snapshot_version,
            research_summary=research_summary,
            qualification_summary=qualification_summary,
            uncertainty_notes=uncertainty_notes,
            research_json=research_json,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def list_for_account(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
    ) -> Sequence[AccountResearchSnapshot]:
        statement = (
            select(AccountResearchSnapshot)
            .where(
                AccountResearchSnapshot.tenant_id == tenant_id,
                AccountResearchSnapshot.account_id == account_id,
            )
            .order_by(
                AccountResearchSnapshot.created_at.asc(),
                AccountResearchSnapshot.id.asc(),
            )
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_latest_for_account(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
    ) -> AccountResearchSnapshot | None:
        statement = (
            select(AccountResearchSnapshot)
            .where(
                AccountResearchSnapshot.tenant_id == tenant_id,
                AccountResearchSnapshot.account_id == account_id,
            )
            .order_by(
                AccountResearchSnapshot.snapshot_version.desc(),
                AccountResearchSnapshot.created_at.desc(),
                AccountResearchSnapshot.id.desc(),
            )
        )
        result = await self._session.execute(statement)
        return result.scalars().first()
