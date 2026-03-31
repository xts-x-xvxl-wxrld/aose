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
from app.repositories.account_repository import AccountRepository
from app.repositories.account_research_snapshot_repository import AccountResearchSnapshotRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.workflow_runs import WorkflowRunService
from app.tools.contracts import (
    ContactEnrichmentRequest,
    ContactEnrichmentResponse,
    ContentNormalizerRequest,
    ContentNormalizerResponse,
    SearchResultRecord,
    ToolSourceReference,
    WebSearchRequest,
    WebSearchResponse,
)
from app.workers.runtime import execute_workflow_request
from app.workflows.contact_search import ContactSearchToolset, ContactSearchWorkflow

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


class _StubWebSearchTool:
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        return WebSearchResponse(
            results=[
                SearchResultRecord(
                    title=f"{request.query_text} result",
                    url=f"https://search.example/{abs(hash(request.query_text))}",
                    snippet="Relevant public context for contact discovery.",
                )
            ]
        )


class _StructuredNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(
            normalized_payload={
                "target_personas": [
                    "Revenue operations leaders",
                    "Sales operations leaders",
                ],
                "selection_criteria": [
                    "Director+ roles with systems ownership",
                    "Contacts closest to GTM operations change",
                ],
                "ranked_contact_rationale": (
                    "Ranked revenue-operations contacts for the selected account."
                ),
                "missing_data_flags": ["low_source_confidence"],
                "contacts": [
                    {
                        "full_name": "Pat Lee",
                        "job_title": "Director of Revenue Operations",
                        "email": "pat@example.com",
                        "linkedin_url": "https://linkedin.com/in/pat-lee",
                        "ranking_summary": "Best fit for the seller's workflow proposition.",
                        "person_data_json": {"provider_key": "pat-key"},
                        "evidence": [
                            {
                                "source_type": "web",
                                "source_url": "https://company.example/team/pat-lee",
                                "title": "Leadership Team",
                                "snippet_text": "Pat Lee leads revenue operations.",
                            }
                        ],
                    },
                    {
                        "full_name": "Jordan Smith",
                        "job_title": "Head of Sales Operations",
                        "ranking_summary": "Good secondary match with role ambiguity preserved.",
                        "missing_data_flags": ["role_match_uncertain"],
                        "person_data_json": {"provider_key": "jordan-key"},
                        "evidence": [
                            {
                                "source_type": "web",
                                "source_url": "https://linkedin.example/jordan-smith",
                                "title": "Jordan Smith profile",
                                "snippet_text": "Jordan Smith works in sales operations.",
                            }
                        ],
                    },
                ],
            }
        )


class _EmptyNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=None)


class _StubContactEnrichmentTool:
    async def execute(self, request: ContactEnrichmentRequest) -> ContactEnrichmentResponse:
        if request.contact_name == "Pat Lee":
            return ContactEnrichmentResponse(
                phone="+1-555-0100",
                source_references=[
                    ToolSourceReference(
                        provider_name="provider-a",
                        source_url="https://provider.example/pat-lee",
                        title="Pat Lee enrichment",
                    )
                ],
            )
        if request.contact_name == "Jordan Smith":
            return ContactEnrichmentResponse(
                linkedin_url="https://linkedin.com/in/jordan-smith",
                person_profile={"department": "sales operations"},
                source_references=[
                    ToolSourceReference(
                        provider_name="provider-a",
                        source_url="https://provider.example/jordan-smith",
                        title="Jordan Smith enrichment",
                    )
                ],
            )
        return ContactEnrichmentResponse()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_contact_search_workflow_merges_email_before_linkedin_and_uses_snapshot(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    snapshot_repository = AccountResearchSnapshotRepository(db_session)
    contact_repository = ContactRepository(db_session)
    evidence_repository = SourceEvidenceRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-contact-workflow")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme Seller",
        company_domain="seller.example",
        product_summary="Workflow automation for revenue teams.",
        value_proposition="Helps revenue teams prioritize better-fit accounts.",
        target_market_summary="US fintech",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industries": ["fintech"], "department": ["revenue operations"]},
        status="active",
    )
    source_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={"seed": "account-source"},
    )
    account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        source_workflow_run_id=source_run.id,
        name="Acme Fintech",
        domain="acme-fintech.example",
        normalized_domain="acme-fintech.example",
        industry="fintech",
        status="accepted",
    )
    snapshot = await snapshot_repository.create(
        tenant_id=tenant.id,
        account_id=account.id,
        workflow_run_id=source_run.id,
        created_by_user_id=user.id,
        snapshot_version=1,
        research_json={"summary": "expanding revops tooling"},
        research_summary="The account is expanding its revops tooling footprint.",
        qualification_summary="Prioritize revops and systems leaders.",
    )
    email_match_contact = await contact_repository.create(
        tenant_id=tenant.id,
        account_id=account.id,
        created_by_user_id=user.id,
        full_name="Pat Legacy",
        job_title="Legacy Role",
        email="pat@example.com",
        linkedin_url="https://linkedin.com/in/pat-legacy",
        status="candidate",
        person_data_json={"source": "legacy"},
    )
    linkedin_match_contact = await contact_repository.create(
        tenant_id=tenant.id,
        account_id=account.id,
        created_by_user_id=user.id,
        full_name="Pat Other",
        job_title="Other Role",
        email="other@example.com",
        linkedin_url="https://linkedin.com/in/pat-lee",
        status="candidate",
    )
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.CONTACT_SEARCH,
        requested_payload_json={
            "account_id": str(account.id),
            "seller_profile_id": str(seller.id),
            "icp_profile_id": str(icp.id),
            "contact_objective": "find revops leaders",
        },
    )
    await db_session.commit()

    workflow = ContactSearchWorkflow(
        db_session,
        run_service=run_service,
        tools=ContactSearchToolset(
            web_search=_StubWebSearchTool(),
            content_normalizer=_StructuredNormalizerTool(),
            contact_enrichment=_StubContactEnrichmentTool(),
        ),
    )

    result = await execute_workflow_request(
        request=run_service.build_execution_request(run=run, request_id="req-contact-search"),
        run_service=run_service,
        handler=workflow.execute,
    )
    refreshed_run = await run_service.get_run_for_tenant(tenant_id=tenant.id, run_id=run.id)
    contacts = await contact_repository.list_for_account(tenant_id=tenant.id, account_id=account.id)
    evidence_rows = await evidence_repository.list_for_run(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
    )
    refreshed_email_match = await contact_repository.get_for_tenant(
        tenant_id=tenant.id,
        contact_id=email_match_contact.id,
    )
    refreshed_linkedin_match = await contact_repository.get_for_tenant(
        tenant_id=tenant.id,
        contact_id=linkedin_match_contact.id,
    )

    assert refreshed_run is not None
    assert refreshed_run.status == "succeeded"
    assert result.normalized_result_json["outcome"] == "contacts_ranked"
    assert result.normalized_result_json["used_research_snapshot_id"] == str(snapshot.id)
    assert result.normalized_result_json["reason_summary"] == (
        "Ranked revenue-operations contacts for the selected account."
    )
    assert result.normalized_result_json["missing_data_flags"] == [
        "low_source_confidence",
        "role_match_uncertain",
        "missing_email",
    ]
    assert result.normalized_result_json["contact_ids"] == [
        str(email_match_contact.id),
        str(contacts[-1].id),
    ]
    assert len(contacts) == 3
    assert refreshed_email_match is not None
    assert refreshed_email_match.id == email_match_contact.id
    assert refreshed_email_match.full_name == "Pat Lee"
    assert refreshed_email_match.linkedin_url == "https://linkedin.com/in/pat-lee"
    assert refreshed_email_match.phone == "+1-555-0100"
    assert refreshed_email_match.person_data_json["used_research_snapshot_id"] == str(snapshot.id)
    assert refreshed_linkedin_match is not None
    assert refreshed_linkedin_match.id == linkedin_match_contact.id
    assert refreshed_linkedin_match.email == "other@example.com"
    new_contact = contacts[-1]
    assert new_contact.full_name == "Jordan Smith"
    assert new_contact.linkedin_url == "https://linkedin.com/in/jordan-smith"
    assert new_contact.person_data_json["missing_data_flags"] == [
        "role_match_uncertain",
        "missing_email",
    ]
    assert len(evidence_rows) == 4
    assert {str(evidence.contact_id) for evidence in evidence_rows} == {
        str(email_match_contact.id),
        str(new_contact.id),
    }


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_contact_search_workflow_records_zero_result_success_with_explicit_flags(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    contact_repository = ContactRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-contact-workflow-empty")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme Seller",
        product_summary="Workflow automation for revenue teams.",
        value_proposition="Helps revenue teams prioritize better-fit accounts.",
    )
    source_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={"seed": "account-source"},
    )
    account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        source_workflow_run_id=source_run.id,
        name="Northwind Health",
        status="accepted",
    )
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.CONTACT_SEARCH,
        requested_payload_json={
            "account_id": str(account.id),
            "seller_profile_id": str(seller.id),
        },
    )
    await db_session.commit()

    workflow = ContactSearchWorkflow(
        db_session,
        run_service=run_service,
        tools=ContactSearchToolset(
            web_search=_StubWebSearchTool(),
            content_normalizer=_EmptyNormalizerTool(),
            contact_enrichment=None,
        ),
    )

    result = await execute_workflow_request(
        request=run_service.build_execution_request(run=run, request_id="req-contact-search-empty"),
        run_service=run_service,
        handler=workflow.execute,
    )
    contacts = await contact_repository.list_for_account(tenant_id=tenant.id, account_id=account.id)

    assert result.normalized_result_json == {
        "outcome": "contacts_ranked",
        "contact_ids": [],
        "missing_data_flags": [],
        "used_research_snapshot_id": None,
        "reason_summary": (
            "Ranked contact candidates for Northwind Health using Acme Seller context."
        ),
    }
    assert contacts == []
