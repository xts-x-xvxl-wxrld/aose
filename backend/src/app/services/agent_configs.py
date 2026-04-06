from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AgentConfigVersion
from app.repositories.admin_audit_log_repository import AdminAuditLogRepository
from app.repositories.agent_config_repository import AgentConfigRepository
from app.services.admin_access import AdminAccessService
from app.services.errors import ServiceError


SUPPORTED_AGENT_NAMES = (
    "orchestrator_agent",
    "account_search_agent",
    "account_research_agent",
    "contact_search_agent",
)

WORKFLOW_AGENT_NAME_BY_TYPE = {
    "account_search": "account_search_agent",
    "account_research": "account_research_agent",
    "contact_search": "contact_search_agent",
}


@dataclass(frozen=True)
class EffectiveAgentConfig:
    agent_name: str
    instructions: str | None
    system_prompt: str | None
    model: str | None
    model_settings_json: dict[str, Any]
    feature_flags_json: dict[str, Any]
    source: str
    version_id: str | None = None
    version: int | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "instructions": self.instructions,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "model_settings_json": dict(self.model_settings_json),
            "feature_flags_json": dict(self.feature_flags_json),
        }


def get_code_default_agent_config(*, agent_name: str, settings: Settings) -> EffectiveAgentConfig:
    defaults = {
        "orchestrator_agent": EffectiveAgentConfig(
            agent_name="orchestrator_agent",
            instructions=(
                "You are the top-level orchestrator for the outbound research system. "
                "Your job is to understand the user goal and decide whether the next specialist "
                "should be account search, account research, or contact search. "
                "Keep routing rules deterministic, avoid inventing completed work, and rely on the durable workflow system."
            ),
            system_prompt=None,
            model=settings.openai_agent_model,
            model_settings_json={},
            feature_flags_json={},
            source="code_default",
        ),
        "account_search_agent": EffectiveAgentConfig(
            agent_name="account_search_agent",
            instructions=(
                "You focus on discovering target accounts for a seller. "
                "Use workflow-owned search evidence, stay precision-first, and only promote defensible candidates. "
                "Keep uncertainty explicit and do not invent missing company facts."
            ),
            system_prompt=None,
            model=settings.openai_agent_model,
            model_settings_json={},
            feature_flags_json={},
            source="code_default",
        ),
        "account_research_agent": EffectiveAgentConfig(
            agent_name="account_research_agent",
            instructions=(
                "You focus on researching a selected account. "
                "Synthesize compact, evidence-backed account intelligence, preserve uncertainty, "
                "and do not claim research findings that were not supported by gathered sources."
            ),
            system_prompt=None,
            model=settings.openai_agent_model,
            model_settings_json={},
            feature_flags_json={},
            source="code_default",
        ),
        "contact_search_agent": EffectiveAgentConfig(
            agent_name="contact_search_agent",
            instructions=(
                "You focus on identifying relevant people at a target account. "
                "Rank provider-backed candidates conservatively, preserve missing-data flags, "
                "and do not fabricate contacts or overstate confidence."
            ),
            system_prompt=None,
            model=settings.openai_agent_model,
            model_settings_json={},
            feature_flags_json={},
            source="code_default",
        ),
    }
    try:
        return defaults[agent_name]
    except KeyError as exc:
        raise ServiceError(
            status_code=404,
            error_code="resource_not_found",
            message="Unsupported agent configuration target.",
            details={"agent_name": agent_name},
        ) from exc


class AgentConfigService:
    def __init__(self, session: AsyncSession, *, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._configs = AgentConfigRepository(session)
        self._audits = AdminAuditLogRepository(session)
        self._access = AdminAccessService(session)

    async def resolve_effective_config(
        self,
        *,
        tenant_id: UUID | None,
        agent_name: str,
    ) -> EffectiveAgentConfig:
        code_default = get_code_default_agent_config(agent_name=agent_name, settings=self._settings)
        tenant_row = None
        if tenant_id is not None:
            tenant_row = await self._configs.get_active_for_scope(
                scope_type="tenant",
                tenant_id=tenant_id,
                agent_name=agent_name,
            )
        if tenant_row is not None:
            return _row_to_effective_config(row=tenant_row, source="tenant_override", fallback=code_default)

        global_row = await self._configs.get_active_for_scope(
            scope_type="global",
            tenant_id=None,
            agent_name=agent_name,
        )
        if global_row is not None:
            return _row_to_effective_config(row=global_row, source="global_override", fallback=code_default)
        return code_default

    async def build_run_config_snapshot(
        self,
        *,
        tenant_id: UUID | None,
        workflow_type: str,
    ) -> dict[str, Any]:
        snapshot_agents = {}
        workflow_agent_name = WORKFLOW_AGENT_NAME_BY_TYPE.get(workflow_type)
        for agent_name in SUPPORTED_AGENT_NAMES:
            resolved = await self.resolve_effective_config(tenant_id=tenant_id, agent_name=agent_name)
            snapshot_agents[agent_name] = {
                **resolved.as_payload(),
                "source": resolved.source,
                "version_id": resolved.version_id,
                "version": resolved.version,
            }
        return {
            "workflow_type": workflow_type,
            "workflow_agent_name": workflow_agent_name,
            "agents": snapshot_agents,
        }

    async def list_scope_configs(
        self,
        *,
        actor_user_id: UUID,
        scope_type: str,
        tenant_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        if scope_type == "global":
            await self._access.require_platform_admin(actor_user_id=actor_user_id)
        else:
            assert tenant_id is not None
            await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)

        tenant_versions = list(
            await self._configs.list_for_scope(
                scope_type=scope_type,
                tenant_id=tenant_id if scope_type == "tenant" else None,
            )
        )
        global_versions = list(await self._configs.list_for_scope(scope_type="global", tenant_id=None))
        response: list[dict[str, Any]] = []
        for agent_name in SUPPORTED_AGENT_NAMES:
            code_default = get_code_default_agent_config(agent_name=agent_name, settings=self._settings).as_payload()
            global_active = await self._configs.get_active_for_scope(
                scope_type="global",
                tenant_id=None,
                agent_name=agent_name,
            )
            tenant_active = (
                await self._configs.get_active_for_scope(
                    scope_type="tenant",
                    tenant_id=tenant_id,
                    agent_name=agent_name,
                )
                if tenant_id is not None
                else None
            )
            effective = await self.resolve_effective_config(tenant_id=tenant_id, agent_name=agent_name)
            versions = [
                _row_to_response_payload(row)
                for row in (tenant_versions if scope_type == "tenant" else global_versions)
                if row.agent_name == agent_name
            ]
            response.append(
                {
                    "agent_name": agent_name,
                    "code_default": code_default,
                    "global_active": _row_to_response_payload(global_active) if global_active else None,
                    "tenant_active": _row_to_response_payload(tenant_active) if tenant_active else None,
                    "effective": effective.as_payload(),
                    "versions": versions,
                }
            )
        return response

    async def create_version(
        self,
        *,
        actor_user_id: UUID,
        request_id: str | None,
        scope_type: str,
        tenant_id: UUID | None,
        payload: dict[str, Any],
    ) -> AgentConfigVersion:
        agent_name = payload["agent_name"]
        get_code_default_agent_config(agent_name=agent_name, settings=self._settings)
        if scope_type == "global":
            await self._access.require_platform_admin(actor_user_id=actor_user_id)
            scoped_tenant_id = None
        else:
            if tenant_id is None:
                raise ServiceError(
                    status_code=400,
                    error_code="tenant_context_required",
                    message="Tenant context is required for tenant-scoped config versions.",
                )
            await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
            scoped_tenant_id = tenant_id

        version = await self._configs.next_version_number(
            scope_type=scope_type,
            tenant_id=scoped_tenant_id,
            agent_name=agent_name,
        )
        row = await self._configs.create(
            scope_type=scope_type,
            tenant_id=scoped_tenant_id,
            agent_name=agent_name,
            version=version,
            created_by_user_id=actor_user_id,
            instructions=payload.get("instructions"),
            system_prompt=payload.get("system_prompt"),
            model=payload.get("model"),
            model_settings_json=dict(payload.get("model_settings_json") or {}),
            feature_flags_json=dict(payload.get("feature_flags_json") or {}),
            change_note=payload.get("change_note"),
            status="draft",
        )
        if payload.get("activate"):
            await self._configs.activate(target=row)
        await self._audits.create(
            actor_user_id=actor_user_id,
            tenant_id=scoped_tenant_id,
            action="agent_config.create_version",
            target_type="agent_config_version",
            target_id=row.id,
            request_id=request_id,
            before_json=None,
            after_json=_row_to_response_payload(row),
        )
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def activate_version(
        self,
        *,
        actor_user_id: UUID,
        request_id: str | None,
        version_id: UUID,
        action: str = "agent_config.activate_version",
    ) -> AgentConfigVersion:
        row = await self._configs.get_by_id(version_id=version_id)
        if row is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Agent config version was not found.",
            )
        if row.scope_type == "global":
            await self._access.require_platform_admin(actor_user_id=actor_user_id)
        else:
            assert row.tenant_id is not None
            await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=row.tenant_id)

        before = _row_to_response_payload(row)
        await self._configs.activate(target=row)
        await self._audits.create(
            actor_user_id=actor_user_id,
            tenant_id=row.tenant_id,
            action=action,
            target_type="agent_config_version",
            target_id=row.id,
            request_id=request_id,
            before_json=before,
            after_json=_row_to_response_payload(row),
        )
        await self._session.commit()
        await self._session.refresh(row)
        return row


def _row_to_effective_config(
    *,
    row: AgentConfigVersion,
    source: str,
    fallback: EffectiveAgentConfig,
) -> EffectiveAgentConfig:
    return EffectiveAgentConfig(
        agent_name=row.agent_name,
        instructions=row.instructions if row.instructions is not None else fallback.instructions,
        system_prompt=row.system_prompt if row.system_prompt is not None else fallback.system_prompt,
        model=row.model if row.model is not None else fallback.model,
        model_settings_json=dict(fallback.model_settings_json) | dict(row.model_settings_json or {}),
        feature_flags_json=dict(fallback.feature_flags_json) | dict(row.feature_flags_json or {}),
        source=source,
        version_id=str(row.id),
        version=row.version,
    )


def _row_to_response_payload(row: AgentConfigVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "tenant_id": row.tenant_id,
        "agent_name": row.agent_name,
        "version": row.version,
        "status": row.status,
        "change_note": row.change_note,
        "payload": {
            "instructions": row.instructions,
            "system_prompt": row.system_prompt,
            "model": row.model,
            "model_settings_json": dict(row.model_settings_json or {}),
            "feature_flags_json": dict(row.feature_flags_json or {}),
        },
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "activated_at": row.activated_at,
    }
