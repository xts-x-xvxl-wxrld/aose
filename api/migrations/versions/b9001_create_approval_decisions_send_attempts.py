"""create approval_decisions and send_attempts tables

Revision ID: b9001
Revises: b8001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b9001"
down_revision: Union[str, None] = "b8001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_decisions",
        sa.Column("decision_id", sa.String(), nullable=False),
        sa.Column("decision_key", sa.String(), nullable=False),
        sa.Column("draft_id", sa.String(), nullable=False),
        sa.Column("work_item_id", sa.String(), nullable=False),
        sa.Column("contact_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reviewer", sa.String(), nullable=True),
        sa.Column("reviewer_id", sa.String(), nullable=False),
        sa.Column("reviewer_role", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("overridden_gates_json", postgresql.JSONB(), nullable=False),
        sa.Column("policy_pack_id", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('approved', 'rejected', 'needs_rewrite', 'needs_more_evidence')",
            name="ck_approval_decisions_status",
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["outreach_drafts.draft_id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.contact_id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.work_item_id"]),
        sa.PrimaryKeyConstraint("decision_id"),
        sa.UniqueConstraint("decision_key", name="uq_approval_decisions_decision_key"),
    )
    op.create_index(
        "ix_approval_decisions_decision_key", "approval_decisions", ["decision_key"]
    )
    op.create_index(
        "ix_approval_decisions_draft_id", "approval_decisions", ["draft_id"]
    )
    op.create_index(
        "ix_approval_decisions_contact_id", "approval_decisions", ["contact_id"]
    )
    op.create_index(
        "ix_approval_decisions_decided_at", "approval_decisions", ["decided_at"]
    )

    op.create_table(
        "send_attempts",
        sa.Column("send_id", sa.String(), nullable=False),
        sa.Column("draft_id", sa.String(), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("policy_pack_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["outreach_drafts.draft_id"]),
        sa.ForeignKeyConstraint(["decision_id"], ["approval_decisions.decision_id"]),
        sa.PrimaryKeyConstraint("send_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_send_attempts_idempotency_key"),
    )
    op.create_index(
        "ix_send_attempts_idempotency_key", "send_attempts", ["idempotency_key"]
    )
    op.create_index("ix_send_attempts_draft_id", "send_attempts", ["draft_id"])
    op.create_index("ix_send_attempts_decision_id", "send_attempts", ["decision_id"])
    op.create_index("ix_send_attempts_created_at", "send_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_send_attempts_created_at", table_name="send_attempts")
    op.drop_index("ix_send_attempts_decision_id", table_name="send_attempts")
    op.drop_index("ix_send_attempts_draft_id", table_name="send_attempts")
    op.drop_index("ix_send_attempts_idempotency_key", table_name="send_attempts")
    op.drop_table("send_attempts")
    op.drop_index("ix_approval_decisions_decided_at", table_name="approval_decisions")
    op.drop_index("ix_approval_decisions_contact_id", table_name="approval_decisions")
    op.drop_index("ix_approval_decisions_draft_id", table_name="approval_decisions")
    op.drop_index("ix_approval_decisions_decision_key", table_name="approval_decisions")
    op.drop_table("approval_decisions")
