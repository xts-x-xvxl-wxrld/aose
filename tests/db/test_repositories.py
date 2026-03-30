from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import load_model_modules
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
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
async def test_identity_repositories_lookup_expected_records(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)

    user = await user_repository.create(
        external_auth_subject="subject-123",
        email="owner@example.com",
        display_name="Owner User",
    )
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    membership = await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="owner")
    await db_session.commit()

    found_user = await user_repository.get_by_external_auth_subject(external_auth_subject="subject-123")
    found_tenant = await tenant_repository.get_by_slug(slug="tenant-one")
    found_membership = await membership_repository.get_by_tenant_and_user(
        tenant_id=tenant.id,
        user_id=user.id,
    )

    assert found_user is not None and found_user.id == user.id
    assert found_tenant is not None and found_tenant.id == tenant.id
    assert found_membership is not None and found_membership.id == membership.id


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_seller_and_icp_repositories_enforce_tenant_scoped_access(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)

    user = await user_repository.create(external_auth_subject="subject-abc")
    tenant_one = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    tenant_two = await tenant_repository.create(name="Tenant Two", slug="tenant-two")
    seller = await seller_repository.create(
        tenant_id=tenant_one.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summarizes the product",
        value_proposition="Explains the value",
        profile_json={"segments": ["mid-market"]},
    )
    icp = await icp_repository.create(
        tenant_id=tenant_one.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Primary ICP",
        criteria_json={"industries": ["software"]},
    )
    await db_session.commit()

    visible_seller = await seller_repository.get_for_tenant(
        tenant_id=tenant_one.id,
        seller_profile_id=seller.id,
    )
    hidden_seller = await seller_repository.get_for_tenant(
        tenant_id=tenant_two.id,
        seller_profile_id=seller.id,
    )
    visible_icp = await icp_repository.get_for_tenant(
        tenant_id=tenant_one.id,
        icp_profile_id=icp.id,
    )
    hidden_icp = await icp_repository.get_for_tenant(
        tenant_id=tenant_two.id,
        icp_profile_id=icp.id,
    )

    assert visible_seller is not None and visible_seller.id == seller.id
    assert hidden_seller is None
    assert visible_icp is not None and visible_icp.id == icp.id
    assert hidden_icp is None


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_seller_and_icp_updates_track_updated_by_user(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)

    owner = await user_repository.create(external_auth_subject="subject-owner")
    editor = await user_repository.create(external_auth_subject="subject-editor")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")

    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=owner.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summarizes the product",
        value_proposition="Explains the value",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=owner.id,
        name="Primary ICP",
        criteria_json={"industries": ["software"]},
    )
    await db_session.commit()

    updated_seller = await seller_repository.update(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        updated_by_user_id=editor.id,
        changes={"company_domain": "acme.example", "source_status": "manual"},
    )
    updated_icp = await icp_repository.update(
        tenant_id=tenant.id,
        icp_profile_id=icp.id,
        updated_by_user_id=editor.id,
        changes={"status": "active", "exclusions_json": {"geography": ["antarctica"]}},
    )
    await db_session.commit()

    assert updated_seller is not None
    assert updated_seller.updated_by_user_id == editor.id
    assert updated_seller.company_domain == "acme.example"
    assert updated_icp is not None
    assert updated_icp.updated_by_user_id == editor.id
    assert updated_icp.status == "active"
