from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdminOverviewResponse(BaseModel):
    total_tenants: int
    total_runs: int
    active_runs: int
    failed_runs: int
    total_llm_calls: int
    total_tool_calls: int


class AdminTenantSummaryResponse(BaseModel):
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    tenant_status: str
    active_member_count: int = 0
    total_runs: int = 0
    active_runs: int = 0
    failed_runs: int = 0


class AdminTenantListResponse(BaseModel):
    tenants: list[AdminTenantSummaryResponse]


class AdminTenantOpsOverviewResponse(BaseModel):
    tenant_id: UUID
    total_runs: int
    queued_runs: int
    running_runs: int
    succeeded_runs: int
    failed_runs: int
    awaiting_review_runs: int
    total_llm_calls: int
    total_tool_calls: int


class AdminRunSummaryResponse(BaseModel):
    run_id: UUID
    tenant_id: UUID
    thread_id: UUID | None = None
    workflow_type: str
    status: str
    status_detail: str | None = None
    error_code: str | None = None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AdminRunListResponse(BaseModel):
    runs: list[AdminRunSummaryResponse]
    limit: int
    offset: int


class AdminRunDetailResponse(AdminRunSummaryResponse):
    requested_payload_json: dict[str, Any]
    config_snapshot_json: dict[str, Any] | None = None
    normalized_result_json: dict[str, Any] | None = None


class AdminRunEventResponse(BaseModel):
    event_id: UUID
    run_id: UUID
    event_name: str
    payload_json: dict[str, Any]
    created_at: datetime


class AdminRunEventListResponse(BaseModel):
    events: list[AdminRunEventResponse]


class LlmCallLogResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    thread_id: UUID | None = None
    agent_name: str | None = None
    workflow_type: str | None = None
    provider_name: str
    model_name: str | None = None
    status: str
    schema_hint: str | None = None
    request_profile: str | None = None
    input_excerpt: str | None = None
    output_excerpt: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error_code: str | None = None
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_micros: int | None = None
    created_at: datetime
    updated_at: datetime


class LlmCallLogListResponse(BaseModel):
    calls: list[LlmCallLogResponse]
    limit: int
    offset: int


class ToolCallLogResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    thread_id: UUID | None = None
    agent_name: str | None = None
    workflow_type: str | None = None
    tool_name: str
    provider_name: str | None = None
    status: str
    correlation_key: str | None = None
    input_excerpt: str | None = None
    output_excerpt: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error_code: str | None = None
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class ToolCallLogListResponse(BaseModel):
    calls: list[ToolCallLogResponse]
    limit: int
    offset: int


class AgentConfigPayloadResponse(BaseModel):
    instructions: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    model_settings_json: dict[str, Any] = Field(default_factory=dict)
    feature_flags_json: dict[str, Any] = Field(default_factory=dict)


class AgentConfigVersionResponse(BaseModel):
    id: UUID
    scope_type: str
    tenant_id: UUID | None = None
    agent_name: str
    version: int
    status: str
    change_note: str | None = None
    payload: AgentConfigPayloadResponse
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None


class AgentConfigViewResponse(BaseModel):
    agent_name: str
    code_default: AgentConfigPayloadResponse
    global_active: AgentConfigVersionResponse | None = None
    tenant_active: AgentConfigVersionResponse | None = None
    effective: AgentConfigPayloadResponse
    versions: list[AgentConfigVersionResponse] = Field(default_factory=list)


class AgentConfigScopeResponse(BaseModel):
    scope_type: str
    tenant_id: UUID | None = None
    configs: list[AgentConfigViewResponse]


class AgentConfigVersionCreateRequest(BaseModel):
    agent_name: str
    instructions: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    model_settings_json: dict[str, Any] = Field(default_factory=dict)
    feature_flags_json: dict[str, Any] = Field(default_factory=dict)
    change_note: str | None = None
    activate: bool = False


class AdminAuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID
    tenant_id: UUID | None = None
    action: str
    target_type: str
    target_id: UUID | None = None
    request_id: str | None = None
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    created_at: datetime


class AdminAuditLogListResponse(BaseModel):
    logs: list[AdminAuditLogResponse]
    limit: int
    offset: int
