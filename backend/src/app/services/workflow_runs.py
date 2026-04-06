from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
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
from app.repositories.llm_call_log_repository import LlmCallLogRepository
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.tool_call_log_repository import ToolCallLogRepository
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
        self._llm_calls = LlmCallLogRepository(session)
        self._messages = ConversationMessageRepository(session)
        self._tool_calls = ToolCallLogRepository(session)
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
                "agent_config_version_ids": _extract_agent_config_version_ids(
                    current_run.config_snapshot_json
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
        assistant_summary = _resolve_terminal_assistant_summary_override(
            workflow_status=WorkflowRunStatus.SUCCEEDED,
            normalized_result_json=normalized_result_json,
        )
        terminal_outcome_family = _resolve_terminal_outcome_family(
            workflow_status=WorkflowRunStatus.SUCCEEDED,
            normalized_result_json=normalized_result_json,
        )
        summary_selection_reason = _resolve_summary_selection_reason(normalized_result_json)
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
                "assistant_summary": assistant_summary,
                "terminal_outcome_family": terminal_outcome_family,
                "summary_selection_reason": summary_selection_reason,
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
                    content_text=assistant_summary
                    or _workflow_terminal_assistant_summary(
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
        assistant_summary = _resolve_terminal_assistant_summary_override(
            workflow_status=WorkflowRunStatus.FAILED,
            normalized_result_json=normalized_result_json,
        )
        terminal_outcome_family = _resolve_terminal_outcome_family(
            workflow_status=WorkflowRunStatus.FAILED,
            normalized_result_json=normalized_result_json,
        )
        summary_selection_reason = _resolve_summary_selection_reason(normalized_result_json)
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
                "assistant_summary": assistant_summary,
                "terminal_outcome_family": terminal_outcome_family,
                "summary_selection_reason": summary_selection_reason,
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
                    content_text=assistant_summary
                    or _workflow_terminal_assistant_summary(
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
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is not None:
            await self._tool_calls.create(
                tenant_id=tenant_id,
                run_id=run_id,
                thread_id=run.thread_id,
                agent_name=_resolve_workflow_agent_name(run.workflow_type),
                workflow_type=run.workflow_type,
                tool_name=tool_name,
                provider_name=provider_name,
                status="started",
                correlation_key=correlation_key,
                input_excerpt=_truncate_excerpt(input_summary),
                output_excerpt=None,
                input_hash=_hash_value(input_summary),
                output_hash=None,
                error_code=None,
                raw_metadata_json={},
                latency_ms=None,
            )
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
        log_row = await self._tool_calls.find_latest_open_call(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name=tool_name,
            provider_name=provider_name,
            correlation_key=None,
        )
        finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if log_row is not None:
            await self._tool_calls.mark_finished(
                row=log_row,
                status="completed",
                output_excerpt=_truncate_excerpt(output_summary),
                output_hash=_hash_value(output_summary),
                error_code=error_code,
                raw_metadata_json={"produced_evidence_results": produced_evidence_results},
                finished_at=finished_at,
                latency_ms=_compute_latency_ms(log_row.created_at, finished_at),
            )
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

    async def emit_tool_failed(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        tool_name: str,
        failure_summary: str,
        provider_name: str | None = None,
        error_code: str | None = None,
    ) -> RunEvent:
        log_row = await self._tool_calls.find_latest_open_call(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name=tool_name,
            provider_name=provider_name,
            correlation_key=None,
        )
        finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if log_row is not None:
            await self._tool_calls.mark_finished(
                row=log_row,
                status="failed",
                output_excerpt=_truncate_excerpt(failure_summary),
                output_hash=_hash_value(failure_summary),
                error_code=error_code,
                raw_metadata_json={},
                finished_at=finished_at,
                latency_ms=_compute_latency_ms(log_row.created_at, finished_at),
            )
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.TOOL_FAILED,
            payload_json={
                "tool_name": tool_name,
                "provider_name": provider_name,
                "failure_summary": failure_summary,
                "error_code": error_code,
            },
        )

    async def emit_reasoning_validated(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        schema_name: str,
        output_summary: str,
        provider_name: str | None = None,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.REASONING_VALIDATED,
            payload_json={
                "schema_name": schema_name,
                "provider_name": provider_name,
                "output_summary": output_summary,
            },
        )

    async def emit_reasoning_failed_validation(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        schema_name: str,
        failure_summary: str,
        provider_name: str | None = None,
        fallback_summary: str | None = None,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.REASONING_FAILED_VALIDATION,
            payload_json={
                "schema_name": schema_name,
                "provider_name": provider_name,
                "failure_summary": failure_summary,
                "fallback_summary": fallback_summary,
            },
        )

    async def emit_candidate_accepted(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        entity_type: str,
        candidate_label: str,
        reason_summary: str | None = None,
        provider_name: str | None = None,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.CANDIDATE_ACCEPTED,
            payload_json={
                "entity_type": entity_type,
                "candidate_label": candidate_label,
                "reason_summary": reason_summary,
                "provider_name": provider_name,
            },
        )

    async def emit_candidate_rejected(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        entity_type: str,
        candidate_label: str,
        reason_summary: str | None = None,
        provider_name: str | None = None,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.CANDIDATE_REJECTED,
            payload_json={
                "entity_type": entity_type,
                "candidate_label": candidate_label,
                "reason_summary": reason_summary,
                "provider_name": provider_name,
            },
        )

    async def emit_provider_routing_decision(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        capability: str,
        selected_provider: str,
        fallback_provider: str | None = None,
        routing_basis: str | None = None,
        reason_summary: str | None = None,
        from_provider: str | None = None,
        trigger_reason: str | None = None,
        allowed: bool | None = None,
    ) -> RunEvent:
        return await self.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_name=RunEventName.PROVIDER_ROUTING_DECISION,
            payload_json={
                "capability": capability,
                "from_provider": from_provider,
                "selected_provider": selected_provider,
                "fallback_provider": fallback_provider,
                "routing_basis": routing_basis,
                "trigger_reason": trigger_reason,
                "allowed": allowed,
                "reason_summary": reason_summary,
            },
        )

    async def emit_assistant_progress_update(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        content_text: str,
    ) -> None:
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None or run.thread_id is None:
            return

        run_messages = await self._messages.list_for_run(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if any(
            message.role == "assistant"
            and message.message_type == "assistant_reply"
            and message.content_text == content_text
            for message in run_messages
        ):
            return

        thread_messages = await self._messages.list_for_thread(
            tenant_id=tenant_id,
            thread_id=run.thread_id,
        )
        message_time = _next_message_time(
            thread_messages[-1].created_at if thread_messages else None
        )
        await self._messages.create(
            tenant_id=tenant_id,
            thread_id=run.thread_id,
            run_id=run.id,
            role="assistant",
            message_type="assistant_reply",
            content_text=content_text,
            created_at=message_time,
        )
        await self._session.commit()

    async def record_llm_call(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        agent_name: str,
        provider_name: str,
        model_name: str | None,
        schema_hint: str | None,
        input_payload: dict[str, Any] | list[dict[str, Any]] | str,
        output_payload: dict[str, Any] | list[dict[str, Any]] | None,
        status: str,
        latency_ms: int | None,
        error_code: str | None,
        raw_metadata_json: dict[str, Any] | None = None,
    ) -> None:
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            return
        usage = raw_metadata_json.get("usage") if isinstance(raw_metadata_json, dict) else {}
        input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
        request_profile = raw_metadata_json.get("request_profile") if isinstance(raw_metadata_json, dict) else None
        await self._llm_calls.create(
            tenant_id=tenant_id,
            run_id=run_id,
            thread_id=run.thread_id,
            agent_name=agent_name,
            workflow_type=run.workflow_type,
            provider_name=provider_name,
            model_name=model_name,
            status=status,
            schema_hint=schema_hint,
            request_profile=request_profile if isinstance(request_profile, str) else None,
            input_excerpt=_truncate_excerpt(_serialize_for_excerpt(input_payload)),
            output_excerpt=_truncate_excerpt(_serialize_for_excerpt(output_payload)),
            input_hash=_hash_value(_serialize_for_excerpt(input_payload)),
            output_hash=_hash_value(_serialize_for_excerpt(output_payload)),
            error_code=error_code,
            raw_metadata_json=dict(raw_metadata_json or {}),
            latency_ms=latency_ms,
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) else None,
            estimated_cost_micros=None,
        )
        await self._session.commit()

    async def attach_config_snapshot(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        config_snapshot_json: dict[str, Any],
    ) -> WorkflowRun | None:
        run = await self._runs.update(
            tenant_id=tenant_id,
            run_id=run_id,
            changes={"config_snapshot_json": config_snapshot_json},
        )
        if run is not None:
            await self._session.commit()
            await self._session.refresh(run)
        return run

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


def _resolve_terminal_assistant_summary_override(
    *,
    workflow_status: WorkflowRunStatus,
    normalized_result_json: dict[str, Any] | None,
) -> str | None:
    if workflow_status not in {WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED}:
        return None
    if not isinstance(normalized_result_json, dict):
        return None
    assistant_summary = normalized_result_json.get("assistant_summary")
    if isinstance(assistant_summary, str) and assistant_summary.strip():
        return assistant_summary.strip()
    return None


def _resolve_terminal_outcome_family(
    *,
    workflow_status: WorkflowRunStatus,
    normalized_result_json: dict[str, Any] | None,
) -> str:
    if isinstance(normalized_result_json, dict):
        outcome = normalized_result_json.get("outcome")
        if isinstance(outcome, str) and outcome.strip():
            return outcome.strip()
    return workflow_status.value


def _resolve_summary_selection_reason(
    normalized_result_json: dict[str, Any] | None,
) -> str | None:
    if not isinstance(normalized_result_json, dict):
        return None
    summary_selection_reason = normalized_result_json.get("summary_selection_reason")
    if isinstance(summary_selection_reason, str) and summary_selection_reason.strip():
        return summary_selection_reason.strip()
    return None


def _truncate_excerpt(value: str | None, *, limit: int = 512) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:limit]


def _hash_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _serialize_for_excerpt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _compute_latency_ms(started_at: datetime | None, finished_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(int((finished_at - started_at.replace(tzinfo=None)).total_seconds() * 1000), 0)


def _resolve_workflow_agent_name(workflow_type: str) -> str | None:
    if workflow_type == WorkflowType.ACCOUNT_SEARCH.value:
        return "account_search_agent"
    if workflow_type == WorkflowType.ACCOUNT_RESEARCH.value:
        return "account_research_agent"
    if workflow_type == WorkflowType.CONTACT_SEARCH.value:
        return "contact_search_agent"
    return None


def _extract_agent_config_version_ids(config_snapshot_json: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(config_snapshot_json, dict):
        return {}
    agents = config_snapshot_json.get("agents")
    if not isinstance(agents, dict):
        return {}
    return {
        str(agent_name): str(payload.get("version_id"))
        for agent_name, payload in agents.items()
        if isinstance(payload, dict) and payload.get("version_id") is not None
    }


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
