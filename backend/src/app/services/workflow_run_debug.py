from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import AuthIdentity
from app.models import ConversationMessage, RunEvent, TenantMembership, User, WorkflowRun
from app.repositories.conversation_message_repository import ConversationMessageRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.run_event_repository import RunEventRepository
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.workflow_runs import WorkflowRunService


@dataclass(slots=True)
class _PendingProviderAttempt:
    provider_name: str | None
    tool_name: str
    attempt_number: int
    request_summary: str | None


class WorkflowRunDebugService:
    def __init__(
        self,
        session: AsyncSession,
        run_service: WorkflowRunService | None = None,
    ) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)
        self._events = RunEventRepository(session)
        self._messages = ConversationMessageRepository(session)
        self._run_service = run_service or WorkflowRunService(session)

    async def get_debug_bundle(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
        run_id: UUID,
    ) -> dict[str, object]:
        await self._require_active_membership(identity=identity, tenant_id=tenant_id)
        run = await self._run_service.get_run_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )

        run_events = list(await self._events.list_for_run(tenant_id=tenant_id, run_id=run.id))
        run_messages = list(await self._messages.list_for_run(tenant_id=tenant_id, run_id=run.id))
        user_summary_snapshot = _select_user_summary_snapshot(run_messages, run)
        summary_selection_reason = _extract_summary_selection_reason(run, run_events)

        return {
            "workflow_run_id": run.id,
            "thread_id": run.thread_id,
            "workflow_type": run.workflow_type,
            "workflow_status": run.status,
            "requested_payload_json": run.requested_payload_json,
            "normalized_result_json": run.normalized_result_json,
            "provider_attempts": _build_provider_attempts(run_events),
            "fallback_decisions": _build_fallback_decisions(run_events),
            "reasoning_validation": _build_reasoning_validation(run_events),
            "user_summary_snapshot": user_summary_snapshot,
            "terminal_outcome_family": _extract_terminal_outcome_family(run),
            "summary_selection_reason": summary_selection_reason,
        }

    async def _require_active_membership(
        self,
        *,
        identity: AuthIdentity,
        tenant_id: UUID,
    ) -> tuple[User, TenantMembership]:
        user = await self._users.get_by_external_auth_subject(
            external_auth_subject=identity.external_auth_subject
        )
        if user is None:
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message="User does not have an active membership in the requested tenant.",
            )
        membership = await self._memberships.get_by_tenant_and_user(
            tenant_id=tenant_id,
            user_id=user.id,
        )
        if membership is None or membership.status != "active":
            raise ServiceError(
                status_code=403,
                error_code="tenant_membership_required",
                message="User does not have an active membership in the requested tenant.",
            )
        return user, membership


def _build_provider_attempts(run_events: list[RunEvent]) -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    pending_attempts: list[_PendingProviderAttempt] = []
    attempt_counters: dict[tuple[str, str | None], int] = {}

    for event in run_events:
        payload = event.payload_json or {}
        if event.event_name == "tool.started":
            tool_name = _string_value(payload.get("tool_name")) or "unknown_tool"
            provider_name = _string_value(payload.get("provider_name"))
            counter_key = (tool_name, provider_name)
            attempt_number = attempt_counters.get(counter_key, 0) + 1
            attempt_counters[counter_key] = attempt_number
            pending_attempts.append(
                _PendingProviderAttempt(
                    provider_name=provider_name,
                    tool_name=tool_name,
                    attempt_number=attempt_number,
                    request_summary=_string_value(payload.get("input_summary")),
                )
            )
            continue

        if event.event_name not in {"tool.completed", "tool.failed"}:
            continue

        tool_name = _string_value(payload.get("tool_name")) or "unknown_tool"
        provider_name = _string_value(payload.get("provider_name"))
        matched_attempt = None
        for index, pending_attempt in enumerate(pending_attempts):
            if pending_attempt.tool_name != tool_name:
                continue
            if pending_attempt.provider_name != provider_name:
                continue
            matched_attempt = pending_attempts.pop(index)
            break

        attempts.append(
            {
                "provider_name": provider_name,
                "tool_name": tool_name,
                "operation": tool_name,
                "attempt_number": (
                    matched_attempt.attempt_number
                    if matched_attempt is not None
                    else attempt_counters.get((tool_name, provider_name), 1)
                ),
                "request_summary": (
                    matched_attempt.request_summary if matched_attempt is not None else None
                ),
                "outcome": "failed" if event.event_name == "tool.failed" else "completed",
                "error_code": _string_value(payload.get("error_code")),
                "output_summary": _string_value(payload.get("output_summary")),
                "failure_summary": _string_value(payload.get("failure_summary")),
                "produced_evidence_results": bool(payload.get("produced_evidence_results", False)),
            }
        )

    return attempts


def _build_fallback_decisions(run_events: list[RunEvent]) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    for event in run_events:
        if event.event_name != "provider.routing_decision":
            continue
        payload = event.payload_json or {}
        selected_provider = _string_value(payload.get("selected_provider"))
        if selected_provider is None:
            continue
        decisions.append(
            {
                "capability": _string_value(payload.get("capability")),
                "from_provider": _string_value(payload.get("from_provider")),
                "to_provider": selected_provider,
                "fallback_provider": _string_value(payload.get("fallback_provider")),
                "trigger_reason": _string_value(payload.get("trigger_reason")),
                "routing_basis": _string_value(payload.get("routing_basis")),
                "allowed": payload.get("allowed")
                if isinstance(payload.get("allowed"), bool)
                else None,
                "decision_summary": _string_value(payload.get("reason_summary")),
            }
        )
    return decisions


def _build_reasoning_validation(run_events: list[RunEvent]) -> list[dict[str, object]]:
    validations: list[dict[str, object]] = []
    for event in run_events:
        if event.event_name not in {"reasoning.validated", "reasoning.failed_validation"}:
            continue
        payload = event.payload_json or {}
        schema_name = _string_value(payload.get("schema_name"))
        if schema_name is None:
            continue
        validations.append(
            {
                "schema_name": schema_name,
                "provider_name": _string_value(payload.get("provider_name")),
                "status": (
                    "validated"
                    if event.event_name == "reasoning.validated"
                    else "failed_validation"
                ),
                "failure_summary": _string_value(payload.get("failure_summary")),
                "fallback_summary": _string_value(payload.get("fallback_summary")),
                "output_summary": _string_value(payload.get("output_summary")),
            }
        )
    return validations


def _select_user_summary_snapshot(
    run_messages: list[ConversationMessage],
    run: WorkflowRun,
) -> str | None:
    assistant_messages = [
        message.content_text
        for message in run_messages
        if message.role == "assistant" and message.message_type == "assistant_reply"
    ]
    if assistant_messages:
        return assistant_messages[-1]
    normalized_result_json = run.normalized_result_json or {}
    assistant_summary = normalized_result_json.get("assistant_summary")
    return assistant_summary.strip() if isinstance(assistant_summary, str) and assistant_summary.strip() else None


def _extract_terminal_outcome_family(run: WorkflowRun) -> str:
    normalized_result_json = run.normalized_result_json or {}
    outcome = normalized_result_json.get("outcome")
    if isinstance(outcome, str) and outcome.strip():
        return outcome.strip()
    return run.status


def _extract_summary_selection_reason(run: WorkflowRun, run_events: list[RunEvent]) -> str | None:
    normalized_result_json = run.normalized_result_json or {}
    summary_selection_reason = normalized_result_json.get("summary_selection_reason")
    if isinstance(summary_selection_reason, str) and summary_selection_reason.strip():
        return summary_selection_reason.strip()

    for event in reversed(run_events):
        payload = event.payload_json or {}
        summary_selection_reason = payload.get("summary_selection_reason")
        if isinstance(summary_selection_reason, str) and summary_selection_reason.strip():
            return summary_selection_reason.strip()
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None
