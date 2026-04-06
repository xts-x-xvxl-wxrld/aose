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
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.tenancy import TenancyService

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
async def test_create_tenant_provisions_owner_membership(db_session: AsyncSession) -> None:
    service = TenancyService(db_session)

    tenant, membership = await service.create_tenant(
        identity=AuthIdentity(
            external_auth_subject="subject-owner",
            email="owner@example.com",
            display_name="Owner",
        ),
        tenant_name="Acme Workspace",
        tenant_slug="Acme Workspace",
        self_serve_enabled=True,
    )

    memberships = await service.list_user_tenants(
        identity=AuthIdentity(
            external_auth_subject="subject-owner",
            email="owner@example.com",
            display_name="Owner",
        )
    )

    assert tenant.name == "Acme Workspace"
    assert tenant.slug == "acme-workspace"
    assert membership.role == "owner"
    assert membership.status == "active"
    assert len(memberships) == 1
    assert memberships[0][0].id == membership.id
    assert memberships[0][1].id == tenant.id


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_owner_can_create_member_from_existing_email(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    service = TenancyService(db_session)

    owner = await user_repository.create(
        external_auth_subject="subject-owner",
        email="owner@example.com",
        display_name="Owner",
    )
    invitee = await user_repository.create(
        external_auth_subject="subject-member",
        email="member@example.com",
        display_name="Member",
    )
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    await membership_repository.create(tenant_id=tenant.id, user_id=owner.id, role="owner")
    await db_session.commit()

    membership, user = await service.create_member(
        identity=AuthIdentity(
            external_auth_subject="subject-owner",
            email="owner@example.com",
            display_name="Owner",
        ),
        tenant_id=tenant.id,
        target_user_id=None,
        target_email="member@example.com",
        role="member",
    )

    assert membership.user_id == invitee.id
    assert membership.role == "member"
    assert user.id == invitee.id


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_admin_cannot_disable_owner_membership(db_session: AsyncSession) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    service = TenancyService(db_session)

    owner = await user_repository.create(
        external_auth_subject="subject-owner",
        email="owner@example.com",
    )
    admin = await user_repository.create(
        external_auth_subject="subject-admin",
        email="admin@example.com",
    )
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    owner_membership = await membership_repository.create(
        tenant_id=tenant.id,
        user_id=owner.id,
        role="owner",
    )
    await membership_repository.create(tenant_id=tenant.id, user_id=admin.id, role="admin")
    await db_session.commit()

    with pytest.raises(ServiceError) as exc_info:
        await service.update_member(
            identity=AuthIdentity(
                external_auth_subject="subject-admin",
                email="admin@example.com",
                display_name="Admin",
            ),
            tenant_id=tenant.id,
            membership_id=owner_membership.id,
            role=None,
            status="disabled",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ownership_conflict"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_transfer_ownership_demotes_actor_and_promotes_target(
    db_session: AsyncSession,
) -> None:
    user_repository = UserRepository(db_session)
    tenant_repository = TenantRepository(db_session)
    membership_repository = MembershipRepository(db_session)
    service = TenancyService(db_session)

    owner = await user_repository.create(
        external_auth_subject="subject-owner",
        email="owner@example.com",
    )
    target = await user_repository.create(
        external_auth_subject="subject-target",
        email="target@example.com",
    )
    tenant = await tenant_repository.create(name="Tenant One", slug="tenant-one")
    owner_membership = await membership_repository.create(
        tenant_id=tenant.id,
        user_id=owner.id,
        role="owner",
    )
    target_membership = await membership_repository.create(
        tenant_id=tenant.id,
        user_id=target.id,
        role="member",
    )
    await db_session.commit()

    previous_owner, new_owner = await service.transfer_ownership(
        identity=AuthIdentity(
            external_auth_subject="subject-owner",
            email="owner@example.com",
            display_name="Owner",
        ),
        tenant_id=tenant.id,
        target_membership_id=target_membership.id,
    )

    assert previous_owner.id == owner_membership.id
    assert previous_owner.role == "admin"
    assert new_owner.id == target_membership.id
    assert new_owner.role == "owner"
