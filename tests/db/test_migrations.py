from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from .helpers import get_postgres_test_urls


def _reset_database(sync_url: str) -> None:
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _alembic_config(sync_url: str) -> Config:
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", sync_url)
    return config


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
def test_migration_upgrade_creates_phase_1_tables() -> None:
    _async_url, sync_url = get_postgres_test_urls()
    _reset_database(sync_url)

    config = _alembic_config(sync_url)
    command.upgrade(config, "head")

    engine = create_engine(sync_url)
    inspector = inspect(engine)

    assert {"users", "tenants", "tenant_memberships", "seller_profiles", "icp_profiles"} <= set(
        inspector.get_table_names()
    )

    user_unique_columns = {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("users")}
    tenant_unique_columns = {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("tenants")}
    membership_unique_columns = {
        tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("tenant_memberships")
    }
    assert ("external_auth_subject",) in user_unique_columns
    assert ("slug",) in tenant_unique_columns
    assert ("tenant_id", "user_id") in membership_unique_columns

    tenant_membership_indexes = {index["name"] for index in inspector.get_indexes("tenant_memberships")}
    seller_indexes = {index["name"] for index in inspector.get_indexes("seller_profiles")}
    icp_indexes = {index["name"] for index in inspector.get_indexes("icp_profiles")}
    assert "ix_tenant_memberships_tenant_id" in tenant_membership_indexes
    assert "ix_tenant_memberships_user_id" in tenant_membership_indexes
    assert "ix_seller_profiles_company_domain" in seller_indexes
    assert "ix_seller_profiles_tenant_id" in seller_indexes
    assert "ix_icp_profiles_tenant_id" in icp_indexes
    assert "ix_icp_profiles_seller_profile_id" in icp_indexes

    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
def test_migration_downgrade_returns_to_base_state() -> None:
    _async_url, sync_url = get_postgres_test_urls()
    _reset_database(sync_url)

    config = _alembic_config(sync_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(sync_url)
    inspector = inspect(engine)
    assert inspector.get_table_names() == ["alembic_version"]
    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
def test_migration_constraints_reject_invalid_and_duplicate_rows() -> None:
    _async_url, sync_url = get_postgres_test_urls()
    _reset_database(sync_url)

    config = _alembic_config(sync_url)
    command.upgrade(config, "head")

    engine = create_engine(sync_url)
    user_id = uuid4()
    tenant_id = uuid4()
    membership_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, external_auth_subject, status) "
                "VALUES (:user_id, 'subject-1', 'active')"
            ),
            {"user_id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO tenants (id, name, slug, status) "
                "VALUES (:tenant_id, 'Tenant One', 'tenant-one', 'active')"
            ),
            {"tenant_id": tenant_id},
        )
        connection.execute(
            text(
                "INSERT INTO tenant_memberships (id, tenant_id, user_id, role, status) "
                "VALUES (:membership_id, :tenant_id, :user_id, 'owner', 'active')"
            ),
            {"membership_id": membership_id, "tenant_id": tenant_id, "user_id": user_id},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, external_auth_subject, status) "
                    "VALUES (:user_id, 'subject-1', 'active')"
                ),
                {"user_id": uuid4()},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, status) "
                    "VALUES (:tenant_id, 'Tenant Two', 'tenant-one', 'active')"
                ),
                {"tenant_id": uuid4()},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenant_memberships (id, tenant_id, user_id, role, status) "
                    "VALUES (:membership_id, :tenant_id, :user_id, 'owner', 'active')"
                ),
                {"membership_id": uuid4(), "tenant_id": tenant_id, "user_id": user_id},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenant_memberships (id, tenant_id, user_id, role, status) "
                    "VALUES (:membership_id, :tenant_id, :user_id, 'invalid', 'active')"
                ),
                {"membership_id": uuid4(), "tenant_id": tenant_id, "user_id": user_id},
            )

    engine.dispose()
