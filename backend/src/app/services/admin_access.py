from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TenantMembership, User
from app.repositories.membership_repository import MembershipRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError


TENANT_ADMIN_ROLES = {"owner", "admin"}


class AdminAccessService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)

    async def require_platform_admin(self, *, actor_user_id: UUID) -> User:
        user = await self._users.get_by_id(user_id=actor_user_id)
        if user is None or not user.is_platform_admin or user.status != "active":
            raise ServiceError(
                status_code=403,
                error_code="admin_access_required",
                message="Platform admin access is required for this endpoint.",
            )
        return user

    async def require_tenant_admin(
        self,
        *,
        actor_user_id: UUID,
        tenant_id: UUID,
        allow_platform_admin: bool = True,
    ) -> tuple[User, TenantMembership | None]:
        user = await self._users.get_by_id(user_id=actor_user_id)
        if user is None or user.status != "active":
            raise ServiceError(
                status_code=403,
                error_code="admin_access_required",
                message="Admin access is required for this endpoint.",
            )
        if allow_platform_admin and user.is_platform_admin:
            return user, None

        membership = await self._memberships.get_by_tenant_and_user(
            tenant_id=tenant_id,
            user_id=actor_user_id,
        )
        if membership is None or membership.status != "active" or membership.role not in TENANT_ADMIN_ROLES:
            raise ServiceError(
                status_code=403,
                error_code="admin_access_required",
                message="Tenant admin access is required for this endpoint.",
            )
        return user, membership
