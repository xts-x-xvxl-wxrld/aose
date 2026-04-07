from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import AuthIdentity
from app.models import ICPProfile, SellerProfile, TenantMembership, User
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError

PROFILE_EDITOR_ROLES = {"owner", "admin", "member"}
SELLER_REQUIRED_FIELDS = ("name", "company_name", "product_summary", "value_proposition")


class SetupService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)
        self._seller_profiles = SellerProfileRepository(session)
        self._icp_profiles = ICPProfileRepository(session)

    async def create_seller_profile(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        name: str,
        company_name: str,
        product_summary: str,
        value_proposition: str,
        company_domain: str | None = None,
        target_market_summary: str | None = None,
        source_status: str | None = None,
        profile_json: dict[str, Any] | None = None,
    ) -> SellerProfile:
        actor_user, _membership = await self._require_profile_editor(
            identity=identity,
            tenant_id=tenant_id,
        )
        seller_profile = await self._seller_profiles.create(
            tenant_id=tenant_id,
            created_by_user_id=actor_user.id,
            name=_normalize_required_text(name, field_name="name"),
            company_name=_normalize_required_text(company_name, field_name="company_name"),
            company_domain=_normalize_optional_text(company_domain),
            product_summary=_normalize_required_text(
                product_summary,
                field_name="product_summary",
            ),
            value_proposition=_normalize_required_text(
                value_proposition,
                field_name="value_proposition",
            ),
            target_market_summary=_normalize_optional_text(target_market_summary),
            source_status=source_status or "manual",
            profile_json=profile_json,
        )
        await self._session.commit()
        await self._session.refresh(seller_profile)
        return seller_profile

    async def list_seller_profiles(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SellerProfile], int]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        seller_profiles = await self._seller_profiles.list_for_tenant(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
        total = await self._seller_profiles.count_for_tenant(tenant_id=tenant_id)
        return seller_profiles, total

    async def get_seller_profile(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        seller_profile_id: UUID,
    ) -> SellerProfile:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
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

    async def update_seller_profile(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        seller_profile_id: UUID,
        changes: dict[str, Any],
    ) -> SellerProfile:
        actor_user, _membership = await self._require_profile_editor(
            identity=identity,
            tenant_id=tenant_id,
        )
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

        normalized_changes = _normalize_seller_changes(changes)
        if not normalized_changes:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="At least one seller profile field must be supplied.",
            )

        updated_profile = await self._seller_profiles.update(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
            updated_by_user_id=actor_user.id,
            changes=normalized_changes,
        )
        assert updated_profile is not None
        await self._session.commit()
        await self._session.refresh(updated_profile)
        return updated_profile

    async def create_icp_profile(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        seller_profile_id: UUID,
        name: str,
        criteria_json: dict[str, Any],
        exclusions_json: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> ICPProfile:
        actor_user, _membership = await self._require_profile_editor(
            identity=identity,
            tenant_id=tenant_id,
        )
        await self._require_seller_profile(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
        )
        _ensure_meaningful_criteria(criteria_json)
        icp_profile = await self._icp_profiles.create(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
            created_by_user_id=actor_user.id,
            name=_normalize_required_text(name, field_name="name"),
            status=status or "draft",
            criteria_json=criteria_json,
            exclusions_json=exclusions_json,
        )
        await self._session.commit()
        await self._session.refresh(icp_profile)
        return icp_profile

    async def list_icp_profiles(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ICPProfile], int]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        icp_profiles = await self._icp_profiles.list_for_tenant(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
        total = await self._icp_profiles.count_for_tenant(tenant_id=tenant_id)
        return icp_profiles, total

    async def get_icp_profile(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        icp_profile_id: UUID,
    ) -> ICPProfile:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
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

    async def update_icp_profile(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        icp_profile_id: UUID,
        changes: dict[str, Any],
    ) -> ICPProfile:
        actor_user, _membership = await self._require_profile_editor(
            identity=identity,
            tenant_id=tenant_id,
        )
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

        normalized_changes = _normalize_icp_changes(changes)
        if not normalized_changes:
            raise ServiceError(
                status_code=422,
                error_code="validation_error",
                message="At least one ICP profile field must be supplied.",
            )

        updated_profile = await self._icp_profiles.update(
            tenant_id=tenant_id,
            icp_profile_id=icp_profile_id,
            updated_by_user_id=actor_user.id,
            changes=normalized_changes,
        )
        assert updated_profile is not None
        await self._session.commit()
        await self._session.refresh(updated_profile)
        return updated_profile

    async def _require_profile_editor(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
    ) -> tuple[User, TenantMembership]:
        return await self._require_active_membership(
            identity=identity,
            tenant_id=tenant_id,
            allowed_roles=PROFILE_EDITOR_ROLES,
            missing_membership_message=(
                "User does not have an active editable membership in the requested tenant."
            ),
        )

    async def _require_active_membership(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        allowed_roles: set[str] | None = None,
        missing_membership_message: str = (
            "User does not have an active membership in the requested tenant."
        ),
    ) -> tuple[User, TenantMembership]:
        user = await self._users.get_by_external_auth_subject(
            external_auth_subject=identity.external_auth_subject
        )
        if user is None:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message=missing_membership_message,
            )

        membership = await self._memberships.get_by_tenant_and_user(
            tenant_id=tenant_id,
            user_id=user.id,
        )
        if membership is None or membership.status != "active":
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message=missing_membership_message,
            )
        if allowed_roles is not None and membership.role not in allowed_roles:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message=missing_membership_message,
            )
        return user, membership

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


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message=f"{field_name} is required.",
            details={"field": field_name},
        )
    normalized = str(value).strip()
    if not normalized:
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message=f"{field_name} is required.",
            details={"field": field_name},
        )
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_seller_changes(changes: dict[str, Any]) -> dict[str, Any]:
    normalized_changes: dict[str, Any] = {}
    for field_name, field_value in changes.items():
        if field_name in SELLER_REQUIRED_FIELDS:
            normalized_changes[field_name] = _normalize_required_text(
                field_value,
                field_name=field_name,
            )
            continue
        if field_name in {"company_domain", "target_market_summary"}:
            normalized_changes[field_name] = _normalize_optional_text(field_value)
            continue
        if field_name in {"source_status", "profile_json"}:
            normalized_changes[field_name] = field_value
    return normalized_changes


def _normalize_icp_changes(changes: dict[str, Any]) -> dict[str, Any]:
    normalized_changes: dict[str, Any] = {}
    for field_name, field_value in changes.items():
        if field_name == "name":
            normalized_changes[field_name] = _normalize_required_text(
                field_value,
                field_name=field_name,
            )
            continue
        if field_name == "status":
            if field_value is None:
                raise ServiceError(
                    status_code=422,
                    error_code="validation_error",
                    message="status may not be null.",
                    details={"field": "status"},
                )
            normalized_changes[field_name] = field_value
            continue
        if field_name == "criteria_json":
            if field_value is None:
                raise ServiceError(
                    status_code=422,
                    error_code="validation_error",
                    message="criteria_json may not be null.",
                    details={"field": "criteria_json"},
                )
            _ensure_meaningful_criteria(field_value)
            normalized_changes[field_name] = field_value
            continue
        if field_name == "exclusions_json":
            normalized_changes[field_name] = field_value
    return normalized_changes


def _ensure_meaningful_criteria(criteria_json: Any) -> None:
    if not isinstance(criteria_json, dict) or not criteria_json:
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message="ICP profiles require at least one meaningful targeting criterion.",
            details={"field": "criteria_json"},
        )
    if not any(_value_is_meaningful(value) for value in criteria_json.values()):
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message="ICP profiles require at least one meaningful targeting criterion.",
            details={"field": "criteria_json"},
        )


def _value_is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_value_is_meaningful(child) for child in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_value_is_meaningful(child) for child in value)
    return True
