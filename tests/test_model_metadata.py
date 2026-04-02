from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from app.db.base import Base
from app.models import (
    Account,
    AccountResearchSnapshot,
    ApprovalDecision,
    Artifact,
    Contact,
    ConversationMessage,
    ConversationThread,
    ICPProfile,
    RunEvent,
    SellerProfile,
    SourceEvidence,
    Tenant,
    TenantMembership,
    User,
    WorkflowRun,
)


def _check_constraints(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.sqltext.text
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _foreign_key_rules(table_name: str) -> dict[tuple[str, ...], str | None]:
    return {
        tuple(element.parent.name for element in constraint.elements): constraint.ondelete
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _unique_constraints(table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint.columns.keys())
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _unique_indexes(table_name: str) -> dict[str, tuple[str, ...]]:
    return {
        index.name: tuple(index.columns.keys())
        for index in Base.metadata.tables[table_name].indexes
        if isinstance(index, Index) and index.unique
    }


def test_phase_1_tables_are_registered_in_metadata() -> None:
    table_names = set(Base.metadata.tables)

    assert {
        "users",
        "tenants",
        "tenant_memberships",
        "seller_profiles",
        "icp_profiles",
        "conversation_threads",
        "conversation_messages",
        "workflow_runs",
        "run_events",
        "accounts",
        "account_research_snapshots",
        "contacts",
        "source_evidence",
        "artifacts",
        "approval_decisions",
    } <= table_names


def test_expected_phase_1_columns_exist() -> None:
    assert {"id", "external_auth_subject", "email", "display_name", "status", "created_at", "updated_at"} <= set(
        User.__table__.c.keys()
    )
    assert {"id", "name", "slug", "status", "created_at", "updated_at"} <= set(Tenant.__table__.c.keys())
    assert {"id", "tenant_id", "user_id", "role", "status", "created_at", "updated_at"} <= set(
        TenantMembership.__table__.c.keys()
    )
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
    assert {
        "id",
        "tenant_id",
        "created_by_user_id",
        "seller_profile_id",
        "active_workflow",
        "status",
        "current_run_id",
        "summary_text",
        "created_at",
        "updated_at",
    } <= set(ConversationThread.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "thread_id",
        "run_id",
        "role",
        "message_type",
        "content_text",
        "created_by_user_id",
        "created_at",
    } <= set(ConversationMessage.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "thread_id",
        "created_by_user_id",
        "workflow_type",
        "status",
        "status_detail",
        "requested_payload_json",
        "normalized_result_json",
        "error_code",
        "correlation_id",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    } <= set(WorkflowRun.__table__.c.keys())
    assert {"id", "tenant_id", "run_id", "event_name", "payload_json", "created_at"} <= set(
        RunEvent.__table__.c.keys()
    )
    assert {
        "id",
        "tenant_id",
        "created_by_user_id",
        "updated_by_user_id",
        "source_workflow_run_id",
        "name",
        "domain",
        "normalized_domain",
        "linkedin_url",
        "hq_location",
        "employee_range",
        "industry",
        "status",
        "fit_summary",
        "fit_signals_json",
        "canonical_data_json",
        "created_at",
        "updated_at",
    } <= set(Account.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "account_id",
        "workflow_run_id",
        "created_by_user_id",
        "snapshot_version",
        "research_summary",
        "qualification_summary",
        "uncertainty_notes",
        "research_json",
        "created_at",
    } <= set(AccountResearchSnapshot.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "account_id",
        "created_by_user_id",
        "updated_by_user_id",
        "full_name",
        "job_title",
        "email",
        "linkedin_url",
        "phone",
        "status",
        "ranking_summary",
        "person_data_json",
        "created_at",
        "updated_at",
    } <= set(Contact.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "workflow_run_id",
        "account_id",
        "contact_id",
        "source_type",
        "provider_name",
        "source_url",
        "title",
        "snippet_text",
        "captured_at",
        "freshness_at",
        "confidence_score",
        "metadata_json",
        "created_at",
    } <= set(SourceEvidence.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "workflow_run_id",
        "created_by_user_id",
        "artifact_type",
        "format",
        "title",
        "content_markdown",
        "content_json",
        "storage_url",
        "created_at",
        "updated_at",
    } <= set(Artifact.__table__.c.keys())
    assert {
        "id",
        "tenant_id",
        "workflow_run_id",
        "artifact_id",
        "reviewed_by_user_id",
        "decision",
        "rationale",
        "reviewed_at",
        "created_at",
    } <= set(ApprovalDecision.__table__.c.keys())


def test_phase_1_unique_constraints_and_indexes_exist() -> None:
    assert ("external_auth_subject",) in _unique_constraints("users")
    assert ("slug",) in _unique_constraints("tenants")
    assert ("tenant_id", "user_id") in _unique_constraints("tenant_memberships")

    workflow_indexes = _unique_indexes("workflow_runs")
    account_indexes = _unique_indexes("accounts")

    assert workflow_indexes["uq_workflow_runs_tenant_correlation_id"] == ("tenant_id", "correlation_id")
    assert account_indexes["uq_accounts_tenant_normalized_domain"] == ("tenant_id", "normalized_domain")


def test_phase_1_status_and_contract_checks_exist() -> None:
    assert "status IN ('active', 'disabled')" in _check_constraints("users")
    assert "status IN ('active', 'suspended')" in _check_constraints("tenants")
    membership_checks = _check_constraints("tenant_memberships")
    assert "role IN ('owner', 'admin', 'member', 'reviewer')" in membership_checks
    assert "status IN ('active', 'invited', 'disabled')" in membership_checks
    assert "source_status IN ('manual', 'imported', 'generated')" in _check_constraints("seller_profiles")
    assert "status IN ('draft', 'active', 'archived')" in _check_constraints("icp_profiles")

    thread_checks = _check_constraints("conversation_threads")
    assert "status IN ('active', 'closed')" in thread_checks
    assert (
        "active_workflow IN ('seller_profile_setup', 'icp_profile_setup', 'account_search', 'account_research', 'contact_search')"
        in thread_checks
    )

    message_checks = _check_constraints("conversation_messages")
    assert "role IN ('user', 'assistant', 'system')" in message_checks
    assert "message_type IN ('user_turn', 'assistant_reply', 'system_note', 'workflow_status')" in message_checks
    assert "message_type <> 'user_turn' OR created_by_user_id IS NOT NULL" in message_checks
    assert "message_type <> 'user_turn' OR run_id IS NULL" in message_checks

    workflow_run_checks = _check_constraints("workflow_runs")
    assert (
        "workflow_type IN ('seller_profile_setup', 'icp_profile_setup', 'account_search', 'account_research', 'contact_search')"
        in workflow_run_checks
    )
    assert "status IN ('queued', 'running', 'awaiting_review', 'succeeded', 'failed', 'cancelled')" in workflow_run_checks

    assert (
        "event_name IN ('run.started', 'agent.handoff', 'agent.completed', 'tool.started', 'tool.completed', 'tool.failed', 'reasoning.validated', 'reasoning.failed_validation', 'candidate.accepted', 'candidate.rejected', 'provider.routing_decision', 'run.awaiting_review', 'run.completed', 'run.failed')"
        in _check_constraints("run_events")
    )

    artifact_checks = _check_constraints("artifacts")
    assert (
        "artifact_type IN ('research_brief', 'seller_summary', 'icp_summary', 'run_summary', 'review_packet', 'outreach_draft')"
        in artifact_checks
    )
    assert "format IN ('markdown', 'json', 'external_pointer')" in artifact_checks
    assert (
        "((format = 'markdown' AND content_markdown IS NOT NULL) OR (format = 'json' AND content_json IS NOT NULL) OR (format = 'external_pointer' AND storage_url IS NOT NULL))"
        in artifact_checks
    )

    approval_checks = _check_constraints("approval_decisions")
    assert "decision IN ('approved', 'rejected', 'needs_changes')" in approval_checks
    assert "decision = 'approved' OR rationale IS NOT NULL" in approval_checks


def test_json_fields_use_jsonb() -> None:
    assert isinstance(SellerProfile.__table__.c.profile_json.type, JSONB)
    assert isinstance(ICPProfile.__table__.c.criteria_json.type, JSONB)
    assert isinstance(ICPProfile.__table__.c.exclusions_json.type, JSONB)
    assert isinstance(WorkflowRun.__table__.c.requested_payload_json.type, JSONB)
    assert isinstance(WorkflowRun.__table__.c.normalized_result_json.type, JSONB)
    assert isinstance(RunEvent.__table__.c.payload_json.type, JSONB)
    assert isinstance(Account.__table__.c.fit_signals_json.type, JSONB)
    assert isinstance(Account.__table__.c.canonical_data_json.type, JSONB)
    assert isinstance(AccountResearchSnapshot.__table__.c.research_json.type, JSONB)
    assert isinstance(Contact.__table__.c.person_data_json.type, JSONB)
    assert isinstance(SourceEvidence.__table__.c.metadata_json.type, JSONB)
    assert isinstance(Artifact.__table__.c.content_json.type, JSONB)


def test_phase_1_foreign_keys_match_expected_delete_rules() -> None:
    membership_fk_rules = _foreign_key_rules("tenant_memberships")
    seller_fk_rules = _foreign_key_rules("seller_profiles")
    icp_fk_rules = _foreign_key_rules("icp_profiles")
    thread_fk_rules = _foreign_key_rules("conversation_threads")
    message_fk_rules = _foreign_key_rules("conversation_messages")
    workflow_run_fk_rules = _foreign_key_rules("workflow_runs")
    run_event_fk_rules = _foreign_key_rules("run_events")
    account_fk_rules = _foreign_key_rules("accounts")
    snapshot_fk_rules = _foreign_key_rules("account_research_snapshots")
    contact_fk_rules = _foreign_key_rules("contacts")
    evidence_fk_rules = _foreign_key_rules("source_evidence")
    artifact_fk_rules = _foreign_key_rules("artifacts")
    approval_fk_rules = _foreign_key_rules("approval_decisions")

    assert membership_fk_rules[("tenant_id",)] == "RESTRICT"
    assert membership_fk_rules[("user_id",)] == "RESTRICT"
    assert seller_fk_rules[("tenant_id",)] == "RESTRICT"
    assert seller_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert seller_fk_rules[("updated_by_user_id",)] == "SET NULL"
    assert icp_fk_rules[("tenant_id",)] == "RESTRICT"
    assert icp_fk_rules[("seller_profile_id",)] == "RESTRICT"
    assert icp_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert icp_fk_rules[("updated_by_user_id",)] == "SET NULL"

    assert thread_fk_rules[("tenant_id",)] == "RESTRICT"
    assert thread_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert thread_fk_rules[("seller_profile_id",)] == "RESTRICT"
    assert thread_fk_rules[("current_run_id",)] == "SET NULL"

    assert message_fk_rules[("tenant_id",)] == "RESTRICT"
    assert message_fk_rules[("thread_id",)] == "RESTRICT"
    assert message_fk_rules[("run_id",)] == "SET NULL"
    assert message_fk_rules[("created_by_user_id",)] == "SET NULL"

    assert workflow_run_fk_rules[("tenant_id",)] == "RESTRICT"
    assert workflow_run_fk_rules[("thread_id",)] == "RESTRICT"
    assert workflow_run_fk_rules[("created_by_user_id",)] == "RESTRICT"

    assert run_event_fk_rules[("tenant_id",)] == "RESTRICT"
    assert run_event_fk_rules[("run_id",)] == "RESTRICT"

    assert account_fk_rules[("tenant_id",)] == "RESTRICT"
    assert account_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert account_fk_rules[("updated_by_user_id",)] == "SET NULL"
    assert account_fk_rules[("source_workflow_run_id",)] == "RESTRICT"

    assert snapshot_fk_rules[("tenant_id",)] == "RESTRICT"
    assert snapshot_fk_rules[("account_id",)] == "RESTRICT"
    assert snapshot_fk_rules[("workflow_run_id",)] == "RESTRICT"
    assert snapshot_fk_rules[("created_by_user_id",)] == "RESTRICT"

    assert contact_fk_rules[("tenant_id",)] == "RESTRICT"
    assert contact_fk_rules[("account_id",)] == "RESTRICT"
    assert contact_fk_rules[("created_by_user_id",)] == "RESTRICT"
    assert contact_fk_rules[("updated_by_user_id",)] == "SET NULL"

    assert evidence_fk_rules[("tenant_id",)] == "RESTRICT"
    assert evidence_fk_rules[("workflow_run_id",)] == "RESTRICT"
    assert evidence_fk_rules[("account_id",)] == "SET NULL"
    assert evidence_fk_rules[("contact_id",)] == "SET NULL"

    assert artifact_fk_rules[("tenant_id",)] == "RESTRICT"
    assert artifact_fk_rules[("workflow_run_id",)] == "SET NULL"
    assert artifact_fk_rules[("created_by_user_id",)] == "SET NULL"

    assert approval_fk_rules[("tenant_id",)] == "RESTRICT"
    assert approval_fk_rules[("workflow_run_id",)] == "RESTRICT"
    assert approval_fk_rules[("artifact_id",)] == "SET NULL"
    assert approval_fk_rules[("reviewed_by_user_id",)] == "RESTRICT"
