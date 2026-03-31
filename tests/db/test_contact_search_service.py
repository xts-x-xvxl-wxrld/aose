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
from app.repositories.account_repository import AccountRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.contact_search import ContactSearchService
from app.services.errors import ServiceError
from app.services.workflow_runs import WorkflowRunService

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
async def test_contact_search_service_creates_queued_run_with_optional_icp_context(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    run_service = WorkflowRunService(db_session)
    service = ContactSearchService(db_session)

    user = await user_repository.create(
        external_auth_subject="subject-contact-search-service",
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
    source_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        workflow_type="account_search",
        requested_payload_json={"seed": "account-search"},
    )
    account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        source_workflow_run_id=source_run.id,
        name="Northstar Bank",
        domain="northstar.example",
        normalized_domain="northstar.example",
        industry="fintech",
        status="accepted",
    )
    await db_session.commit()

    run = await service.create_contact_search_run(
        identity=AuthIdentity(
            external_auth_subject=user.external_auth_subject,
            email=user.email,
            display_name=user.display_name,
        ),
        tenant_id=tenant.id,
        account_id=account.id,
        seller_profile_id=seller.id,
        contact_objective="  find revenue operations leaders with systems ownership  ",
        correlation_id=" corr-contact-search-1 ",
    )

    assert run.workflow_type == "contact_search"
    assert run.status == "queued"
    assert run.requested_payload_json == {
        "account_id": str(account.id),
        "seller_profile_id": str(seller.id),
        "icp_profile_id": None,
        "contact_objective": "find revenue operations leaders with systems ownership",
    }
    assert run.correlation_id == "corr-contact-search-1"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_contact_search_service_rejects_reviewer_access(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    seller_repository = SellerProfileRepository(db_session)
    account_repository = AccountRepository(db_session)
    run_service = WorkflowRunService(db_session)
    service = ContactSearchService(db_session)

    reviewer = await user_repository.create(external_auth_subject="subject-contact-search-reviewer")
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=reviewer.id, role="reviewer")
    seller = await seller_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=reviewer.id,
        name="Core Seller",
        company_name="Acme",
        product_summary="Summary",
        value_proposition="Value",
    )
    source_run = await run_service.create_queued_run(
        tenant_id=tenant.id,
        created_by_user_id=reviewer.id,
        workflow_type="account_search",
        requested_payload_json={"seed": "account-search"},
    )
    account = await account_repository.create(
        tenant_id=tenant.id,
        created_by_user_id=reviewer.id,
        source_workflow_run_id=source_run.id,
        name="Northwind Health",
        status="accepted",
    )
    await db_session.commit()

    with pytest.raises(ServiceError) as exc_info:
        await service.create_contact_search_run(
            identity=AuthIdentity(
                external_auth_subject=reviewer.external_auth_subject,
                email=reviewer.email,
                display_name=reviewer.display_name,
            ),
            tenant_id=tenant.id,
            account_id=account.id,
            seller_profile_id=seller.id,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "tenant_membership_required"
