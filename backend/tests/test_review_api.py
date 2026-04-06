from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session, get_optional_db_session
from app.main import create_app
from app.models import load_model_modules
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
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


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_review_routes_expose_evidence_artifact_and_approval_flow(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    async with session_factory() as session:
        user_repository = UserRepository(session)
        tenant_repository = TenantRepository(session)
        membership_repository = MembershipRepository(session)
        evidence_repository = SourceEvidenceRepository(session)
        artifact_repository = ArtifactRepository(session)
        run_service = WorkflowRunService(session)

        reviewer = await user_repository.create(external_auth_subject="reviewer-subject")
        member = await user_repository.create(external_auth_subject="member-subject")
        tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
        await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
        await membership_repository.create(tenant_id=tenant.id, user_id=member.id, role="member")
        run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=reviewer.id,
            workflow_type="account_research",
            requested_payload_json={"objective": "Review evidence"},
        )
        await run_service.mark_running(
            tenant_id=tenant.id,
            run_id=run.id,
            status_detail="Worker started.",
        )
        await run_service.emit_tool_started(
            tenant_id=tenant.id,
            run_id=run.id,
            tool_name="web_search",
            provider_name="firecrawl",
            input_summary="Searching for accounts.",
            correlation_key="debug-web-search-1",
        )
        await run_service.emit_tool_completed(
            tenant_id=tenant.id,
            run_id=run.id,
            tool_name="web_search",
            provider_name="firecrawl",
            output_summary="Provider was unavailable.",
            error_code="provider_unavailable",
            produced_evidence_results=False,
        )
        await run_service.emit_provider_routing_decision(
            tenant_id=tenant.id,
            run_id=run.id,
            capability="account_search_web_search",
            from_provider="firecrawl",
            selected_provider="google_local_places",
            routing_basis="phase3_account_search_resilience_fallback",
            trigger_reason="provider_unavailable",
            allowed=True,
            reason_summary="Primary provider triggered fallback.",
        )
        artifact = await artifact_repository.create(
            tenant_id=tenant.id,
            workflow_run_id=run.id,
            created_by_user_id=reviewer.id,
            artifact_type="review_packet",
            format="json",
            title="Review Packet",
            content_json={"status": "awaiting_review"},
        )
        await evidence_repository.create(
            tenant_id=tenant.id,
            workflow_run_id=run.id,
            source_type="web",
            provider_name="example-search",
            source_url="https://example.com",
            title="Example Result",
        )
        await run_service.mark_awaiting_review(
            tenant_id=tenant.id,
            run_id=run.id,
            review_reason="Needs reviewer confirmation.",
            artifact_id=artifact.id,
            normalized_result_json={"outcome": "pending_review"},
        )
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            evidence_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{run.id}/evidence",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert evidence_response.status_code == 200
            evidence_body = evidence_response.json()
            assert len(evidence_body["evidence"]) == 1
            assert evidence_body["evidence"][0]["workflow_run_id"] == str(run.id)
            assert evidence_body["next_cursor"] is None

            debug_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{run.id}/debug",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert debug_response.status_code == 200
            debug_body = debug_response.json()
            assert debug_body["workflow_run_id"] == str(run.id)
            assert debug_body["provider_attempts"][0]["provider_name"] == "firecrawl"
            assert debug_body["provider_attempts"][0]["error_code"] == "provider_unavailable"
            assert debug_body["fallback_decisions"][0]["to_provider"] == "google_local_places"

            artifact_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/artifacts/{artifact.id}",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert artifact_response.status_code == 200
            assert artifact_response.json()["artifact_id"] == str(artifact.id)

            approval_response = await client.post(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{run.id}/approvals",
                json={"decision": "approved", "artifact_id": str(artifact.id)},
                headers={"Authorization": "Bearer reviewer-subject"},
            )
            assert approval_response.status_code == 201
            approval_body = approval_response.json()
            assert approval_body["workflow_run_id"] == str(run.id)
            assert approval_body["artifact_id"] == str(artifact.id)
            assert approval_body["decision"] == "approved"
            assert approval_body["run_status_after_decision"] == "succeeded"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_review_routes_reject_invalid_review_requests(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    async with session_factory() as session:
        user_repository = UserRepository(session)
        tenant_repository = TenantRepository(session)
        membership_repository = MembershipRepository(session)
        artifact_repository = ArtifactRepository(session)
        run_service = WorkflowRunService(session)

        reviewer = await user_repository.create(external_auth_subject="reviewer-subject")
        member = await user_repository.create(external_auth_subject="member-subject")
        tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
        await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
        await membership_repository.create(tenant_id=tenant.id, user_id=member.id, role="member")
        awaiting_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=reviewer.id,
            workflow_type="contact_search",
            requested_payload_json={"objective": "Review contacts"},
        )
        await run_service.mark_running(
            tenant_id=tenant.id,
            run_id=awaiting_run.id,
            status_detail="Worker started.",
        )
        await run_service.mark_awaiting_review(
            tenant_id=tenant.id,
            run_id=awaiting_run.id,
            review_reason="Needs reviewer confirmation.",
        )
        ready_artifact = await artifact_repository.create(
            tenant_id=tenant.id,
            workflow_run_id=awaiting_run.id,
            created_by_user_id=reviewer.id,
            artifact_type="review_packet",
            format="json",
            title="Ready Packet",
            content_json={"status": "awaiting_review"},
        )
        non_review_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=reviewer.id,
            workflow_type="contact_search",
            requested_payload_json={"objective": "Still queued"},
        )
        other_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=reviewer.id,
            workflow_type="contact_search",
            requested_payload_json={"objective": "Other review"},
        )
        mismatched_artifact = await artifact_repository.create(
            tenant_id=tenant.id,
            workflow_run_id=other_run.id,
            created_by_user_id=reviewer.id,
            artifact_type="review_packet",
            format="json",
            title="Wrong Packet",
            content_json={"status": "awaiting_review"},
        )
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            missing_rationale = await client.post(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{awaiting_run.id}/approvals",
                json={"decision": "rejected", "artifact_id": str(ready_artifact.id)},
                headers={"Authorization": "Bearer reviewer-subject"},
            )
            assert missing_rationale.status_code == 422

            member_forbidden = await client.post(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{awaiting_run.id}/approvals",
                json={"decision": "approved", "artifact_id": str(ready_artifact.id)},
                headers={"Authorization": "Bearer member-subject"},
            )
            assert member_forbidden.status_code == 403
            assert member_forbidden.json()["error_code"] == "tenant_membership_required"

            not_awaiting_review = await client.post(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{non_review_run.id}/approvals",
                json={"decision": "approved"},
                headers={"Authorization": "Bearer reviewer-subject"},
            )
            assert not_awaiting_review.status_code == 409
            assert not_awaiting_review.json()["error_code"] == "review_state_conflict"

            mismatched_artifact_response = await client.post(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{awaiting_run.id}/approvals",
                json={"decision": "approved", "artifact_id": str(mismatched_artifact.id)},
                headers={"Authorization": "Bearer reviewer-subject"},
            )
            assert mismatched_artifact_response.status_code == 409
            assert mismatched_artifact_response.json()["error_code"] == "review_state_conflict"
    finally:
        app.dependency_overrides.clear()
