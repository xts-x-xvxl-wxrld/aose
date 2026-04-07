from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import AuthIdentityDep, DbSessionDep
from app.models import ICPProfile, SellerProfile
from app.schemas.setup import (
    ICPProfileCreateRequest,
    ICPProfileListResponse,
    ICPProfileResponse,
    ICPProfileUpdateRequest,
    SellerProfileCreateRequest,
    SellerProfileListResponse,
    SellerProfileResponse,
    SellerProfileUpdateRequest,
)
from app.services.setup import SetupService

router = APIRouter()


@router.post(
    "/tenants/{tenant_id}/seller-profiles",
    response_model=SellerProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_seller_profile(
    tenant_id: UUID,
    payload: SellerProfileCreateRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> SellerProfileResponse:
    seller_profile = await SetupService(db_session).create_seller_profile(
        identity=identity,
        tenant_id=tenant_id,
        **payload.model_dump(),
    )
    return _to_seller_profile_response(seller_profile)


@router.get(
    "/tenants/{tenant_id}/seller-profiles",
    response_model=SellerProfileListResponse,
)
async def list_seller_profiles(
    tenant_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SellerProfileListResponse:
    seller_profiles, total = await SetupService(db_session).list_seller_profiles(
        identity=identity,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    return SellerProfileListResponse(
        items=[_to_seller_profile_response(seller_profile) for seller_profile in seller_profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tenants/{tenant_id}/seller-profiles/{seller_profile_id}",
    response_model=SellerProfileResponse,
)
async def get_seller_profile(
    tenant_id: UUID,
    seller_profile_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> SellerProfileResponse:
    seller_profile = await SetupService(db_session).get_seller_profile(
        identity=identity,
        tenant_id=tenant_id,
        seller_profile_id=seller_profile_id,
    )
    return _to_seller_profile_response(seller_profile)


@router.patch(
    "/tenants/{tenant_id}/seller-profiles/{seller_profile_id}",
    response_model=SellerProfileResponse,
)
async def update_seller_profile(
    tenant_id: UUID,
    seller_profile_id: UUID,
    payload: SellerProfileUpdateRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> SellerProfileResponse:
    seller_profile = await SetupService(db_session).update_seller_profile(
        identity=identity,
        tenant_id=tenant_id,
        seller_profile_id=seller_profile_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return _to_seller_profile_response(seller_profile)


@router.post(
    "/tenants/{tenant_id}/icp-profiles",
    response_model=ICPProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_icp_profile(
    tenant_id: UUID,
    payload: ICPProfileCreateRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> ICPProfileResponse:
    icp_profile = await SetupService(db_session).create_icp_profile(
        identity=identity,
        tenant_id=tenant_id,
        **payload.model_dump(),
    )
    return _to_icp_profile_response(icp_profile)


@router.get(
    "/tenants/{tenant_id}/icp-profiles",
    response_model=ICPProfileListResponse,
)
async def list_icp_profiles(
    tenant_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ICPProfileListResponse:
    icp_profiles, total = await SetupService(db_session).list_icp_profiles(
        identity=identity,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    return ICPProfileListResponse(
        items=[_to_icp_profile_response(icp_profile) for icp_profile in icp_profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tenants/{tenant_id}/icp-profiles/{icp_profile_id}",
    response_model=ICPProfileResponse,
)
async def get_icp_profile(
    tenant_id: UUID,
    icp_profile_id: UUID,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> ICPProfileResponse:
    icp_profile = await SetupService(db_session).get_icp_profile(
        identity=identity,
        tenant_id=tenant_id,
        icp_profile_id=icp_profile_id,
    )
    return _to_icp_profile_response(icp_profile)


@router.patch(
    "/tenants/{tenant_id}/icp-profiles/{icp_profile_id}",
    response_model=ICPProfileResponse,
)
async def update_icp_profile(
    tenant_id: UUID,
    icp_profile_id: UUID,
    payload: ICPProfileUpdateRequest,
    identity: AuthIdentityDep,
    db_session: DbSessionDep,
) -> ICPProfileResponse:
    icp_profile = await SetupService(db_session).update_icp_profile(
        identity=identity,
        tenant_id=tenant_id,
        icp_profile_id=icp_profile_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return _to_icp_profile_response(icp_profile)


def _to_seller_profile_response(seller_profile: SellerProfile) -> SellerProfileResponse:
    return SellerProfileResponse(
        seller_profile_id=seller_profile.id,
        tenant_id=seller_profile.tenant_id,
        created_by_user_id=seller_profile.created_by_user_id,
        updated_by_user_id=seller_profile.updated_by_user_id,
        name=seller_profile.name,
        company_name=seller_profile.company_name,
        company_domain=seller_profile.company_domain,
        product_summary=seller_profile.product_summary,
        value_proposition=seller_profile.value_proposition,
        target_market_summary=seller_profile.target_market_summary,
        source_status=seller_profile.source_status,
        profile_json=seller_profile.profile_json,
        created_at=seller_profile.created_at,
        updated_at=seller_profile.updated_at,
    )


def _to_icp_profile_response(icp_profile: ICPProfile) -> ICPProfileResponse:
    return ICPProfileResponse(
        icp_profile_id=icp_profile.id,
        tenant_id=icp_profile.tenant_id,
        seller_profile_id=icp_profile.seller_profile_id,
        created_by_user_id=icp_profile.created_by_user_id,
        updated_by_user_id=icp_profile.updated_by_user_id,
        name=icp_profile.name,
        status=icp_profile.status,
        criteria_json=icp_profile.criteria_json,
        exclusions_json=icp_profile.exclusions_json,
        created_at=icp_profile.created_at,
        updated_at=icp_profile.updated_at,
    )
