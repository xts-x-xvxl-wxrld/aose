"""create outreach_drafts and personalization_anchors tables

Revision ID: b8001
Revises: b7001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8001"
down_revision: Union[str, None] = "b7001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outreach_drafts",
        sa.Column("draft_id", sa.String(), nullable=False),
        sa.Column("contact_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("risk_flags_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.contact_id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"]),
        sa.PrimaryKeyConstraint("draft_id"),
    )
    op.create_index("ix_outreach_drafts_contact_id", "outreach_drafts", ["contact_id"])
    op.create_index("ix_outreach_drafts_account_id", "outreach_drafts", ["account_id"])
    op.create_index("ix_outreach_drafts_created_at", "outreach_drafts", ["created_at"])

    op.create_table(
        "personalization_anchors",
        sa.Column("anchor_key", sa.String(), nullable=False),
        sa.Column("draft_id", sa.String(), nullable=False),
        sa.Column("span", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", postgresql.JSONB(), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["outreach_drafts.draft_id"]),
        sa.PrimaryKeyConstraint("anchor_key"),
    )
    op.create_index(
        "ix_personalization_anchors_draft_id", "personalization_anchors", ["draft_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personalization_anchors_draft_id", table_name="personalization_anchors"
    )
    op.drop_table("personalization_anchors")
    op.drop_index("ix_outreach_drafts_created_at", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_account_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_contact_id", table_name="outreach_drafts")
    op.drop_table("outreach_drafts")
