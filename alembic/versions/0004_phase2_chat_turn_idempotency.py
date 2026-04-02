"""phase2 chat turn idempotency

Revision ID: 0004_phase2_chat_idem
Revises: 0003_phase2_chat_thread_context
Create Date: 2026-04-01 19:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_phase2_chat_idem"
down_revision: str | None = "0003_phase2_chat_thread_context"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("request_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "request_payload_json",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_conversation_messages_tenant_user_request_id",
        "conversation_messages",
        ["tenant_id", "created_by_user_id", "request_id"],
        unique=True,
        postgresql_where=sa.text(
            "message_type = 'user_turn' AND request_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_conversation_messages_tenant_user_request_id",
        table_name="conversation_messages",
    )
    op.drop_column("conversation_messages", "request_payload_json")
    op.drop_column("conversation_messages", "request_id")
