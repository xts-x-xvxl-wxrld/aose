"""create structured_events table

Revision ID: c4001
Revises: b10001
Create Date: 2026-03-08

Implements SPEC-C4 structured event persistence.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c4001"
down_revision: Union[str, None] = "b10001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALID_EVENT_TYPES = (
    "handler_started",
    "handler_succeeded",
    "handler_parked",
    "handler_failed_contract",
    "handler_failed_transient",
    "handler_noop_idempotent",
    "budget_decremented",
    "retry_scheduled",
    "work_item_completed",
    "work_item_parked",
    "work_item_failed_contract",
    "work_item_failed_transient",
)
_VALID_OUTCOMES = (
    "ok",
    "parked",
    "failed_contract",
    "failed_transient",
    "retry_scheduled",
    "noop",
)

_ET_SQL = ", ".join(f"'{v}'" for v in _VALID_EVENT_TYPES)
_OC_SQL = ", ".join(f"'{v}'" for v in _VALID_OUTCOMES)


def upgrade() -> None:
    op.create_table(
        "structured_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("work_item_id", sa.String(), nullable=False),
        sa.Column("entity_ref_type", sa.String(), nullable=False),
        sa.Column("entity_ref_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("counters", JSONB(), nullable=False),
        sa.Column("refs", JSONB(), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(
            ["work_item_id"],
            ["work_items.work_item_id"],
            name="fk_structured_events_work_item_id",
        ),
        sa.CheckConstraint(
            f"event_type IN ({_ET_SQL})",
            name="ck_structured_events_event_type",
        ),
        sa.CheckConstraint(
            f"outcome IN ({_OC_SQL})",
            name="ck_structured_events_outcome",
        ),
    )
    op.create_index(
        "ix_structured_events_work_item_id",
        "structured_events",
        ["work_item_id"],
    )
    op.create_index(
        "ix_structured_events_entity_ref",
        "structured_events",
        ["entity_ref_type", "entity_ref_id"],
    )
    op.create_index(
        "ix_structured_events_occurred_at",
        "structured_events",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_structured_events_occurred_at", table_name="structured_events")
    op.drop_index("ix_structured_events_entity_ref", table_name="structured_events")
    op.drop_index("ix_structured_events_work_item_id", table_name="structured_events")
    op.drop_table("structured_events")
