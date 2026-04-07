from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import AuthIdentity
from app.models import (
    Account,
    ApprovalDecision,
    Contact,
    RunEvent,
    TenantMembership,
    User,
    WorkflowRun,
)
from app.repositories.account_repository import AccountRepository
from app.repositories.approval_decision_repository import ApprovalDecisionRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.errors import ServiceError


@dataclass(slots=True)
class WorkflowRunView:
    run: WorkflowRun
    account_ids: list[UUID]
    contact_ids: list[UUID]
    artifact_ids: list[UUID]
    evidence_count: int
    review_reason: str | None
    latest_approval: ApprovalDecision | None
    seller_profile_id: UUID | None
    icp_profile_id: UUID | None
    selected_account_id: UUID | None
    selected_contact_id: UUID | None
    visible_summary: str | None
    outcome: str | None


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)
        self._accounts = AccountRepository(session)
        self._contacts = ContactRepository(session)
        self._runs = WorkflowRunRepository(session)
        self._artifacts = ArtifactRepository(session)
        self._evidence = SourceEvidenceRepository(session)
        self._approvals = ApprovalDecisionRepository(session)
        self._events = RunEventRepository(session)

    async def list_accounts(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        seller_profile_id: UUID | None = None,
        icp_profile_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Account], int]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        accounts = await self._accounts.list_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
            icp_profile_id=icp_profile_id,
            limit=limit,
            offset=offset,
        )
        total = await self._accounts.count_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
            icp_profile_id=icp_profile_id,
        )
        return accounts, total

    async def get_account(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        account_id: UUID,
    ) -> Account:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        account = await self._accounts.get_for_tenant(
            tenant_id=tenant_id,
            account_id=account_id,
        )
        if account is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Account was not found in the requested tenant.",
            )
        return account

    async def list_contacts(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        account_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Contact], int]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        contacts = await self._contacts.list_for_tenant(
            tenant_id=tenant_id,
            account_id=account_id,
            limit=limit,
            offset=offset,
        )
        total = await self._contacts.count_for_tenant(
            tenant_id=tenant_id,
            account_id=account_id,
        )
        return contacts, total

    async def get_contact(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> Contact:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        contact = await self._contacts.get_for_tenant(
            tenant_id=tenant_id,
            contact_id=contact_id,
        )
        if contact is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Contact was not found in the requested tenant.",
            )
        return contact

    async def list_workflow_runs(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WorkflowRunView], int]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        runs = await self._runs.list_for_tenant(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
        total = await self._runs.count_for_tenant(tenant_id=tenant_id)
        return [await self._build_run_view(tenant_id=tenant_id, run=run) for run in runs], total

    async def get_workflow_run(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        run_id: UUID,
    ) -> WorkflowRunView:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        return await self._build_run_view(tenant_id=tenant_id, run=run)

    async def _build_run_view(
        self,
        *,
        tenant_id: UUID,
        run: WorkflowRun,
    ) -> WorkflowRunView:
        normalized_result_json = run.normalized_result_json or {}
        artifacts = await self._artifacts.list_for_run(
            tenant_id=tenant_id,
            workflow_run_id=run.id,
        )
        approvals = list(
            await self._approvals.list_for_run(
                tenant_id=tenant_id,
                workflow_run_id=run.id,
            )
        )
        run_events = list(await self._events.list_for_run(tenant_id=tenant_id, run_id=run.id))
        return WorkflowRunView(
            run=run,
            account_ids=_uuid_list_from_mapping(normalized_result_json, "accepted_account_ids"),
            contact_ids=_uuid_list_from_mapping(normalized_result_json, "contact_ids"),
            artifact_ids=[artifact.id for artifact in artifacts],
            evidence_count=await self._evidence.count_for_run(
                tenant_id=tenant_id,
                workflow_run_id=run.id,
            ),
            review_reason=_extract_review_reason(run_events, run),
            latest_approval=approvals[-1] if approvals else None,
            seller_profile_id=_extract_uuid(run.requested_payload_json, "seller_profile_id"),
            icp_profile_id=_extract_uuid(run.requested_payload_json, "icp_profile_id"),
            selected_account_id=_extract_selected_account_id(run),
            selected_contact_id=_extract_selected_contact_id(run),
            visible_summary=_extract_visible_summary(run),
            outcome=_extract_outcome(run),
        )

    async def _require_active_membership(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
    ) -> tuple[User, TenantMembership]:
        user = await self._users.get_by_external_auth_subject(
            external_auth_subject=identity.external_auth_subject
        )
        if user is None:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message="User does not have an active membership in the requested tenant.",
            )

        membership = await self._memberships.get_by_tenant_and_user(
            tenant_id=tenant_id,
            user_id=user.id,
        )
        if membership is None or membership.status != "active":
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message="User does not have an active membership in the requested tenant.",
            )
        return user, membership


def _extract_uuid(payload: dict[str, object], key: str) -> UUID | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _uuid_list_from_mapping(payload: dict[str, object], key: str) -> list[UUID]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    normalized: list[UUID] = []
    for item in value:
        if not isinstance(item, str):
            continue
        try:
            normalized.append(UUID(item))
        except ValueError:
            continue
    return normalized


def _extract_selected_account_id(run: WorkflowRun) -> UUID | None:
    return _extract_uuid(run.requested_payload_json, "account_id") or _extract_uuid(
        run.requested_payload_json,
        "selected_account_id",
    )


def _extract_selected_contact_id(run: WorkflowRun) -> UUID | None:
    return _extract_uuid(run.requested_payload_json, "contact_id") or _extract_uuid(
        run.requested_payload_json,
        "selected_contact_id",
    )


def _extract_visible_summary(run: WorkflowRun) -> str | None:
    normalized_result_json = run.normalized_result_json or {}
    assistant_summary = normalized_result_json.get("assistant_summary")
    if isinstance(assistant_summary, str) and assistant_summary.strip():
        return assistant_summary.strip()
    if isinstance(run.status_detail, str) and run.status_detail.strip():
        return run.status_detail.strip()
    return None


def _extract_outcome(run: WorkflowRun) -> str | None:
    normalized_result_json = run.normalized_result_json or {}
    outcome = normalized_result_json.get("outcome")
    if isinstance(outcome, str) and outcome.strip():
        return outcome.strip()
    return None


def _extract_review_reason(run_events: list[RunEvent], run: WorkflowRun) -> str | None:
    for event in reversed(run_events):
        if event.event_name != "run.awaiting_review":
            continue
        payload = event.payload_json or {}
        review_reason = payload.get("review_reason")
        if isinstance(review_reason, str) and review_reason.strip():
            return review_reason.strip()
    if (
        run.status == "awaiting_review"
        and isinstance(run.status_detail, str)
        and run.status_detail.strip()
    ):
        return run.status_detail.strip()
    return None
