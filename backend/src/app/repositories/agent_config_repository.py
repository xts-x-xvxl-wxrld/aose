from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentConfigVersion


class AgentConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        scope_type: str,
        tenant_id: UUID | None,
        agent_name: str,
        version: int,
        created_by_user_id: UUID,
        instructions: str | None,
        system_prompt: str | None,
        model: str | None,
        model_settings_json: dict,
        feature_flags_json: dict,
        change_note: str | None,
        status: str = "draft",
    ) -> AgentConfigVersion:
        row = AgentConfigVersion(
            scope_type=scope_type,
            tenant_id=tenant_id,
            agent_name=agent_name,
            version=version,
            created_by_user_id=created_by_user_id,
            instructions=instructions,
            system_prompt=system_prompt,
            model=model,
            model_settings_json=model_settings_json,
            feature_flags_json=feature_flags_json,
            change_note=change_note,
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_id(self, *, version_id: UUID) -> AgentConfigVersion | None:
        result = await self._session.execute(
            select(AgentConfigVersion).where(AgentConfigVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def list_for_scope(
        self,
        *,
        scope_type: str,
        tenant_id: UUID | None,
        agent_name: str | None = None,
    ) -> Sequence[AgentConfigVersion]:
        statement = select(AgentConfigVersion).where(
            AgentConfigVersion.scope_type == scope_type,
            AgentConfigVersion.tenant_id == tenant_id,
        )
        if agent_name is not None:
            statement = statement.where(AgentConfigVersion.agent_name == agent_name)
        statement = statement.order_by(
            AgentConfigVersion.agent_name.asc(),
            AgentConfigVersion.version.desc(),
            AgentConfigVersion.created_at.desc(),
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_active_for_scope(
        self,
        *,
        scope_type: str,
        tenant_id: UUID | None,
        agent_name: str,
    ) -> AgentConfigVersion | None:
        result = await self._session.execute(
            select(AgentConfigVersion).where(
                AgentConfigVersion.scope_type == scope_type,
                AgentConfigVersion.tenant_id == tenant_id,
                AgentConfigVersion.agent_name == agent_name,
                AgentConfigVersion.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def next_version_number(
        self,
        *,
        scope_type: str,
        tenant_id: UUID | None,
        agent_name: str,
    ) -> int:
        result = await self._session.execute(
            select(func.max(AgentConfigVersion.version)).where(
                AgentConfigVersion.scope_type == scope_type,
                AgentConfigVersion.tenant_id == tenant_id,
                AgentConfigVersion.agent_name == agent_name,
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def activate(self, *, target: AgentConfigVersion) -> AgentConfigVersion:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await self._session.execute(
            select(AgentConfigVersion).where(
                AgentConfigVersion.scope_type == target.scope_type,
                AgentConfigVersion.tenant_id == target.tenant_id,
                AgentConfigVersion.agent_name == target.agent_name,
                AgentConfigVersion.status == "active",
                AgentConfigVersion.id != target.id,
            )
        )
        for row in result.scalars().all():
            row.status = "archived"
        target.status = "active"
        target.activated_at = now
        await self._session.flush()
        return target

    async def find_effective(
        self,
        *,
        tenant_id: UUID | None,
        agent_name: str,
    ) -> AgentConfigVersion | None:
        scopes = []
        if tenant_id is not None:
            scopes.append(
                and_(
                    AgentConfigVersion.scope_type == "tenant",
                    AgentConfigVersion.tenant_id == tenant_id,
                    AgentConfigVersion.agent_name == agent_name,
                    AgentConfigVersion.status == "active",
                )
            )
        scopes.append(
            and_(
                AgentConfigVersion.scope_type == "global",
                AgentConfigVersion.tenant_id.is_(None),
                AgentConfigVersion.agent_name == agent_name,
                AgentConfigVersion.status == "active",
            )
        )
        result = await self._session.execute(
            select(AgentConfigVersion)
            .where(or_(*scopes))
            .order_by(
                AgentConfigVersion.scope_type.desc(),
                AgentConfigVersion.activated_at.desc().nullslast(),
                AgentConfigVersion.created_at.desc(),
            )
        )
        return result.scalars().first()
