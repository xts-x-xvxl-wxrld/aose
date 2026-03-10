"""create contacts and contact_aliases tables

Revision ID: b7001
Revises: b6001
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7001"
down_revision: Union[str, None] = "b6001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("contact_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("role_json", sa.JSON(), nullable=True),
        sa.Column("channels_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"]),
        sa.PrimaryKeyConstraint("contact_id"),
    )
    op.create_index("ix_contacts_account_id", "contacts", ["account_id"])

    op.create_table(
        "contact_aliases",
        sa.Column("contact_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("alias_type", sa.String(), nullable=False),
        sa.Column("alias_value", sa.Text(), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.contact_id"]),
        sa.PrimaryKeyConstraint("contact_id", "alias_type"),
        sa.UniqueConstraint(
            "account_id",
            "alias_type",
            "alias_value",
            name="uq_contact_aliases_account_type_value",
        ),
    )
    op.create_index("ix_contact_aliases_contact_id", "contact_aliases", ["contact_id"])
    op.create_index("ix_contact_aliases_account_id", "contact_aliases", ["account_id"])
    op.create_index(
        "ix_contact_aliases_account_type_value",
        "contact_aliases",
        ["account_id", "alias_type", "alias_value"],
    )


def downgrade() -> None:
    op.drop_index("ix_contact_aliases_account_type_value", table_name="contact_aliases")
    op.drop_index("ix_contact_aliases_account_id", table_name="contact_aliases")
    op.drop_index("ix_contact_aliases_contact_id", table_name="contact_aliases")
    op.drop_table("contact_aliases")
    op.drop_index("ix_contacts_account_id", table_name="contacts")
    op.drop_table("contacts")
