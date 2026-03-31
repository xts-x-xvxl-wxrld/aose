from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.types import AuthIdentity
from app.db.base import Base
from app.models import load_model_modules
from app.repositories.approval_decision_repository import ApprovalDecisionRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.review import ReviewService
from app.services.workflow_runs import WorkflowRunService
from tests.db.helpers import get_postgres_test_urls

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
async def test_review_service_reads_tenant_scoped_evidence_and_artifacts(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    evidence_repository = SourceEvidenceRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)
    run_service = WorkflowRunService(db_session)

    member = await user_repository.create(external_auth_subject="subject-review-member")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=member.id, role="member")
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=member.id,
        workflow_type="account_research",
        requested_payload_json={"objective": "Review evidence"},
    )
    evidence = await evidence_repository.create(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
        source_type="web",
        provider_name="example-search",
        source_url="https://example.com",
        title="Example Result",
    )
    artifact = await artifact_repository.create(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
        created_by_user_id=member.id,
        artifact_type="review_packet",
        format="json",
        title="Review Packet",
        content_json={"status": "queued"},
    )
    await db_session.commit()

    service = ReviewService(db_session, run_service=run_service)
    identity = AuthIdentity(
        external_auth_subject=member.external_auth_subject,
        email=member.email,
        display_name=member.display_name,
    )

    evidence_rows = await service.list_evidence_for_run(
        identity=identity,
        tenant_id=tenant.id,
        run_id=run.id,
    )
    artifact_row = await service.get_artifact(
        identity=identity,
        tenant_id=tenant.id,
        artifact_id=artifact.id,
    )

    assert [row.id for row in evidence_rows] == [evidence.id]
    assert artifact_row.id == artifact.id


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_review_service_approved_decision_creates_history_and_completes_run(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)
    approval_repository = ApprovalDecisionRepository(db_session)
    run_service = WorkflowRunService(db_session)

    reviewer = await user_repository.create(external_auth_subject="subject-review-approver")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
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
    artifact = await artifact_repository.create(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
        created_by_user_id=reviewer.id,
        artifact_type="review_packet",
        format="json",
        title="Review Packet",
        content_json={"status": "awaiting_review"},
    )
    awaiting_run = await run_service.mark_awaiting_review(
        tenant_id=tenant.id,
        run_id=run.id,
        review_reason="Needs reviewer confirmation.",
        artifact_id=artifact.id,
        normalized_result_json={"outcome": "pending_review"},
    )

    service = ReviewService(db_session, run_service=run_service)
    approval, updated_run = await service.submit_approval(
        identity=AuthIdentity(
            external_auth_subject=reviewer.external_auth_subject,
            email=reviewer.email,
            display_name=reviewer.display_name,
        ),
        tenant_id=tenant.id,
        run_id=awaiting_run.id,
        decision="approved",
        artifact_id=artifact.id,
    )
    approvals = await approval_repository.list_for_run(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
    )
    events = await run_service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)

    assert approval.decision == "approved"
    assert updated_run.status == "succeeded"
    assert updated_run.normalized_result_json == {"outcome": "pending_review"}
    assert [row.id for row in approvals] == [approval.id]
    assert [event.event_name for event in events] == [
        "run.started",
        "run.awaiting_review",
        "run.completed",
    ]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_error_code"),
    [
        ("rejected", "review_rejected"),
        ("needs_changes", "review_needs_changes"),
    ],
)
async def test_review_service_negative_decisions_fail_the_run(
    db_session: AsyncSession,
    decision: str,
    expected_error_code: str,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)
    run_service = WorkflowRunService(db_session)

    reviewer = await user_repository.create(
        external_auth_subject=f"subject-{decision}-approver"
    )
    tenant = await tenant_repository.create(name=f"Tenant {decision}", slug=f"tenant-{decision}")
    await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=reviewer.id,
        workflow_type="contact_search",
        requested_payload_json={"objective": "Review contacts"},
    )
    await run_service.mark_running(
        tenant_id=tenant.id,
        run_id=run.id,
        status_detail="Worker started.",
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
    await run_service.mark_awaiting_review(
        tenant_id=tenant.id,
        run_id=run.id,
        review_reason="Needs reviewer confirmation.",
        artifact_id=artifact.id,
        normalized_result_json={"outcome": "pending_review"},
    )

    service = ReviewService(db_session, run_service=run_service)
    _approval, updated_run = await service.submit_approval(
        identity=AuthIdentity(
            external_auth_subject=reviewer.external_auth_subject,
            email=reviewer.email,
            display_name=reviewer.display_name,
        ),
        tenant_id=tenant.id,
        run_id=run.id,
        decision=decision,
        rationale=f"{decision} rationale",
        artifact_id=artifact.id,
    )

    assert updated_run.status == "failed"
    assert updated_run.error_code == expected_error_code


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_review_service_rejects_non_reviewable_state_and_artifact_mismatches(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)
    run_service = WorkflowRunService(db_session)

    reviewer = await user_repository.create(external_auth_subject="subject-review-conflict")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=reviewer.id,
        workflow_type="account_search",
        requested_payload_json={"objective": "Review accounts"},
    )
    other_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=reviewer.id,
        workflow_type="account_search",
        requested_payload_json={"objective": "Other review"},
    )
    mismatched_artifact = await artifact_repository.create(
        tenant_id=tenant.id,
        workflow_run_id=other_run.id,
        created_by_user_id=reviewer.id,
        artifact_type="review_packet",
        format="json",
        title="Other Packet",
        content_json={"status": "awaiting_review"},
    )
    await db_session.commit()

    service = ReviewService(db_session, run_service=run_service)
    identity = AuthIdentity(
        external_auth_subject=reviewer.external_auth_subject,
        email=reviewer.email,
        display_name=reviewer.display_name,
    )

    with pytest.raises(ServiceError) as not_awaiting_review:
        await service.submit_approval(
            identity=identity,
            tenant_id=tenant.id,
            run_id=run.id,
            decision="approved",
        )
    assert not_awaiting_review.value.status_code == 409
    assert not_awaiting_review.value.error_code == "review_state_conflict"

    await run_service.mark_running(
        tenant_id=tenant.id,
        run_id=run.id,
        status_detail="Worker started.",
    )
    await run_service.mark_awaiting_review(
        tenant_id=tenant.id,
        run_id=run.id,
        review_reason="Needs reviewer confirmation.",
    )

    with pytest.raises(ServiceError) as artifact_mismatch:
        await service.submit_approval(
            identity=identity,
            tenant_id=tenant.id,
            run_id=run.id,
            decision="approved",
            artifact_id=mismatched_artifact.id,
        )
    assert artifact_mismatch.value.status_code == 409
    assert artifact_mismatch.value.error_code == "review_state_conflict"
