from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.db.base import Base
from app.models import ICPProfile, SellerProfile, Tenant, TenantMembership, User


def _check_constraints(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.sqltext.text
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_phase_1_tables_are_registered_in_metadata() -> None:
    table_names = set(Base.metadata.tables)

    assert {"users", "tenants", "tenant_memberships", "seller_profiles", "icp_profiles"} <= table_names


def test_expected_phase_1_columns_exist() -> None:
    assert {"id", "external_auth_subject", "email", "display_name", "status", "created_at", "updated_at"} <= set(User.__table__.c.keys())
    assert {"id", "name", "slug", "status", "created_at", "updated_at"} <= set(Tenant.__table__.c.keys())
    assert {"id", "tenant_id", "user_id", "role", "status", "created_at", "updated_at"} <= set(TenantMembership.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "created_by_user_id",
        "updated_by_user_id",
        "name",
        "company_name",
        "company_domain",
        "product_summary",
        "value_proposition",
        "target_market_summary",
        "source_status",
        "profile_json",
        "created_at",
        "updated_at",
    } <= set(SellerProfile.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "seller_profile_id",
        "created_by_user_id",
        "updated_by_user_id",
        "name",
        "status",
        "criteria_json",
        "exclusions_json",
        "created_at",
        "updated_at",
    } <= set(ICPProfile.__table__.c.keys())


def test_phase_1_unique_constraints_exist() -> None:
    user_uniques = {
        tuple(constraint.columns.keys())
        for constraint in User.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    tenant_uniques = {
        tuple(constraint.columns.keys())
        for constraint in Tenant.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    membership_uniques = {
        tuple(constraint.columns.keys())
        for constraint in TenantMembership.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("external_auth_subject",) in user_uniques
    assert ("slug",) in tenant_uniques
    assert ("tenant_id", "user_id") in membership_uniques


def test_phase_1_status_and_role_checks_exist() -> None:
    assert "status IN ('active', 'disabled')" in _check_constraints("users")
    assert "status IN ('active', 'suspended')" in _check_constraints("tenants")
    membership_checks = _check_constraints("tenant_memberships")
    assert "role IN ('owner', 'admin', 'member', 'reviewer')" in membership_checks
    assert "status IN ('active', 'invited', 'disabled')" in membership_checks
    assert "source_status IN ('manual', 'imported', 'generated')" in _check_constraints("seller_profiles")
    assert "status IN ('draft', 'active', 'archived')" in _check_constraints("icp_profiles")


def test_seller_and_icp_json_fields_use_jsonb() -> None:
    assert isinstance(SellerProfile.__table__.c.profile_json.type, JSONB)
    assert isinstance(ICPProfile.__table__.c.criteria_json.type, JSONB)
    assert isinstance(ICPProfile.__table__.c.exclusions_json.type, JSONB)


def test_phase_1_foreign_keys_match_expected_delete_rules() -> None:
    membership_fk_rules = {
        tuple(element.parent.name for element in constraint.elements): constraint.ondelete
        for constraint in TenantMembership.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    seller_fk_rules = {
        tuple(element.parent.name for element in constraint.elements): constraint.ondelete
        for constraint in SellerProfile.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    icp_fk_rules = {
        tuple(element.parent.name for element in constraint.elements): constraint.ondelete
        for constraint in ICPProfile.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }

    assert membership_fk_rules[("tenant_id",)] == "RESTRICT"
    assert membership_fk_rules[("user_id",)] == "RESTRICT"
    assert seller_fk_rules[("tenant_id",)] == "RESTRICT"
    assert seller_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert seller_fk_rules[("updated_by_user_id",)] == "SET NULL"
    assert icp_fk_rules[("tenant_id",)] == "RESTRICT"
    assert icp_fk_rules[("seller_profile_id",)] == "RESTRICT"
    assert icp_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert icp_fk_rules[("updated_by_user_id",)] == "SET NULL"
