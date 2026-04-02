"""phase3 run event taxonomy

Revision ID: 0005_phase3_run_event_taxonomy
Revises: 0004_phase2_chat_idem
Create Date: 2026-04-02 22:10:00.000000
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0005_phase3_run_event_taxonomy"
down_revision: str | None = "0004_phase2_chat_idem"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


_PHASE2_EVENT_CHECK = (
    "event_name IN ('run.started', 'agent.handoff', 'agent.completed', "
    "'tool.started', 'tool.completed', 'run.awaiting_review', "
    "'run.completed', 'run.failed')"
)

_PHASE3_EVENT_CHECK = (
    "event_name IN ('run.started', 'agent.handoff', 'agent.completed', "
    "'tool.started', 'tool.completed', 'tool.failed', "
    "'reasoning.validated', 'reasoning.failed_validation', "
    "'candidate.accepted', 'candidate.rejected', "
    "'provider.routing_decision', 'run.awaiting_review', "
    "'run.completed', 'run.failed')"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_run_events_event_name_allowed"),
        "run_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_run_events_event_name_allowed"),
        "run_events",
        _PHASE3_EVENT_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_run_events_event_name_allowed"),
        "run_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_run_events_event_name_allowed"),
        "run_events",
        _PHASE2_EVENT_CHECK,
    )
