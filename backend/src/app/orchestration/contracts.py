from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict


class WorkflowType(StrEnum):
    SELLER_PROFILE_SETUP = "seller_profile_setup"
    ICP_PROFILE_SETUP = "icp_profile_setup"
    ACCOUNT_SEARCH = "account_search"
    ACCOUNT_RESEARCH = "account_research"
    CONTACT_SEARCH = "contact_search"


WORKFLOW_TYPES = tuple(workflow_type.value for workflow_type in WorkflowType)


class WorkflowRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


WORKFLOW_RUN_STATUSES = tuple(status.value for status in WorkflowRunStatus)
ALLOWED_WORKFLOW_RUN_TRANSITIONS = frozenset(
    {
        (WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.AWAITING_REVIEW),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.SUCCEEDED),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.FAILED),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.CANCELLED),
        (WorkflowRunStatus.AWAITING_REVIEW, WorkflowRunStatus.SUCCEEDED),
        (WorkflowRunStatus.AWAITING_REVIEW, WorkflowRunStatus.FAILED),
        (WorkflowRunStatus.AWAITING_REVIEW, WorkflowRunStatus.CANCELLED),
    }
)


class RunEventName(StrEnum):
    RUN_STARTED = "run.started"
    AGENT_HANDOFF = "agent.handoff"
    AGENT_COMPLETED = "agent.completed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    REASONING_VALIDATED = "reasoning.validated"
    REASONING_FAILED_VALIDATION = "reasoning.failed_validation"
    CANDIDATE_ACCEPTED = "candidate.accepted"
    CANDIDATE_REJECTED = "candidate.rejected"
    PROVIDER_ROUTING_DECISION = "provider.routing_decision"
    RUN_AWAITING_REVIEW = "run.awaiting_review"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


RUN_EVENT_NAMES = tuple(event_name.value for event_name in RunEventName)


class MissingInputCode(StrEnum):
    SELLER_PROFILE_REQUIRED = "seller_profile_required"
    ICP_PROFILE_REQUIRED = "icp_profile_required"
    SELECTED_ACCOUNT_REQUIRED = "selected_account_required"
    SELECTED_CONTACT_REQUIRED = "selected_contact_required"
    REVIEW_DECISION_REQUIRED = "review_decision_required"


MISSING_INPUT_CODES = tuple(code.value for code in MissingInputCode)


class OrchestratorDecisionType(StrEnum):
    REPLY_INLINE = "reply_inline"
    HANDOFF_TO_ACCOUNT_SEARCH = "handoff_to_account_search"
    HANDOFF_TO_ACCOUNT_RESEARCH = "handoff_to_account_research"
    HANDOFF_TO_CONTACT_SEARCH = "handoff_to_contact_search"
    START_WORKFLOW_RUN = "start_workflow_run"
    REQUEST_USER_REVIEW = "request_user_review"


ORCHESTRATOR_DECISION_TYPES = tuple(
    decision_type.value for decision_type in OrchestratorDecisionType
)


class ConversationReplyMode(StrEnum):
    INLINE_REPLY = "inline_reply"
    WORKFLOW_QUEUED = "workflow_queued"
    WORKFLOW_RUNNING = "workflow_running"
    AWAITING_REVIEW = "awaiting_review"


CONVERSATION_REPLY_MODES = tuple(reply_mode.value for reply_mode in ConversationReplyMode)


class OrchestratorInput(TypedDict):
    tenant_id: str
    user_id: str
    thread_id: str | None
    user_message: str
    active_workflow: WorkflowType | None
    seller_profile_id: str | None
    seller_profile_status: str | None
    icp_profile_id: str | None
    icp_profile_status: str | None
    selected_account_id: str | None
    selected_contact_id: str | None
    latest_run_status: WorkflowRunStatus | None
    conversation_summary: str | None


class OrchestratorDecision(TypedDict):
    decision_type: OrchestratorDecisionType
    workflow_type: WorkflowType | None
    target_agent: str | None
    reply_message: str | None
    reasoning_summary: str
    requires_persistence: bool
    missing_inputs: list[MissingInputCode]
    handoff_payload: dict[str, Any] | None
    confidence: float


def is_allowed_workflow_run_transition(
    current_status: WorkflowRunStatus | str,
    next_status: WorkflowRunStatus | str,
) -> bool:
    try:
        normalized_current = WorkflowRunStatus(current_status)
        normalized_next = WorkflowRunStatus(next_status)
    except ValueError:
        return False

    return (normalized_current, normalized_next) in ALLOWED_WORKFLOW_RUN_TRANSITIONS


def validate_orchestrator_decision(decision: OrchestratorDecision) -> None:
    decision_type = decision["decision_type"]
    workflow_type = decision["workflow_type"]
    target_agent = decision["target_agent"]
    reply_message = decision["reply_message"]
    handoff_payload = decision["handoff_payload"]

    if decision_type is OrchestratorDecisionType.REPLY_INLINE and not reply_message:
        raise ValueError("reply_inline decisions require reply_message")

    if decision_type is OrchestratorDecisionType.START_WORKFLOW_RUN and workflow_type is None:
        raise ValueError("start_workflow_run decisions require workflow_type")

    if decision_type in {
        OrchestratorDecisionType.HANDOFF_TO_ACCOUNT_SEARCH,
        OrchestratorDecisionType.HANDOFF_TO_ACCOUNT_RESEARCH,
        OrchestratorDecisionType.HANDOFF_TO_CONTACT_SEARCH,
    } and not target_agent:
        raise ValueError("handoff decisions require target_agent")

    if decision_type is OrchestratorDecisionType.REQUEST_USER_REVIEW:
        if not reply_message:
            raise ValueError("request_user_review decisions require reply_message")
        if handoff_payload is None:
            raise ValueError("request_user_review decisions require handoff_payload")
        if "review_reason" not in handoff_payload:
            raise ValueError(
                "request_user_review decisions require review_reason in handoff_payload"
            )
        if "workflow_run_id" not in handoff_payload and "artifact_id" not in handoff_payload:
            raise ValueError(
                "request_user_review decisions require workflow_run_id "
                "or artifact_id in handoff_payload"
            )
