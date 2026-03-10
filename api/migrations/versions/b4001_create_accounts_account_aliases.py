"""create accounts and account_aliases tables

Revision ID: b4001
Revises: b3001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4001"
down_revision: Union[str, None] = "b3001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_index("ix_accounts_domain", "accounts", ["domain"])

    op.create_table(
        "account_aliases",
        sa.Column("account_alias_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("alias_type", sa.String(), nullable=False),
        sa.Column("alias_value", sa.Text(), nullable=False),
        sa.Column("source_provider", sa.String(), nullable=True),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"]),
        sa.PrimaryKeyConstraint("account_alias_id"),
        sa.UniqueConstraint(
            "account_id",
            "alias_type",
            "alias_value",
            name="uq_account_aliases_account_type_value",
        ),
    )
    op.create_index("ix_account_aliases_account_id", "account_aliases", ["account_id"])
    op.create_index(
        "ix_account_aliases_alias_type_value",
        "account_aliases",
        ["alias_type", "alias_value"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_aliases_alias_type_value", table_name="account_aliases")
    op.drop_index("ix_account_aliases_account_id", table_name="account_aliases")
    op.drop_table("account_aliases")
    op.drop_index("ix_accounts_domain", table_name="accounts")
    op.drop_table("accounts")
