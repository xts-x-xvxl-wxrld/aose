"""add accounts confidence check and outreach_drafts policy_pack_id

Revision ID: h1002
Revises: h1001
Create Date: 2026-03-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h1002"
down_revision: Union[str, None] = "h1001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_accounts_confidence_range",
        "accounts",
        "confidence >= 0.0 AND confidence <= 1.0",
    )
    op.add_column(
        "outreach_drafts",
        sa.Column(
            "policy_pack_id",
            sa.String(),
            nullable=False,
            server_default="safe_v0_1",
        ),
    )
    op.alter_column("outreach_drafts", "policy_pack_id", server_default=None)


def downgrade() -> None:
    op.drop_column("outreach_drafts", "policy_pack_id")
    op.drop_constraint("ck_accounts_confidence_range", "accounts", type_="check")
