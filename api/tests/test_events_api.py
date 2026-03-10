"""
API-side tests for SPEC-C4: structured events endpoint.

Acceptance check 5: recent-events query returns at most 20 events per entity.
"""

from aose_api.main import _RECENT_EVENTS_LIMIT


def test_recent_events_limit_is_twenty() -> None:
    """Acceptance check 5: query limit locked to 20 per CONTRACT.yaml run_view_requirement."""
    assert _RECENT_EVENTS_LIMIT == 20
