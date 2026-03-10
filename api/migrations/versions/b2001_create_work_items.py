"""create work_items table

Revision ID: b2001
Revises:
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("work_item_id", sa.String(), nullable=False),
        sa.Column("entity_ref_type", sa.String(), nullable=False),
        sa.Column("entity_ref_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("attempt_budget_remaining", sa.Integer(), nullable=False),
        sa.Column("attempt_budget_policy", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("trace_run_id", sa.String(), nullable=False),
        sa.Column("trace_parent_work_item_id", sa.String(), nullable=True),
        sa.Column("trace_correlation_id", sa.String(), nullable=False),
        sa.Column("trace_policy_pack_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("work_item_id"),
    )
    op.create_index("ix_work_items_stage", "work_items", ["stage"])
    op.create_index("ix_work_items_idempotency_key", "work_items", ["idempotency_key"])
    op.create_index(
        "ix_work_items_entity_ref",
        "work_items",
        ["entity_ref_type", "entity_ref_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_work_items_entity_ref", table_name="work_items")
    op.drop_index("ix_work_items_idempotency_key", table_name="work_items")
    op.drop_index("ix_work_items_stage", table_name="work_items")
    op.drop_table("work_items")
