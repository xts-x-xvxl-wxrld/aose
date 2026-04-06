from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db_session, get_optional_db_session
from app.config import get_settings
from app.db.base import Base
from app.main import create_app
from app.models import load_model_modules
from app.orchestration.contracts import WorkflowType
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.user_repository import UserRepository
from app.services.runtime import InProcessWorkflowExecutor, WorkflowExecutionRequest
from app.services.runtime_wiring import build_workflow_executor
from app.services.workflow_runs import WorkflowRunService
from tests.db.helpers import get_postgres_test_urls

load_model_modules()


async def _reset_async_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    async_url, _sync_url = get_postgres_test_urls()
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    await _reset_async_database(session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _extract_first_frame_text(body_text: str) -> dict[str, str]:
    first_line = body_text.strip().splitlines()[0]
    assert first_line.startswith("data: ")
    return json.loads(first_line.removeprefix("data: "))


def _extract_data_frames(body_text: str) -> list[object]:
    frames: list[object] = []
    for line in body_text.strip().splitlines():
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ")
        if payload == "[DONE]":
            frames.append(payload)
            continue
        frames.append(json.loads(payload))
    return frames


async def _wait_for(
    callback,
    *,
    timeout: float = 10.0,
    interval: float = 0.05,
):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = await callback()
        if result:
            return result
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("Timed out while waiting for async state to settle.")
        await asyncio.sleep(interval)


async def _load_terminal_thread_messages(
    *,
    client: AsyncClient,
    tenant_id: str,
    thread_id: str,
) -> list[dict[str, object]] | None:
    response = await client.get(f"/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages")
    if response.status_code != 200:
        return None
    messages = response.json()["messages"]
    if len(messages) < 6:
        return None
    if messages[-1]["message_type"] != "assistant_reply":
        return None
    return messages


def _configure_test_workflow_executor(
    *,
    app,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app.state.workflow_executor = build_workflow_executor(session_factory)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_entry_discovers_zero_one_and_multiple_tenants(db_engine: AsyncEngine) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/tenants")
            assert response.status_code == 200
            assert response.json()["tenants"] == []

            first_tenant = await client.post(
                "/api/v1/tenants",
                json={"name": "Tenant One", "slug": "tenant-one"},
            )
            assert first_tenant.status_code == 201

            response = await client.get("/api/v1/tenants")
            assert response.status_code == 200
            assert len(response.json()["tenants"]) == 1

            second_tenant = await client.post(
                "/api/v1/tenants",
                json={"name": "Tenant Two", "slug": "tenant-two"},
            )
            assert second_tenant.status_code == 201

            response = await client.get("/api/v1/tenants")
            assert response.status_code == 200
            assert len(response.json()["tenants"]) == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_stream_requires_request_id_and_respects_route_tenant(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Primary Tenant", "slug": "primary-tenant"},
            )
            assert create_response.status_code == 201
            tenant_id = create_response.json()["tenant_id"]

            missing_header = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                json={"user_message": "hello"},
            )
            assert missing_header.status_code == 422
            assert missing_header.json()["error_code"] == "validation_error"

            stream_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={
                    "X-Request-ID": "req-chat-001",
                    "X-Tenant-ID": "ignored-tenant-hint",
                },
                json={"user_message": "Start the chat workspace."},
            )
            assert stream_response.status_code == 200
            assert stream_response.headers["content-type"].startswith("text/event-stream")

            frame = _extract_first_frame_text(stream_response.text)
            assert frame["request_id"] == "req-chat-001"
            thread_id = frame["thread_id"]

            thread_response = await client.get(
                f"/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}"
            )
            assert thread_response.status_code == 200
            assert thread_response.json()["tenant_id"] == tenant_id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_thread_and_message_routes_reject_cross_tenant_lookup(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            first_tenant = await client.post(
                "/api/v1/tenants",
                json={"name": "Tenant One", "slug": "tenant-one"},
            )
            second_tenant = await client.post(
                "/api/v1/tenants",
                json={"name": "Tenant Two", "slug": "tenant-two"},
            )
            assert first_tenant.status_code == 201
            assert second_tenant.status_code == 201

            tenant_one_id = first_tenant.json()["tenant_id"]
            tenant_two_id = second_tenant.json()["tenant_id"]

            stream_response = await client.post(
                f"/api/v1/tenants/{tenant_one_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-002"},
                json={"user_message": "Persist this first turn."},
            )
            assert stream_response.status_code == 200

            frame = _extract_first_frame_text(stream_response.text)
            thread_id = UUID(frame["thread_id"])

            wrong_thread_response = await client.get(
                f"/api/v1/tenants/{tenant_two_id}/chat/threads/{thread_id}"
            )
            assert wrong_thread_response.status_code == 404
            assert wrong_thread_response.json()["error_code"] == "resource_not_found"

            wrong_messages_response = await client.get(
                f"/api/v1/tenants/{tenant_two_id}/chat/threads/{thread_id}/messages"
            )
            assert wrong_messages_response.status_code == 404
            assert wrong_messages_response.json()["error_code"] == "resource_not_found"

            messages_response = await client.get(
                f"/api/v1/tenants/{tenant_one_id}/chat/threads/{thread_id}/messages"
            )
            assert messages_response.status_code == 200
            body = messages_response.json()
            assert [message["message_type"] for message in body["messages"]] == [
                "user_turn",
                "assistant_reply",
            ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_stream_retry_reuses_first_turn_without_duplicate_thread_or_messages(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Retry Tenant", "slug": "retry-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            first_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-retry-001"},
                json={"user_message": "Persist this turn once."},
            )
            assert first_response.status_code == 200
            first_frame = _extract_first_frame_text(first_response.text)

            retry_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-retry-001"},
                json={"user_message": "Persist this turn once."},
            )
            assert retry_response.status_code == 200
            retry_frame = _extract_first_frame_text(retry_response.text)

            assert retry_frame == first_frame

            messages_response = await client.get(
                f"/api/v1/tenants/{tenant_id}/chat/threads/{first_frame['thread_id']}/messages"
            )
            assert messages_response.status_code == 200
            assert [
                message["message_type"] for message in messages_response.json()["messages"]
            ] == [
                "user_turn",
                "assistant_reply",
            ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_stream_rejects_conflicting_retry_for_same_request_id(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Conflict Tenant", "slug": "conflict-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            first_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-conflict-001"},
                json={"user_message": "Research this account."},
            )
            assert first_response.status_code == 200

            conflicting_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-conflict-001"},
                json={"user_message": "Find contacts for this account."},
            )
            assert conflicting_response.status_code == 409
            assert conflicting_response.json()["error_code"] == "request_id_conflict"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_stream_retry_reuses_follow_up_turn_on_existing_thread(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Follow Up Tenant", "slug": "follow-up-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            first_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-follow-up-001"},
                json={"user_message": "Start the thread."},
            )
            assert first_response.status_code == 200
            thread_id = _extract_first_frame_text(first_response.text)["thread_id"]

            follow_up_payload = {
                "thread_id": thread_id,
                "user_message": "Continue with this thread.",
            }
            follow_up_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-follow-up-002"},
                json=follow_up_payload,
            )
            assert follow_up_response.status_code == 200

            retry_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-follow-up-002"},
                json=follow_up_payload,
            )
            assert retry_response.status_code == 200

            messages_response = await client.get(
                f"/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages"
            )
            assert messages_response.status_code == 200
            assert [
                message["message_type"] for message in messages_response.json()["messages"]
            ] == [
                "user_turn",
                "assistant_reply",
                "user_turn",
                "assistant_reply",
            ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_stream_starts_workflow_and_emits_meta_frame(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Workflow Tenant", "slug": "workflow-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            settings = get_settings()
            async with session_factory() as session:
                users = UserRepository(session)
                user = await users.get_by_external_auth_subject(
                    external_auth_subject=settings.fake_auth_subject,
                )
                if user is None:
                    user = await users.create(
                        external_auth_subject=settings.fake_auth_subject,
                        email=settings.fake_auth_email,
                        display_name=settings.fake_auth_display_name,
                    )
                seller_profile = await SellerProfileRepository(session).create(
                    tenant_id=UUID(tenant_id),
                    created_by_user_id=user.id,
                    name="Primary Seller",
                    company_name="Acme",
                    company_domain="acme.test",
                    product_summary="Outbound platform",
                    value_proposition="Helps teams find accounts",
                )
                icp_profile = await ICPProfileRepository(session).create(
                    tenant_id=UUID(tenant_id),
                    seller_profile_id=seller_profile.id,
                    created_by_user_id=user.id,
                    name="Fintech ICP",
                    criteria_json={"industry": ["fintech"]},
                    status="active",
                )
                await session.commit()

            stream_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-workflow-001"},
                json={
                    "user_message": "Find companies matching my ICP.",
                    "seller_profile_id": str(seller_profile.id),
                    "icp_profile_id": str(icp_profile.id),
                },
            )
            assert stream_response.status_code == 200

            frames = _extract_data_frames(stream_response.text)
            assert len(frames) >= 3
            assert frames[0]["thread_id"]
            assert "accepted your account search request" in frames[0]["text"].lower()
            thread_id = frames[0]["thread_id"]
            meta_frames = [frame["meta"] for frame in frames[1:-1]]
            assert meta_frames
            assert all(meta_frame["workflow_run_id"] is not None for meta_frame in meta_frames)
            assert {meta_frame["type"] for meta_frame in meta_frames}.issubset(
                {
                    "queued",
                    "running",
                    "awaiting_review",
                    "completed",
                    "failed",
                    "agent_handoff",
                    "agent_completed",
                    "tool_started",
                    "tool_completed",
                    "reasoning_validated",
                    "reasoning_failed_validation",
                    "provider_routing_decision",
                }
            )
            assert frames[-1] == "[DONE]"

            initial_messages = await client.get(
                f"/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages"
            )
            assert initial_messages.status_code == 200
            initial_body = initial_messages.json()
            assert [message["message_type"] for message in initial_body["messages"][:3]] == [
                "user_turn",
                "assistant_reply",
                "workflow_status",
            ]

            final_messages = await _wait_for(
                lambda: _load_terminal_thread_messages(
                    client=client,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                )
            )
            assert final_messages[-1]["message_type"] == "assistant_reply"
            final_summary = final_messages[-1]["content_text"].lower()
            assert (
                "finished the account search workflow" in final_summary
                or "looks like one of our sources is down" in final_summary
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_stream_returns_before_background_workflow_completion(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    release_execution = asyncio.Event()
    execution_started = asyncio.Event()

    async def delayed_account_search_handler(request: WorkflowExecutionRequest) -> None:
        execution_started.set()
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await run_service.mark_running(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                status_detail="Background workflow started.",
            )
        await release_execution.wait()
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await run_service.mark_succeeded(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                result_summary="Background account search completed.",
                normalized_result_json={"outcome": "no_results"},
                canonical_output_ids={"account_ids": []},
            )

    executor = InProcessWorkflowExecutor()
    executor.register_handler(WorkflowType.ACCOUNT_SEARCH, delayed_account_search_handler)
    app.state.workflow_executor = executor

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Delayed Workflow Tenant", "slug": "delayed-workflow-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            settings = get_settings()
            async with session_factory() as session:
                users = UserRepository(session)
                user = await users.get_by_external_auth_subject(
                    external_auth_subject=settings.fake_auth_subject,
                )
                if user is None:
                    user = await users.create(
                        external_auth_subject=settings.fake_auth_subject,
                        email=settings.fake_auth_email,
                        display_name=settings.fake_auth_display_name,
                    )
                seller_profile = await SellerProfileRepository(session).create(
                    tenant_id=UUID(tenant_id),
                    created_by_user_id=user.id,
                    name="Primary Seller",
                    company_name="Acme",
                    company_domain="acme.test",
                    product_summary="Outbound platform",
                    value_proposition="Helps teams find accounts",
                )
                icp_profile = await ICPProfileRepository(session).create(
                    tenant_id=UUID(tenant_id),
                    seller_profile_id=seller_profile.id,
                    created_by_user_id=user.id,
                    name="Fintech ICP",
                    criteria_json={"industry": ["fintech"]},
                    status="active",
                )
                await session.commit()

            stream_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-delayed-workflow-001"},
                json={
                    "user_message": "Find companies matching my ICP.",
                    "seller_profile_id": str(seller_profile.id),
                    "icp_profile_id": str(icp_profile.id),
                },
            )
            assert stream_response.status_code == 200

            first_frame = _extract_first_frame_text(stream_response.text)
            thread_id = first_frame["thread_id"]
            assert "accepted your account search request" in first_frame["text"].lower()

            await asyncio.wait_for(execution_started.wait(), timeout=1.0)

            messages_response = await client.get(
                f"/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages"
            )
            assert messages_response.status_code == 200
            messages = messages_response.json()["messages"]
            assert [message["message_type"] for message in messages[:3]] == [
                "user_turn",
                "assistant_reply",
                "workflow_status",
            ]
            assert sum(message["message_type"] == "assistant_reply" for message in messages) == 1

            release_execution.set()
            await executor.wait_for_all()

            final_messages = await _wait_for(
                lambda: _load_terminal_thread_messages(
                    client=client,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                )
            )
            assert sum(message["message_type"] == "assistant_reply" for message in final_messages) == 2
            assert "background account search completed" in final_messages[-1]["content_text"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_thread_surfaces_degraded_account_search_summary_from_terminal_result(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    release_execution = asyncio.Event()
    execution_started = asyncio.Event()

    async def degraded_account_search_handler(request: WorkflowExecutionRequest) -> None:
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await run_service.mark_running(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                status_detail="Background workflow started.",
            )
            await run_service.emit_assistant_progress_update(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                content_text="Hmm, looks like one of our sources is down. I'm trying a backup source now.",
            )
        execution_started.set()
        await release_execution.wait()
        async with session_factory() as session:
            run_service = WorkflowRunService(session)
            await run_service.mark_succeeded(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                result_summary="No credible account candidates matched the current seller and ICP context.",
                normalized_result_json={
                    "outcome": "provider_failure_with_fallback_exhausted",
                    "assistant_summary": (
                        "Hmm, looks like one of our sources is down. I tried a backup source too, "
                        "but I couldn't confirm any reliable matches from the available data."
                    ),
                    "summary_selection_reason": "Selected degraded-failure summary for fallback exhaustion.",
                },
                canonical_output_ids={"account_ids": []},
            )

    executor = InProcessWorkflowExecutor()
    executor.register_handler(WorkflowType.ACCOUNT_SEARCH, degraded_account_search_handler)
    app.state.workflow_executor = executor

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Degraded Workflow Tenant", "slug": "degraded-workflow-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            settings = get_settings()
            async with session_factory() as session:
                users = UserRepository(session)
                user = await users.get_by_external_auth_subject(
                    external_auth_subject=settings.fake_auth_subject,
                )
                if user is None:
                    user = await users.create(
                        external_auth_subject=settings.fake_auth_subject,
                        email=settings.fake_auth_email,
                        display_name=settings.fake_auth_display_name,
                    )
                seller_profile = await SellerProfileRepository(session).create(
                    tenant_id=UUID(tenant_id),
                    created_by_user_id=user.id,
                    name="Primary Seller",
                    company_name="Acme",
                    company_domain="acme.test",
                    product_summary="Outbound platform",
                    value_proposition="Helps teams find accounts",
                )
                icp_profile = await ICPProfileRepository(session).create(
                    tenant_id=UUID(tenant_id),
                    seller_profile_id=seller_profile.id,
                    created_by_user_id=user.id,
                    name="Fintech ICP",
                    criteria_json={"industry": ["fintech"]},
                    status="active",
                )
                await session.commit()

            stream_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/chat/stream",
                headers={"X-Request-ID": "req-chat-degraded-workflow-001"},
                json={
                    "user_message": "Find companies matching my ICP.",
                    "seller_profile_id": str(seller_profile.id),
                    "icp_profile_id": str(icp_profile.id),
                },
            )
            assert stream_response.status_code == 200

            first_frame = _extract_first_frame_text(stream_response.text)
            thread_id = first_frame["thread_id"]
            await asyncio.wait_for(execution_started.wait(), timeout=1.0)

            interim_messages = await client.get(
                f"/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages"
            )
            assert interim_messages.status_code == 200
            assert any(
                "trying a backup source now" in message["content_text"].lower()
                for message in interim_messages.json()["messages"]
                if message["message_type"] == "assistant_reply"
            )

            release_execution.set()
            await executor.wait_for_all()

            final_messages = await _wait_for(
                lambda: _load_terminal_thread_messages(
                    client=client,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                )
            )
            assert "i tried a backup source too" in final_messages[-1]["content_text"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_events_route_projects_queued_state_without_durable_run_started_event(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Event Tenant", "slug": "event-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            settings = get_settings()
            async with session_factory() as session:
                users = UserRepository(session)
                user = await users.get_by_external_auth_subject(
                    external_auth_subject=settings.fake_auth_subject,
                )
                if user is None:
                    user = await users.create(
                        external_auth_subject=settings.fake_auth_subject,
                        email=settings.fake_auth_email,
                        display_name=settings.fake_auth_display_name,
                    )
                run_service = WorkflowRunService(session)
                run = await run_service.create_queued_run(
                    tenant_id=UUID(tenant_id),
                    created_by_user_id=user.id,
                    workflow_type="account_search",
                    requested_payload_json={"objective": "Find fintech accounts"},
                )
                await session.commit()

            response = await client.get(f"/api/v1/tenants/{tenant_id}/chat/events")
            assert response.status_code == 200
            body = response.json()
            assert body["events"]
            assert body["events"][0]["workflow_run_id"] == str(run.id)
            assert body["events"][0]["type"] == "queued"
            assert body["events"][0]["workflow_status"] == "queued"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_chat_events_route_projects_agent_and_tool_events(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    _configure_test_workflow_executor(app=app, session_factory=session_factory)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Projected Event Tenant", "slug": "projected-event-tenant"},
            )
            assert tenant_response.status_code == 201
            tenant_id = tenant_response.json()["tenant_id"]

            settings = get_settings()
            async with session_factory() as session:
                users = UserRepository(session)
                user = await users.get_by_external_auth_subject(
                    external_auth_subject=settings.fake_auth_subject,
                )
                if user is None:
                    user = await users.create(
                        external_auth_subject=settings.fake_auth_subject,
                        email=settings.fake_auth_email,
                        display_name=settings.fake_auth_display_name,
                    )
                run_service = WorkflowRunService(session)
                run = await run_service.create_queued_run(
                    tenant_id=UUID(tenant_id),
                    created_by_user_id=user.id,
                    workflow_type="account_research",
                    requested_payload_json={"account_id": "acct_123"},
                )
                await run_service.mark_running(
                    tenant_id=UUID(tenant_id),
                    run_id=run.id,
                    status_detail="Started.",
                )
                await run_service.emit_agent_handoff(
                    tenant_id=UUID(tenant_id),
                    run_id=run.id,
                    from_agent="planner",
                    to_agent="researcher",
                    reason="Need deep research.",
                )
                await run_service.emit_tool_started(
                    tenant_id=UUID(tenant_id),
                    run_id=run.id,
                    tool_name="web_search",
                    input_summary="Search for company updates.",
                    provider_name="firecrawl",
                )
                await run_service.emit_tool_completed(
                    tenant_id=UUID(tenant_id),
                    run_id=run.id,
                    tool_name="web_search",
                    output_summary="Collected result set.",
                    provider_name="firecrawl",
                )
                await run_service.mark_succeeded(
                    tenant_id=UUID(tenant_id),
                    run_id=run.id,
                    result_summary="Research complete.",
                )
                await session.commit()

            response = await client.get(f"/api/v1/tenants/{tenant_id}/chat/events")
            assert response.status_code == 200
            event_types = [event["type"] for event in response.json()["events"]]
            assert "completed" in event_types
            assert "tool_completed" in event_types
            assert "tool_started" in event_types
            assert "agent_handoff" in event_types
            assert "running" in event_types
    finally:
        app.dependency_overrides.clear()
