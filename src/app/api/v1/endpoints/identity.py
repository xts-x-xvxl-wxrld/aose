from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentMembershipsDep, CurrentUserDep, RequestContextDep
from app.schemas.identity import MeResponse, TenantListResponse, TenantSummary


router = APIRouter()


@router.get("/me", response_model=MeResponse)
def get_me(current_user: CurrentUserDep, request_context: RequestContextDep) -> MeResponse:
    return MeResponse(
        user_id=current_user.user_id,
        external_auth_subject=current_user.external_auth_subject,
        email=current_user.email,
        display_name=current_user.display_name,
        request_id=request_context["request_id"],
    )


@router.get("/tenants", response_model=TenantListResponse)
def list_tenants(memberships: CurrentMembershipsDep) -> TenantListResponse:
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
