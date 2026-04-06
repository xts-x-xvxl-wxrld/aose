from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.orchestration.contracts import (
    ConversationReplyMode,
    MissingInputCode,
    OrchestratorDecision,
    OrchestratorDecisionType,
    WorkflowRunStatus,
    WorkflowType,
    validate_orchestrator_decision,
)


class ConversationCreateRequest(BaseModel):
    user_message: str = Field(min_length=1)
    seller_profile_id: UUID | None = None
    icp_profile_id: UUID | None = None
    active_workflow: WorkflowType | None = None


class ConversationMessageCreateRequest(BaseModel):
    user_message: str = Field(min_length=1)
    seller_profile_id: UUID | None = None
    icp_profile_id: UUID | None = None
    selected_account_id: UUID | None = None
    selected_contact_id: UUID | None = None


class ConversationTurnResponse(BaseModel):
    thread_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID | None = None
    reply_mode: ConversationReplyMode
    reply_message: str | None = None
    workflow_run_id: UUID | None = None
    workflow_status: WorkflowRunStatus | None = None
    missing_inputs: list[MissingInputCode] = Field(default_factory=list)
    request_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reply_mode_requirements(self) -> ConversationTurnResponse:
        if self.reply_mode is ConversationReplyMode.INLINE_REPLY:
            if self.assistant_message_id is None:
                raise ValueError("inline_reply responses require assistant_message_id")
            if self.reply_message is None:
                raise ValueError("inline_reply responses require reply_message")

        if self.reply_mode in {
            ConversationReplyMode.WORKFLOW_QUEUED,
            ConversationReplyMode.WORKFLOW_RUNNING,
            ConversationReplyMode.AWAITING_REVIEW,
        } and self.workflow_run_id is None:
            raise ValueError("workflow-backed responses require workflow_run_id")

        return self


class OrchestratorDecisionModel(BaseModel):
    decision_type: OrchestratorDecisionType
    workflow_type: WorkflowType | None = None
    target_agent: str | None = None
    reply_message: str | None = None
    reasoning_summary: str = Field(min_length=1)
    requires_persistence: bool
    missing_inputs: list[MissingInputCode] = Field(default_factory=list)
    handoff_payload: dict[str, object] | None = None
    confidence: float

    @model_validator(mode="after")
    def validate_contract(self) -> OrchestratorDecisionModel:
        decision: OrchestratorDecision = {
            "decision_type": self.decision_type,
            "workflow_type": self.workflow_type,
            "target_agent": self.target_agent,
            "reply_message": self.reply_message,
            "reasoning_summary": self.reasoning_summary,
            "requires_persistence": self.requires_persistence,
            "missing_inputs": self.missing_inputs,
            "handoff_payload": self.handoff_payload,
            "confidence": self.confidence,
        }
        validate_orchestrator_decision(decision)
        return self
