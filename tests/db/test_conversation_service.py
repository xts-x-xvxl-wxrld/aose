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
from app.repositories.account_repository import AccountRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.conversation import ConversationService, normalize_chat_turn_request_payload
from app.services.errors import ServiceError
from app.services.runtime import InProcessWorkflowExecutor
from app.services.runtime_wiring import build_workflow_executor
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
        request_id="req-conversation-001",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Find fintech accounts for this ICP.",
            active_workflow=WorkflowType.ACCOUNT_SEARCH,
        ),
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
    assert thread.context_json is None


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
        request_id="req-conversation-run-001",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Start account search.",
            active_workflow=WorkflowType.ACCOUNT_SEARCH,
        ),
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


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_conversation_service_normalizes_persisted_thread_context_for_follow_up_turns(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_profiles = SellerProfileRepository(db_session)
    icp_profiles = ICPProfileRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())

    user = await user_repository.create(external_auth_subject="subject-conversation-follow-up")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    seller_profile = await seller_profiles.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Primary Seller",
        company_name="Acme",
        company_domain="acme.test",
        product_summary="Outbound platform",
        value_proposition="Helps teams find accounts",
    )
    icp_profile = await icp_profiles.create(
        tenant_id=tenant.id,
        seller_profile_id=seller_profile.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industry": ["fintech"]},
        status="active",
    )
    await db_session.commit()

    thread, _message = await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id="req-follow-up-001",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Find companies for this ICP.",
            seller_profile_id=seller_profile.id,
            active_workflow=WorkflowType.ACCOUNT_SEARCH,
        ),
        user_message="Find companies for this ICP.",
        seller_profile_id=seller_profile.id,
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )
    await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id="req-follow-up-002",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Use this ICP.",
            thread_id=thread.id,
            icp_profile_id=icp_profile.id,
        ),
        user_message="Use this ICP.",
        thread_id=thread.id,
        icp_profile_id=icp_profile.id,
    )

    orchestrator_input = await service.normalize_chat_turn_input(
        context={
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "membership_role": "member",
            "request_id": "req_follow_up",
        },
        user_message="go ahead",
        thread_id=thread.id,
    )

    refreshed_thread = await service.get_thread_for_tenant(tenant_id=tenant.id, thread_id=thread.id)

    assert refreshed_thread is not None
    assert refreshed_thread.context_json == {"icp_profile_id": str(icp_profile.id)}
    assert orchestrator_input["thread_id"] == str(thread.id)
    assert orchestrator_input["seller_profile_id"] == str(seller_profile.id)
    assert orchestrator_input["icp_profile_id"] == str(icp_profile.id)
    assert orchestrator_input["active_workflow"] is WorkflowType.ACCOUNT_SEARCH


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_conversation_service_rejects_cross_tenant_selection_during_normalization(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_profiles = SellerProfileRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())

    user = await user_repository.create(external_auth_subject="subject-cross-tenant-context")
    first_tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    second_tenant = await tenant_repository.create(name="Tenant Two", slug="tenant-two")
    seller_profile = await seller_profiles.create(
        tenant_id=second_tenant.id,
        created_by_user_id=user.id,
        name="Other Seller",
        company_name="Elsewhere",
        company_domain="elsewhere.test",
        product_summary="Other outbound platform",
        value_proposition="Other ICP targeting",
    )
    await db_session.commit()

    with pytest.raises(ServiceError, match="Seller profile was not found"):
        await service.normalize_chat_turn_input(
            context={
                "tenant_id": str(first_tenant.id),
                "user_id": str(user.id),
                "membership_role": "member",
                "request_id": "req_cross_tenant",
            },
            user_message="Find accounts for this seller.",
            seller_profile_id=seller_profile.id,
        )


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_conversation_service_explicit_account_override_drops_stale_persisted_contact(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    account_repository = AccountRepository(db_session)
    contact_repository = ContactRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())
    workflow_run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-override")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await db_session.commit()

    thread, _message = await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id="req-account-override-001",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Find contacts for this account.",
            active_workflow=WorkflowType.CONTACT_SEARCH,
        ),
        user_message="Find contacts for this account.",
        active_workflow=WorkflowType.CONTACT_SEARCH,
    )
    seed_run = await workflow_run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={"objective": "seed accounts"},
        thread_id=thread.id,
    )
    first_account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        source_workflow_run_id=seed_run.id,
        name="First Account",
        status="new",
    )
    second_account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        source_workflow_run_id=seed_run.id,
        name="Second Account",
        status="new",
    )
    contact = await contact_repository.create(
        tenant_id=tenant.id,
        account_id=first_account.id,
        created_by_user_id=user.id,
        full_name="Jordan Buyer",
        status="new",
    )
    await db_session.commit()

    await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id="req-account-override-002",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Use this account contact context.",
            thread_id=thread.id,
            selected_account_id=first_account.id,
            selected_contact_id=contact.id,
        ),
        user_message="Use this account contact context.",
        thread_id=thread.id,
        selected_account_id=first_account.id,
        selected_contact_id=contact.id,
    )

    orchestrator_input = await service.normalize_chat_turn_input(
        context={
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "membership_role": "member",
            "request_id": "req_account_override",
        },
        user_message="find contacts for this account",
        thread_id=thread.id,
        selected_account_id=second_account.id,
    )

    assert orchestrator_input["selected_account_id"] == str(second_account.id)
    assert orchestrator_input["selected_contact_id"] is None


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_conversation_service_starts_chat_workflow_run_and_links_thread(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_profiles = SellerProfileRepository(db_session)
    icp_profiles = ICPProfileRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())

    user = await user_repository.create(external_auth_subject="subject-chat-workflow-run")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    seller_profile = await seller_profiles.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Primary Seller",
        company_name="Acme",
        company_domain="acme.test",
        product_summary="Outbound platform",
        value_proposition="Helps teams find accounts",
    )
    icp_profile = await icp_profiles.create(
        tenant_id=tenant.id,
        seller_profile_id=seller_profile.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industry": ["fintech"]},
        status="active",
    )
    await db_session.commit()

    thread, _message = await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id="req-chat-workflow-run-001",
        request_payload_json=normalize_chat_turn_request_payload(
            user_message="Find companies matching my ICP.",
            seller_profile_id=seller_profile.id,
            icp_profile_id=icp_profile.id,
            active_workflow=WorkflowType.ACCOUNT_SEARCH,
        ),
        user_message="Find companies matching my ICP.",
        seller_profile_id=seller_profile.id,
        icp_profile_id=icp_profile.id,
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )

    async_url, _sync_url = get_postgres_test_urls()
    executor_engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(
        bind=executor_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    executor = build_workflow_executor(session_factory)
    try:
        workflow_run, response_message = await service.start_workflow_run(
            tenant_id=tenant.id,
            thread_id=thread.id,
            created_by_user_id=user.id,
            request_id="req-chat-workflow-run-001",
            workflow_type=WorkflowType.ACCOUNT_SEARCH,
            user_message="Find companies matching my ICP.",
            seller_profile_id=str(seller_profile.id),
            icp_profile_id=str(icp_profile.id),
            selected_account_id=None,
            executor=executor,
        )
        await executor.wait_for_all()
    finally:
        await executor_engine.dispose()

    refreshed_run = await service.get_current_run_for_thread(tenant_id=tenant.id, thread_id=thread.id)
    refreshed_thread = await service.get_thread_for_tenant(tenant_id=tenant.id, thread_id=thread.id)
    messages = await service.list_messages_for_thread(tenant_id=tenant.id, thread_id=thread.id)

    assert refreshed_thread is not None
    assert refreshed_run is not None
    assert refreshed_thread.current_run_id == workflow_run.id
    assert workflow_run.thread_id == thread.id
    assert WorkflowRunStatus(refreshed_run.status) is WorkflowRunStatus.SUCCEEDED
    assert response_message.message_type == "assistant_reply"
    assert [message.message_type for message in messages[:3]] == [
        "user_turn",
        "assistant_reply",
        "workflow_status",
    ]
    assert messages[-1].message_type == "assistant_reply"
    assert "finished the account search workflow" in messages[-1].content_text.lower()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_conversation_service_repairs_interrupted_workflow_start_from_request_id(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_profiles = SellerProfileRepository(db_session)
    icp_profiles = ICPProfileRepository(db_session)
    service = ConversationService(db_session, orchestrator=_StubOrchestrator())
    workflow_run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-chat-workflow-repair")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    seller_profile = await seller_profiles.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Primary Seller",
        company_name="Acme",
        company_domain="acme.test",
        product_summary="Outbound platform",
        value_proposition="Helps teams find accounts",
    )
    icp_profile = await icp_profiles.create(
        tenant_id=tenant.id,
        seller_profile_id=seller_profile.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industry": ["fintech"]},
        status="active",
    )
    await db_session.commit()

    request_id = "req-chat-workflow-repair-001"
    request_payload_json = normalize_chat_turn_request_payload(
        user_message="Find companies matching my ICP.",
        seller_profile_id=seller_profile.id,
        icp_profile_id=icp_profile.id,
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )
    thread, user_message = await service.record_user_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id=request_id,
        request_payload_json=request_payload_json,
        user_message="Find companies matching my ICP.",
        seller_profile_id=seller_profile.id,
        icp_profile_id=icp_profile.id,
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )
    run = await workflow_run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={
            "seller_profile_id": str(seller_profile.id),
            "icp_profile_id": str(icp_profile.id),
            "search_objective": "Find companies matching my ICP.",
        },
        thread_id=thread.id,
        correlation_id=request_id,
        status_detail="Queued account search workflow run from chat.",
    )
    await service.attach_run_to_thread(
        tenant_id=tenant.id,
        thread_id=thread.id,
        workflow_run_id=run.id,
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )

    accepted_turn = await service.resolve_accepted_chat_turn(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        request_id=request_id,
        request_payload_json=request_payload_json,
    )

    assert accepted_turn is not None
    assert accepted_turn.user_message.id == user_message.id
    assert accepted_turn.response_message is None

    repaired_outcome = await service.repair_accepted_workflow_turn(
        tenant_id=tenant.id,
        thread_id=thread.id,
        request_id=request_id,
        executor=InProcessWorkflowExecutor(),
    )

    assert repaired_outcome is not None
    repaired_run, response_message = repaired_outcome
    messages = await service.list_messages_for_thread(tenant_id=tenant.id, thread_id=thread.id)

    assert repaired_run.id == run.id
    assert response_message.message_type == "assistant_reply"
    assert [message.message_type for message in messages[:3]] == [
        "user_turn",
        "assistant_reply",
        "workflow_status",
    ]
    assert sum(message.message_type == "assistant_reply" for message in messages) == 1
