from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import AuthIdentityDep, DbSessionDep
from app.models import Account, Contact
from app.schemas.workspace import (
    AccountListResponse,
    AccountResponse,
    ContactListResponse,
    ContactResponse,
    WorkflowRunApprovalSummaryResponse,
    WorkflowRunDetailResponse,
    WorkflowRunListResponse,
    WorkflowRunSummaryResponse,
)
from app.services.workspace import WorkflowRunView, WorkspaceService

router = APIRouter()


@router.get("/tenants/{tenant_id}/accounts", response_model=AccountListResponse)
async def list_accounts(
    tenant_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
    seller_profile_id: UUID | None = None,
    icp_profile_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountListResponse:
    accounts, total = await WorkspaceService(db_session).list_accounts(
        identity=identity,
        tenant_id=tenant_id,
        seller_profile_id=seller_profile_id,
        icp_profile_id=icp_profile_id,
        limit=limit,
        offset=offset,
    )
    return AccountListResponse(
        items=[_to_account_response(account) for account in accounts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tenants/{tenant_id}/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    tenant_id: UUID,
    account_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> AccountResponse:
    account = await WorkspaceService(db_session).get_account(
        identity=identity,
        tenant_id=tenant_id,
        account_id=account_id,
    )
    return _to_account_response(account)


@router.get("/tenants/{tenant_id}/contacts", response_model=ContactListResponse)
async def list_contacts(
    tenant_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
    account_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ContactListResponse:
    contacts, total = await WorkspaceService(db_session).list_contacts(
        identity=identity,
        tenant_id=tenant_id,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )
    return ContactListResponse(
        items=[_to_contact_response(contact) for contact in contacts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tenants/{tenant_id}/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(
    tenant_id: UUID,
    contact_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> ContactResponse:
    contact = await WorkspaceService(db_session).get_contact(
        identity=identity,
        tenant_id=tenant_id,
        contact_id=contact_id,
    )
    return _to_contact_response(contact)


@router.get("/tenants/{tenant_id}/workflow-runs", response_model=WorkflowRunListResponse)
async def list_workflow_runs(
    tenant_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> WorkflowRunListResponse:
    runs, total = await WorkspaceService(db_session).list_workflow_runs(
        identity=identity,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    return WorkflowRunListResponse(
        items=[_to_workflow_run_summary_response(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tenants/{tenant_id}/workflow-runs/{run_id}",
    response_model=WorkflowRunDetailResponse,
)
async def get_workflow_run(
    tenant_id: UUID,
    run_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> WorkflowRunDetailResponse:
    run = await WorkspaceService(db_session).get_workflow_run(
        identity=identity,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return _to_workflow_run_detail_response(run)


def _to_account_response(account: Account) -> AccountResponse:
    return AccountResponse(
        account_id=account.id,
        tenant_id=account.tenant_id,
        source_workflow_run_id=account.source_workflow_run_id,
        name=account.name,
        domain=account.domain,
        linkedin_url=account.linkedin_url,
        hq_location=account.hq_location,
        employee_range=account.employee_range,
        industry=account.industry,
        status=account.status,
        fit_summary=account.fit_summary,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _to_contact_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        contact_id=contact.id,
        tenant_id=contact.tenant_id,
        account_id=contact.account_id,
        full_name=contact.full_name,
        job_title=contact.job_title,
        email=contact.email,
        linkedin_url=contact.linkedin_url,
        phone=contact.phone,
        status=contact.status,
        ranking_summary=contact.ranking_summary,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


def _to_workflow_run_summary_response(run_view: WorkflowRunView) -> WorkflowRunSummaryResponse:
    return WorkflowRunSummaryResponse(
        workflow_run_id=run_view.run.id,
        thread_id=run_view.run.thread_id,
        workflow_type=run_view.run.workflow_type,
        status=run_view.run.status,
        outcome=run_view.outcome,
        visible_summary=run_view.visible_summary,
        seller_profile_id=run_view.seller_profile_id,
        icp_profile_id=run_view.icp_profile_id,
        selected_account_id=run_view.selected_account_id,
        selected_contact_id=run_view.selected_contact_id,
        review_required=run_view.run.status == "awaiting_review",
        created_at=run_view.run.created_at,
        updated_at=run_view.run.updated_at,
        started_at=run_view.run.started_at,
        finished_at=run_view.run.finished_at,
    )


def _to_workflow_run_detail_response(run_view: WorkflowRunView) -> WorkflowRunDetailResponse:
    latest_approval = None
    if run_view.latest_approval is not None:
        latest_approval = WorkflowRunApprovalSummaryResponse(
            decision=run_view.latest_approval.decision,
            rationale=run_view.latest_approval.rationale,
            reviewed_at=run_view.latest_approval.reviewed_at,
        )
    return WorkflowRunDetailResponse(
        **_to_workflow_run_summary_response(run_view).model_dump(),
        account_ids=run_view.account_ids,
        contact_ids=run_view.contact_ids,
        artifact_ids=run_view.artifact_ids,
        evidence_count=run_view.evidence_count,
        review_reason=run_view.review_reason,
        latest_approval=latest_approval,
    )
