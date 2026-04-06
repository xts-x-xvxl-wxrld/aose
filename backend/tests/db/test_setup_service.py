from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.types import AuthIdentity
from app.db.base import Base
from app.models import load_model_modules
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.setup import SetupService

from .helpers import get_postgres_test_urls

load_model_modules()


async def _reset_async_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async_url, _sync_url = get_postgres_test_urls()
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    await _reset_async_database(session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_setup_service_creates_and_updates_seller_and_icp_profiles(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    service = SetupService(db_session)

    owner = await user_repository.create(external_auth_subject="subject-setup-owner")
    editor = await user_repository.create(external_auth_subject="subject-setup-editor")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=owner.id, role="owner")
    await membership_repository.create(tenant_id=tenant.id, user_id=editor.id, role="member")
    await db_session.commit()

    seller_profile = await service.create_seller_profile(
        identity=AuthIdentity(
            external_auth_subject="subject-setup-owner",
            email=None,
            display_name=None,
        ),
        tenant_id=tenant.id,
        name=" Core Seller ",
        company_name=" Acme Inc ",
        product_summary=" Solves a hard workflow problem ",
        value_proposition=" Replaces manual qualification work ",
        target_market_summary=" Mid-market SaaS teams ",
    )
    updated_seller = await service.update_seller_profile(
        identity=AuthIdentity(
            external_auth_subject="subject-setup-editor",
            email=None,
            display_name=None,
        ),
        tenant_id=tenant.id,
        seller_profile_id=seller_profile.id,
        changes={
            "company_domain": " acme.example ",
            "target_market_summary": None,
            "profile_json": {"segments": ["software"]},
        },
    )
    icp_profile = await service.create_icp_profile(
        identity=AuthIdentity(
            external_auth_subject="subject-setup-editor",
            email=None,
            display_name=None,
        ),
        tenant_id=tenant.id,
        seller_profile_id=seller_profile.id,
        name=" North America SaaS ICP ",
        criteria_json={"industries": ["software"], "geography": ["north america"]},
    )
    updated_icp = await service.update_icp_profile(
        identity=AuthIdentity(
            external_auth_subject="subject-setup-owner",
            email=None,
            display_name=None,
        ),
        tenant_id=tenant.id,
        icp_profile_id=icp_profile.id,
        changes={
            "status": "active",
            "exclusions_json": {"company_sizes": ["1-10"]},
        },
    )
    refreshed_seller = await seller_repository.get_for_tenant(
        tenant_id=tenant.id,
        seller_profile_id=seller_profile.id,
    )

    assert seller_profile.name == "Core Seller"
    assert seller_profile.company_name == "Acme Inc"
    assert seller_profile.source_status == "manual"
    assert updated_seller.company_domain == "acme.example"
    assert updated_seller.target_market_summary is None
    assert updated_seller.updated_by_user_id == editor.id
    assert icp_profile.name == "North America SaaS ICP"
    assert updated_icp.status == "active"
    assert updated_icp.updated_by_user_id == owner.id
    assert refreshed_seller is not None
    assert refreshed_seller.profile_json == {"segments": ["software"]}


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_setup_service_rejects_reviewer_writes_and_meaningless_icp_criteria(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    service = SetupService(db_session)

    owner = await user_repository.create(external_auth_subject="subject-setup-owner")
    reviewer = await user_repository.create(external_auth_subject="subject-setup-reviewer")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=owner.id, role="owner")
    await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
    seller_profile = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=owner.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Solves a hard workflow problem",
        value_proposition="Replaces manual qualification work",
    )
    await db_session.commit()

    with pytest.raises(ServiceError) as reviewer_error:
        await service.create_seller_profile(
            identity=AuthIdentity(
                external_auth_subject="subject-setup-reviewer",
                email=None,
                display_name=None,
            ),
            tenant_id=tenant.id,
            name="Blocked Seller",
            company_name="Blocked Company",
            product_summary="Blocked summary",
            value_proposition="Blocked value",
        )

    with pytest.raises(ServiceError) as criteria_error:
        await service.create_icp_profile(
            identity=AuthIdentity(
                external_auth_subject="subject-setup-owner",
                email=None,
                display_name=None,
            ),
            tenant_id=tenant.id,
            seller_profile_id=seller_profile.id,
            name="Invalid ICP",
            criteria_json={"industries": [], "geography": "   "},
        )

    assert reviewer_error.value.status_code == 403
    assert reviewer_error.value.error_code == "tenant_membership_required"
    assert criteria_error.value.status_code == 422
    assert criteria_error.value.error_code == "validation_error"
