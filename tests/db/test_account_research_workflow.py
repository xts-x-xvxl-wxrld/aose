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
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.workflow_runs import WorkflowRunService
from app.tools.contracts import (
    CompanyEnrichmentRequest,
    CompanyEnrichmentResponse,
    ContentNormalizerRequest,
    ContentNormalizerResponse,
    PageFetchRequest,
    PageFetchResponse,
    PageScrapeRequest,
    PageScrapeResponse,
    SearchResultRecord,
    ToolSourceReference,
    WebSearchRequest,
    WebSearchResponse,
)
from app.workers.runtime import execute_workflow_request
from app.workflows.account_research import AccountResearchToolset, AccountResearchWorkflow

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


class _StubCompanyEnrichmentTool:
    async def execute(self, request: CompanyEnrichmentRequest) -> CompanyEnrichmentResponse:
        return CompanyEnrichmentResponse(
            normalized_company_name=request.company_name,
            normalized_domain=request.domain,
            company_profile={
                "summary": "Fast-growing fintech operator with distributed sales teams.",
                "category": "payments",
            },
            source_references=[
                ToolSourceReference(
                    provider_name="provider-a",
                    source_url="https://provider.example/acme-fintech",
                    title="Provider Company Profile",
                )
            ],
        )


class _StubWebSearchTool:
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        return WebSearchResponse(
            results=[
                SearchResultRecord(
                    title=f"{request.query_text} result",
                    url="https://news.example/acme-fintech",
                    snippet="Acme Fintech is expanding revenue operations and buyer enablement.",
                )
            ]
        )


class _StubPageFetchTool:
    async def execute(self, request: PageFetchRequest) -> PageFetchResponse:
        return PageFetchResponse(
            status_code=200,
            body_text=f"Fetched public page for {request.url}.",
            content_type="text/html",
        )


class _StubPageScrapeTool:
    async def execute(self, request: PageScrapeRequest) -> PageScrapeResponse:
        return PageScrapeResponse(
            normalized_text="The company is hiring GTM operations roles and expanding into the US market.",
            headings=["Growth", "Expansion"],
            links=["https://news.example/acme-fintech/jobs"],
        )


class _StructuredNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(
            normalized_payload={
                "research_plan": {
                    "research_strategy": "Prioritize seller fit, ICP fit, and buying relevance.",
                    "focus_areas": ["seller fit", "ICP fit", "buying signals"],
                },
                "evidence_categories": ["provider", "web"],
                "structured_research_summary": {
                    "account_overview": "Acme Fintech is a US-focused payments company.",
                    "fit_to_seller_proposition": "The account has revenue operations complexity that fits the seller proposition.",
                    "fit_to_icp": "The account aligns with fintech and United States ICP signals.",
                    "buying_relevance_signals": [
                        "Hiring GTM operations staff.",
                        "Public expansion into the US market.",
                    ],
                    "risks_or_disqualifiers": ["Formal buying timeline is still unverified."],
                },
                "uncertainty_notes": ["Public evidence is directional and should be revalidated."],
                "research_summary": "Completed seller-aware research with ICP-backed fit signals.",
                "qualification_summary": "Likely strong ICP fit with active operational signals.",
                "research_brief_markdown": "# Research Brief\n\nStructured normalizer output.",
            }
        )


class _EmptyNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=None)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_research_workflow_persists_snapshot_evidence_and_brief_artifact(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    snapshot_repository = AccountResearchSnapshotRepository(db_session)
    evidence_repository = SourceEvidenceRepository(db_session)
    artifact_repository = ArtifactRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-research-workflow")
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
        criteria_json={"industries": ["fintech"], "geography": ["United States"]},
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
        hq_location="United States",
        employee_range="201-500",
        status="accepted",
        fit_summary="Existing fit signal from account search.",
        fit_signals_json={"growth_signal": True},
    )
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_RESEARCH,
        requested_payload_json={
            "account_id": str(account.id),
            "seller_profile_id": str(seller.id),
            "icp_profile_id": str(icp.id),
            "research_objective": "Validate account fit and buying relevance.",
        },
    )
    await db_session.commit()

    request = run_service.build_execution_request(run=run, request_id="req-account-research")
    workflow = AccountResearchWorkflow(
        db_session,
        run_service=run_service,
        tools=AccountResearchToolset(
            web_search=_StubWebSearchTool(),
            page_fetch=_StubPageFetchTool(),
            page_scrape=_StubPageScrapeTool(),
            content_normalizer=_StructuredNormalizerTool(),
            company_enrichment=_StubCompanyEnrichmentTool(),
        ),
    )

    result = await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=workflow.execute,
    )
    refreshed_run = await run_service.get_run_for_tenant(tenant_id=tenant.id, run_id=run.id)
    events = await run_service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)
    latest_snapshot = await snapshot_repository.get_latest_for_account(
        tenant_id=tenant.id,
        account_id=account.id,
    )
    evidence_rows = await evidence_repository.list_for_run(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
    )

    assert refreshed_run is not None
    assert refreshed_run.status == "succeeded"
    assert result.normalized_result_json["outcome"] == "research_completed"
    assert result.normalized_result_json["snapshot_version"] == 1
    assert result.normalized_result_json["icp_context_present"] is True
    assert latest_snapshot is not None
    assert latest_snapshot.snapshot_version == 1
    assert latest_snapshot.research_summary == "Completed seller-aware research with ICP-backed fit signals."
    assert latest_snapshot.research_json["structured_research_summary"]["fit_to_icp"] == (
        "The account aligns with fintech and United States ICP signals."
    )
    assert len(latest_snapshot.research_json["structured_research_summary"]["linked_evidence_ids"]) == len(
        evidence_rows
    )
    assert len(evidence_rows) == 3
    artifact = await artifact_repository.get_for_tenant(
        tenant_id=tenant.id,
        artifact_id=result.canonical_output_ids["artifact_ids"][0],  # type: ignore[index]
    )
    assert artifact is not None
    assert artifact.artifact_type == "research_brief"
    assert [event.event_name for event in events] == [
        "run.started",
        "agent.handoff",
        "tool.started",
        "tool.completed",
        "tool.started",
        "tool.completed",
        "tool.started",
        "tool.completed",
        "tool.started",
        "tool.completed",
        "tool.started",
        "tool.completed",
        "agent.completed",
        "run.completed",
    ]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_research_workflow_omits_icp_fit_without_context_and_increments_versions(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    snapshot_repository = AccountResearchSnapshotRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-research-rerun")
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
        domain=None,
        industry="healthtech",
        status="accepted",
    )
    first_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_RESEARCH,
        requested_payload_json={
            "account_id": str(account.id),
            "seller_profile_id": str(seller.id),
            "research_objective": "Initial research pass.",
        },
    )
    second_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_RESEARCH,
        requested_payload_json={
            "account_id": str(account.id),
            "seller_profile_id": str(seller.id),
            "research_objective": "Refresh research without ICP context.",
        },
    )
    await db_session.commit()

    workflow = AccountResearchWorkflow(
        db_session,
        run_service=run_service,
        tools=AccountResearchToolset(
            web_search=_StubWebSearchTool(),
            page_fetch=_StubPageFetchTool(),
            page_scrape=_StubPageScrapeTool(),
            content_normalizer=_EmptyNormalizerTool(),
            company_enrichment=_StubCompanyEnrichmentTool(),
        ),
    )

    first_result = await execute_workflow_request(
        request=run_service.build_execution_request(run=first_run, request_id="req-research-rerun-1"),
        run_service=run_service,
        handler=workflow.execute,
    )
    second_result = await execute_workflow_request(
        request=run_service.build_execution_request(run=second_run, request_id="req-research-rerun-2"),
        run_service=run_service,
        handler=workflow.execute,
    )
    snapshots = await snapshot_repository.list_for_account(
        tenant_id=tenant.id,
        account_id=account.id,
    )

    assert first_result.normalized_result_json["snapshot_version"] == 1
    assert second_result.normalized_result_json["snapshot_version"] == 2
    assert second_result.normalized_result_json["icp_context_present"] is False
    assert len(snapshots) == 2
    assert "fit_to_icp" not in snapshots[-1].research_json["structured_research_summary"]
    assert "ICP context was not provided" in (snapshots[-1].uncertainty_notes or "")
