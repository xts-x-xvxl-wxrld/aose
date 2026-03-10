"""add Epic H event types to structured_events check constraint

Revision ID: h1001
Revises: f10001
Create Date: 2026-03-09

Adds evidence_digest_built, draft_generated, draft_flagged_for_review,
and approval_recorded to the ck_structured_events_event_type constraint.
Required by CONTRACT.yaml structured_events.required_event_kinds for Epic H.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "h1001"
down_revision: Union[str, None] = "f10001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_EVENT_TYPES = (
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

_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + (
    "evidence_digest_built",
    "draft_generated",
    "draft_flagged_for_review",
    "approval_recorded",
)

_OLD_SQL = ", ".join(f"'{v}'" for v in _OLD_EVENT_TYPES)
_NEW_SQL = ", ".join(f"'{v}'" for v in _NEW_EVENT_TYPES)


def upgrade() -> None:
    op.drop_constraint(
        "ck_structured_events_event_type", "structured_events", type_="check"
    )
    op.create_check_constraint(
        "ck_structured_events_event_type",
        "structured_events",
        f"event_type IN ({_NEW_SQL})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_structured_events_event_type", "structured_events", type_="check"
    )
    op.create_check_constraint(
        "ck_structured_events_event_type",
        "structured_events",
        f"event_type IN ({_OLD_SQL})",
    )
