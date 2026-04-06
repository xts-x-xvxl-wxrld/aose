from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog, LlmCallLog, RunEvent, Tenant, TenantMembership, ToolCallLog, WorkflowRun
from app.repositories.admin_audit_log_repository import AdminAuditLogRepository
from app.repositories.llm_call_log_repository import LlmCallLogRepository
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.tool_call_log_repository import ToolCallLogRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.admin_access import AdminAccessService
from app.services.errors import ServiceError


class AdminOpsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._access = AdminAccessService(session)
        self._runs = WorkflowRunRepository(session)
        self._events = RunEventRepository(session)
        self._llm_calls = LlmCallLogRepository(session)
        self._tool_calls = ToolCallLogRepository(session)
        self._audits = AdminAuditLogRepository(session)

    async def get_platform_overview(self, *, actor_user_id: UUID) -> dict:
        await self._access.require_platform_admin(actor_user_id=actor_user_id)
        tenant_count = await self._scalar(select(func.count()).select_from(Tenant))
        run_counts = await self._session.execute(
            select(
                func.count(WorkflowRun.id),
                func.sum(case((WorkflowRun.status.in_(["queued", "running"]), 1), else_=0)),
                func.sum(case((WorkflowRun.status == "failed", 1), else_=0)),
            )
        )
        total_runs, active_runs, failed_runs = run_counts.one()
        total_llm_calls = await self._scalar(select(func.count()).select_from(LlmCallLog))
        total_tool_calls = await self._scalar(select(func.count()).select_from(ToolCallLog))
        return {
            "total_tenants": int(tenant_count or 0),
            "total_runs": int(total_runs or 0),
            "active_runs": int(active_runs or 0),
            "failed_runs": int(failed_runs or 0),
            "total_llm_calls": int(total_llm_calls or 0),
            "total_tool_calls": int(total_tool_calls or 0),
        }

    async def list_tenants(self, *, actor_user_id: UUID) -> list[dict]:
        await self._access.require_platform_admin(actor_user_id=actor_user_id)
        member_counts = (
            select(
                TenantMembership.tenant_id.label("tenant_id"),
                func.sum(case((TenantMembership.status == "active", 1), else_=0)).label(
                    "active_member_count"
                ),
            )
            .group_by(TenantMembership.tenant_id)
            .subquery()
        )
        run_counts = (
            select(
                WorkflowRun.tenant_id.label("tenant_id"),
                func.count(WorkflowRun.id).label("total_runs"),
                func.sum(case((WorkflowRun.status.in_(["queued", "running"]), 1), else_=0)).label(
                    "active_runs"
                ),
                func.sum(case((WorkflowRun.status == "failed", 1), else_=0)).label("failed_runs"),
            )
            .group_by(WorkflowRun.tenant_id)
            .subquery()
        )
        statement = (
            select(
                Tenant.id,
                Tenant.name,
                Tenant.slug,
                Tenant.status,
                member_counts.c.active_member_count,
                run_counts.c.total_runs,
                run_counts.c.active_runs,
                run_counts.c.failed_runs,
            )
            .select_from(Tenant)
            .join(member_counts, member_counts.c.tenant_id == Tenant.id, isouter=True)
            .join(run_counts, run_counts.c.tenant_id == Tenant.id, isouter=True)
            .order_by(Tenant.created_at.asc(), Tenant.id.asc())
        )
        result = await self._session.execute(statement)
        return [
            {
                "tenant_id": tenant_id,
                "tenant_name": name,
                "tenant_slug": slug,
                "tenant_status": status,
                "active_member_count": int(active_member_count or 0),
                "total_runs": int(total_runs or 0),
                "active_runs": int(active_runs or 0),
                "failed_runs": int(failed_runs or 0),
            }
            for tenant_id, name, slug, status, active_member_count, total_runs, active_runs, failed_runs in result.all()
        ]

    async def get_tenant_overview(self, *, actor_user_id: UUID, tenant_id: UUID) -> dict:
        await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
        result = await self._session.execute(
            select(
                func.count(WorkflowRun.id),
                func.sum(case((WorkflowRun.status == "queued", 1), else_=0)),
                func.sum(case((WorkflowRun.status == "running", 1), else_=0)),
                func.sum(case((WorkflowRun.status == "succeeded", 1), else_=0)),
                func.sum(case((WorkflowRun.status == "failed", 1), else_=0)),
                func.sum(case((WorkflowRun.status == "awaiting_review", 1), else_=0)),
            ).where(WorkflowRun.tenant_id == tenant_id)
        )
        total_runs, queued_runs, running_runs, succeeded_runs, failed_runs, awaiting_review_runs = result.one()
        total_llm_calls = await self._scalar(
            select(func.count()).select_from(LlmCallLog).where(LlmCallLog.tenant_id == tenant_id)
        )
        total_tool_calls = await self._scalar(
            select(func.count()).select_from(ToolCallLog).where(ToolCallLog.tenant_id == tenant_id)
        )
        return {
            "tenant_id": tenant_id,
            "total_runs": int(total_runs or 0),
            "queued_runs": int(queued_runs or 0),
            "running_runs": int(running_runs or 0),
            "succeeded_runs": int(succeeded_runs or 0),
            "failed_runs": int(failed_runs or 0),
            "awaiting_review_runs": int(awaiting_review_runs or 0),
            "total_llm_calls": int(total_llm_calls or 0),
            "total_tool_calls": int(total_tool_calls or 0),
        }

    async def list_runs(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> list[WorkflowRun]:
        await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
        return await self._runs.list_for_tenant(
            tenant_id=tenant_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get_run(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID,
        run_id: UUID,
    ) -> WorkflowRun:
        await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        return run

    async def list_run_events(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID,
        run_id: UUID,
    ) -> list[RunEvent]:
        await self.get_run(actor_user_id=actor_user_id, tenant_id=tenant_id, run_id=run_id)
        return list(await self._events.list_for_run(tenant_id=tenant_id, run_id=run_id))

    async def list_llm_calls(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID,
        run_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[LlmCallLog]:
        await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
        return list(await self._llm_calls.list_for_tenant(tenant_id=tenant_id, run_id=run_id, limit=limit, offset=offset))

    async def list_tool_calls(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID,
        run_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[ToolCallLog]:
        await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
        return list(await self._tool_calls.list_for_tenant(tenant_id=tenant_id, run_id=run_id, limit=limit, offset=offset))

    async def list_audit_logs(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[AdminAuditLog]:
        if tenant_id is None:
            await self._access.require_platform_admin(actor_user_id=actor_user_id)
        else:
            await self._access.require_tenant_admin(actor_user_id=actor_user_id, tenant_id=tenant_id)
        return list(await self._audits.list_logs(tenant_id=tenant_id, limit=limit, offset=offset))

    async def _scalar(self, statement):
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
