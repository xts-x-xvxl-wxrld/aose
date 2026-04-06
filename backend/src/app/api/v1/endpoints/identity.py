from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import (
    AuthIdentityDep,
    CurrentMembershipsDep,
    CurrentUserDep,
    OptionalDbSessionDep,
    RequestContextDep,
    SettingsDep,
)
from app.repositories.user_repository import UserRepository
from app.schemas.identity import MeResponse, TenantListResponse, TenantSummary
from app.services.tenancy import TenancyService

router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: CurrentUserDep,
    request_context: RequestContextDep,
    identity: AuthIdentityDep,
    db_session: OptionalDbSessionDep,
) -> MeResponse:
    persisted_user = None
    if db_session is not None:
        try:
            persisted_user = await UserRepository(db_session).get_by_external_auth_subject(
                external_auth_subject=identity.external_auth_subject
            )
        except SQLAlchemyError:
            persisted_user = None

    if persisted_user is not None:
        return MeResponse(
            user_id=str(persisted_user.id),
            external_auth_subject=persisted_user.external_auth_subject,
            email=persisted_user.email,
            display_name=persisted_user.display_name,
            is_platform_admin=persisted_user.is_platform_admin,
            request_id=request_context["request_id"],
        )

    return MeResponse(
        user_id=current_user.user_id,
        external_auth_subject=current_user.external_auth_subject,
        email=current_user.email,
        display_name=current_user.display_name,
        is_platform_admin=current_user.is_platform_admin,
        request_id=request_context["request_id"],
    )


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    memberships: CurrentMembershipsDep,
    identity: AuthIdentityDep,
    settings: SettingsDep,
    db_session: OptionalDbSessionDep,
) -> TenantListResponse:
    persisted_memberships = []
    if db_session is not None:
        try:
            persisted_memberships = await TenancyService(db_session).list_user_tenants(
                identity=identity
            )
        except SQLAlchemyError:
            persisted_memberships = []

    if persisted_memberships:
        return TenantListResponse(
            tenants=[
                TenantSummary(
                    tenant_id=str(membership.tenant_id),
                    tenant_name=tenant.name,
                    role=membership.role,
                    status=membership.status,
                )
                for membership, tenant in persisted_memberships
            ]
        )

    if not settings.fake_auth_enabled:
        return TenantListResponse(tenants=[])

    return TenantListResponse(
        tenants=[
            TenantSummary(
                tenant_id=membership.tenant_id,
                tenant_name=membership.tenant_name,
                role=membership.role,
                status=membership.status,
            )
            for membership in memberships
        ]
    )
