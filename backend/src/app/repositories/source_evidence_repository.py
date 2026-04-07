from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SourceEvidence


class SourceEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        workflow_run_id: UUID,
        source_type: str,
        account_id: UUID | None = None,
        contact_id: UUID | None = None,
        provider_name: str | None = None,
        source_url: str | None = None,
        title: str | None = None,
        snippet_text: str | None = None,
        captured_at: datetime | None = None,
        freshness_at: datetime | None = None,
        confidence_score: float | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> SourceEvidence:
        evidence = SourceEvidence(
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
            account_id=account_id,
            contact_id=contact_id,
            source_type=source_type,
            provider_name=provider_name,
            source_url=source_url,
            title=title,
            snippet_text=snippet_text,
            captured_at=captured_at,
            freshness_at=freshness_at,
            confidence_score=confidence_score,
            metadata_json=metadata_json,
        )
        self._session.add(evidence)
        await self._session.flush()
        return evidence

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        workflow_run_id: UUID,
    ) -> Sequence[SourceEvidence]:
        statement = (
            select(SourceEvidence)
            .where(
                SourceEvidence.tenant_id == tenant_id,
                SourceEvidence.workflow_run_id == workflow_run_id,
            )
            .order_by(SourceEvidence.created_at.asc(), SourceEvidence.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_for_run(
        self,
        *,
        tenant_id: UUID,
        workflow_run_id: UUID,
    ) -> int:
        statement = select(func.count(SourceEvidence.id)).where(
            SourceEvidence.tenant_id == tenant_id,
            SourceEvidence.workflow_run_id == workflow_run_id,
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())
