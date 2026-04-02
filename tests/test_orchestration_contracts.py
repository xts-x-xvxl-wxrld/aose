from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.orchestration.contracts import (
    ConversationReplyMode,
    MissingInputCode,
    OrchestratorDecisionType,
    RunEventName,
    WorkflowRunStatus,
    WorkflowType,
    is_allowed_workflow_run_transition,
    validate_orchestrator_decision,
)
from app.schemas.orchestration import (
    ConversationCreateRequest,
    ConversationTurnResponse,
    OrchestratorDecisionModel,
)
from app.workers.types import WorkflowRunStatus as WorkerWorkflowRunStatus
from app.workers.types import WorkflowType as WorkerWorkflowType


def test_orchestration_enums_stay_stable() -> None:
    assert [workflow_type.value for workflow_type in WorkflowType] == [
        "seller_profile_setup",
        "icp_profile_setup",
        "account_search",
        "account_research",
        "contact_search",
    ]
    assert [status.value for status in WorkflowRunStatus] == [
        "queued",
        "running",
        "awaiting_review",
        "succeeded",
        "failed",
        "cancelled",
    ]
    assert [event_name.value for event_name in RunEventName] == [
        "run.started",
        "agent.handoff",
        "agent.completed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "reasoning.validated",
        "reasoning.failed_validation",
        "candidate.accepted",
        "candidate.rejected",
        "provider.routing_decision",
        "run.awaiting_review",
        "run.completed",
        "run.failed",
    ]
    assert [code.value for code in MissingInputCode] == [
        "seller_profile_required",
        "icp_profile_required",
        "selected_account_required",
        "selected_contact_required",
        "review_decision_required",
    ]
    assert [decision_type.value for decision_type in OrchestratorDecisionType] == [
        "reply_inline",
        "handoff_to_account_search",
        "handoff_to_account_research",
        "handoff_to_contact_search",
        "start_workflow_run",
        "request_user_review",
    ]
    assert [reply_mode.value for reply_mode in ConversationReplyMode] == [
        "inline_reply",
        "workflow_queued",
        "workflow_running",
        "awaiting_review",
    ]


def test_worker_types_reexport_canonical_workflow_enums() -> None:
    assert WorkerWorkflowType is WorkflowType
    assert WorkerWorkflowRunStatus is WorkflowRunStatus


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING),
        ("running", "awaiting_review"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "cancelled"),
        ("awaiting_review", "succeeded"),
        ("awaiting_review", "failed"),
        ("awaiting_review", "cancelled"),
    ],
)
def test_allowed_workflow_run_transitions_match_the_spec(
    current_status: object,
    next_status: object,
) -> None:
    assert is_allowed_workflow_run_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("queued", "queued"),
        ("queued", "succeeded"),
        ("succeeded", "failed"),
        ("failed", "running"),
        ("cancelled", "running"),
        ("not_a_status", "running"),
    ],
)
def test_disallowed_workflow_run_transitions_are_rejected(
    current_status: str,
    next_status: str,
) -> None:
    assert not is_allowed_workflow_run_transition(current_status, next_status)


def test_reply_inline_decisions_require_reply_message() -> None:
    with pytest.raises(ValueError, match="reply_message"):
        validate_orchestrator_decision(
            {
                "decision_type": OrchestratorDecisionType.REPLY_INLINE,
                "workflow_type": None,
                "target_agent": None,
                "reply_message": None,
                "reasoning_summary": "Need clarification",
                "requires_persistence": False,
                "missing_inputs": [MissingInputCode.SELLER_PROFILE_REQUIRED],
                "handoff_payload": None,
                "confidence": 0.9,
            }
        )


def test_request_user_review_decisions_require_review_reason_and_reference() -> None:
    with pytest.raises(ValueError, match="review_reason"):
        validate_orchestrator_decision(
            {
                "decision_type": OrchestratorDecisionType.REQUEST_USER_REVIEW,
                "workflow_type": None,
                "target_agent": None,
                "reply_message": "Please review this result.",
                "reasoning_summary": "Human review is required",
                "requires_persistence": True,
                "missing_inputs": [MissingInputCode.REVIEW_DECISION_REQUIRED],
                "handoff_payload": {"artifact_id": str(uuid4())},
                "confidence": 0.7,
            }
        )

    with pytest.raises(ValueError, match="workflow_run_id or artifact_id"):
        validate_orchestrator_decision(
            {
                "decision_type": OrchestratorDecisionType.REQUEST_USER_REVIEW,
                "workflow_type": None,
                "target_agent": None,
                "reply_message": "Please review this result.",
                "reasoning_summary": "Human review is required",
                "requires_persistence": True,
                "missing_inputs": [MissingInputCode.REVIEW_DECISION_REQUIRED],
                "handoff_payload": {"review_reason": "Needs human confirmation"},
                "confidence": 0.7,
            }
        )


def test_orchestrator_decision_model_enforces_workflow_requirements() -> None:
    with pytest.raises(ValidationError, match="workflow_type"):
        OrchestratorDecisionModel(
            decision_type="start_workflow_run",
            reasoning_summary="Start async work",
            requires_persistence=True,
            missing_inputs=[],
            handoff_payload=None,
            confidence=0.85,
        )

    decision = OrchestratorDecisionModel(
        decision_type="request_user_review",
        workflow_type=None,
        target_agent=None,
        reply_message="Please review the generated output.",
        reasoning_summary="A human decision is required before completion.",
        requires_persistence=True,
        missing_inputs=["review_decision_required"],
        handoff_payload={"review_reason": "approval gate", "workflow_run_id": str(uuid4())},
        confidence=0.66,
    )

    assert decision.decision_type is OrchestratorDecisionType.REQUEST_USER_REVIEW
    assert decision.missing_inputs == [MissingInputCode.REVIEW_DECISION_REQUIRED]


def test_conversation_create_request_requires_first_user_message() -> None:
    with pytest.raises(ValidationError):
        ConversationCreateRequest(user_message="")

    request = ConversationCreateRequest(
        user_message="Find accounts for this seller.",
        active_workflow="account_search",
    )

    assert request.active_workflow is WorkflowType.ACCOUNT_SEARCH


def test_conversation_turn_response_enforces_inline_shape() -> None:
    with pytest.raises(ValidationError, match="assistant_message_id"):
        ConversationTurnResponse(
            thread_id=uuid4(),
            user_message_id=uuid4(),
            reply_mode="inline_reply",
            reply_message="Please add an ICP profile.",
            request_id="req_123",
        )

    response = ConversationTurnResponse(
        thread_id=uuid4(),
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        reply_mode="inline_reply",
        reply_message="Please add an ICP profile.",
        missing_inputs=["icp_profile_required"],
        request_id="req_123",
    )

    assert response.reply_mode is ConversationReplyMode.INLINE_REPLY
    assert response.missing_inputs == [MissingInputCode.ICP_PROFILE_REQUIRED]


def test_conversation_turn_response_enforces_workflow_shape() -> None:
    with pytest.raises(ValidationError, match="workflow_run_id"):
        ConversationTurnResponse(
            thread_id=uuid4(),
            user_message_id=uuid4(),
            reply_mode="workflow_queued",
            request_id="req_456",
        )

    response = ConversationTurnResponse(
        thread_id=uuid4(),
        user_message_id=uuid4(),
        reply_mode="awaiting_review",
        workflow_run_id=uuid4(),
        workflow_status="awaiting_review",
        missing_inputs=["review_decision_required"],
        request_id="req_456",
    )

    assert response.reply_mode is ConversationReplyMode.AWAITING_REVIEW
    assert response.workflow_status is WorkflowRunStatus.AWAITING_REVIEW
