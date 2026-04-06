from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session, get_optional_db_session
from app.main import create_app
from app.models import load_model_modules
from app.repositories.membership_repository import MembershipRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from tests.db.helpers import get_postgres_test_urls

load_model_modules()


async def _reset_async_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    async_url, _sync_url = get_postgres_test_urls()
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    await _reset_async_database(session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_setup_routes_create_and_update_seller_and_icp_profiles(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Acme Workspace", "slug": "acme-workspace"},
            )
            assert create_tenant_response.status_code == 201
            tenant_id = create_tenant_response.json()["tenant_id"]

            create_seller_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/seller-profiles",
                json={
                    "name": "Acme Seller",
                    "company_name": "Acme",
                    "product_summary": "Automates seller research",
                    "value_proposition": "Cuts setup time",
                },
            )
            assert create_seller_response.status_code == 201
            seller_body = create_seller_response.json()
            assert seller_body["tenant_id"] == tenant_id
            assert seller_body["source_status"] == "manual"
            assert seller_body["updated_by_user_id"] is None

            update_seller_response = await client.patch(
                f"/api/v1/tenants/{tenant_id}/seller-profiles/{seller_body['seller_profile_id']}",
                json={
                    "company_domain": "acme.example",
                    "target_market_summary": "Mid-market software teams",
                    "profile_json": {"buyer_pains": ["manual qualification"]},
                },
            )
            assert update_seller_response.status_code == 200
            updated_seller_body = update_seller_response.json()
            assert updated_seller_body["company_domain"] == "acme.example"
            assert updated_seller_body["target_market_summary"] == "Mid-market software teams"
            assert updated_seller_body["updated_by_user_id"] == seller_body["created_by_user_id"]

            create_icp_response = await client.post(
                f"/api/v1/tenants/{tenant_id}/icp-profiles",
                json={
                    "seller_profile_id": seller_body["seller_profile_id"],
                    "name": "Primary ICP",
                    "criteria_json": {
                        "industries": ["software"],
                        "company_size_guidance": "50-500 employees",
                    },
                },
            )
            assert create_icp_response.status_code == 201
            icp_body = create_icp_response.json()
            assert icp_body["seller_profile_id"] == seller_body["seller_profile_id"]
            assert icp_body["status"] == "draft"

            update_icp_response = await client.patch(
                f"/api/v1/tenants/{tenant_id}/icp-profiles/{icp_body['icp_profile_id']}",
                json={
                    "status": "active",
                    "exclusions_json": {"geography": ["antarctica"]},
                },
            )
            assert update_icp_response.status_code == 200
            updated_icp_body = update_icp_response.json()
            assert updated_icp_body["status"] == "active"
            assert updated_icp_body["exclusions_json"] == {"geography": ["antarctica"]}
            assert updated_icp_body["updated_by_user_id"] == icp_body["created_by_user_id"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_setup_routes_reject_invalid_icp_input_and_reviewer_edits(
    db_engine: AsyncEngine,
) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    async with session_factory() as session:
        user_repository = UserRepository(session)
        tenant_repository = TenantRepository(session)
        membership_repository = MembershipRepository(session)
        owner = await user_repository.create(external_auth_subject="owner-subject")
        reviewer = await user_repository.create(external_auth_subject="reviewer-subject")
        tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
        await membership_repository.create(tenant_id=tenant.id, user_id=owner.id, role="owner")
        await membership_repository.create(
            tenant_id=tenant.id,
            user_id=reviewer.id,
            role="reviewer",
        )
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            reviewer_response = await client.post(
                f"/api/v1/tenants/{tenant.id}/seller-profiles",
                json={
                    "name": "Blocked Seller",
                    "company_name": "Blocked Company",
                    "product_summary": "Blocked summary",
                    "value_proposition": "Blocked value",
                },
                headers={"Authorization": "Bearer reviewer-subject"},
            )
            assert reviewer_response.status_code == 403
            assert reviewer_response.json()["error_code"] == "tenant_membership_required"

            invalid_icp_response = await client.post(
                f"/api/v1/tenants/{tenant.id}/icp-profiles",
                json={
                    "seller_profile_id": str(uuid4()),
                    "name": "Invalid ICP",
                    "criteria_json": {"industries": []},
                },
                headers={"Authorization": "Bearer owner-subject"},
            )
            assert invalid_icp_response.status_code == 404
            assert invalid_icp_response.json()["error_code"] == "resource_not_found"
    finally:
        app.dependency_overrides.clear()
