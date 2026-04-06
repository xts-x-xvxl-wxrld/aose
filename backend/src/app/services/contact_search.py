from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import AuthIdentity
from app.models import Account, ICPProfile, SellerProfile, TenantMembership, User, WorkflowRun
from app.repositories.account_repository import AccountRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.workflow_runs import WorkflowRunService
from app.workflows.contact_search import ContactSearchWorkflowInput

CONTACT_SEARCH_EDITOR_ROLES = {"owner", "admin", "member"}


class ContactSearchService:
    def __init__(
        self,
        session: AsyncSession,
        run_service: WorkflowRunService | None = None,
    ) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)
        self._accounts = AccountRepository(session)
        self._seller_profiles = SellerProfileRepository(session)
        self._icp_profiles = ICPProfileRepository(session)
        self._run_service = run_service or WorkflowRunService(session)

    async def create_contact_search_run(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        account_id: UUID,
        seller_profile_id: UUID,
        icp_profile_id: UUID | None = None,
        contact_objective: str | None = None,
        thread_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowRun:
        actor_user, _membership = await self._require_contact_search_actor(
            identity=identity,
            tenant_id=tenant_id,
        )
        account = await self._require_account(
            tenant_id=tenant_id,
            account_id=account_id,
        )
        seller_profile = await self._require_seller_profile(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
        )
        icp_profile = await self._require_icp_profile(
            tenant_id=tenant_id,
            icp_profile_id=icp_profile_id,
        )
        if icp_profile is not None and icp_profile.seller_profile_id != seller_profile.id:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="ICP profile does not belong to the requested seller profile.",
            )

        workflow_input = ContactSearchWorkflowInput(
            account_id=account.id,
            seller_profile_id=seller_profile.id,
            icp_profile_id=icp_profile.id if icp_profile is not None else None,
            contact_objective=_normalize_optional_text(contact_objective),
        )
        return await self._run_service.create_queued_run(
            tenant_id=tenant_id,
            created_by_user_id=actor_user.id,
            workflow_type="contact_search",
            requested_payload_json=workflow_input.model_dump(mode="json"),
            thread_id=thread_id,
            correlation_id=_normalize_optional_text(correlation_id),
            status_detail="Queued contact search workflow run.",
        )

    async def _require_contact_search_actor(
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
        if membership.role not in CONTACT_SEARCH_EDITOR_ROLES:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message="User does not have permission to run contact search in this tenant.",
            )
        return user, membership

    async def _require_account(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
    ) -> Account:
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

    async def _require_seller_profile(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID,
    ) -> SellerProfile:
        seller_profile = await self._seller_profiles.get_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
        )
        if seller_profile is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Seller profile was not found in the requested tenant.",
            )
        return seller_profile

    async def _require_icp_profile(
        self,
        *,
        tenant_id: UUID,
        icp_profile_id: UUID | None,
    ) -> ICPProfile | None:
        if icp_profile_id is None:
            return None

        icp_profile = await self._icp_profiles.get_for_tenant(
            tenant_id=tenant_id,
            icp_profile_id=icp_profile_id,
        )
        if icp_profile is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="ICP profile was not found in the requested tenant.",
            )
        return icp_profile


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
