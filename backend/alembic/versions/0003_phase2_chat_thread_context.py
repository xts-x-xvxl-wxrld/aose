"""phase2 chat thread context

Revision ID: 0003_phase2_chat_thread_context
Revises: 0002_phase1_persistence_and_artifacts
Create Date: 2026-04-01 18:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_phase2_chat_thread_context"
down_revision: str | None = "0002_phase1_persistence"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_threads", "context_json")
