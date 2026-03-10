"""create seller_profiles and query_objects tables

Revision ID: b3001
Revises: b2001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3001"
down_revision: Union[str, None] = "b2001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_profiles",
        sa.Column("seller_id", sa.String(), nullable=False),
        sa.Column("offer_what", sa.Text(), nullable=False),
        sa.Column("offer_where", postgresql.JSONB(), nullable=False),
        sa.Column("offer_who", postgresql.JSONB(), nullable=False),
        sa.Column("offer_positioning", postgresql.JSONB(), nullable=False),
        sa.Column("constraints_avoid_claims", postgresql.JSONB(), nullable=False),
        sa.Column("constraints_allowed_channels", postgresql.JSONB(), nullable=False),
        sa.Column("constraints_languages", postgresql.JSONB(), nullable=False),
        sa.Column("policy_pack_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("seller_id"),
    )
    op.create_table(
        "query_objects",
        sa.Column("query_object_id", sa.String(), nullable=False),
        sa.Column("seller_id", sa.String(), nullable=False),
        sa.Column("buyer_context", sa.Text(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("keywords", postgresql.JSONB(), nullable=False),
        sa.Column("exclusions", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["seller_id"], ["seller_profiles.seller_id"]),
        sa.PrimaryKeyConstraint("query_object_id"),
    )
    op.create_index("ix_query_objects_seller_id", "query_objects", ["seller_id"])


def downgrade() -> None:
    op.drop_index("ix_query_objects_seller_id", table_name="query_objects")
    op.drop_table("query_objects")
    op.drop_table("seller_profiles")
