"""add phase 1 persistence and artifact tables

Revision ID: 0002_phase1_persistence
Revises: 0001_phase1_identity_setup
Create Date: 2026-03-31 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_phase1_persistence"
down_revision = "0001_phase1_identity_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("active_workflow", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("current_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'closed')", name=op.f("ck_conversation_threads_status_allowed")),
        sa.CheckConstraint(
            "active_workflow IN ('seller_profile_setup', 'icp_profile_setup', 'account_search', 'account_research', 'contact_search')",
            name=op.f("ck_conversation_threads_active_workflow_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_conversation_threads_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_conversation_threads_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seller_profile_id"],
            ["seller_profiles.id"],
            name=op.f("fk_conversation_threads_seller_profile_id_seller_profiles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_threads")),
    )
    op.create_index(
        op.f("ix_conversation_threads_tenant_id"),
        "conversation_threads",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_threads_seller_profile_id"),
        "conversation_threads",
        ["seller_profile_id"],
        unique=False,
    )

    op.create_table(
        "workflow_runs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("requested_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "workflow_type IN ('seller_profile_setup', 'icp_profile_setup', 'account_search', 'account_research', 'contact_search')",
            name=op.f("ck_workflow_runs_workflow_type_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_review', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_workflow_runs_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_workflow_runs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            name=op.f("fk_workflow_runs_thread_id_conversation_threads"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_workflow_runs_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(op.f("ix_workflow_runs_tenant_id"), "workflow_runs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_workflow_runs_thread_id"), "workflow_runs", ["thread_id"], unique=False)
    op.create_index(
        "uq_workflow_runs_tenant_correlation_id",
        "workflow_runs",
        ["tenant_id", "correlation_id"],
        unique=True,
        postgresql_where=sa.text("correlation_id IS NOT NULL"),
    )

    op.create_foreign_key(
        op.f("fk_conversation_threads_current_run_id_workflow_runs"),
        "conversation_threads",
        "workflow_runs",
        ["current_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "conversation_messages",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name=op.f("ck_conversation_messages_role_allowed"),
        ),
        sa.CheckConstraint(
            "message_type IN ('user_turn', 'assistant_reply', 'system_note', 'workflow_status')",
            name=op.f("ck_conversation_messages_message_type_allowed"),
        ),
        sa.CheckConstraint(
            "message_type <> 'user_turn' OR created_by_user_id IS NOT NULL",
            name=op.f("ck_conversation_messages_user_turn_requires_creator"),
        ),
        sa.CheckConstraint(
            "message_type <> 'user_turn' OR run_id IS NULL",
            name=op.f("ck_conversation_messages_user_turn_run_id_null"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_conversation_messages_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            name=op.f("fk_conversation_messages_thread_id_conversation_threads"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_conversation_messages_run_id_workflow_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_conversation_messages_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_messages")),
    )
    op.create_index(op.f("ix_conversation_messages_tenant_id"), "conversation_messages", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_conversation_messages_thread_id"), "conversation_messages", ["thread_id"], unique=False)
    op.create_index(op.f("ix_conversation_messages_run_id"), "conversation_messages", ["run_id"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "event_name IN ('run.started', 'agent.handoff', 'agent.completed', 'tool.started', 'tool.completed', 'run.awaiting_review', 'run.completed', 'run.failed')",
            name=op.f("ck_run_events_event_name_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_run_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_run_events_run_id_workflow_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_events")),
    )
    op.create_index(op.f("ix_run_events_tenant_id"), "run_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_run_events_run_id"), "run_events", ["run_id"], unique=False)

    op.create_table(
        "accounts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_workflow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("normalized_domain", sa.String(length=255), nullable=True),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column("hq_location", sa.String(length=255), nullable=True),
        sa.Column("employee_range", sa.String(length=128), nullable=True),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fit_summary", sa.Text(), nullable=True),
        sa.Column("fit_signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("canonical_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_accounts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_accounts_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_accounts_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_accounts_source_workflow_run_id_workflow_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
    )
    op.create_index(op.f("ix_accounts_tenant_id"), "accounts", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_accounts_source_workflow_run_id"),
        "accounts",
        ["source_workflow_run_id"],
        unique=False,
    )
    op.create_index(
        "uq_accounts_tenant_normalized_domain",
        "accounts",
        ["tenant_id", "normalized_domain"],
        unique=True,
        postgresql_where=sa.text("normalized_domain IS NOT NULL"),
    )

    op.create_table(
        "account_research_snapshots",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("research_summary", sa.Text(), nullable=True),
        sa.Column("qualification_summary", sa.Text(), nullable=True),
        sa.Column("uncertainty_notes", sa.Text(), nullable=True),
        sa.Column("research_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_account_research_snapshots_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_research_snapshots_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_account_research_snapshots_workflow_run_id_workflow_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_account_research_snapshots_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_research_snapshots")),
    )
    op.create_index(
        op.f("ix_account_research_snapshots_tenant_id"),
        "account_research_snapshots",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_research_snapshots_account_id"),
        "account_research_snapshots",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_research_snapshots_workflow_run_id"),
        "account_research_snapshots",
        ["workflow_run_id"],
        unique=False,
    )

    op.create_table(
        "contacts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ranking_summary", sa.Text(), nullable=True),
        sa.Column("person_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_contacts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_contacts_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_contacts_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_contacts_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index(op.f("ix_contacts_tenant_id"), "contacts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_contacts_account_id"), "contacts", ["account_id"], unique=False)

    op.create_table(
        "source_evidence",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("snippet_text", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_source_evidence_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_source_evidence_workflow_run_id_workflow_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_source_evidence_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_source_evidence_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_evidence")),
    )
    op.create_index(op.f("ix_source_evidence_tenant_id"), "source_evidence", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_source_evidence_workflow_run_id"),
        "source_evidence",
        ["workflow_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_source_evidence_account_id"), "source_evidence", ["account_id"], unique=False)
    op.create_index(op.f("ix_source_evidence_contact_id"), "source_evidence", ["contact_id"], unique=False)

    op.create_table(
        "artifacts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "artifact_type IN ('research_brief', 'seller_summary', 'icp_summary', 'run_summary', 'review_packet', 'outreach_draft')",
            name=op.f("ck_artifacts_artifact_type_allowed"),
        ),
        sa.CheckConstraint(
            "format IN ('markdown', 'json', 'external_pointer')",
            name=op.f("ck_artifacts_format_allowed"),
        ),
        sa.CheckConstraint(
            "((format = 'markdown' AND content_markdown IS NOT NULL) OR (format = 'json' AND content_json IS NOT NULL) OR (format = 'external_pointer' AND storage_url IS NOT NULL))",
            name=op.f("ck_artifacts_format_content_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_artifacts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_artifacts_workflow_run_id_workflow_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_artifacts_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
    )
    op.create_index(op.f("ix_artifacts_tenant_id"), "artifacts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_artifacts_workflow_run_id"), "artifacts", ["workflow_run_id"], unique=False)

    op.create_table(
        "approval_decisions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'needs_changes')",
            name=op.f("ck_approval_decisions_decision_allowed"),
        ),
        sa.CheckConstraint(
            "decision = 'approved' OR rationale IS NOT NULL",
            name=op.f("ck_approval_decisions_decision_requires_rationale"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_approval_decisions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_approval_decisions_workflow_run_id_workflow_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_approval_decisions_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_approval_decisions_reviewed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_decisions")),
    )
    op.create_index(op.f("ix_approval_decisions_tenant_id"), "approval_decisions", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_approval_decisions_workflow_run_id"),
        "approval_decisions",
        ["workflow_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_decisions_artifact_id"),
        "approval_decisions",
        ["artifact_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_approval_decisions_artifact_id"), table_name="approval_decisions")
    op.drop_index(op.f("ix_approval_decisions_workflow_run_id"), table_name="approval_decisions")
    op.drop_index(op.f("ix_approval_decisions_tenant_id"), table_name="approval_decisions")
    op.drop_table("approval_decisions")

    op.drop_index(op.f("ix_artifacts_workflow_run_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_tenant_id"), table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index(op.f("ix_source_evidence_contact_id"), table_name="source_evidence")
    op.drop_index(op.f("ix_source_evidence_account_id"), table_name="source_evidence")
    op.drop_index(op.f("ix_source_evidence_workflow_run_id"), table_name="source_evidence")
    op.drop_index(op.f("ix_source_evidence_tenant_id"), table_name="source_evidence")
    op.drop_table("source_evidence")

    op.drop_index(op.f("ix_contacts_account_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_tenant_id"), table_name="contacts")
    op.drop_table("contacts")

    op.drop_index(op.f("ix_account_research_snapshots_workflow_run_id"), table_name="account_research_snapshots")
    op.drop_index(op.f("ix_account_research_snapshots_account_id"), table_name="account_research_snapshots")
    op.drop_index(op.f("ix_account_research_snapshots_tenant_id"), table_name="account_research_snapshots")
    op.drop_table("account_research_snapshots")

    op.drop_index("uq_accounts_tenant_normalized_domain", table_name="accounts")
    op.drop_index(op.f("ix_accounts_source_workflow_run_id"), table_name="accounts")
    op.drop_index(op.f("ix_accounts_tenant_id"), table_name="accounts")
    op.drop_table("accounts")

    op.drop_index(op.f("ix_run_events_run_id"), table_name="run_events")
    op.drop_index(op.f("ix_run_events_tenant_id"), table_name="run_events")
    op.drop_table("run_events")

    op.drop_index(op.f("ix_conversation_messages_run_id"), table_name="conversation_messages")
    op.drop_index(op.f("ix_conversation_messages_thread_id"), table_name="conversation_messages")
    op.drop_index(op.f("ix_conversation_messages_tenant_id"), table_name="conversation_messages")
    op.drop_table("conversation_messages")

    op.drop_constraint(
        op.f("fk_conversation_threads_current_run_id_workflow_runs"),
        "conversation_threads",
        type_="foreignkey",
    )
    op.drop_index("uq_workflow_runs_tenant_correlation_id", table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_thread_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_tenant_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index(op.f("ix_conversation_threads_seller_profile_id"), table_name="conversation_threads")
    op.drop_index(op.f("ix_conversation_threads_tenant_id"), table_name="conversation_threads")
    op.drop_table("conversation_threads")
