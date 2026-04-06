from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tools.contracts import ContentNormalizerRequest, ContentNormalizerResponse
from app.workers.runtime import WorkflowExecutionError
from app.workflows.account_search import (
    AccountSearchAttemptRecord,
    LLMAccountSearchPlanner,
)


class _StubRunService:
    def __init__(self) -> None:
        self.tool_started: list[dict[str, object]] = []
        self.tool_completed: list[dict[str, object]] = []
        self.reasoning_validated: list[dict[str, object]] = []
        self.reasoning_failed_validation: list[dict[str, object]] = []
        self.llm_calls: list[dict[str, object]] = []

    async def emit_tool_started(self, **kwargs: object) -> None:
        self.tool_started.append(kwargs)

    async def emit_tool_completed(self, **kwargs: object) -> None:
        self.tool_completed.append(kwargs)

    async def emit_reasoning_validated(self, **kwargs: object) -> None:
        self.reasoning_validated.append(kwargs)

    async def emit_reasoning_failed_validation(self, **kwargs: object) -> None:
        self.reasoning_failed_validation.append(kwargs)

    async def record_llm_call(self, **kwargs: object) -> None:
        self.llm_calls.append(kwargs)


class _SequenceNormalizer:
    provider_name = "openai"

    def __init__(self, responses: list[ContentNormalizerResponse]) -> None:
        self._responses = responses
        self.requests: list[ContentNormalizerRequest] = []

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return self._responses[index]


def _seller_profile() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name="Primary Seller",
        company_name="Acme Seller",
        company_domain="seller.example",
        product_summary="Workflow automation for revenue teams.",
        value_proposition="Helps revops teams prioritize fit.",
        target_market_summary="US fintech and adjacent B2B software teams.",
        profile_json={},
    )


def _icp_profile() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        seller_profile_id=uuid4(),
        name="Fintech ICP",
        status="active",
        criteria_json={"industries": ["fintech"], "geography": ["United States"]},
        exclusions_json={"segments": ["banks"]},
    )


def _workflow_input() -> SimpleNamespace:
    return SimpleNamespace(
        seller_profile_id=uuid4(),
        icp_profile_id=uuid4(),
        search_objective="Find companies matching my ICP.",
        user_targeting_constraints={"exclude": ["banks"]},
        model_dump=lambda mode="json": {
            "seller_profile_id": str(uuid4()),
            "icp_profile_id": str(uuid4()),
            "search_objective": "Find companies matching my ICP.",
            "user_targeting_constraints": {"exclude": ["banks"]},
        },
    )


def _run() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        config_snapshot_json={
            "agents": {
                "account_search_agent": {
                    "model": "gpt-5.4-mini",
                    "instructions": "Use seller and ICP context to plan high-signal account searches.",
                    "system_prompt": "You are a careful account-search specialist.",
                }
            }
        },
    )


@pytest.mark.asyncio
async def test_llm_account_search_planner_returns_first_valid_plan() -> None:
    run_service = _StubRunService()
    normalizer = _SequenceNormalizer(
        [
            ContentNormalizerResponse(
                normalized_payload={
                    "search_strategy": "Prioritize B2B fintech operators with revops complexity.",
                    "query_ideas": [
                        "B2B fintech revenue operations software companies United States",
                        "payments infrastructure companies United States series B series C",
                    ],
                    "fit_criteria": ["industry: fintech", "geography: United States"],
                    "clarification_questions": [],
                },
                raw_metadata_json={"model": "gpt-5.4-mini"},
            )
        ]
    )
    planner = LLMAccountSearchPlanner(content_normalizer=normalizer, run_service=run_service)

    plan = await planner.build_plan(
        tenant_id=uuid4(),
        run=_run(),
        workflow_input=_workflow_input(),
        seller_profile=_seller_profile(),
        icp_profile=_icp_profile(),
        attempt_number=1,
        prior_attempts=[],
    )

    assert len(normalizer.requests) == 1
    assert plan.query_ideas[0].startswith("B2B fintech")
    assert run_service.reasoning_validated[0]["schema_name"] == "account_search_query_plan"
    assert run_service.llm_calls[0]["schema_hint"] == "account_search_query_plan"


@pytest.mark.asyncio
async def test_llm_account_search_planner_retries_invalid_plan_then_succeeds() -> None:
    run_service = _StubRunService()
    normalizer = _SequenceNormalizer(
        [
            ContentNormalizerResponse(
                normalized_payload={
                    "search_strategy": "Too generic",
                    "query_ideas": ["Find companies matching my ICP."],
                }
            ),
            ContentNormalizerResponse(
                normalized_payload={
                    "search_strategy": "Refine toward B2B fintech operators with workflow pain.",
                    "query_ideas": [
                        "B2B fintech software companies United States",
                        "revenue operations tooling companies fintech United States",
                    ],
                    "fit_criteria": ["industry: fintech"],
                    "clarification_questions": [],
                }
            ),
        ]
    )
    planner = LLMAccountSearchPlanner(content_normalizer=normalizer, run_service=run_service)
    prior_attempts = [
        AccountSearchAttemptRecord(
            attempt_number=1,
            search_strategy="Legacy search",
            query_ideas=["legacy fintech query"],
            candidate_count=8,
            accepted_count=0,
            reason_summary="Too noisy and not ICP-specific enough.",
        )
    ]

    plan = await planner.build_plan(
        tenant_id=uuid4(),
        run=_run(),
        workflow_input=_workflow_input(),
        seller_profile=_seller_profile(),
        icp_profile=_icp_profile(),
        attempt_number=2,
        prior_attempts=prior_attempts,
    )

    assert len(normalizer.requests) == 2
    assert plan.search_strategy.startswith("Refine toward B2B fintech")
    assert run_service.reasoning_failed_validation[0]["schema_name"] == "account_search_query_plan"
    second_payload = normalizer.requests[1].raw_payload
    assert second_payload["attempt_number"] == 2
    assert second_payload["prior_attempts"][0]["reason_summary"] == "Too noisy and not ICP-specific enough."
    assert second_payload["prior_planner_failure_summary"] is not None


@pytest.mark.asyncio
async def test_llm_account_search_planner_fails_closed_after_five_invalid_attempts() -> None:
    run_service = _StubRunService()
    normalizer = _SequenceNormalizer(
        [
            ContentNormalizerResponse(normalized_payload={"search_strategy": "Generic", "query_ideas": []})
            for _ in range(5)
        ]
    )
    planner = LLMAccountSearchPlanner(content_normalizer=normalizer, run_service=run_service)

    with pytest.raises(WorkflowExecutionError) as exc_info:
        await planner.build_plan(
            tenant_id=uuid4(),
            run=_run(),
            workflow_input=_workflow_input(),
            seller_profile=_seller_profile(),
            icp_profile=_icp_profile(),
            attempt_number=1,
            prior_attempts=[],
        )

    assert exc_info.value.error_code == "account_search_planner_failed"
    assert len(normalizer.requests) == 5
    assert len(run_service.tool_started) == 5
    assert len(run_service.tool_completed) == 5
