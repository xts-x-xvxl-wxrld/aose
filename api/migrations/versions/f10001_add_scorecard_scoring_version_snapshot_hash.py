"""add scoring_version and evidence_snapshot_hash to scorecards

Revision ID: f10001
Revises: c4001
Create Date: 2026-03-09

Implements Epic F1 scorecard shape extensions.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f10001"
down_revision: Union[str, None] = "c4001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column(
            "scoring_version",
            sa.String(),
            nullable=False,
            server_default="fit_intent_rules_v0_1",
        ),
    )
    op.add_column(
        "scorecards",
        sa.Column(
            "evidence_snapshot_hash",
            sa.String(),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column("scorecards", "scoring_version", server_default=None)
    op.alter_column("scorecards", "evidence_snapshot_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("scorecards", "evidence_snapshot_hash")
    op.drop_column("scorecards", "scoring_version")
