from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        artifact_type: str,
        format: str,
        title: str,
        workflow_run_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        content_markdown: str | None = None,
        content_json: dict[str, Any] | None = None,
        storage_url: str | None = None,
    ) -> Artifact:
        artifact = Artifact(
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
            created_by_user_id=created_by_user_id,
            artifact_type=artifact_type,
            format=format,
            title=title,
            content_markdown=content_markdown,
            content_json=content_json,
            storage_url=storage_url,
        )
        self._session.add(artifact)
        await self._session.flush()
        return artifact

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID,
    ) -> Artifact | None:
        statement = select(Artifact).where(
            Artifact.tenant_id == tenant_id,
            Artifact.id == artifact_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID,
        changes: dict[str, Any],
    ) -> Artifact | None:
        artifact = await self.get_for_tenant(tenant_id=tenant_id, artifact_id=artifact_id)
        if artifact is None:
            return None

        for field_name, field_value in changes.items():
            setattr(artifact, field_name, field_value)
        await self._session.flush()
        return artifact
