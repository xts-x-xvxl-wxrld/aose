from __future__ import annotations

import os
from collections.abc import AsyncIterator

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

from app.db.base import Base
from app.db.session import get_db_session, get_optional_db_session
from app.main import create_app
from app.models import load_model_modules
from app.repositories.account_repository import AccountRepository
from app.repositories.approval_decision_repository import ApprovalDecisionRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
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
async def test_workspace_routes_expose_user_visible_read_surfaces(
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
        users = UserRepository(session)
        tenants = TenantRepository(session)
        memberships = MembershipRepository(session)
        seller_profiles = SellerProfileRepository(session)
        icp_profiles = ICPProfileRepository(session)
        accounts = AccountRepository(session)
        contacts = ContactRepository(session)
        artifacts = ArtifactRepository(session)
        evidence = SourceEvidenceRepository(session)
        approvals = ApprovalDecisionRepository(session)
        run_service = WorkflowRunService(session)

        owner = await users.create(external_auth_subject="owner-subject")
        member = await users.create(external_auth_subject="member-subject")
        tenant = await tenants.create(name="Tenant One", slug="tenant-one")
        await memberships.create(tenant_id=tenant.id, user_id=owner.id, role="owner")
        await memberships.create(tenant_id=tenant.id, user_id=member.id, role="member")

        primary_seller = await seller_profiles.create(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            name="Primary Seller",
            company_name="Acme",
            product_summary="Automates seller research",
            value_proposition="Faster account discovery",
            company_domain="acme.example",
        )
        primary_icp = await icp_profiles.create(
            tenant_id=tenant.id,
            seller_profile_id=primary_seller.id,
            created_by_user_id=owner.id,
            name="Fintech ICP",
            status="active",
            criteria_json={"industries": ["fintech"]},
        )
        secondary_seller = await seller_profiles.create(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            name="Secondary Seller",
            company_name="Acme Two",
            product_summary="Automates research",
            value_proposition="Different ICP",
        )
        secondary_icp = await icp_profiles.create(
            tenant_id=tenant.id,
            seller_profile_id=secondary_seller.id,
            created_by_user_id=owner.id,
            name="Healthcare ICP",
            status="active",
            criteria_json={"industries": ["healthcare"]},
        )

        account_search_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            workflow_type="account_search",
            requested_payload_json={
                "seller_profile_id": str(primary_seller.id),
                "icp_profile_id": str(primary_icp.id),
                "search_objective": "Find fintech accounts",
            },
        )
        await run_service.mark_running(
            tenant_id=tenant.id,
            run_id=account_search_run.id,
            status_detail="Searching for fintech accounts.",
        )
        matched_account = await accounts.create(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            source_workflow_run_id=account_search_run.id,
            name="Ramp",
            domain="ramp.com",
            normalized_domain="ramp.com",
            linkedin_url="https://linkedin.com/company/ramp",
            hq_location="New York, NY",
            employee_range="500-1000",
            industry="Fintech",
            status="accepted",
            fit_summary="Strong fintech fit.",
        )
        await evidence.create(
            tenant_id=tenant.id,
            workflow_run_id=account_search_run.id,
            account_id=matched_account.id,
            source_type="web",
            provider_name="firecrawl",
            source_url="https://ramp.com",
            title="Ramp",
        )
        await run_service.mark_succeeded(
            tenant_id=tenant.id,
            run_id=account_search_run.id,
            result_summary="Accepted one account candidate.",
            normalized_result_json={
                "outcome": "accounts_found",
                "accepted_account_ids": [str(matched_account.id)],
                "assistant_summary": "Accepted one account candidate.",
            },
        )

        unrelated_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            workflow_type="account_search",
            requested_payload_json={
                "seller_profile_id": str(secondary_seller.id),
                "icp_profile_id": str(secondary_icp.id),
                "search_objective": "Find healthcare accounts",
            },
        )
        await run_service.mark_running(
            tenant_id=tenant.id,
            run_id=unrelated_run.id,
            status_detail="Searching for healthcare accounts.",
        )
        await accounts.create(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            source_workflow_run_id=unrelated_run.id,
            name="Health Co",
            status="accepted",
        )
        await run_service.mark_succeeded(
            tenant_id=tenant.id,
            run_id=unrelated_run.id,
            result_summary="Accepted one healthcare account candidate.",
            normalized_result_json={"outcome": "accounts_found", "accepted_account_ids": []},
        )

        contact_search_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            workflow_type="contact_search",
            requested_payload_json={
                "seller_profile_id": str(primary_seller.id),
                "icp_profile_id": str(primary_icp.id),
                "account_id": str(matched_account.id),
                "contact_objective": "Find finance contacts",
            },
        )
        await run_service.mark_running(
            tenant_id=tenant.id,
            run_id=contact_search_run.id,
            status_detail="Searching for contacts.",
        )
        matched_contact = await contacts.create(
            tenant_id=tenant.id,
            account_id=matched_account.id,
            created_by_user_id=owner.id,
            full_name="Jamie Doe",
            job_title="VP Finance",
            email="jamie@ramp.com",
            linkedin_url="https://linkedin.com/in/jamie-doe",
            status="ranked",
            ranking_summary="Strong finance persona fit.",
        )
        review_artifact = await artifacts.create(
            tenant_id=tenant.id,
            workflow_run_id=contact_search_run.id,
            created_by_user_id=owner.id,
            artifact_type="review_packet",
            format="json",
            title="Contact Review Packet",
            content_json={"status": "awaiting_review"},
        )
        await evidence.create(
            tenant_id=tenant.id,
            workflow_run_id=contact_search_run.id,
            contact_id=matched_contact.id,
            source_type="web",
            provider_name="findymail",
            source_url="https://ramp.com/team/jamie",
            title="Jamie Doe",
        )
        await run_service.mark_awaiting_review(
            tenant_id=tenant.id,
            run_id=contact_search_run.id,
            review_reason="Need reviewer approval before using this contact.",
            artifact_id=review_artifact.id,
            normalized_result_json={
                "outcome": "pending_review",
                "contact_ids": [str(matched_contact.id)],
                "assistant_summary": "Need review before using this contact.",
            },
        )

        research_run = await run_service.create_queued_run(
            tenant_id=tenant.id,
            created_by_user_id=owner.id,
            workflow_type="account_research",
            requested_payload_json={
                "seller_profile_id": str(primary_seller.id),
                "icp_profile_id": str(primary_icp.id),
                "account_id": str(matched_account.id),
                "research_objective": "Research Ramp",
            },
        )
        await run_service.mark_running(
            tenant_id=tenant.id,
            run_id=research_run.id,
            status_detail="Researching account.",
        )
        research_artifact = await artifacts.create(
            tenant_id=tenant.id,
            workflow_run_id=research_run.id,
            created_by_user_id=owner.id,
            artifact_type="research_brief",
            format="markdown",
            title="Ramp Brief",
            content_markdown="# Ramp",
        )
        await run_service.mark_awaiting_review(
            tenant_id=tenant.id,
            run_id=research_run.id,
            review_reason="Research needs a final check.",
            artifact_id=research_artifact.id,
            normalized_result_json={
                "outcome": "pending_review",
                "assistant_summary": "Research needs review.",
            },
        )
        await approvals.create(
            tenant_id=tenant.id,
            workflow_run_id=research_run.id,
            artifact_id=research_artifact.id,
            reviewed_by_user_id=owner.id,
            decision="approved",
        )
        await run_service.mark_succeeded(
            tenant_id=tenant.id,
            run_id=research_run.id,
            result_summary="Research approved.",
            normalized_result_json={
                "outcome": "research_completed",
                "assistant_summary": "Research approved.",
            },
        )
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            account_list_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/accounts",
                params={
                    "seller_profile_id": str(primary_seller.id),
                    "icp_profile_id": str(primary_icp.id),
                    "limit": 10,
                    "offset": 0,
                },
                headers={"Authorization": "Bearer member-subject"},
            )
            assert account_list_response.status_code == 200
            account_list_body = account_list_response.json()
            assert account_list_body["total"] == 1
            assert account_list_body["items"][0]["account_id"] == str(matched_account.id)
            assert "canonical_data_json" not in account_list_body["items"][0]
            assert "fit_signals_json" not in account_list_body["items"][0]

            account_detail_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/accounts/{matched_account.id}",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert account_detail_response.status_code == 200
            assert account_detail_response.json()["name"] == "Ramp"

            contact_list_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/contacts",
                params={"account_id": str(matched_account.id), "limit": 10, "offset": 0},
                headers={"Authorization": "Bearer member-subject"},
            )
            assert contact_list_response.status_code == 200
            contact_list_body = contact_list_response.json()
            assert contact_list_body["total"] == 1
            assert contact_list_body["items"][0]["contact_id"] == str(matched_contact.id)
            assert "person_data_json" not in contact_list_body["items"][0]

            contact_detail_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/contacts/{matched_contact.id}",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert contact_detail_response.status_code == 200
            assert contact_detail_response.json()["email"] == "jamie@ramp.com"

            run_list_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/workflow-runs",
                params={"limit": 10, "offset": 0},
                headers={"Authorization": "Bearer member-subject"},
            )
            assert run_list_response.status_code == 200
            run_list_body = run_list_response.json()
            assert run_list_body["total"] == 4
            assert {item["workflow_run_id"] for item in run_list_body["items"]} >= {
                str(account_search_run.id),
                str(contact_search_run.id),
                str(research_run.id),
            }
            contact_run_summary = next(
                item
                for item in run_list_body["items"]
                if item["workflow_run_id"] == str(contact_search_run.id)
            )
            assert contact_run_summary["review_required"] is True
            assert "requested_payload_json" not in contact_run_summary

            contact_run_detail_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{contact_search_run.id}",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert contact_run_detail_response.status_code == 200
            contact_run_detail = contact_run_detail_response.json()
            assert contact_run_detail["status"] == "awaiting_review"
            assert contact_run_detail["review_required"] is True
            assert contact_run_detail["review_reason"] == (
                "Need reviewer approval before using this contact."
            )
            assert contact_run_detail["artifact_ids"] == [str(review_artifact.id)]
            assert contact_run_detail["contact_ids"] == [str(matched_contact.id)]
            assert contact_run_detail["selected_account_id"] == str(matched_account.id)
            assert contact_run_detail["evidence_count"] == 1
            assert contact_run_detail["latest_approval"] is None
            assert "normalized_result_json" not in contact_run_detail

            research_run_detail_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/workflow-runs/{research_run.id}",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert research_run_detail_response.status_code == 200
            research_run_detail = research_run_detail_response.json()
            assert research_run_detail["latest_approval"]["decision"] == "approved"
            assert research_run_detail["selected_account_id"] == str(matched_account.id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_workspace_routes_reject_cross_tenant_access_and_missing_records(
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
        users = UserRepository(session)
        tenants = TenantRepository(session)
        memberships = MembershipRepository(session)

        member = await users.create(external_auth_subject="member-subject")
        stranger = await users.create(external_auth_subject="stranger-subject")
        tenant = await tenants.create(name="Tenant One", slug="tenant-one")
        hidden_tenant = await tenants.create(name="Tenant Two", slug="tenant-two")
        await memberships.create(tenant_id=tenant.id, user_id=member.id, role="member")
        await memberships.create(tenant_id=hidden_tenant.id, user_id=stranger.id, role="member")
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            forbidden_response = await client.get(
                f"/api/v1/tenants/{hidden_tenant.id}/accounts",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert forbidden_response.status_code == 403
            assert forbidden_response.json()["error_code"] == "tenant_membership_required"

            empty_runs_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/workflow-runs",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert empty_runs_response.status_code == 200
            assert empty_runs_response.json() == {
                "items": [],
                "total": 0,
                "limit": 20,
                "offset": 0,
            }

            missing_contact_response = await client.get(
                f"/api/v1/tenants/{tenant.id}/contacts/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                headers={"Authorization": "Bearer member-subject"},
            )
            assert missing_contact_response.status_code == 404
            assert missing_contact_response.json()["error_code"] == "resource_not_found"
    finally:
        app.dependency_overrides.clear()
