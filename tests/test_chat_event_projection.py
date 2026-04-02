from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.chat_event_projection import (
    project_run_event,
    project_run_status,
    project_run_timeline,
)


def _run(*, status: str = "queued"):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        workflow_type="account_search",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _event(*, event_name: str, payload_json: dict | None = None):
    return SimpleNamespace(
        run_id=uuid4(),
        event_name=event_name,
        payload_json=payload_json or {},
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def test_project_run_status_maps_queued_to_chat_meta() -> None:
    projection = project_run_status(run=_run(status="queued"))

    assert projection.type == "queued"
    assert projection.workflow_status == "queued"
    assert projection.payload["workflow_type"] == "account_search"


def test_project_run_event_maps_tool_and_agent_events_to_chat_meta() -> None:
    run = _run(status="running")

    tool_projection = project_run_event(
        run=run,
        run_event=_event(
            event_name="tool.started",
            payload_json={"tool_name": "web_search", "provider_name": "firecrawl"},
        ),
    )
    handoff_projection = project_run_event(
        run=run,
        run_event=_event(
            event_name="agent.handoff",
            payload_json={"from_agent": "planner", "to_agent": "researcher"},
        ),
    )

    assert tool_projection is not None
    assert tool_projection.type == "tool_started"
    assert tool_projection.workflow_status == "running"
    assert tool_projection.payload["tool_name"] == "web_search"

    assert handoff_projection is not None
    assert handoff_projection.type == "agent_handoff"
    assert handoff_projection.workflow_status == "running"
    assert handoff_projection.payload["to_agent"] == "researcher"


def test_project_run_event_maps_phase3_reasoning_and_routing_events() -> None:
    run = _run(status="running")

    reasoning_projection = project_run_event(
        run=run,
        run_event=_event(
            event_name="reasoning.validated",
            payload_json={"schema_name": "contact_search_candidates"},
        ),
    )
    routing_projection = project_run_event(
        run=run,
        run_event=_event(
            event_name="provider.routing_decision",
            payload_json={"selected_provider": "findymail"},
        ),
    )

    assert reasoning_projection is not None
    assert reasoning_projection.type == "reasoning_validated"
    assert reasoning_projection.workflow_status == "running"
    assert reasoning_projection.payload["schema_name"] == "contact_search_candidates"

    assert routing_projection is not None
    assert routing_projection.type == "provider_routing_decision"
    assert routing_projection.workflow_status == "running"
    assert routing_projection.payload["selected_provider"] == "findymail"


def test_project_run_timeline_uses_durable_events_and_terminal_status() -> None:
    run = _run(status="succeeded")
    run_events = [
        _event(event_name="run.started", payload_json={"thread_id": str(run.thread_id)}),
        _event(event_name="tool.started", payload_json={"tool_name": "web_search"}),
        _event(event_name="tool.completed", payload_json={"tool_name": "web_search"}),
        _event(event_name="run.completed", payload_json={"result_summary": "Done"}),
    ]

    projections = project_run_timeline(run=run, run_events=run_events)

    assert [projection.type for projection in projections] == [
        "running",
        "tool_started",
        "tool_completed",
        "completed",
    ]
    assert projections[-1].workflow_status == "succeeded"
