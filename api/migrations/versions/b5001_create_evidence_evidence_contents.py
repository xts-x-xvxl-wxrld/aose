"""create evidence_contents and evidence tables

Revision ID: b5001
Revises: b4001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b5001"
down_revision: Union[str, None] = "b4001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # evidence_contents must be created first because evidence.content_ref_id
    # references it.
    op.create_table(
        "evidence_contents",
        sa.Column("evidence_content_id", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("raw_ref_kind", sa.String(), nullable=True),
        sa.Column("raw_ref_id", sa.String(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("evidence_content_id"),
        sa.UniqueConstraint("content_hash", name="uq_evidence_contents_content_hash"),
    )
    op.create_index(
        "ix_evidence_contents_content_hash", "evidence_contents", ["content_hash"]
    )

    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("claim_frame", sa.Text(), nullable=False),
        sa.Column("source_provider", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(), nullable=False),
        sa.Column("content_ref_id", sa.String(), nullable=True),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_evidence_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["content_ref_id"],
            ["evidence_contents.evidence_content_id"],
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index("ix_evidence_canonical_url", "evidence", ["canonical_url"])
    op.create_index("ix_evidence_captured_at", "evidence", ["captured_at"])
    op.create_index("ix_evidence_content_ref_id", "evidence", ["content_ref_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_content_ref_id", table_name="evidence")
    op.drop_index("ix_evidence_captured_at", table_name="evidence")
    op.drop_index("ix_evidence_canonical_url", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_evidence_contents_content_hash", table_name="evidence_contents")
    op.drop_table("evidence_contents")
