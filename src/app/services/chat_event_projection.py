from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunEvent, WorkflowRun
from app.orchestration.contracts import RunEventName, WorkflowRunStatus
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository

_RUNNING_META_EVENT_TYPES = {
    "agent_handoff",
    "agent_completed",
    "tool_started",
    "tool_completed",
    "tool_failed",
    "reasoning_validated",
    "reasoning_failed_validation",
    "candidate_accepted",
    "candidate_rejected",
    "provider_routing_decision",
}


@dataclass(slots=True)
class ChatMetaEventProjection:
    type: str
    thread_id: UUID | None
    workflow_run_id: UUID
    workflow_status: str | None
    payload: dict[str, Any]
    created_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "thread_id": str(self.thread_id) if self.thread_id is not None else None,
            "workflow_run_id": str(self.workflow_run_id),
            "workflow_status": self.workflow_status,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }


class ChatEventProjectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = WorkflowRunRepository(session)
        self._events = RunEventRepository(session)

    async def list_projected_events_for_tenant(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChatMetaEventProjection]:
        recent_events = await self._events.list_recent_for_tenant(
            tenant_id=tenant_id,
            thread_id=thread_id,
            limit=max(limit * 3, 20),
            offset=0,
        )
        projected_events = await self._project_recent_run_events(
            tenant_id=tenant_id,
            run_events=recent_events,
        )

        queued_runs = await self._runs.list_for_tenant(
            tenant_id=tenant_id,
            thread_id=thread_id,
            status=WorkflowRunStatus.QUEUED.value,
            limit=max(limit * 2, 20),
            offset=0,
        )
        run_ids_with_events = {projection.workflow_run_id for projection in projected_events}
        for queued_run in queued_runs:
            if queued_run.id in run_ids_with_events:
                continue
            projected_events.append(project_run_status(run=queued_run))

        projected_events.sort(
            key=lambda projection: (projection.created_at, projection.workflow_run_id),
            reverse=True,
        )
        return projected_events[offset : offset + limit]

    async def project_stream_events_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> list[ChatMetaEventProjection]:
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            return []
        run_events = await self._events.list_for_run(tenant_id=tenant_id, run_id=run_id)
        projections = project_run_timeline(run=run, run_events=run_events)
        return projections or [project_run_status(run=run)]

    async def _project_recent_run_events(
        self,
        *,
        tenant_id: UUID,
        run_events: list[RunEvent],
    ) -> list[ChatMetaEventProjection]:
        projected_events: list[ChatMetaEventProjection] = []
        cached_runs: dict[UUID, WorkflowRun] = {}
        for run_event in run_events:
            run = cached_runs.get(run_event.run_id)
            if run is None:
                run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_event.run_id)
                if run is None:
                    continue
                cached_runs[run.id] = run
            projected_event = project_run_event(run=run, run_event=run_event)
            if projected_event is not None:
                projected_events.append(projected_event)
        return projected_events


def project_run_timeline(
    *,
    run: WorkflowRun,
    run_events: list[RunEvent],
) -> list[ChatMetaEventProjection]:
    projected_events: list[ChatMetaEventProjection] = []

    if not run_events and run.status == WorkflowRunStatus.QUEUED.value:
        return [project_run_status(run=run)]

    for run_event in run_events:
        projected_event = project_run_event(run=run, run_event=run_event)
        if projected_event is not None:
            projected_events.append(projected_event)

    if not projected_events:
        projected_events.append(project_run_status(run=run))
        return projected_events

    latest_type = projected_events[-1].type
    terminal_type = _status_to_meta_type(run.status)
    if terminal_type in {"awaiting_review", "completed", "failed"} and latest_type != terminal_type:
        projected_events.append(project_run_status(run=run))

    return projected_events


def project_run_status(*, run: WorkflowRun) -> ChatMetaEventProjection:
    return ChatMetaEventProjection(
        type=_status_to_meta_type(run.status),
        thread_id=run.thread_id,
        workflow_run_id=run.id,
        workflow_status=run.status,
        payload={"workflow_type": run.workflow_type},
        created_at=run.updated_at if run.status != WorkflowRunStatus.QUEUED.value else run.created_at,
    )


def project_run_event(
    *,
    run: WorkflowRun,
    run_event: RunEvent,
) -> ChatMetaEventProjection | None:
    event_type = _event_name_to_meta_type(run_event.event_name)
    if event_type is None:
        return None

    payload = {"workflow_type": run.workflow_type, **_normalize_payload(run_event.payload_json)}
    workflow_status = run.status if event_type not in _RUNNING_META_EVENT_TYPES else "running"
    if event_type in {"queued", "running", "awaiting_review", "completed", "failed"}:
        workflow_status = _meta_type_to_workflow_status(event_type)

    return ChatMetaEventProjection(
        type=event_type,
        thread_id=run.thread_id,
        workflow_run_id=run.id,
        workflow_status=workflow_status,
        payload=payload,
        created_at=run_event.created_at,
    )


def _normalize_payload(payload_json: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload_json, dict):
        return {}
    return dict(payload_json)


def _event_name_to_meta_type(event_name: str) -> str | None:
    normalized_event_name = RunEventName(event_name)
    if normalized_event_name is RunEventName.RUN_STARTED:
        return "running"
    if normalized_event_name is RunEventName.AGENT_HANDOFF:
        return "agent_handoff"
    if normalized_event_name is RunEventName.AGENT_COMPLETED:
        return "agent_completed"
    if normalized_event_name is RunEventName.TOOL_STARTED:
        return "tool_started"
    if normalized_event_name is RunEventName.TOOL_COMPLETED:
        return "tool_completed"
    if normalized_event_name is RunEventName.TOOL_FAILED:
        return "tool_failed"
    if normalized_event_name is RunEventName.REASONING_VALIDATED:
        return "reasoning_validated"
    if normalized_event_name is RunEventName.REASONING_FAILED_VALIDATION:
        return "reasoning_failed_validation"
    if normalized_event_name is RunEventName.CANDIDATE_ACCEPTED:
        return "candidate_accepted"
    if normalized_event_name is RunEventName.CANDIDATE_REJECTED:
        return "candidate_rejected"
    if normalized_event_name is RunEventName.PROVIDER_ROUTING_DECISION:
        return "provider_routing_decision"
    if normalized_event_name is RunEventName.RUN_AWAITING_REVIEW:
        return "awaiting_review"
    if normalized_event_name is RunEventName.RUN_COMPLETED:
        return "completed"
    if normalized_event_name is RunEventName.RUN_FAILED:
        return "failed"
    return None


def _status_to_meta_type(status: str) -> str:
    normalized_status = WorkflowRunStatus(status)
    if normalized_status is WorkflowRunStatus.QUEUED:
        return "queued"
    if normalized_status is WorkflowRunStatus.RUNNING:
        return "running"
    if normalized_status is WorkflowRunStatus.AWAITING_REVIEW:
        return "awaiting_review"
    if normalized_status is WorkflowRunStatus.SUCCEEDED:
        return "completed"
    return "failed"


def _meta_type_to_workflow_status(meta_type: str) -> str:
    if meta_type == "completed":
        return WorkflowRunStatus.SUCCEEDED.value
    if meta_type == "failed":
        return WorkflowRunStatus.FAILED.value
    return meta_type
