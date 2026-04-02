from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.orchestration.contracts import WorkflowType
from app.services.runtime import InProcessWorkflowExecutor, WorkflowExecutionRequest
from app.services.workflow_runs import WorkflowRunService
from app.workers.runtime import execute_workflow_request
from app.workflows.account_research import AccountResearchWorkflow
from app.workflows.account_search import AccountSearchWorkflow
from app.workflows.contact_search import ContactSearchWorkflow


def build_workflow_executor(
    session_factory: async_sessionmaker[AsyncSession],
) -> InProcessWorkflowExecutor:
    executor = InProcessWorkflowExecutor()
    executor.register_handler(
        WorkflowType.ACCOUNT_SEARCH,
        _build_account_search_handler(session_factory),
    )
    executor.register_handler(
        WorkflowType.ACCOUNT_RESEARCH,
        _build_account_research_handler(session_factory),
    )
    executor.register_handler(
        WorkflowType.CONTACT_SEARCH,
        _build_contact_search_handler(session_factory),
    )
    return executor


def _build_account_search_handler(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            workflow = AccountSearchWorkflow(session, run_service=run_service)
            await execute_workflow_request(
                request=request,
                run_service=run_service,
                handler=workflow.execute,
            )

    return handler


def _build_account_research_handler(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            workflow = AccountResearchWorkflow(session, run_service=run_service)
            await execute_workflow_request(
                request=request,
                run_service=run_service,
                handler=workflow.execute,
            )

    return handler


def _build_contact_search_handler(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            workflow = ContactSearchWorkflow(session, run_service=run_service)
            await execute_workflow_request(
                request=request,
                run_service=run_service,
                handler=workflow.execute,
            )

    return handler
