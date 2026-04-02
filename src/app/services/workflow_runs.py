from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunEvent, WorkflowRun
from app.orchestration.contracts import (
    RunEventName,
    WorkflowRunStatus,
    WorkflowType,
    is_allowed_workflow_run_transition,
)
from app.repositories.conversation_message_repository import ConversationMessageRepository
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.errors import ServiceError
from app.services.runtime import (
    WorkflowExecutionRequest,
    WorkflowExecutor,
    dispatch_workflow_run,
)

_UNSET = object()


class WorkflowRunService:
    def __init__(
        self,
        session: AsyncSession,
        executor: WorkflowExecutor | None = None,
    ) -> None:
        self._session = session
        self._runs = WorkflowRunRepository(session)
        self._events = RunEventRepository(session)
        self._messages = ConversationMessageRepository(session)
        self._executor = executor

    async def create_queued_run(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        workflow_type: WorkflowType | str,
        requested_payload_json: dict[str, Any],
        thread_id: UUID | None = None,
        status_detail: str | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowRun:
        normalized_workflow_type = (
            WorkflowType(workflow_type)
            if isinstance(workflow_type, str)
            else workflow_type
        )

        run = await self._runs.create(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            workflow_type=normalized_workflow_type.value,
            status="queued",
            requested_payload_json=requested_payload_json,
            thread_id=thread_id,
            status_detail=status_detail,
            correlation_id=correlation_id,
        )
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def get_run_for_tenant(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> WorkflowRun | None:
        return await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)

    async def emit_event(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        event_name: RunEventName | str,
        payload_json: dict[str, Any],
    ) -> RunEvent:
        normalized_event_name = (
            RunEventName(event_name).value
            if isinstance(event_name, str)
            else event_name.value
        )
        event = await self._events.create(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=normalized_event_name,
            payload_json=payload_json,
        )
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def list_events_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> list[RunEvent]:
        return list(await self._events.list_for_run(tenant_id=tenant_id, run_id=run_id))

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        status_detail: str | None = None,
    ) -> WorkflowRun:
        run, _event = await self._transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            next_status=WorkflowRunStatus.RUNNING,
            status_detail=status_detail,
            event_name=RunEventName.RUN_STARTED,
            event_payload_builder=lambda current_run: {
                "workflow_type": current_run.workflow_type,
                "thread_id": (
                    str(current_run.thread_id) if current_run.thread_id is not None else None
                ),
            },
            thread_message_builder=lambda current_run: [
                _thread_message(
                    role="system",
                    message_type="workflow_status",
                    content_text=_workflow_status_message_text(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.RUNNING,
                    ),
                )
            ],
        )
        return run

    async def mark_awaiting_review(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        review_reason: str,
        artifact_id: UUID | None = None,
        status_detail: str | None = None,
        normalized_result_json: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        run, _event = await self._transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            next_status=WorkflowRunStatus.AWAITING_REVIEW,
            status_detail=status_detail,
            normalized_result_json=normalized_result_json,
            event_name=RunEventName.RUN_AWAITING_REVIEW,
            event_payload_builder=lambda current_run: {
                "review_reason": review_reason,
                "workflow_run_id": str(current_run.id),
                "artifact_id": str(artifact_id) if artifact_id is not None else None,
            },
            thread_message_builder=lambda current_run: [
                _thread_message(
                    role="system",
                    message_type="workflow_status",
                    content_text=_workflow_status_message_text(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.AWAITING_REVIEW,
                    ),
                ),
                _thread_message(
                    role="assistant",
                    message_type="assistant_reply",
                    content_text=_workflow_terminal_assistant_summary(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.AWAITING_REVIEW,
                        summary_text=review_reason,
                    ),
                ),
            ],
        )
        return run

    async def mark_succeeded(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        result_summary: str,
        normalized_result_json: dict[str, Any] | None = None,
        canonical_output_ids: dict[str, list[str]] | None = None,
        status_detail: str | None = None,
    ) -> WorkflowRun:
        run, _event = await self._transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            next_status=WorkflowRunStatus.SUCCEEDED,
            status_detail=status_detail,
            normalized_result_json=normalized_result_json,
            error_code=None,
            event_name=RunEventName.RUN_COMPLETED,
            event_payload_builder=lambda _current_run: {
                "result_summary": result_summary,
                "canonical_output_ids": canonical_output_ids or {},
            },
            thread_message_builder=lambda current_run: [
                _thread_message(
                    role="system",
                    message_type="workflow_status",
                    content_text=_workflow_status_message_text(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.SUCCEEDED,
                    ),
                ),
                _thread_message(
                    role="assistant",
                    message_type="assistant_reply",
                    content_text=_workflow_terminal_assistant_summary(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.SUCCEEDED,
                        summary_text=result_summary,
                    ),
                ),
            ],
        )
        return run

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        error_code: str,
        failure_summary: str,
        normalized_result_json: dict[str, Any] | None = None,
        status_detail: str | None = None,
    ) -> WorkflowRun:
        run, _event = await self._transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            next_status=WorkflowRunStatus.FAILED,
            status_detail=status_detail,
            normalized_result_json=normalized_result_json,
            error_code=error_code,
            event_name=RunEventName.RUN_FAILED,
            event_payload_builder=lambda _current_run: {
                "error_code": error_code,
                "failure_summary": failure_summary,
            },
            thread_message_builder=lambda current_run: [
                _thread_message(
                    role="system",
                    message_type="workflow_status",
                    content_text=_workflow_status_message_text(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.FAILED,
                    ),
                ),
                _thread_message(
                    role="assistant",
                    message_type="assistant_reply",
                    content_text=_workflow_terminal_assistant_summary(
                        workflow_type=current_run.workflow_type,
                        status=WorkflowRunStatus.FAILED,
                        summary_text=failure_summary,
                    ),
                ),
            ],
        )
        return run

    async def emit_agent_handoff(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        from_agent: str,
        to_agent: str,
        reason: str,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.AGENT_HANDOFF,
            payload_json={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
            },
        )

    async def emit_agent_completed(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        agent_name: str,
        result_summary: str,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.AGENT_COMPLETED,
            payload_json={
                "agent_name": agent_name,
                "result_summary": result_summary,
            },
        )

    async def emit_tool_started(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        tool_name: str,
        input_summary: str,
        provider_name: str | None = None,
        correlation_key: str | None = None,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.TOOL_STARTED,
            payload_json={
                "tool_name": tool_name,
                "provider_name": provider_name,
                "input_summary": input_summary,
                "correlation_key": correlation_key,
            },
        )

    async def emit_tool_completed(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        tool_name: str,
        output_summary: str,
        provider_name: str | None = None,
        error_code: str | None = None,
        produced_evidence_results: bool = False,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.TOOL_COMPLETED,
            payload_json={
                "tool_name": tool_name,
                "provider_name": provider_name,
                "output_summary": output_summary,
                "error_code": error_code,
                "produced_evidence_results": produced_evidence_results,
            },
        )

    def build_execution_request(
        self,
        *,
        run: WorkflowRun,
        request_id: str | None = None,
    ) -> WorkflowExecutionRequest:
        return WorkflowExecutionRequest(
            run_id=run.id,
            tenant_id=run.tenant_id,
            created_by_user_id=run.created_by_user_id,
            workflow_type=WorkflowType(run.workflow_type),
            thread_id=run.thread_id,
            request_id=request_id,
        )

    async def dispatch_queued_run(
        self,
        *,
        run: WorkflowRun,
        request_id: str | None = None,
    ) -> WorkflowExecutionRequest:
        if self._executor is None:
            raise RuntimeError("WorkflowRunService requires an executor to dispatch queued runs.")
        if run.status != WorkflowRunStatus.QUEUED.value:
            raise ServiceError(
                status_code=409,
                error_code="review_state_conflict",
                message="Only queued workflow runs may be dispatched.",
            )

        request = self.build_execution_request(run=run, request_id=request_id)
        return await dispatch_workflow_run(self._executor, request)

    async def _transition_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        next_status: WorkflowRunStatus,
        status_detail: str | None | object = _UNSET,
        normalized_result_json: dict[str, Any] | None | object = _UNSET,
        error_code: str | None | object = _UNSET,
        event_name: RunEventName | None = None,
        event_payload_builder: Callable[[WorkflowRun], dict[str, Any]] | None = None,
        thread_message_builder: Callable[[WorkflowRun], list[dict[str, str]]] | None = None,
    ) -> tuple[WorkflowRun, RunEvent | None]:
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        if not is_allowed_workflow_run_transition(run.status, next_status):
            raise ServiceError(
                status_code=409,
                error_code="review_state_conflict",
                message=(
                    f"Workflow run cannot transition from {run.status} to {next_status.value}."
                ),
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        changes: dict[str, Any] = {"status": next_status.value}
        if next_status is WorkflowRunStatus.RUNNING and run.started_at is None:
            changes["started_at"] = now
        if next_status in {
            WorkflowRunStatus.SUCCEEDED,
            WorkflowRunStatus.FAILED,
            WorkflowRunStatus.CANCELLED,
        }:
            changes["finished_at"] = now
        if status_detail is not _UNSET:
            changes["status_detail"] = status_detail
        if normalized_result_json is not _UNSET:
            changes["normalized_result_json"] = normalized_result_json
        if error_code is not _UNSET:
            changes["error_code"] = error_code

        updated_run = await self._runs.update(
            tenant_id=tenant_id,
            run_id=run_id,
            changes=changes,
        )
        assert updated_run is not None

        event: RunEvent | None = None
        if event_name is not None:
            payload = event_payload_builder(updated_run) if event_payload_builder else {}
            event = await self._events.create(
                tenant_id=tenant_id,
                run_id=run_id,
                event_name=event_name.value,
                payload_json=payload,
            )
        if thread_message_builder is not None and updated_run.thread_id is not None:
            thread_messages = await self._messages.list_for_thread(
                tenant_id=tenant_id,
                thread_id=updated_run.thread_id,
            )
            message_time = _next_message_time(
                thread_messages[-1].created_at if thread_messages else None
            )
            for index, message in enumerate(thread_message_builder(updated_run)):
                await self._messages.create(
                    tenant_id=tenant_id,
                    thread_id=updated_run.thread_id,
                    run_id=updated_run.id,
                    role=message["role"],
                    message_type=message["message_type"],
                    content_text=message["content_text"],
                    created_at=message_time + timedelta(microseconds=index),
                )

        await self._session.commit()
        await self._session.refresh(updated_run)
        if event is not None:
            await self._session.refresh(event)
        return updated_run, event


def _thread_message(*, role: str, message_type: str, content_text: str) -> dict[str, str]:
    return {
        "role": role,
        "message_type": message_type,
        "content_text": content_text,
    }


def _workflow_status_message_text(*, workflow_type: str, status: WorkflowRunStatus) -> str:
    workflow_label = workflow_type.replace("_", " ")
    if status is WorkflowRunStatus.RUNNING:
        return f"I started the {workflow_label} workflow for this thread."
    if status is WorkflowRunStatus.AWAITING_REVIEW:
        return f"The {workflow_label} workflow is waiting for review."
    if status is WorkflowRunStatus.SUCCEEDED:
        return f"The {workflow_label} workflow finished successfully."
    if status is WorkflowRunStatus.FAILED:
        return f"The {workflow_label} workflow finished with a failure."
    return f"The {workflow_label} workflow is {status.value}."


def _workflow_terminal_assistant_summary(
    *,
    workflow_type: str,
    status: WorkflowRunStatus,
    summary_text: str,
) -> str:
    workflow_label = workflow_type.replace("_", " ")
    normalized_summary = summary_text.strip()
    if status is WorkflowRunStatus.AWAITING_REVIEW:
        return (
            f"I finished the {workflow_label} workflow and it now needs review. "
            f"{normalized_summary}"
        )
    if status is WorkflowRunStatus.SUCCEEDED:
        return f"I finished the {workflow_label} workflow. {normalized_summary}"
    return f"I hit a problem while running the {workflow_label} workflow. {normalized_summary}"


def _next_message_time(reference: datetime | None) -> datetime:
    candidate = datetime.now(timezone.utc)
    if reference is None:
        return candidate
    reference_time = reference
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    else:
        reference_time = reference_time.astimezone(timezone.utc)
    return max(candidate, reference_time + timedelta(microseconds=1))
