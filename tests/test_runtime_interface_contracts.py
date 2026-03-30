from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.auth.types import RequestContext
from app.orchestration.contracts import WorkflowRunStatus, WorkflowType
from app.services.conversation import ConversationService
from app.services.errors import ServiceError
from app.services.runtime import (
    InProcessWorkflowExecutor,
    WorkflowExecutionRequest,
    dispatch_workflow_run,
)
from app.tools.contracts import (
    CompanyEnrichmentRequest,
    ContactEnrichmentRequest,
    ContentNormalizerResponse,
    PageFetchRequest,
    WebSearchRequest,
)
from app.workflows.contracts import (
    AccountResearchRunResult,
    AccountResearchRunResultOutcome,
    AccountSearchRunResult,
    AccountSearchRunResultOutcome,
    ContactMissingDataFlag,
    ContactSearchRunResult,
    ContactSearchRunResultOutcome,
)


class _StubOrchestrator:
    async def decide(self, orchestrator_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "decision_type": "reply_inline",
            "workflow_type": None,
            "target_agent": None,
            "reply_message": "stub",
            "reasoning_summary": "stub",
            "requires_persistence": False,
            "missing_inputs": [],
            "handoff_payload": None,
            "confidence": 1.0,
        }


def test_conversation_service_builds_normalized_orchestrator_input() -> None:
    service = ConversationService(session=None, orchestrator=_StubOrchestrator())  # type: ignore[arg-type]
    context: RequestContext = {
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "membership_role": "member",
        "request_id": "req_123",
    }

    orchestrator_input = service.build_orchestrator_input(
        context=context,
        user_message="Find accounts for this ICP.",
        active_workflow="account_search",
        icp_profile_id=str(uuid4()),
        latest_run_status="queued",
    )

    assert orchestrator_input["active_workflow"] is WorkflowType.ACCOUNT_SEARCH
    assert orchestrator_input["latest_run_status"] is WorkflowRunStatus.QUEUED


def test_conversation_service_requires_tenant_context() -> None:
    service = ConversationService(session=None, orchestrator=_StubOrchestrator())  # type: ignore[arg-type]
    context: RequestContext = {
        "tenant_id": None,
        "user_id": str(uuid4()),
        "membership_role": None,
        "request_id": "req_123",
    }

    with pytest.raises(ServiceError, match="Tenant context is required"):
        service.build_orchestrator_input(context=context, user_message="hello")


@pytest.mark.asyncio
async def test_in_process_workflow_executor_dispatches_registered_handler() -> None:
    received: list[WorkflowExecutionRequest] = []

    async def handler(request: WorkflowExecutionRequest) -> None:
        received.append(request)

    executor = InProcessWorkflowExecutor({WorkflowType.ACCOUNT_SEARCH: handler})
    request = WorkflowExecutionRequest(
        run_id=uuid4(),
        tenant_id=uuid4(),
        created_by_user_id=uuid4(),
        workflow_type=WorkflowType.ACCOUNT_SEARCH,
        thread_id=None,
        request_id="req_456",
    )

    dispatched_request = await dispatch_workflow_run(executor, request)

    assert dispatched_request == request
    assert received == [request]


@pytest.mark.asyncio
async def test_in_process_workflow_executor_rejects_missing_handler() -> None:
    executor = InProcessWorkflowExecutor()
    request = WorkflowExecutionRequest(
        run_id=uuid4(),
        tenant_id=uuid4(),
        created_by_user_id=uuid4(),
        workflow_type=WorkflowType.ACCOUNT_RESEARCH,
        thread_id=None,
    )

    with pytest.raises(LookupError, match="ACCOUNT_RESEARCH".lower()):
        await executor.dispatch(request)


def test_tool_contracts_validate_required_identifiers() -> None:
    with pytest.raises(ValidationError):
        PageFetchRequest()

    with pytest.raises(ValidationError):
        CompanyEnrichmentRequest()

    with pytest.raises(ValidationError):
        ContactEnrichmentRequest(account_id=uuid4())

    request = WebSearchRequest(query_text="acme fintech", result_limit=5)
    response = ContentNormalizerResponse(
        normalized_payload=[{"normalized_domain": "acme.com"}],
        missing_fields=[],
    )

    assert request.result_limit == 5
    assert response.normalized_payload == [{"normalized_domain": "acme.com"}]


def test_workflow_result_contracts_freeze_minimum_shapes() -> None:
    account_search_result = AccountSearchRunResult(
        outcome=AccountSearchRunResultOutcome.NO_RESULTS,
        accepted_account_ids=[],
        reason_summary="No credible accounts matched the ICP.",
        search_attempt_count=2,
    )
    account_research_result = AccountResearchRunResult(
        outcome=AccountResearchRunResultOutcome.RESEARCH_COMPLETED,
        snapshot_id=uuid4(),
        snapshot_version=1,
        icp_context_present=False,
        reason_summary="Completed seller-aware research without ICP context.",
    )
    contact_search_result = ContactSearchRunResult(
        outcome=ContactSearchRunResultOutcome.CONTACTS_RANKED,
        contact_ids=[],
        missing_data_flags=[
            ContactMissingDataFlag.MISSING_EMAIL,
            ContactMissingDataFlag.ROLE_MATCH_UNCERTAIN,
        ],
        used_research_snapshot_id=None,
        reason_summary="Ranked low-confidence contacts from public sources.",
    )

    assert account_search_result.outcome is AccountSearchRunResultOutcome.NO_RESULTS
    assert account_search_result.search_attempt_count == 2
    assert not account_research_result.icp_context_present
    assert contact_search_result.missing_data_flags == [
        ContactMissingDataFlag.MISSING_EMAIL,
        ContactMissingDataFlag.ROLE_MATCH_UNCERTAIN,
    ]
