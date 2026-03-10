"""create scorecards table

Revision ID: b6001
Revises: b5001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b6001"
down_revision: Union[str, None] = "b5001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scorecards",
        sa.Column("scorecard_id", sa.String(), nullable=False),
        sa.Column("entity_ref_type", sa.String(), nullable=False),
        sa.Column("entity_ref_id", sa.String(), nullable=False),
        sa.Column("fit_score", sa.Float(), nullable=False),
        sa.Column("fit_confidence", sa.Float(), nullable=False),
        sa.Column("fit_reasons_json", postgresql.JSONB(), nullable=False),
        sa.Column("intent_score", sa.Float(), nullable=False),
        sa.Column("intent_confidence", sa.Float(), nullable=False),
        sa.Column("intent_reasons_json", postgresql.JSONB(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "fit_score >= 0.0 AND fit_score <= 1.0",
            name="ck_scorecards_fit_score_range",
        ),
        sa.CheckConstraint(
            "fit_confidence >= 0.0 AND fit_confidence <= 1.0",
            name="ck_scorecards_fit_confidence_range",
        ),
        sa.CheckConstraint(
            "intent_score >= 0.0 AND intent_score <= 1.0",
            name="ck_scorecards_intent_score_range",
        ),
        sa.CheckConstraint(
            "intent_confidence >= 0.0 AND intent_confidence <= 1.0",
            name="ck_scorecards_intent_confidence_range",
        ),
        sa.PrimaryKeyConstraint("scorecard_id"),
    )
    op.create_index(
        "ix_scorecards_entity_ref",
        "scorecards",
        ["entity_ref_type", "entity_ref_id"],
    )
    op.create_index("ix_scorecards_computed_at", "scorecards", ["computed_at"])


def downgrade() -> None:
    op.drop_index("ix_scorecards_computed_at", table_name="scorecards")
    op.drop_index("ix_scorecards_entity_ref", table_name="scorecards")
    op.drop_table("scorecards")
