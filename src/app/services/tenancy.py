from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import AuthIdentity
from app.models import Tenant, TenantMembership, User
from app.repositories.membership_repository import MembershipRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError

DIRECT_MEMBER_STATUSES = {"active", "disabled"}
MEMBERSHIP_ADMIN_ROLES = {"owner", "admin"}


class TenancyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tenants = TenantRepository(session)
        self._memberships = MembershipRepository(session)

    async def create_tenant(
        self,
        *,
        identity: AuthIdentity,
        tenant_name: str,
        tenant_slug: str,
        self_serve_enabled: bool,
    ) -> tuple[Tenant, TenantMembership]:
        if not self_serve_enabled:
            raise ServiceError(
                status_code=403,
                error_code="tenant_creation_disabled",
                message="Self-serve tenant creation is disabled for this deployment.",
            )

        normalized_name = tenant_name.strip()
        normalized_slug = _normalize_slug(tenant_slug)
        if not normalized_name:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="Tenant name is required.",
                details={"field": "name"},
            )
        if not normalized_slug:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="Tenant slug is invalid after normalization.",
                details={"field": "slug"},
            )

        existing_tenant = await self._tenants.get_by_slug(slug=normalized_slug)
        if existing_tenant is not None:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="A tenant with that slug already exists.",
                details={"slug": normalized_slug},
            )

        user = await self._ensure_user_from_identity(identity=identity)
        tenant = await self._tenants.create(name=normalized_name, slug=normalized_slug)
        membership = await self._memberships.create(
            tenant_id=tenant.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
        await self._session.commit()
        await self._session.refresh(tenant)
        await self._session.refresh(membership)
        return tenant, membership

    async def list_user_tenants(
        self,
        *,
        identity: AuthIdentity,
    ) -> Sequence[tuple[TenantMembership, Tenant]]:
        user = await self._users.get_by_external_auth_subject(
            external_auth_subject=identity.external_auth_subject
        )
        if user is None:
            return []
        return await self._memberships.list_for_user(user_id=user.id)

    async def list_members(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
    ) -> Sequence[tuple[TenantMembership, User]]:
        await self._require_actor_membership(identity=identity, tenant_id=tenant_id)
        return await self._memberships.list_for_tenant(tenant_id=tenant_id)

    async def create_member(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        target_user_id: UUID | None,
        target_email: str | None,
        role: str,
    ) -> tuple[TenantMembership, User]:
        _ensure_direct_member_role(role)
        _ensure_known_status("active")

        actor_user, actor_membership = await self._require_actor_membership(
            identity=identity,
            tenant_id=tenant_id,
            allowed_roles=MEMBERSHIP_ADMIN_ROLES,
        )
        target_user = await self._resolve_target_user(user_id=target_user_id, email=target_email)
        if target_user.status != "active":
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Disabled users cannot be added to a tenant.",
            )
        if target_user.id == actor_user.id and role != actor_membership.role:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Use membership update routes to change the acting member's role.",
            )
        if role == "owner" and actor_membership.role != "owner":
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Only an owner may create another owner membership.",
            )

        existing_membership = await self._memberships.get_by_tenant_and_user(
            tenant_id=tenant_id,
            user_id=target_user.id,
        )
        if existing_membership is not None:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="That user already has a membership in the tenant.",
                details={"membership_id": str(existing_membership.id)},
            )

        membership = await self._memberships.create(
            tenant_id=tenant_id,
            user_id=target_user.id,
            role=role,
            status="active",
        )
        await self._session.commit()
        await self._session.refresh(membership)
        return membership, target_user

    async def update_member(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        membership_id: UUID,
        role: str | None,
        status: str | None,
    ) -> tuple[TenantMembership, User]:
        if role is None and status is None:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="At least one of role or status must be supplied.",
            )
        if role is not None:
            _ensure_direct_member_role(role)
        if status is not None:
            _ensure_known_status(status)

        actor_membership = (
            await self._require_actor_membership(
                identity=identity,
                tenant_id=tenant_id,
                allowed_roles=MEMBERSHIP_ADMIN_ROLES,
            )
        )[1]
        target_membership = await self._get_target_membership(
            tenant_id=tenant_id,
            membership_id=membership_id,
        )
        target_user = await self._get_target_user(target_membership=target_membership)

        next_role = role or target_membership.role
        next_status = status or target_membership.status

        if actor_membership.role != "owner" and (
            target_membership.role == "owner" or next_role == "owner"
        ):
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Only an owner may manage owner memberships.",
            )

        await self._ensure_owner_retained(
            tenant_id=tenant_id,
            target_membership=target_membership,
            next_role=next_role,
            next_status=next_status,
        )

        target_membership.role = next_role
        target_membership.status = next_status
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(target_membership)
        return target_membership, target_user

    async def delete_member(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> None:
        actor_membership = (
            await self._require_actor_membership(
                identity=identity,
                tenant_id=tenant_id,
                allowed_roles=MEMBERSHIP_ADMIN_ROLES,
            )
        )[1]
        target_membership = await self._get_target_membership(
            tenant_id=tenant_id,
            membership_id=membership_id,
        )

        if actor_membership.role != "owner" and target_membership.role == "owner":
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Only an owner may remove an owner membership.",
            )

        await self._ensure_owner_retained(
            tenant_id=tenant_id,
            target_membership=target_membership,
            next_role=None,
            next_status=None,
            deleting=True,
        )
        await self._memberships.delete(target_membership)
        await self._session.commit()

    async def transfer_ownership(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        target_membership_id: UUID,
    ) -> tuple[TenantMembership, TenantMembership]:
        actor_user, actor_membership = await self._require_actor_membership(
            identity=identity,
            tenant_id=tenant_id,
            allowed_roles={"owner"},
        )
        target_membership = await self._get_target_membership(
            tenant_id=tenant_id,
            membership_id=target_membership_id,
        )

        if target_membership.user_id == actor_user.id:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Ownership transfer target must be a different membership.",
            )
        if target_membership.status != "active":
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Ownership transfer target must be active.",
            )
        if target_membership.role == "owner":
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Ownership transfer target is already an owner.",
            )

        actor_membership.role = "admin"
        target_membership.role = "owner"
        target_membership.status = "active"
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(actor_membership)
        await self._session.refresh(target_membership)
        return actor_membership, target_membership

    async def _ensure_user_from_identity(self, *, identity: AuthIdentity) -> User:
        user = await self._users.get_by_external_auth_subject(
            external_auth_subject=identity.external_auth_subject
        )
        if user is None:
            return await self._users.create(
                external_auth_subject=identity.external_auth_subject,
                email=identity.email,
                display_name=identity.display_name,
            )

        updated = False
        if identity.email != user.email:
            user.email = identity.email
            updated = True
        if identity.display_name != user.display_name:
            user.display_name = identity.display_name
            updated = True
        if updated:
            await self._session.flush()
        return user

    async def _require_actor_membership(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        allowed_roles: set[str] | None = None,
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
        if allowed_roles is not None and membership.role not in allowed_roles:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Acting member is not allowed to perform this membership change.",
            )
        return user, membership

    async def _resolve_target_user(
        self,
        *,
        user_id: UUID | None,
        email: str | None,
    ) -> User:
        if user_id is None and not email:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="Either user_id or email must be supplied.",
            )

        resolved_user: User | None = None
        if user_id is not None:
            resolved_user = await self._users.get_by_id(user_id=user_id)
            if resolved_user is None:
                raise ServiceError(
                    status_code=422,
                    error_code="validation_error",
                    message="Phase 1 member creation requires an existing user.",
                    details={"field": "user_id"},
                )

        if email:
            matches = list(await self._users.list_by_email(email=email))
            if not matches:
                raise ServiceError(
                    status_code=422,
                    error_code="validation_error",
                    message="Phase 1 email-based member creation requires an existing user.",
                    details={"field": "email"},
                )
            if len(matches) > 1:
                raise ServiceError(
                    status_code=422,
                    error_code="validation_error",
                    message="Email must resolve to exactly one existing user.",
                    details={"field": "email"},
                )
            email_user = matches[0]
            if resolved_user is not None and email_user.id != resolved_user.id:
                raise ServiceError(
                    status_code=422,
                    error_code="validation_error",
                    message="Provided user_id and email resolve to different users.",
                )
            resolved_user = email_user

        assert resolved_user is not None
        return resolved_user

    async def _get_target_membership(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> TenantMembership:
        membership = await self._memberships.get_by_id_for_tenant(
            tenant_id=tenant_id,
            membership_id=membership_id,
        )
        if membership is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Membership was not found in the requested tenant.",
            )
        return membership

    async def _get_target_user(self, *, target_membership: TenantMembership) -> User:
        user = await self._users.get_by_id(user_id=target_membership.user_id)
        if user is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="User for the requested membership was not found.",
            )
        return user

    async def _ensure_owner_retained(
        self,
        *,
        tenant_id: UUID,
        target_membership: TenantMembership,
        next_role: str | None,
        next_status: str | None,
        deleting: bool = False,
    ) -> None:
        current_is_active_owner = (
            target_membership.role == "owner" and target_membership.status == "active"
        )
        if not current_is_active_owner:
            return

        next_is_active_owner = not deleting and (next_role == "owner") and (next_status == "active")
        if next_is_active_owner:
            return

        active_owner_count = await self._memberships.count_active_owners(tenant_id=tenant_id)
        if active_owner_count <= 1:
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Tenant must retain at least one active owner.",
            )


def _ensure_direct_member_role(role: str) -> None:
    if role not in {"owner", "admin", "member", "reviewer"}:
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message="Invalid membership role.",
            details={"field": "role"},
        )


def _ensure_known_status(status: str) -> None:
    if status not in DIRECT_MEMBER_STATUSES:
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message="Phase 1 direct member management only supports active and disabled statuses.",
            details={"field": "status"},
        )


def _normalize_slug(raw_slug: str) -> str:
    slug = raw_slug.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
