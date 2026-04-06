from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DbSessionDep, PersistedActorUserDep, RequestIdDep
from app.schemas.admin import (
    AdminAuditLogListResponse,
    AdminAuditLogResponse,
    AdminOverviewResponse,
    AdminRunDetailResponse,
    AdminRunEventListResponse,
    AdminRunEventResponse,
    AdminRunListResponse,
    AdminRunSummaryResponse,
    AdminTenantListResponse,
    AdminTenantOpsOverviewResponse,
    AdminTenantSummaryResponse,
    AgentConfigScopeResponse,
    AgentConfigVersionCreateRequest,
    AgentConfigVersionResponse,
    LlmCallLogListResponse,
    LlmCallLogResponse,
    ToolCallLogListResponse,
    ToolCallLogResponse,
)
from app.services.admin_ops import AdminOpsService
from app.services.agent_configs import AgentConfigService, _row_to_response_payload
from app.config import get_settings

router = APIRouter(prefix="/admin")


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_platform_overview(
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AdminOverviewResponse:
    payload = await AdminOpsService(db_session).get_platform_overview(actor_user_id=actor_user.id)
    return AdminOverviewResponse(**payload)


@router.get("/tenants", response_model=AdminTenantListResponse)
async def list_tenants(
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AdminTenantListResponse:
    rows = await AdminOpsService(db_session).list_tenants(actor_user_id=actor_user.id)
    return AdminTenantListResponse(
        tenants=[AdminTenantSummaryResponse(**row) for row in rows]
    )


@router.get("/tenants/{tenant_id}/ops/overview", response_model=AdminTenantOpsOverviewResponse)
async def get_tenant_overview(
    tenant_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AdminTenantOpsOverviewResponse:
    payload = await AdminOpsService(db_session).get_tenant_overview(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
    )
    return AdminTenantOpsOverviewResponse(**payload)


@router.get("/tenants/{tenant_id}/ops/runs", response_model=AdminRunListResponse)
async def list_runs(
    tenant_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
) -> AdminRunListResponse:
    runs = await AdminOpsService(db_session).list_runs(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    return AdminRunListResponse(
        runs=[_to_run_summary_response(run) for run in runs],
        limit=limit,
        offset=offset,
    )


@router.get("/tenants/{tenant_id}/ops/runs/{run_id}", response_model=AdminRunDetailResponse)
async def get_run(
    tenant_id: UUID,
    run_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AdminRunDetailResponse:
    run = await AdminOpsService(db_session).get_run(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return AdminRunDetailResponse(
        **_to_run_summary_response(run).model_dump(),
        requested_payload_json=run.requested_payload_json,
        config_snapshot_json=run.config_snapshot_json,
        normalized_result_json=run.normalized_result_json,
    )


@router.get("/tenants/{tenant_id}/ops/runs/{run_id}/events", response_model=AdminRunEventListResponse)
async def list_run_events(
    tenant_id: UUID,
    run_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AdminRunEventListResponse:
    events = await AdminOpsService(db_session).list_run_events(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return AdminRunEventListResponse(
        events=[
            AdminRunEventResponse(
                event_id=event.id,
                run_id=event.run_id,
                event_name=event.event_name,
                payload_json=event.payload_json,
                created_at=event.created_at,
            )
            for event in events
        ]
    )


@router.get("/tenants/{tenant_id}/ops/llm-calls", response_model=LlmCallLogListResponse)
async def list_llm_calls(
    tenant_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
    run_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LlmCallLogListResponse:
    rows = await AdminOpsService(db_session).list_llm_calls(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return LlmCallLogListResponse(
        calls=[LlmCallLogResponse.model_validate(row, from_attributes=True) for row in rows],
        limit=limit,
        offset=offset,
    )


@router.get("/tenants/{tenant_id}/ops/tool-calls", response_model=ToolCallLogListResponse)
async def list_tool_calls(
    tenant_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
    run_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ToolCallLogListResponse:
    rows = await AdminOpsService(db_session).list_tool_calls(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return ToolCallLogListResponse(
        calls=[ToolCallLogResponse.model_validate(row, from_attributes=True) for row in rows],
        limit=limit,
        offset=offset,
    )


@router.get("/agent-configs/global", response_model=AgentConfigScopeResponse)
async def list_global_agent_configs(
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AgentConfigScopeResponse:
    service = AgentConfigService(db_session, settings=get_settings())
    configs = await service.list_scope_configs(actor_user_id=actor_user.id, scope_type="global")
    return AgentConfigScopeResponse(scope_type="global", tenant_id=None, configs=configs)


@router.get("/tenants/{tenant_id}/agent-configs", response_model=AgentConfigScopeResponse)
async def list_tenant_agent_configs(
    tenant_id: UUID,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
) -> AgentConfigScopeResponse:
    service = AgentConfigService(db_session, settings=get_settings())
    configs = await service.list_scope_configs(
        actor_user_id=actor_user.id,
        scope_type="tenant",
        tenant_id=tenant_id,
    )
    return AgentConfigScopeResponse(scope_type="tenant", tenant_id=tenant_id, configs=configs)


@router.post(
    "/agent-configs/global/versions",
    response_model=AgentConfigVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_global_agent_config_version(
    payload: AgentConfigVersionCreateRequest,
    actor_user: PersistedActorUserDep,
    request_id: RequestIdDep,
    db_session: DbSessionDep,
) -> AgentConfigVersionResponse:
    service = AgentConfigService(db_session, settings=get_settings())
    row = await service.create_version(
        actor_user_id=actor_user.id,
        request_id=request_id,
        scope_type="global",
        tenant_id=None,
        payload=payload.model_dump(mode="json"),
    )
    return AgentConfigVersionResponse(**_row_to_response_payload(row))


@router.post(
    "/tenants/{tenant_id}/agent-configs/versions",
    response_model=AgentConfigVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant_agent_config_version(
    tenant_id: UUID,
    payload: AgentConfigVersionCreateRequest,
    actor_user: PersistedActorUserDep,
    request_id: RequestIdDep,
    db_session: DbSessionDep,
) -> AgentConfigVersionResponse:
    service = AgentConfigService(db_session, settings=get_settings())
    row = await service.create_version(
        actor_user_id=actor_user.id,
        request_id=request_id,
        scope_type="tenant",
        tenant_id=tenant_id,
        payload=payload.model_dump(mode="json"),
    )
    return AgentConfigVersionResponse(**_row_to_response_payload(row))


@router.post("/agent-configs/{version_id}/activate", response_model=AgentConfigVersionResponse)
async def activate_agent_config_version(
    version_id: UUID,
    actor_user: PersistedActorUserDep,
    request_id: RequestIdDep,
    db_session: DbSessionDep,
) -> AgentConfigVersionResponse:
    service = AgentConfigService(db_session, settings=get_settings())
    row = await service.activate_version(
        actor_user_id=actor_user.id,
        request_id=request_id,
        version_id=version_id,
    )
    return AgentConfigVersionResponse(**_row_to_response_payload(row))


@router.post("/agent-configs/{version_id}/rollback", response_model=AgentConfigVersionResponse)
async def rollback_agent_config_version(
    version_id: UUID,
    actor_user: PersistedActorUserDep,
    request_id: RequestIdDep,
    db_session: DbSessionDep,
) -> AgentConfigVersionResponse:
    service = AgentConfigService(db_session, settings=get_settings())
    row = await service.activate_version(
        actor_user_id=actor_user.id,
        request_id=request_id,
        version_id=version_id,
        action="agent_config.rollback_version",
    )
    return AgentConfigVersionResponse(**_row_to_response_payload(row))


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
async def list_audit_logs(
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
    tenant_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminAuditLogListResponse:
    rows = await AdminOpsService(db_session).list_audit_logs(
        actor_user_id=actor_user.id,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    return AdminAuditLogListResponse(
        logs=[AdminAuditLogResponse.model_validate(row, from_attributes=True) for row in rows],
        limit=limit,
        offset=offset,
    )


def _to_run_summary_response(run) -> AdminRunSummaryResponse:
    return AdminRunSummaryResponse(
        run_id=run.id,
        tenant_id=run.tenant_id,
        thread_id=run.thread_id,
        workflow_type=run.workflow_type,
        status=run.status,
        status_detail=run.status_detail,
        error_code=run.error_code,
        created_by_user_id=run.created_by_user_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
