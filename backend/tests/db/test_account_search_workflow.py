from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import WorkflowRun
from app.db.base import Base
from app.models import load_model_modules
from app.orchestration.contracts import WorkflowType
from app.repositories.account_repository import AccountRepository
from app.repositories.conversation_message_repository import ConversationMessageRepository
from app.repositories.conversation_thread_repository import ConversationThreadRepository
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
        tenant_id: UUID,
        run: WorkflowRun,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: object,
        icp_profile: object,
        attempt_number: int,
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchPlan:
        _ = tenant_id
        _ = run
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


class _AcceptAllPlanner(_StubPlanner):
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
        _ = attempt_number
        _ = plan
        _ = prior_attempts
        return AccountSearchSelection(
            accepted_candidates=list(candidates),
            reason_summary="Accepted fallback account shortlist.",
            credible_search_space_exhausted=True,
        )


class _StubWebSearchTool:
    provider_name = "firecrawl"

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
    provider_name = "openai"

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
    provider_name = "openai"

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=[])


class _FailingPrimaryWebSearchTool:
    provider_name = "firecrawl"

    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        _ = request
        return WebSearchResponse(results=[], error_code="provider_unavailable")


class _BadResponsePrimaryWebSearchTool:
    provider_name = "firecrawl"

    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        _ = request
        return WebSearchResponse(
            results=[],
            raw_result_summary="firecrawl search failed across compatibility profiles",
            error_code="provider_bad_response",
        )


class _GoogleFallbackSearchTool:
    provider_name = "google_local_places"

    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        return WebSearchResponse(
            results=[
                SearchResultRecord(
                    title=f"Fallback result for {request.query_text}",
                    url="https://fallback-account.example",
                    snippet="Fallback place-centric result",
                    provider_name="google_local_places",
                )
            ]
        )


class _StructuredFallbackNormalizerTool:
    provider_name = "openai"

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(
            normalized_payload={
                "accepted_candidates": [
                    {
                        "name": "Fallback Account",
                        "domain": "fallback-account.example",
                        "industry": "fintech",
                        "fit_summary": "Fallback candidate from backup search.",
                        "evidence": [
                            {
                                "source_type": "web",
                                "provider_name": "google_local_places",
                                "source_url": "https://fallback-account.example",
                                "title": "Fallback Account",
                            }
                        ],
                    }
                ],
                "rejected_candidates": [],
            }
        )


class _UnavailableNormalizerTool:
    provider_name = "openai"

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=None, error_code="provider_unavailable")


class _BadResponseNormalizerTool:
    provider_name = "openai"

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        search_results = request.raw_payload["search_results"]
        return ContentNormalizerResponse(
            normalized_payload=None,
            raw_result_summary=(
                f"openai request failed across compatibility profiles with {len(search_results)} search result(s)"
            ),
            error_code="provider_bad_response",
        )


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
        "assistant_summary": "I finished the account search workflow. Accepted the refined account shortlist.",
        "summary_selection_reason": "Selected normal success summary because accepted account candidates were found on the primary path.",
        "primary_provider_name": "firecrawl",
        "fallback_provider_name": None,
        "primary_provider_failed": False,
        "fallback_attempted": False,
        "fallback_used": False,
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
    event_names = [event.event_name for event in events]
    assert event_names[0:2] == ["run.started", "agent.handoff"]
    assert event_names[-2:] == ["agent.completed", "run.completed"]
    assert event_names.count("reasoning.validated") == 2
    assert "candidate.accepted" in event_names
    assert "candidate.rejected" in event_names


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
        "assistant_summary": "I finished the account search workflow. No credible account candidates were found.",
        "summary_selection_reason": "Selected true no-results summary because the workflow exhausted the search space without a known upstream provider outage.",
        "primary_provider_name": "firecrawl",
        "fallback_provider_name": None,
        "primary_provider_failed": False,
        "fallback_attempted": False,
        "fallback_used": False,
    }


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_falls_back_to_google_local_places_and_surfaces_degraded_messages(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    thread_repository = ConversationThreadRepository(db_session)
    account_repository = AccountRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow-fallback")
    tenant = await tenant_repository.create(name="Tenant Fallback", slug="tenant-fallback")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    thread = await thread_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        active_workflow="account_search",
    )
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme Seller",
        product_summary="Workflow automation for sales teams.",
        value_proposition="Helps revenue teams prioritize ICP accounts.",
        target_market_summary="Austin fintech",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industries": ["fintech"], "geography": ["Austin"]},
        status="active",
    )
    run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        requested_payload_json={
            "seller_profile_id": str(seller.id),
            "icp_profile_id": str(icp.id),
            "search_objective": "Find fintech clinics in Austin",
        },
        thread_id=thread.id,
    )
    await db_session.commit()

    request = run_service.build_execution_request(run=run, request_id="req-account-search-fallback")
    workflow = AccountSearchWorkflow(
        db_session,
        run_service=run_service,
        planner=_AcceptAllPlanner(),
        tools=AccountSearchToolset(
            web_search=_FailingPrimaryWebSearchTool(),
            content_normalizer=_StructuredFallbackNormalizerTool(),
            fallback_web_search=_GoogleFallbackSearchTool(),
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
    accepted_account_id = UUID(result.normalized_result_json["accepted_account_ids"][0])
    persisted_account = await account_repository.get_for_tenant(
        tenant_id=tenant.id,
        account_id=accepted_account_id,
    )
    run_messages = await ConversationMessageRepository(db_session).list_for_run(
        tenant_id=tenant.id,
        run_id=run.id,
    )

    assert refreshed_run is not None
    assert persisted_account is not None
    assert refreshed_run.status == "succeeded"
    assert result.normalized_result_json == {
        "outcome": "accounts_found_via_fallback",
        "accepted_account_ids": [str(persisted_account.id)],
        "reason_summary": "Accepted fallback account shortlist.",
        "search_attempt_count": 1,
        "assistant_summary": "I had trouble with one of our main sources, but I was able to continue with a backup search and found a smaller set of candidates.",
        "summary_selection_reason": "Selected degraded-success summary because the primary provider failed and fallback produced accepted candidates.",
        "primary_provider_name": "firecrawl",
        "fallback_provider_name": "google_local_places",
        "primary_provider_failed": True,
        "fallback_attempted": True,
        "fallback_used": True,
    }
    assert any(
        event.event_name == "provider.routing_decision"
        and event.payload_json.get("selected_provider") == "google_local_places"
        for event in events
    )
    assert any(
        message.message_type == "assistant_reply"
        and "trying a backup source now" in message.content_text.lower()
        for message in run_messages
    )
    assert any(
        message.message_type == "assistant_reply"
        and "backup search" in message.content_text.lower()
        for message in run_messages
    )


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_marks_provider_failure_with_fallback_exhausted(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow-exhausted")
    tenant = await tenant_repository.create(name="Tenant Exhausted", slug="tenant-exhausted")
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

    request = run_service.build_execution_request(run=run, request_id="req-account-search-exhausted")
    workflow = AccountSearchWorkflow(
        db_session,
        run_service=run_service,
        planner=_NoResultsPlanner(),
        tools=AccountSearchToolset(
            web_search=_FailingPrimaryWebSearchTool(),
            content_normalizer=_EmptyNormalizerTool(),
            fallback_web_search=_GoogleFallbackSearchTool(),
            company_enrichment=None,
        ),
    )

    result = await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=workflow.execute,
    )

    assert result.normalized_result_json == {
        "outcome": "provider_failure_with_fallback_exhausted",
        "accepted_account_ids": [],
        "reason_summary": "No credible account candidates were found.",
        "search_attempt_count": 1,
        "assistant_summary": "Hmm, looks like one of our sources is down. I tried a backup source too, but I couldn't confirm any reliable matches from the available data.",
        "summary_selection_reason": "Selected degraded-failure summary because the primary provider failed, fallback ran, and no reliable candidates were accepted.",
        "primary_provider_name": "firecrawl",
        "fallback_provider_name": "google_local_places",
        "primary_provider_failed": True,
        "fallback_attempted": True,
        "fallback_used": True,
    }


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_uses_fallback_when_primary_returns_bad_response(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow-bad-response")
    tenant = await tenant_repository.create(name="Tenant Bad Response", slug="tenant-bad-response")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme Seller",
        product_summary="Workflow automation for sales teams.",
        value_proposition="Helps revenue teams prioritize ICP accounts.",
        target_market_summary="Austin fintech",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industries": ["fintech"], "geography": ["Austin"]},
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

    result = await execute_workflow_request(
        request=run_service.build_execution_request(run=run, request_id="req-account-search-bad-response"),
        run_service=run_service,
        handler=AccountSearchWorkflow(
            db_session,
            run_service=run_service,
            planner=_AcceptAllPlanner(),
            tools=AccountSearchToolset(
                web_search=_BadResponsePrimaryWebSearchTool(),
                content_normalizer=_StructuredFallbackNormalizerTool(),
                fallback_web_search=_GoogleFallbackSearchTool(),
                company_enrichment=None,
            ),
        ).execute,
    )

    assert result.normalized_result_json["outcome"] == "accounts_found_via_fallback"
    assert result.normalized_result_json["primary_provider_failed"] is True
    assert result.normalized_result_json["fallback_attempted"] is True
    assert result.normalized_result_json["fallback_used"] is True


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_falls_back_to_deterministic_candidates_when_normalizer_returns_bad_response(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow-normalizer-bad-response")
    tenant = await tenant_repository.create(name="Tenant Normalizer Retry", slug="tenant-normalizer-retry")
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

    result = await execute_workflow_request(
        request=run_service.build_execution_request(
            run=run,
            request_id="req-account-search-normalizer-bad-response",
        ),
        run_service=run_service,
        handler=AccountSearchWorkflow(
            db_session,
            run_service=run_service,
            planner=_AcceptAllPlanner(),
            tools=AccountSearchToolset(
                web_search=_StubWebSearchTool(),
                content_normalizer=_BadResponseNormalizerTool(),
                company_enrichment=None,
            ),
        ).execute,
    )

    accepted_account_id = UUID(result.normalized_result_json["accepted_account_ids"][0])
    persisted_account = await account_repository.get_for_tenant(
        tenant_id=tenant.id,
        account_id=accepted_account_id,
    )

    assert persisted_account is not None
    assert result.normalized_result_json["outcome"] == "accounts_found"
    assert result.normalized_result_json["primary_provider_failed"] is False
    assert result.normalized_result_json["fallback_attempted"] is False


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_workflow_skips_reasoning_failed_validation_when_normalizer_provider_is_unavailable(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    run_service = WorkflowRunService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-workflow-normalizer")
    tenant = await tenant_repository.create(name="Tenant Normalizer", slug="tenant-normalizer")
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

    request = run_service.build_execution_request(run=run, request_id="req-account-search-normalizer")
    workflow = AccountSearchWorkflow(
        db_session,
        run_service=run_service,
        planner=_NoResultsPlanner(),
        tools=AccountSearchToolset(
            web_search=_StubWebSearchTool(),
            content_normalizer=_UnavailableNormalizerTool(),
            company_enrichment=None,
        ),
    )

    await execute_workflow_request(
        request=request,
        run_service=run_service,
        handler=workflow.execute,
    )
    events = await run_service.list_events_for_run(tenant_id=tenant.id, run_id=run.id)

    assert "reasoning.failed_validation" not in [event.event_name for event in events]
