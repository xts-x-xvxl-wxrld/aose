from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import load_model_modules
from app.orchestration.contracts import WorkflowType
from app.repositories.conversation_thread_repository import ConversationThreadRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.runtime import InProcessWorkflowExecutor, WorkflowExecutionRequest
from app.services.workflow_runs import WorkflowRunService
from app.workflows.contracts import AccountSearchRunResult, AccountSearchRunResultOutcome

from .helpers import get_postgres_test_urls

load_model_modules()


async def _reset_async_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async_url, _sync_url = get_postgres_test_urls()
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    await _reset_async_database(session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_workflow_run_service_creates_dispatches_and_lists_events(
    db_session: AsyncSession,
) -> None:
    received_requests: list[WorkflowExecutionRequest] = []
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    thread_repository = ConversationThreadRepository(db_session)

    async def account_search_handler(request: WorkflowExecutionRequest) -> None:
        received_requests.append(request)

    executor = InProcessWorkflowExecutor()
    executor.register_handler(WorkflowType.ACCOUNT_SEARCH, account_search_handler)
    service = WorkflowRunService(db_session, executor=executor)

    user = await user_repository.create(external_auth_subject="subject-workflow-run-service")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    thread = await thread_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        active_workflow="account_search",
    )
    await db_session.commit()

    result = AccountSearchRunResult(
        outcome=AccountSearchRunResultOutcome.NO_RESULTS,
        accepted_account_ids=[],
        reason_summary="No matches found.",
        search_attempt_count=1,
    )

    run = await service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type="account_search",
        requested_payload_json={"objective": "Find fintech accounts"},
        thread_id=thread.id,
        status_detail="Queued for immediate in-process execution.",
        correlation_id="corr-123",
    )
    dispatched_request = await service.dispatch_queued_run(run=run, request_id="req_789")
    first_event = await service.emit_event(
        tenant_id=tenant.id,
        run_id=run.id,
        event_name="run.started",
        payload_json={"workflow_type": run.workflow_type, "thread_id": str(thread.id)},
    )
    second_event = await service.emit_event(
        tenant_id=tenant.id,
        run_id=run.id,
        event_name="run.completed",
        payload_json=result.model_dump(mode="json"),
    )
    events = await service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)

    assert run.status == "queued"
    assert run.workflow_type == "account_search"
    assert dispatched_request.run_id == run.id
    assert received_requests == [dispatched_request]
    assert [event.id for event in events] == [first_event.id, second_event.id]
    assert events[1].payload_json["outcome"] == "no_results"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_workflow_run_service_lifecycle_helpers_update_status_and_emit_tool_events(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-workflow-lifecycle")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await db_session.commit()

    run = await service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={"objective": "Find fintech accounts"},
    )
    running_run = await service.mark_running(
        tenant_id=tenant.id,
        run_id=run.id,
        status_detail="Worker claimed the run.",
    )
    await service.emit_tool_started(
        tenant_id=tenant.id,
        run_id=run.id,
        tool_name="web_search",
        provider_name="example-search",
        input_summary="Searching for fintech accounts.",
        correlation_key="tool-123",
    )
    await service.emit_tool_completed(
        tenant_id=tenant.id,
        run_id=run.id,
        tool_name="web_search",
        provider_name="example-search",
        output_summary="Collected ranked search results.",
        produced_evidence_results=True,
    )
    succeeded_run = await service.mark_succeeded(
        tenant_id=tenant.id,
        run_id=run.id,
        result_summary="Completed account ranking.",
        normalized_result_json={"outcome": "no_results"},
        canonical_output_ids={"account_ids": []},
    )
    events = await service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)

    assert running_run.started_at is not None
    assert succeeded_run.status == "succeeded"
    assert succeeded_run.finished_at is not None
    assert [event.event_name for event in events] == [
        "run.started",
        "tool.started",
        "tool.completed",
        "run.completed",
    ]
    assert events[1].payload_json["tool_name"] == "web_search"
    assert events[2].payload_json["produced_evidence_results"] is True
