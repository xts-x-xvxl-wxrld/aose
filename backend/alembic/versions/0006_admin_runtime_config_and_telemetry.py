"""admin runtime config and telemetry

Revision ID: 0006_admin_runtime_cfg
Revises: 0005_phase3_run_event_taxonomy
Create Date: 2026-04-06 03:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0006_admin_runtime_cfg"
down_revision: str | None = "0005_phase3_run_event_taxonomy"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("config_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "agent_config_versions",
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("model_settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("feature_flags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scope_type IN ('global', 'tenant')", name=op.f("ck_agent_config_versions_scope_type_allowed")),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name=op.f("ck_agent_config_versions_status_allowed")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_agent_config_versions_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_agent_config_versions_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_config_versions")),
    )
    op.create_index(op.f("ix_agent_config_versions_agent_name"), "agent_config_versions", ["agent_name"], unique=False)
    op.create_index(op.f("ix_agent_config_versions_created_by_user_id"), "agent_config_versions", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_agent_config_versions_tenant_id"), "agent_config_versions", ["tenant_id"], unique=False)
    op.create_index(
        "uq_agent_config_scope_agent_version",
        "agent_config_versions",
        ["scope_type", "tenant_id", "agent_name", "version"],
        unique=True,
    )

    op.create_table(
        "admin_audit_logs",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_admin_audit_logs_actor_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_admin_audit_logs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_logs")),
    )
    op.create_index(op.f("ix_admin_audit_logs_action"), "admin_audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_admin_audit_logs_actor_user_id"), "admin_audit_logs", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_admin_audit_logs_request_id"), "admin_audit_logs", ["request_id"], unique=False)
    op.create_index(op.f("ix_admin_audit_logs_tenant_id"), "admin_audit_logs", ["tenant_id"], unique=False)

    op.create_table(
        "llm_call_logs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=True),
        sa.Column("workflow_type", sa.String(length=64), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schema_hint", sa.String(length=128), nullable=True),
        sa.Column("request_profile", sa.String(length=128), nullable=True),
        sa.Column("input_excerpt", sa.String(length=2000), nullable=True),
        sa.Column("output_excerpt", sa.String(length=2000), nullable=True),
        sa.Column("input_hash", sa.String(length=128), nullable=True),
        sa.Column("output_hash", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("raw_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_micros", sa.BigInteger(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'failed')", name=op.f("ck_llm_call_logs_status_allowed")),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], name=op.f("fk_llm_call_logs_run_id_workflow_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_llm_call_logs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"], name=op.f("fk_llm_call_logs_thread_id_conversation_threads"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call_logs")),
    )
    op.create_index(op.f("ix_llm_call_logs_agent_name"), "llm_call_logs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_model_name"), "llm_call_logs", ["model_name"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_provider_name"), "llm_call_logs", ["provider_name"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_run_id"), "llm_call_logs", ["run_id"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_tenant_id"), "llm_call_logs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_thread_id"), "llm_call_logs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_workflow_type"), "llm_call_logs", ["workflow_type"], unique=False)

    op.create_table(
        "tool_call_logs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=True),
        sa.Column("workflow_type", sa.String(length=64), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("correlation_key", sa.String(length=255), nullable=True),
        sa.Column("input_excerpt", sa.String(length=2000), nullable=True),
        sa.Column("output_excerpt", sa.String(length=2000), nullable=True),
        sa.Column("input_hash", sa.String(length=128), nullable=True),
        sa.Column("output_hash", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("raw_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('started', 'completed', 'failed')", name=op.f("ck_tool_call_logs_status_allowed")),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], name=op.f("fk_tool_call_logs_run_id_workflow_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_tool_call_logs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"], name=op.f("fk_tool_call_logs_thread_id_conversation_threads"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_call_logs")),
    )
    op.create_index(op.f("ix_tool_call_logs_agent_name"), "tool_call_logs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_correlation_key"), "tool_call_logs", ["correlation_key"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_provider_name"), "tool_call_logs", ["provider_name"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_run_id"), "tool_call_logs", ["run_id"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_tenant_id"), "tool_call_logs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_thread_id"), "tool_call_logs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_tool_name"), "tool_call_logs", ["tool_name"], unique=False)
    op.create_index(op.f("ix_tool_call_logs_workflow_type"), "tool_call_logs", ["workflow_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tool_call_logs_workflow_type"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_tool_name"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_thread_id"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_tenant_id"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_run_id"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_provider_name"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_correlation_key"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_tool_call_logs_agent_name"), table_name="tool_call_logs")
    op.drop_table("tool_call_logs")

    op.drop_index(op.f("ix_llm_call_logs_workflow_type"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_thread_id"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_tenant_id"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_run_id"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_provider_name"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_model_name"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_agent_name"), table_name="llm_call_logs")
    op.drop_table("llm_call_logs")

    op.drop_index(op.f("ix_admin_audit_logs_tenant_id"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_request_id"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_actor_user_id"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_action"), table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")

    op.drop_index("uq_agent_config_scope_agent_version", table_name="agent_config_versions")
    op.drop_index(op.f("ix_agent_config_versions_tenant_id"), table_name="agent_config_versions")
    op.drop_index(op.f("ix_agent_config_versions_created_by_user_id"), table_name="agent_config_versions")
    op.drop_index(op.f("ix_agent_config_versions_agent_name"), table_name="agent_config_versions")
    op.drop_table("agent_config_versions")

    op.drop_column("workflow_runs", "config_snapshot_json")
    op.drop_column("users", "is_platform_admin")
