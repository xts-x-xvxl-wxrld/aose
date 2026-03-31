from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import load_model_modules
from app.orchestration.contracts import WorkflowType
from app.repositories.account_repository import AccountRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.workflow_runs import WorkflowRunService
from app.tools.contracts import (
    ContentNormalizerRequest,
    ContentNormalizerResponse,
    SearchResultRecord,
    WebSearchRequest,
    WebSearchResponse,
)
from app.workers.runtime import execute_workflow_request
from app.workflows.account_search import (
    AccountCandidateRecord,
    AccountSearchAttemptRecord,
    AccountSearchPlan,
    AccountSearchSelection,
    AccountSearchToolset,
    AccountSearchWorkflow,
    AccountSearchWorkflowInput,
    CandidateEvidenceRecord,
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


class _StubPlanner:
    async def build_plan(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: object,
        icp_profile: object,
        attempt_number: int,
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchPlan:
        _ = workflow_input
        _ = seller_profile
        _ = icp_profile
        _ = prior_attempts
        return AccountSearchPlan(
            search_strategy=f"Attempt {attempt_number} strategy",
            query_ideas=[f"query-{attempt_number}"],
            fit_criteria=["industry: fintech"],
            clarification_questions=[],
        )

    async def select_candidates(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: object,
        icp_profile: object,
        attempt_number: int,
        plan: AccountSearchPlan,
        candidates: Sequence[AccountCandidateRecord],
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchSelection:
        _ = workflow_input
        _ = seller_profile
        _ = icp_profile
        _ = plan
        _ = prior_attempts
        if attempt_number == 1:
            return AccountSearchSelection(
                accepted_candidates=[],
                reason_summary="First attempt was too noisy, refining once.",
                credible_search_space_exhausted=False,
            )
        return AccountSearchSelection(
            accepted_candidates=list(candidates),
            reason_summary="Accepted the refined account shortlist.",
            credible_search_space_exhausted=True,
        )


class _NoResultsPlanner(_StubPlanner):
    async def select_candidates(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: object,
        icp_profile: object,
        attempt_number: int,
        plan: AccountSearchPlan,
        candidates: Sequence[AccountCandidateRecord],
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchSelection:
        _ = workflow_input
        _ = seller_profile
        _ = icp_profile
        _ = plan
        _ = candidates
        _ = prior_attempts
        return AccountSearchSelection(
            accepted_candidates=[],
            reason_summary="No credible account candidates were found.",
            credible_search_space_exhausted=True,
        )


class _StubWebSearchTool:
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        return WebSearchResponse(
            results=[
                SearchResultRecord(
                    title=f"Result for {request.query_text}",
                    url=f"https://{request.query_text}.example",
                    snippet="Candidate company result",
                )
            ]
        )


class _StubNormalizerTool:
    def __init__(self) -> None:
        self._call_count = 0

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        self._call_count += 1
        if self._call_count == 1:
            return ContentNormalizerResponse(
                normalized_payload=[
                    {
                        "name": "Unclear Candidate",
                        "domain": "unclear.example",
                        "industry": "general software",
                    }
                ]
            )
        return ContentNormalizerResponse(
            normalized_payload=[
                {
                    "name": "Acme Existing",
                    "domain": "acme.example",
                    "industry": "fintech",
                    "fit_summary": "Strong fit for the active ICP.",
                    "fit_signals_json": {"growth_signal": True},
                    "canonical_data_json": {"region": "United States", "category": "payments"},
                    "evidence": [
                        {
                            "source_type": "web",
                            "source_url": "https://acme.example/about",
                            "title": "About Acme",
                            "snippet_text": "Acme serves fintech operators.",
                        }
                    ],
                }
            ]
        )


class _EmptyNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=[])


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_persists_accounts_merges_domain_collisions_and_emits_events(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    evidence_repository = SourceEvidenceRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme Seller",
        company_domain="seller.example",
        product_summary="Workflow automation for sales teams.",
        value_proposition="Helps revenue teams prioritize ICP accounts.",
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
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={
            "seller_profile_id": str(seller.id),
            "icp_profile_id": str(icp.id),
            "search_objective": "Find fintech accounts",
            "user_targeting_constraints": {"exclude": ["banks"]},
        },
    )
    existing_account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        source_workflow_run_id=run.id,
        name="Acme Existing",
        domain="acme.example",
        normalized_domain="acme.example",
        industry="legacy",
        status="accepted",
        fit_signals_json={"existing_signal": True},
        canonical_data_json={"region": "United Kingdom"},
    )
    await db_session.commit()

    request = run_service.build_execution_request(run=run, request_id="req-account-search")
    workflow = AccountSearchWorkflow(
        db_session,
        run_service=run_service,
        planner=_StubPlanner(),
        tools=AccountSearchToolset(
            web_search=_StubWebSearchTool(),
            content_normalizer=_StubNormalizerTool(),
            company_enrichment=None,
        ),
    )

    result = await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=workflow.execute,
    )
    refreshed_run = await run_service.get_run_for_tenant(tenant_id=tenant.id, run_id=run.id)
    events = await run_service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)
    refreshed_account = await account_repository.get_by_normalized_domain(
        tenant_id=tenant.id,
        normalized_domain="acme.example",
    )
    evidence_rows = await evidence_repository.list_for_run(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
    )

    assert refreshed_run is not None
    assert refreshed_run.status == "succeeded"
    assert result.normalized_result_json == {
        "outcome": "accounts_found",
        "accepted_account_ids": [str(existing_account.id)],
        "reason_summary": "Accepted the refined account shortlist.",
        "search_attempt_count": 2,
    }
    assert refreshed_run.normalized_result_json == result.normalized_result_json
    assert result.canonical_output_ids["account_ids"] == [str(existing_account.id)]
    assert result.canonical_output_ids["evidence_ids"] == [str(evidence_rows[0].id)]
    assert refreshed_account is not None
    assert refreshed_account.id == existing_account.id
    assert refreshed_account.industry == "fintech"
    assert refreshed_account.fit_signals_json == {
        "existing_signal": True,
        "growth_signal": True,
    }
    assert refreshed_account.canonical_data_json == {
        "region": "United States",
        "category": "payments",
    }
    assert len(evidence_rows) == 1
    assert evidence_rows[0].account_id == existing_account.id
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
        "agent.completed",
        "run.completed",
    ]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_records_explicit_no_results_outcome(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow-empty")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme Seller",
        product_summary="Workflow automation for sales teams.",
        value_proposition="Helps revenue teams prioritize ICP accounts.",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industries": ["fintech"]},
        status="active",
    )
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={
            "seller_profile_id": str(seller.id),
            "icp_profile_id": str(icp.id),
        },
    )
    await db_session.commit()

    request = run_service.build_execution_request(run=run, request_id="req-account-search-empty")
    workflow = AccountSearchWorkflow(
        db_session,
        run_service=run_service,
        planner=_NoResultsPlanner(),
        tools=AccountSearchToolset(
            web_search=_StubWebSearchTool(),
            content_normalizer=_EmptyNormalizerTool(),
            company_enrichment=None,
        ),
    )

    result = await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=workflow.execute,
    )

    assert result.normalized_result_json == {
        "outcome": "no_results",
        "accepted_account_ids": [],
        "reason_summary": "No credible account candidates were found.",
        "search_attempt_count": 1,
    }
