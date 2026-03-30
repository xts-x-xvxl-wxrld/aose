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
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.conversation import ConversationService
from app.services.workflow_runs import WorkflowRunService

from .helpers import get_postgres_test_urls

load_model_modules()


class _StubOrchestrator:
    async def decide(self, orchestrator_input: dict[str, object]) -> dict[str, object]:
        return {
            "decision_type": "reply_inline",
            "workflow_type": None,
            "target_agent": None,
            "reply_message": "Need more detail.",
            "reasoning_summary": "stub",
            "requires_persistence": False,
            "missing_inputs": [],
            "handoff_payload": None,
            "confidence": 1.0,
        }


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
async def test_conversation_service_records_turns_and_lists_messages(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())

    user = await user_repository.create(external_auth_subject="subject-conversation")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await db_session.commit()

    thread, user_message = await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        user_message="Find fintech accounts for this ICP.",
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )
    assistant_message = await service.append_assistant_reply(
        tenant_id=tenant.id,
        thread_id=thread.id,
        reply_message="I can do that once the run is queued.",
    )
    messages = await service.list_messages_for_thread(
        tenant_id=tenant.id,
        thread_id=thread.id,
    )

    assert thread.active_workflow == "account_search"
    assert user_message.role == "user"
    assert assistant_message.role == "assistant"
    assert [message.message_type for message in messages] == [
        "user_turn",
        "assistant_reply",
    ]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_conversation_service_reuses_thread_and_attaches_current_run(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())
    workflow_run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-conversation-run")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await db_session.commit()

    thread, _message = await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        user_message="Start account search.",
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )
    run = await workflow_run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={"objective": "Find accounts"},
        thread_id=thread.id,
    )
    updated_thread = await service.attach_run_to_thread(
        tenant_id=tenant.id,
        thread_id=thread.id,
        workflow_run_id=run.id,
        active_workflow=WorkflowType.ACCOUNT_RESEARCH,
    )
    workflow_status_message = await service.append_workflow_status_message(
        tenant_id=tenant.id,
        thread_id=thread.id,
        workflow_run_id=run.id,
        content_text="Workflow queued for account research.",
    )

    assert updated_thread.current_run_id == run.id
    assert updated_thread.active_workflow == "account_research"
    assert workflow_status_message.message_type == "workflow_status"
