from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import load_model_modules
from app.repositories.account_repository import AccountRepository
from app.repositories.account_research_snapshot_repository import AccountResearchSnapshotRepository
from app.repositories.approval_decision_repository import ApprovalDecisionRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_message_repository import ConversationMessageRepository
from app.repositories.conversation_thread_repository import ConversationThreadRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
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
async def test_identity_repositories_lookup_expected_records(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)

    user = await user_repository.create(
        external_auth_subject="subject-123",
        email="owner@example.com",
        display_name="Owner User",
    )
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    membership = await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="owner")
    await db_session.commit()

    found_user = await user_repository.get_by_external_auth_subject(external_auth_subject="subject-123")
    found_tenant = await tenant_repository.get_by_slug(slug="tenant-one")
    found_membership = await membership_repository.get_by_tenant_and_user(
        tenant_id=tenant.id,
        user_id=user.id,
    )

    assert found_user is not None and found_user.id == user.id
    assert found_tenant is not None and found_tenant.id == tenant.id
    assert found_membership is not None and found_membership.id == membership.id


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_seller_and_icp_repositories_enforce_tenant_scoped_access(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)

    user = await user_repository.create(external_auth_subject="subject-abc")
    tenant_one = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    tenant_two = await tenant_repository.create(name="Tenant Two", slug="tenant-two")
    seller = await seller_repository.create(
        tenant_id=tenant_one.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summarizes the product",
        value_proposition="Explains the value",
        profile_json={"segments": ["mid-market"]},
    )
    icp = await icp_repository.create(
        tenant_id=tenant_one.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Primary ICP",
        criteria_json={"industries": ["software"]},
    )
    await db_session.commit()

    visible_seller = await seller_repository.get_for_tenant(
        tenant_id=tenant_one.id,
        seller_profile_id=seller.id,
    )
    hidden_seller = await seller_repository.get_for_tenant(
        tenant_id=tenant_two.id,
        seller_profile_id=seller.id,
    )
    visible_icp = await icp_repository.get_for_tenant(
        tenant_id=tenant_one.id,
        icp_profile_id=icp.id,
    )
    hidden_icp = await icp_repository.get_for_tenant(
        tenant_id=tenant_two.id,
        icp_profile_id=icp.id,
    )

    assert visible_seller is not None and visible_seller.id == seller.id
    assert hidden_seller is None
    assert visible_icp is not None and visible_icp.id == icp.id
    assert hidden_icp is None


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_seller_and_icp_updates_track_updated_by_user(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)

    owner = await user_repository.create(external_auth_subject="subject-owner")
    editor = await user_repository.create(external_auth_subject="subject-editor")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")

    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=owner.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summarizes the product",
        value_proposition="Explains the value",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=owner.id,
        name="Primary ICP",
        criteria_json={"industries": ["software"]},
    )
    await db_session.commit()

    updated_seller = await seller_repository.update(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        updated_by_user_id=editor.id,
        changes={"company_domain": "acme.example", "source_status": "manual"},
    )
    updated_icp = await icp_repository.update(
        tenant_id=tenant.id,
        icp_profile_id=icp.id,
        updated_by_user_id=editor.id,
        changes={"status": "active", "exclusions_json": {"geography": ["antarctica"]}},
    )
    await db_session.commit()

    assert updated_seller is not None
    assert updated_seller.updated_by_user_id == editor.id
    assert updated_seller.company_domain == "acme.example"
    assert updated_icp is not None
    assert updated_icp.updated_by_user_id == editor.id
    assert updated_icp.status == "active"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_phase_1_workflow_repositories_enforce_tenant_scope_and_append_only_histories(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    thread_repository = ConversationThreadRepository(db_session)
    message_repository = ConversationMessageRepository(db_session)
    workflow_run_repository = WorkflowRunRepository(db_session)
    run_event_repository = RunEventRepository(db_session)
    account_repository = AccountRepository(db_session)
    snapshot_repository = AccountResearchSnapshotRepository(db_session)
    contact_repository = ContactRepository(db_session)
    evidence_repository = SourceEvidenceRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)
    approval_repository = ApprovalDecisionRepository(db_session)

    user = await user_repository.create(external_auth_subject="subject-persistence")
    reviewer = await user_repository.create(external_auth_subject="subject-reviewer")
    tenant_one = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    tenant_two = await tenant_repository.create(name="Tenant Two", slug="tenant-two")
    seller = await seller_repository.create(
        tenant_id=tenant_one.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summarizes the product",
        value_proposition="Explains the value",
    )
    thread = await thread_repository.create(
        tenant_id=tenant_one.id,
        created_by_user_id=user.id,
        seller_profile_id=seller.id,
        active_workflow="account_search",
    )
    workflow_run = await workflow_run_repository.create(
        tenant_id=tenant_one.id,
        thread_id=thread.id,
        created_by_user_id=user.id,
        workflow_type="account_search",
        status="queued",
        requested_payload_json={"objective": "Find target accounts"},
        correlation_id="corr-123",
    )
    await thread_repository.update(
        tenant_id=tenant_one.id,
        thread_id=thread.id,
        changes={"current_run_id": workflow_run.id, "summary_text": "Working thread"},
    )
    user_message = await message_repository.create(
        tenant_id=tenant_one.id,
        thread_id=thread.id,
        run_id=None,
        role="user",
        message_type="user_turn",
        content_text="Find target accounts",
        created_by_user_id=user.id,
    )
    workflow_message = await message_repository.create(
        tenant_id=tenant_one.id,
        thread_id=thread.id,
        run_id=workflow_run.id,
        role="system",
        message_type="workflow_status",
        content_text="Queued workflow",
    )
    first_event = await run_event_repository.create(
        tenant_id=tenant_one.id,
        run_id=workflow_run.id,
        event_name="run.started",
        payload_json={"workflow_type": "account_search"},
    )
    second_event = await run_event_repository.create(
        tenant_id=tenant_one.id,
        run_id=workflow_run.id,
        event_name="tool.completed",
        payload_json={"tool_name": "search"},
    )
    account = await account_repository.create(
        tenant_id=tenant_one.id,
        created_by_user_id=user.id,
        source_workflow_run_id=workflow_run.id,
        name="Account One",
        status="accepted",
        normalized_domain="acme.example",
        fit_signals_json={"signals": ["growth"]},
    )
    first_snapshot = await snapshot_repository.create(
        tenant_id=tenant_one.id,
        account_id=account.id,
        workflow_run_id=workflow_run.id,
        created_by_user_id=user.id,
        snapshot_version=1,
        research_json={"summary": "v1"},
    )
    second_snapshot = await snapshot_repository.create(
        tenant_id=tenant_one.id,
        account_id=account.id,
        workflow_run_id=workflow_run.id,
        created_by_user_id=user.id,
        snapshot_version=2,
        research_json={"summary": "v2"},
        uncertainty_notes="Still validating",
    )
    contact = await contact_repository.create(
        tenant_id=tenant_one.id,
        account_id=account.id,
        created_by_user_id=user.id,
        full_name="Taylor Contact",
        status="candidate",
        person_data_json={"sources": 2},
    )
    evidence = await evidence_repository.create(
        tenant_id=tenant_one.id,
        workflow_run_id=workflow_run.id,
        account_id=account.id,
        contact_id=contact.id,
        source_type="web",
        metadata_json={"source": "example"},
    )
    artifact = await artifact_repository.create(
        tenant_id=tenant_one.id,
        workflow_run_id=workflow_run.id,
        created_by_user_id=user.id,
        artifact_type="run_summary",
        format="json",
        title="Run Summary",
        content_json={"status": "queued"},
    )
    first_approval = await approval_repository.create(
        tenant_id=tenant_one.id,
        workflow_run_id=workflow_run.id,
        artifact_id=artifact.id,
        reviewed_by_user_id=reviewer.id,
        decision="approved",
    )
    second_approval = await approval_repository.create(
        tenant_id=tenant_one.id,
        workflow_run_id=workflow_run.id,
        artifact_id=artifact.id,
        reviewed_by_user_id=reviewer.id,
        decision="needs_changes",
        rationale="Need a stronger summary",
    )
    await db_session.commit()

    visible_thread = await thread_repository.get_for_tenant(tenant_id=tenant_one.id, thread_id=thread.id)
    hidden_thread = await thread_repository.get_for_tenant(tenant_id=tenant_two.id, thread_id=thread.id)
    visible_run = await workflow_run_repository.get_for_tenant(tenant_id=tenant_one.id, run_id=workflow_run.id)
    hidden_run = await workflow_run_repository.get_for_tenant(tenant_id=tenant_two.id, run_id=workflow_run.id)
    correlation_run = await workflow_run_repository.get_by_correlation_id(
        tenant_id=tenant_one.id,
        correlation_id="corr-123",
    )
    account_by_domain = await account_repository.get_by_normalized_domain(
        tenant_id=tenant_one.id,
        normalized_domain="acme.example",
    )
    hidden_account_by_domain = await account_repository.get_by_normalized_domain(
        tenant_id=tenant_two.id,
        normalized_domain="acme.example",
    )
    messages = await message_repository.list_for_thread(tenant_id=tenant_one.id, thread_id=thread.id)
    run_events = await run_event_repository.list_for_run(tenant_id=tenant_one.id, run_id=workflow_run.id)
    snapshots = await snapshot_repository.list_for_account(tenant_id=tenant_one.id, account_id=account.id)
    latest_snapshot = await snapshot_repository.get_latest_for_account(
        tenant_id=tenant_one.id,
        account_id=account.id,
    )
    contacts = await contact_repository.list_for_account(tenant_id=tenant_one.id, account_id=account.id)
    evidence_rows = await evidence_repository.list_for_run(
        tenant_id=tenant_one.id,
        workflow_run_id=workflow_run.id,
    )
    artifact_row = await artifact_repository.get_for_tenant(tenant_id=tenant_one.id, artifact_id=artifact.id)
    hidden_artifact_row = await artifact_repository.get_for_tenant(tenant_id=tenant_two.id, artifact_id=artifact.id)
    approvals_for_run = await approval_repository.list_for_run(
        tenant_id=tenant_one.id,
        workflow_run_id=workflow_run.id,
    )
    approvals_for_artifact = await approval_repository.list_for_artifact(
        tenant_id=tenant_one.id,
        artifact_id=artifact.id,
    )

    assert visible_thread is not None and visible_thread.current_run_id == workflow_run.id
    assert hidden_thread is None
    assert visible_run is not None and visible_run.id == workflow_run.id
    assert hidden_run is None
    assert correlation_run is not None and correlation_run.id == workflow_run.id
    assert account_by_domain is not None and account_by_domain.id == account.id
    assert hidden_account_by_domain is None
    expected_messages = sorted([user_message, workflow_message], key=lambda row: (row.created_at, row.id))
    expected_events = sorted([first_event, second_event], key=lambda row: (row.created_at, row.id))
    expected_snapshots = sorted([first_snapshot, second_snapshot], key=lambda row: (row.created_at, row.id))
    expected_approvals = sorted([first_approval, second_approval], key=lambda row: (row.created_at, row.id))

    assert [message.id for message in messages] == [message.id for message in expected_messages]
    assert [event.id for event in run_events] == [event.id for event in expected_events]
    assert [snapshot.id for snapshot in snapshots] == [snapshot.id for snapshot in expected_snapshots]
    assert latest_snapshot is not None and latest_snapshot.id == second_snapshot.id
    assert [contact_row.id for contact_row in contacts] == [contact.id]
    assert [evidence_row.id for evidence_row in evidence_rows] == [evidence.id]
    assert artifact_row is not None and artifact_row.id == artifact.id
    assert hidden_artifact_row is None
    assert [approval.id for approval in approvals_for_run] == [approval.id for approval in expected_approvals]
    assert [approval.id for approval in approvals_for_artifact] == [approval.id for approval in expected_approvals]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_phase_1_mutable_repositories_track_updates(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    thread_repository = ConversationThreadRepository(db_session)
    workflow_run_repository = WorkflowRunRepository(db_session)
    account_repository = AccountRepository(db_session)
    contact_repository = ContactRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)

    owner = await user_repository.create(external_auth_subject="subject-owner-persistence")
    editor = await user_repository.create(external_auth_subject="subject-editor-persistence")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=owner.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summarizes the product",
        value_proposition="Explains the value",
    )
    thread = await thread_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=owner.id,
        seller_profile_id=seller.id,
    )
    workflow_run = await workflow_run_repository.create(
        tenant_id=tenant.id,
        thread_id=thread.id,
        created_by_user_id=owner.id,
        workflow_type="account_search",
        status="queued",
        requested_payload_json={"objective": "Find target accounts"},
    )
    account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=owner.id,
        source_workflow_run_id=workflow_run.id,
        name="Account One",
        status="accepted",
    )
    contact = await contact_repository.create(
        tenant_id=tenant.id,
        account_id=account.id,
        created_by_user_id=owner.id,
        full_name="Taylor Contact",
        status="candidate",
    )
    artifact = await artifact_repository.create(
        tenant_id=tenant.id,
        workflow_run_id=workflow_run.id,
        created_by_user_id=owner.id,
        artifact_type="run_summary",
        format="json",
        title="Initial Summary",
        content_json={"status": "queued"},
    )
    await db_session.commit()

    updated_thread = await thread_repository.update(
        tenant_id=tenant.id,
        thread_id=thread.id,
        changes={"summary_text": "Updated thread summary", "active_workflow": "account_search"},
    )
    updated_run = await workflow_run_repository.update(
        tenant_id=tenant.id,
        run_id=workflow_run.id,
        changes={"status": "running", "status_detail": "Executing"},
    )
    updated_account = await account_repository.update(
        tenant_id=tenant.id,
        account_id=account.id,
        updated_by_user_id=editor.id,
        changes={"industry": "software"},
    )
    updated_contact = await contact_repository.update(
        tenant_id=tenant.id,
        contact_id=contact.id,
        updated_by_user_id=editor.id,
        changes={"email": "taylor@example.com"},
    )
    updated_artifact = await artifact_repository.update(
        tenant_id=tenant.id,
        artifact_id=artifact.id,
        changes={"title": "Updated Summary", "content_json": {"status": "running"}},
    )
    await db_session.commit()

    assert updated_thread is not None
    assert updated_thread.summary_text == "Updated thread summary"
    assert updated_thread.active_workflow == "account_search"
    assert updated_run is not None
    assert updated_run.status == "running"
    assert updated_run.status_detail == "Executing"
    assert updated_account is not None
    assert updated_account.updated_by_user_id == editor.id
    assert updated_account.industry == "software"
    assert updated_contact is not None
    assert updated_contact.updated_by_user_id == editor.id
    assert updated_contact.email == "taylor@example.com"
    assert updated_artifact is not None
    assert updated_artifact.title == "Updated Summary"
    assert updated_artifact.content_json == {"status": "running"}
