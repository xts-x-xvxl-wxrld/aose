from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.orchestration.contracts import WorkflowType


class ChatTurnStreamRequest(BaseModel):
    user_message: str = Field(min_length=1)
    thread_id: UUID | None = None
    seller_profile_id: UUID | None = None
    icp_profile_id: UUID | None = None
    selected_account_id: UUID | None = None
    selected_contact_id: UUID | None = None
    active_workflow: WorkflowType | None = None


class ChatThreadResponse(BaseModel):
    thread_id: UUID
    tenant_id: UUID
    created_by_user_id: UUID
    seller_profile_id: UUID | None = None
    active_workflow: WorkflowType | None = None
    status: str
    current_run_id: UUID | None = None
    summary_text: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    message_id: UUID
    thread_id: UUID
    workflow_run_id: UUID | None = None
    role: str
    message_type: str
    content_text: str
    created_by_user_id: UUID | None = None
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    thread_id: UUID
    messages: list[ChatMessageResponse]


class ChatMetaEventResponse(BaseModel):
    type: str
    thread_id: UUID | None = None
    workflow_run_id: UUID
    workflow_status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatEventListResponse(BaseModel):
    events: list[ChatMetaEventResponse]
    limit: int
    offset: int
