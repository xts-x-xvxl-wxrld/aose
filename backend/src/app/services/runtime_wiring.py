from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.orchestration.contracts import WorkflowType
from app.services.agent_configs import AgentConfigService
from app.services.runtime import InProcessWorkflowExecutor, WorkflowExecutionRequest
from app.services.workflow_runs import WorkflowRunService
from app.tools.provider_factory import (
    WorkflowToolFactory,
    build_phase3_tool_factory,
)
from app.workers.runtime import execute_workflow_request
from app.workflows.account_research import AccountResearchWorkflow
from app.workflows.account_search import AccountSearchWorkflow
from app.workflows.contact_search import ContactSearchWorkflow


def build_workflow_executor(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: Settings | None = None,
    tool_factory: WorkflowToolFactory | None = None,
) -> InProcessWorkflowExecutor:
    resolved_settings = settings or get_settings()
    resolved_tool_factory = tool_factory or build_phase3_tool_factory(resolved_settings)
    executor = InProcessWorkflowExecutor()
    executor.register_handler(
        WorkflowType.ACCOUNT_SEARCH,
        _build_account_search_handler(session_factory, resolved_tool_factory, resolved_settings),
    )
    executor.register_handler(
        WorkflowType.ACCOUNT_RESEARCH,
        _build_account_research_handler(session_factory, resolved_tool_factory, resolved_settings),
    )
    executor.register_handler(
        WorkflowType.CONTACT_SEARCH,
        _build_contact_search_handler(session_factory, resolved_tool_factory, resolved_settings),
    )
    return executor


def _build_account_search_handler(
    session_factory: async_sessionmaker[AsyncSession],
    tool_factory: WorkflowToolFactory,
    settings: Settings,
):
    async def handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await _attach_run_config_snapshot(
                session=session,
                run_service=run_service,
                request=request,
                settings=settings,
            )
            workflow = AccountSearchWorkflow(
                session,
                run_service=run_service,
                tools=tool_factory.build_account_search_toolset(),
            )
            await execute_workflow_request(
                request=request,
                run_service=run_service,
                handler=workflow.execute,
            )

    return handler


def _build_account_research_handler(
    session_factory: async_sessionmaker[AsyncSession],
    tool_factory: WorkflowToolFactory,
    settings: Settings,
):
    async def handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await _attach_run_config_snapshot(
                session=session,
                run_service=run_service,
                request=request,
                settings=settings,
            )
            workflow = AccountResearchWorkflow(
                session,
                run_service=run_service,
                tools=tool_factory.build_account_research_toolset(),
            )
            await execute_workflow_request(
                request=request,
                run_service=run_service,
                handler=workflow.execute,
            )

    return handler


def _build_contact_search_handler(
    session_factory: async_sessionmaker[AsyncSession],
    tool_factory: WorkflowToolFactory,
    settings: Settings,
):
    async def handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await _attach_run_config_snapshot(
                session=session,
                run_service=run_service,
                request=request,
                settings=settings,
            )
            workflow = ContactSearchWorkflow(
                session,
                run_service=run_service,
                tools=tool_factory.build_contact_search_toolset(),
            )
            await execute_workflow_request(
                request=request,
                run_service=run_service,
                handler=workflow.execute,
            )

    return handler


async def _attach_run_config_snapshot(
    *,
    session: AsyncSession,
    run_service: WorkflowRunService,
    request: WorkflowExecutionRequest,
    settings: Settings,
) -> None:
    config_service = AgentConfigService(session, settings=settings)
    snapshot = await config_service.build_run_config_snapshot(
        tenant_id=request.tenant_id,
        workflow_type=request.workflow_type.value,
    )
    await run_service.attach_config_snapshot(
        tenant_id=request.tenant_id,
        run_id=request.run_id,
        config_snapshot_json=snapshot,
    )
