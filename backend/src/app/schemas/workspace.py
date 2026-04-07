from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AccountResponse(BaseModel):
    account_id: UUID
    tenant_id: UUID
    source_workflow_run_id: UUID
    name: str
    domain: str | None
    linkedin_url: str | None
    hq_location: str | None
    employee_range: str | None
    industry: str | None
    status: str
    fit_summary: str | None
    created_at: datetime
    updated_at: datetime


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
    limit: int
    offset: int


class ContactResponse(BaseModel):
    contact_id: UUID
    tenant_id: UUID
    account_id: UUID
    full_name: str
    job_title: str | None
    email: str | None
    linkedin_url: str | None
    phone: str | None
    status: str
    ranking_summary: str | None
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    limit: int
    offset: int


class WorkflowRunSummaryResponse(BaseModel):
    workflow_run_id: UUID
    thread_id: UUID | None
    workflow_type: str
    status: str
    outcome: str | None = None
    visible_summary: str | None = None
    seller_profile_id: UUID | None = None
    icp_profile_id: UUID | None = None
    selected_account_id: UUID | None = None
    selected_contact_id: UUID | None = None
    review_required: bool = False
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkflowRunApprovalSummaryResponse(BaseModel):
    decision: str
    rationale: str | None = None
    reviewed_at: datetime


class WorkflowRunDetailResponse(WorkflowRunSummaryResponse):
    account_ids: list[UUID]
    contact_ids: list[UUID]
    artifact_ids: list[UUID]
    evidence_count: int
    review_reason: str | None = None
    latest_approval: WorkflowRunApprovalSummaryResponse | None = None


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunSummaryResponse]
    total: int
    limit: int
    offset: int
