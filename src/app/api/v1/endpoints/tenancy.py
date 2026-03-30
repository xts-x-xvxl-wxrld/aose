from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import AuthIdentityDep, DbSessionDep, SettingsDep
from app.models import TenantMembership
from app.schemas.tenancy import (
    TenantCreateRequest,
    TenantCreateResponse,
    TenantMemberCreateRequest,
    TenantMemberListResponse,
    TenantMemberResponse,
    TenantMemberUpdateRequest,
    TenantOwnershipTransferRequest,
    TenantOwnershipTransferResponse,
)
from app.services.errors import ServiceError
from app.services.tenancy import TenancyService

router = APIRouter()


@router.post("/tenants", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreateRequest,
    identity: AuthIdentityDep,
    settings: SettingsDep,
    db_session: DbSessionDep,
) -> TenantCreateResponse:
    service = TenancyService(db_session)
    try:
        tenant, membership = await service.create_tenant(
            identity=identity,
            tenant_name=payload.name,
            tenant_slug=payload.slug,
            self_serve_enabled=settings.tenant_self_serve_creation_enabled,
        )
    except SQLAlchemyError as exc:
        await db_session.rollback()
        raise ServiceError(
            status_code=409,
            error_code="ownership_conflict",
            message="Tenant creation conflicted with existing tenant state.",
        ) from exc

    return TenantCreateResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        creator_membership_id=membership.id,
        creator_role=membership.role,
        creator_status=membership.status,
    )


@router.get(
    "/tenants/{tenant_id}/members",
    response_model=TenantMemberListResponse,
)
async def list_members(
    tenant_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> TenantMemberListResponse:
    service = TenancyService(db_session)
    members = await service.list_members(identity=identity, tenant_id=tenant_id)
    return TenantMemberListResponse(
        members=[
            _to_member_response(
                membership=membership,
                email=user.email,
                display_name=user.display_name,
            )
            for membership, user in members
        ]
    )


@router.post(
    "/tenants/{tenant_id}/members",
    response_model=TenantMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_member(
    tenant_id: UUID,
    payload: TenantMemberCreateRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> TenantMemberResponse:
    service = TenancyService(db_session)
    membership, user = await service.create_member(
        identity=identity,
        tenant_id=tenant_id,
        target_user_id=payload.user_id,
        target_email=payload.email,
        role=payload.role,
    )
    return _to_member_response(
        membership=membership,
        email=user.email,
        display_name=user.display_name,
    )


@router.patch(
    "/tenants/{tenant_id}/members/{membership_id}",
    response_model=TenantMemberResponse,
)
async def update_member(
    tenant_id: UUID,
    membership_id: UUID,
    payload: TenantMemberUpdateRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> TenantMemberResponse:
    service = TenancyService(db_session)
    membership, user = await service.update_member(
        identity=identity,
        tenant_id=tenant_id,
        membership_id=membership_id,
        role=payload.role,
        status=payload.status,
    )
    return _to_member_response(
        membership=membership,
        email=user.email,
        display_name=user.display_name,
    )


@router.delete(
    "/tenants/{tenant_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_member(
    tenant_id: UUID,
    membership_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> Response:
    service = TenancyService(db_session)
    await service.delete_member(
        identity=identity,
        tenant_id=tenant_id,
        membership_id=membership_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tenants/{tenant_id}/members/{membership_id}/transfer-ownership",
    response_model=TenantOwnershipTransferResponse,
)
async def transfer_ownership(
    tenant_id: UUID,
    membership_id: UUID,
    payload: TenantOwnershipTransferRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> TenantOwnershipTransferResponse:
    service = TenancyService(db_session)
    previous_owner, new_owner = await service.transfer_ownership(
        identity=identity,
        tenant_id=tenant_id,
        target_membership_id=payload.target_membership_id,
    )
    if previous_owner.id != membership_id:
        raise ServiceError(
            status_code=409,
            error_code="ownership_conflict",
            message="Ownership transfer path membership must match the acting owner membership.",
        )
    return TenantOwnershipTransferResponse(
        tenant_id=tenant_id,
        previous_owner_membership_id=previous_owner.id,
        new_owner_membership_id=new_owner.id,
        previous_owner_role=previous_owner.role,
        new_owner_role=new_owner.role,
    )


def _to_member_response(
    *,
    membership: TenantMembership,
    email: str | None,
    display_name: str | None,
) -> TenantMemberResponse:
    return TenantMemberResponse(
        membership_id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        email=email,
        display_name=display_name,
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )
