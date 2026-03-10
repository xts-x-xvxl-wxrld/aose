"""add policy_pack_id to scorecards; unique constraint on work_items.idempotency_key

Revision ID: b10001
Revises: b9001
Create Date: 2026-03-08

Fixes BR-N1 (Scorecard missing policy_pack_id) and BR-N2 (WorkItem
idempotency_key lacks DB-level uniqueness enforcement).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b10001"
down_revision: Union[str, None] = "b9001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BR-N2: enforce idempotency_key uniqueness at the DB level on work_items
    op.create_unique_constraint(
        "uq_work_items_idempotency_key", "work_items", ["idempotency_key"]
    )

    # BR-N1: add policy_pack_id to scorecards
    # server_default used only during the ALTER so existing rows get a value;
    # it is removed immediately after so the column has no default going forward.
    op.add_column(
        "scorecards",
        sa.Column(
            "policy_pack_id",
            sa.String(),
            nullable=False,
            server_default="safe_v0_1",
        ),
    )
    op.alter_column("scorecards", "policy_pack_id", server_default=None)


def downgrade() -> None:
    op.drop_column("scorecards", "policy_pack_id")
    op.drop_constraint("uq_work_items_idempotency_key", "work_items", type_="unique")
