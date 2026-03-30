from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import load_model_modules
from app.orchestration.contracts import WorkflowRunStatus, WorkflowType
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.workflow_runs import WorkflowRunService
from app.workers.runtime import (
    WorkflowExecutionError,
    WorkflowExecutionResult,
    execute_workflow_request,
)

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
async def test_workflow_execution_runtime_marks_success_and_emits_events(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-runtime-success")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await db_session.commit()

    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={"objective": "Find accounts"},
    )
    request = run_service.build_execution_request(run=run, request_id="req-runtime-success")

    async def handler(_request: object) -> WorkflowExecutionResult:
        return WorkflowExecutionResult(
            result_summary="Ranked accounts and persisted them.",
            normalized_result_json={"outcome": "accounts_found", "accepted_account_ids": []},
            canonical_output_ids={"account_ids": []},
            status_detail="Workflow execution completed cleanly.",
        )

    result = await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=handler,
    )
    refreshed_run = await run_service.get_run_for_tenant(tenant_id=tenant.id, run_id=run.id)
    assert refreshed_run is not None
    events = await run_service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)

    assert result.status is WorkflowRunStatus.SUCCEEDED
    assert refreshed_run.status == "succeeded"
    assert refreshed_run.started_at is not None
    assert refreshed_run.finished_at is not None
    assert [event.event_name for event in events] == ["run.started", "run.completed"]
    assert events[1].payload_json["result_summary"] == "Ranked accounts and persisted them."


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_workflow_execution_runtime_marks_failed_on_execution_error(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-runtime-failure")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await db_session.commit()

    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_RESEARCH,
        requested_payload_json={"account_id": "acct_123"},
    )
    request = run_service.build_execution_request(run=run, request_id="req-runtime-failure")

    async def handler(_request: object) -> WorkflowExecutionResult:
        raise WorkflowExecutionError(
            error_code="provider_unavailable",
            message="Provider enrichment is unavailable.",
            status_detail="Retry after provider recovery.",
        )

    result = await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=handler,
    )
    refreshed_run = await run_service.get_run_for_tenant(tenant_id=tenant.id, run_id=run.id)
    assert refreshed_run is not None
    events = await run_service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)

    assert result.status is WorkflowRunStatus.FAILED
    assert refreshed_run.status == "failed"
    assert refreshed_run.error_code == "provider_unavailable"
    assert [event.event_name for event in events] == ["run.started", "run.failed"]
    assert events[1].payload_json["error_code"] == "provider_unavailable"
