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
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.account_search import AccountSearchService
from app.services.errors import ServiceError

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
async def test_account_search_service_creates_normalized_queued_run(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    service = AccountSearchService(db_session)

    user = await user_repository.create(
        external_auth_subject="subject-account-search-service",
        email="member@example.com",
    )
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Core Seller",
        company_name="Acme",
        company_domain="acme.example",
        product_summary="Workflow automation for revenue teams.",
        value_proposition="Helps teams prioritize better-fit accounts.",
        target_market_summary="US fintech companies",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        created_by_user_id=user.id,
        name="Fintech ICP",
        criteria_json={"industries": ["fintech"], "geography": ["United States"]},
        status="active",
    )
    await db_session.commit()

    run = await service.create_account_search_run(
        identity=AuthIdentity(
            external_auth_subject=user.external_auth_subject,
            email=user.email,
            display_name=user.display_name,
        ),
        tenant_id=tenant.id,
        seller_profile_id=seller.id,
        icp_profile_id=icp.id,
        search_objective="  Find mid-market fintech accounts in the US.  ",
        user_targeting_constraints={"exclude": ["banks"]},
        correlation_id=" corr-accounts-1 ",
    )

    assert run.workflow_type == "account_search"
    assert run.status == "queued"
    assert run.requested_payload_json == {
        "seller_profile_id": str(seller.id),
        "icp_profile_id": str(icp.id),
        "search_objective": "Find mid-market fintech accounts in the US.",
        "user_targeting_constraints": {"exclude": ["banks"]},
    }
    assert run.correlation_id == "corr-accounts-1"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_account_search_service_rejects_mismatched_icp_and_seller(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    icp_repository = ICPProfileRepository(db_session)
    service = AccountSearchService(db_session)

    user = await user_repository.create(external_auth_subject="subject-account-search-mismatch")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=user.id, role="member")
    seller_one = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Seller One",
        company_name="Acme",
        product_summary="Summary",
        value_proposition="Value",
    )
    seller_two = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        name="Seller Two",
        company_name="Beta",
        product_summary="Summary",
        value_proposition="Value",
    )
    icp = await icp_repository.create(
        tenant_id=tenant.id,
        seller_profile_id=seller_two.id,
        created_by_user_id=user.id,
        name="Other ICP",
        criteria_json={"industries": ["software"]},
    )
    await db_session.commit()

    with pytest.raises(ServiceError, match="does not belong") as exc_info:
        await service.create_account_search_run(
            identity=AuthIdentity(
                external_auth_subject=user.external_auth_subject,
                email=user.email,
                display_name=user.display_name,
            ),
            tenant_id=tenant.id,
            seller_profile_id=seller_one.id,
            icp_profile_id=icp.id,
        )

    assert exc_info.value.error_code == "ownership_conflict"
