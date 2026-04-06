from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import RequestContext
from app.models import ConversationMessage, ConversationThread, WorkflowRun
from app.orchestration.contracts import (
    OrchestratorDecision,
    OrchestratorInput,
    WorkflowRunStatus,
    WorkflowType,
)
from app.repositories.account_repository import AccountRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_message_repository import ConversationMessageRepository
from app.repositories.conversation_thread_repository import ConversationThreadRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.errors import ServiceError
from app.services.runtime import OrchestratorAdapter, WorkflowExecutor
from app.services.workflow_runs import WorkflowRunService
from app.workflows.account_research import AccountResearchWorkflowInput
from app.workflows.account_search import AccountSearchWorkflowInput
from app.workflows.contact_search import ContactSearchWorkflowInput

THREAD_CONTEXT_FIELDS = (
    "icp_profile_id",
    "selected_account_id",
    "selected_contact_id",
)
CHAT_TURN_PAYLOAD_FIELDS = (
    "user_message",
    "thread_id",
    "seller_profile_id",
    "icp_profile_id",
    "selected_account_id",
    "selected_contact_id",
    "active_workflow",
)


@dataclass(slots=True)
class AcceptedChatTurn:
    thread: ConversationThread
    user_message: ConversationMessage
    response_message: ConversationMessage | None


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        orchestrator: OrchestratorAdapter,
    ) -> None:
        self._session = session
        self._orchestrator = orchestrator
        self._threads = ConversationThreadRepository(session)
        self._messages = ConversationMessageRepository(session)
        self._seller_profiles = SellerProfileRepository(session)
        self._icp_profiles = ICPProfileRepository(session)
        self._accounts = AccountRepository(session)
        self._contacts = ContactRepository(session)
        self._runs = WorkflowRunRepository(session)

    def build_orchestrator_input(
        self,
        *,
        context: RequestContext,
        user_message: str,
        thread_id: str | None = None,
        active_workflow: WorkflowType | str | None = None,
        seller_profile_id: str | None = None,
        seller_profile_status: str | None = None,
        icp_profile_id: str | None = None,
        icp_profile_status: str | None = None,
        selected_account_id: str | None = None,
        selected_contact_id: str | None = None,
        latest_run_status: WorkflowRunStatus | str | None = None,
        conversation_summary: str | None = None,
    ) -> OrchestratorInput:
        if context["tenant_id"] is None:
            raise ServiceError(
                status_code=400,
                error_code="tenant_context_required",
                message="Tenant context is required to build orchestrator input.",
            )

        normalized_workflow = (
            WorkflowType(active_workflow) if isinstance(active_workflow, str) else active_workflow
        )
        normalized_status = (
            WorkflowRunStatus(latest_run_status)
            if isinstance(latest_run_status, str)
            else latest_run_status
        )

        return {
            "tenant_id": context["tenant_id"],
            "user_id": context["user_id"],
            "thread_id": thread_id,
            "user_message": user_message,
            "active_workflow": normalized_workflow,
            "seller_profile_id": seller_profile_id,
            "seller_profile_status": seller_profile_status,
            "icp_profile_id": icp_profile_id,
            "icp_profile_status": icp_profile_status,
            "selected_account_id": selected_account_id,
            "selected_contact_id": selected_contact_id,
            "latest_run_status": normalized_status,
            "conversation_summary": conversation_summary,
        }

    async def decide(
        self,
        *,
        context: RequestContext,
        user_message: str,
        thread_id: str | None = None,
        active_workflow: WorkflowType | str | None = None,
        seller_profile_id: str | None = None,
        seller_profile_status: str | None = None,
        icp_profile_id: str | None = None,
        icp_profile_status: str | None = None,
        selected_account_id: str | None = None,
        selected_contact_id: str | None = None,
        latest_run_status: WorkflowRunStatus | str | None = None,
        conversation_summary: str | None = None,
    ) -> OrchestratorDecision:
        orchestrator_input = self.build_orchestrator_input(
            context=context,
            user_message=user_message,
            thread_id=thread_id,
            active_workflow=active_workflow,
            seller_profile_id=seller_profile_id,
            seller_profile_status=seller_profile_status,
            icp_profile_id=icp_profile_id,
            icp_profile_status=icp_profile_status,
            selected_account_id=selected_account_id,
            selected_contact_id=selected_contact_id,
            latest_run_status=latest_run_status,
            conversation_summary=conversation_summary,
        )
        return await self._orchestrator.decide(orchestrator_input)

    async def normalize_chat_turn_input(
        self,
        *,
        context: RequestContext,
        user_message: str,
        thread_id: UUID | None = None,
        active_workflow: WorkflowType | str | None = None,
        seller_profile_id: UUID | None = None,
        icp_profile_id: UUID | None = None,
        selected_account_id: UUID | None = None,
        selected_contact_id: UUID | None = None,
    ) -> OrchestratorInput:
        if context["tenant_id"] is None:
            raise ServiceError(
                status_code=400,
                error_code="tenant_context_required",
                message="Tenant context is required to normalize chat turns.",
            )

        tenant_id = UUID(context["tenant_id"])
        thread = None
        persisted_context: dict[str, str] = {}
        persisted_active_workflow: WorkflowType | None = None
        persisted_seller_profile_id: UUID | None = None
        latest_run_status: WorkflowRunStatus | None = None
        conversation_summary: str | None = None

        if thread_id is not None:
            thread = await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
            persisted_context = _normalize_context_json(thread.context_json)
            persisted_seller_profile_id = thread.seller_profile_id
            persisted_active_workflow = (
                WorkflowType(thread.active_workflow) if thread.active_workflow is not None else None
            )
            conversation_summary = thread.summary_text
            if thread.current_run_id is not None:
                run = await self._runs.get_for_tenant(
                    tenant_id=tenant_id,
                    run_id=thread.current_run_id,
                )
                if run is not None:
                    latest_run_status = WorkflowRunStatus(run.status)

        normalized_seller_profile_id = await self._resolve_seller_profile_id(
            tenant_id=tenant_id,
            explicit_seller_profile_id=seller_profile_id,
            persisted_seller_profile_id=persisted_seller_profile_id,
        )
        normalized_icp_profile_id = await self._resolve_icp_profile_id(
            tenant_id=tenant_id,
            explicit_icp_profile_id=icp_profile_id,
            persisted_context=persisted_context,
            seller_profile_id=normalized_seller_profile_id,
            explicit_seller_profile_id=seller_profile_id,
        )
        normalized_account_id = await self._resolve_account_id(
            tenant_id=tenant_id,
            explicit_account_id=selected_account_id,
            persisted_context=persisted_context,
        )
        normalized_contact_id = await self._resolve_contact_id(
            tenant_id=tenant_id,
            explicit_contact_id=selected_contact_id,
            persisted_context=persisted_context,
            selected_account_id=normalized_account_id,
            explicit_account_id=selected_account_id,
        )
        normalized_workflow = (
            WorkflowType(active_workflow) if isinstance(active_workflow, str) else active_workflow
        ) or persisted_active_workflow

        return self.build_orchestrator_input(
            context=context,
            user_message=user_message,
            thread_id=str(thread.id) if thread is not None else None,
            active_workflow=normalized_workflow,
            seller_profile_id=(
                str(normalized_seller_profile_id)
                if normalized_seller_profile_id is not None
                else None
            ),
            icp_profile_id=(
                str(normalized_icp_profile_id) if normalized_icp_profile_id is not None else None
            ),
            selected_account_id=(
                str(normalized_account_id) if normalized_account_id is not None else None
            ),
            selected_contact_id=(
                str(normalized_contact_id) if normalized_contact_id is not None else None
            ),
            latest_run_status=latest_run_status,
            conversation_summary=conversation_summary,
        )

    async def record_user_turn(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        request_id: str,
        request_payload_json: dict[str, Any],
        user_message: str,
        thread_id: UUID | None = None,
        seller_profile_id: UUID | None = None,
        icp_profile_id: UUID | None = None,
        selected_account_id: UUID | None = None,
        selected_contact_id: UUID | None = None,
        active_workflow: WorkflowType | str | None = None,
        summary_text: str | None = None,
    ) -> tuple[ConversationThread, ConversationMessage]:
        normalized_workflow = (
            WorkflowType(active_workflow) if isinstance(active_workflow, str) else active_workflow
        )
        thread = await self._get_or_create_thread_for_turn(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            thread_id=thread_id,
            seller_profile_id=seller_profile_id,
            icp_profile_id=icp_profile_id,
            selected_account_id=selected_account_id,
            selected_contact_id=selected_contact_id,
            active_workflow=normalized_workflow,
            summary_text=summary_text,
        )
        message = await self._messages.create(
            tenant_id=tenant_id,
            thread_id=thread.id,
            role="user",
            message_type="user_turn",
            content_text=user_message,
            request_id=request_id,
            request_payload_json=request_payload_json,
            created_by_user_id=created_by_user_id,
        )
        await self._session.commit()
        await self._session.refresh(thread)
        await self._session.refresh(message)
        return thread, message

    async def resolve_accepted_chat_turn(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        request_id: str,
        request_payload_json: dict[str, Any],
    ) -> AcceptedChatTurn | None:
        user_message = await self._messages.get_user_turn_by_request_id(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            request_id=request_id,
        )
        if user_message is None:
            return None

        persisted_payload = normalize_chat_turn_request_payload(
            user_message=user_message.content_text,
            thread_id=user_message.request_payload_json.get("thread_id")
            if isinstance(user_message.request_payload_json, dict)
            else None,
            seller_profile_id=user_message.request_payload_json.get("seller_profile_id")
            if isinstance(user_message.request_payload_json, dict)
            else None,
            icp_profile_id=user_message.request_payload_json.get("icp_profile_id")
            if isinstance(user_message.request_payload_json, dict)
            else None,
            selected_account_id=user_message.request_payload_json.get("selected_account_id")
            if isinstance(user_message.request_payload_json, dict)
            else None,
            selected_contact_id=user_message.request_payload_json.get("selected_contact_id")
            if isinstance(user_message.request_payload_json, dict)
            else None,
            active_workflow=user_message.request_payload_json.get("active_workflow")
            if isinstance(user_message.request_payload_json, dict)
            else None,
        )
        if persisted_payload != request_payload_json:
            raise ServiceError(
                status_code=409,
                error_code="request_id_conflict",
                message="X-Request-ID was already accepted for a different chat turn payload.",
            )

        thread = await self._require_thread(
            tenant_id=tenant_id,
            thread_id=user_message.thread_id,
        )
        response_message = await self._find_response_message_for_user_turn(
            tenant_id=tenant_id,
            thread_id=thread.id,
            user_message_id=user_message.id,
        )
        return AcceptedChatTurn(
            thread=thread,
            user_message=user_message,
            response_message=response_message,
        )

    async def append_assistant_reply(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        reply_message: str,
        run_id: UUID | None = None,
    ) -> ConversationMessage:
        await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        message = await self._messages.create(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            role="assistant",
            message_type="assistant_reply",
            content_text=reply_message,
        )
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def append_workflow_status_message(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        workflow_run_id: UUID,
        content_text: str,
    ) -> ConversationMessage:
        await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        message = await self._messages.create(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=workflow_run_id,
            role="system",
            message_type="workflow_status",
            content_text=content_text,
        )
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def attach_run_to_thread(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        workflow_run_id: UUID,
        active_workflow: WorkflowType | str | None = None,
    ) -> ConversationThread:
        thread = await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        normalized_workflow = (
            WorkflowType(active_workflow) if isinstance(active_workflow, str) else active_workflow
        )
        updated_thread = await self._threads.update(
            tenant_id=tenant_id,
            thread_id=thread.id,
            changes={
                "current_run_id": workflow_run_id,
                "active_workflow": (
                    normalized_workflow.value if normalized_workflow is not None else None
                ),
            },
        )
        assert updated_thread is not None
        await self._session.commit()
        await self._session.refresh(updated_thread)
        return updated_thread

    async def get_current_run_for_thread(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> WorkflowRun | None:
        thread = await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        if thread.current_run_id is None:
            return None
        current_run = await self._runs.get_for_tenant(
            tenant_id=tenant_id,
            run_id=thread.current_run_id,
        )
        if current_run is not None:
            await self._session.refresh(current_run)
        return current_run

    async def get_workflow_run_for_request(
        self,
        *,
        tenant_id: UUID,
        request_id: str,
    ) -> WorkflowRun | None:
        return await self._runs.get_by_correlation_id(
            tenant_id=tenant_id,
            correlation_id=request_id,
        )

    async def start_workflow_run(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        created_by_user_id: UUID,
        request_id: str,
        workflow_type: WorkflowType,
        user_message: str,
        seller_profile_id: str | None,
        icp_profile_id: str | None,
        selected_account_id: str | None,
        executor: WorkflowExecutor,
    ) -> tuple[WorkflowRun, ConversationMessage]:
        run_service = WorkflowRunService(self._session, executor=executor)
        run = await self._runs.get_by_correlation_id(
            tenant_id=tenant_id,
            correlation_id=request_id,
        )
        if run is None:
            requested_payload_json = _build_workflow_requested_payload(
                workflow_type=workflow_type,
                user_message=user_message,
                seller_profile_id=seller_profile_id,
                icp_profile_id=icp_profile_id,
                selected_account_id=selected_account_id,
            )
            run = await run_service.create_queued_run(
                tenant_id=tenant_id,
                created_by_user_id=created_by_user_id,
                workflow_type=workflow_type,
                requested_payload_json=requested_payload_json,
                thread_id=thread_id,
                correlation_id=request_id,
                status_detail=f"Queued {workflow_type.value} workflow run from chat.",
            )
        elif WorkflowType(run.workflow_type) is not workflow_type:
            raise ServiceError(
                status_code=409,
                error_code="request_id_conflict",
                message="X-Request-ID is already linked to a different workflow run.",
            )

        run, assistant_message = await self._materialize_workflow_start_outcome(
            tenant_id=tenant_id,
            thread_id=thread_id,
            workflow_run=run,
            workflow_type=workflow_type,
        )

        if WorkflowRunStatus(run.status) is WorkflowRunStatus.QUEUED:
            try:
                await run_service.dispatch_queued_run(run=run, request_id=request_id)
            except (LookupError, RuntimeError):
                await self._ensure_run_message(
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    workflow_run_id=run.id,
                    role="system",
                    message_type="workflow_status",
                    content_text=_workflow_dispatch_pending_message(workflow_type=workflow_type),
                )
            except Exception:
                current_run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run.id)
                if current_run is None:
                    raise
                await self._session.refresh(current_run)
                run = current_run

        current_run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run.id)
        if current_run is not None:
            await self._session.refresh(current_run)
            return current_run, assistant_message
        return run, assistant_message

    async def repair_accepted_workflow_turn(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        request_id: str,
        executor: WorkflowExecutor,
    ) -> tuple[WorkflowRun, ConversationMessage] | None:
        workflow_run = await self.get_workflow_run_for_request(
            tenant_id=tenant_id,
            request_id=request_id,
        )
        if workflow_run is None:
            return None
        workflow_type = WorkflowType(workflow_run.workflow_type)
        return await self.start_workflow_run(
            tenant_id=tenant_id,
            thread_id=thread_id,
            created_by_user_id=workflow_run.created_by_user_id,
            request_id=request_id,
            workflow_type=workflow_type,
            user_message="",
            seller_profile_id=None,
            icp_profile_id=None,
            selected_account_id=None,
            executor=executor,
        )

    async def _materialize_workflow_start_outcome(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        workflow_run: WorkflowRun,
        workflow_type: WorkflowType,
    ) -> tuple[WorkflowRun, ConversationMessage]:
        thread = await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        if workflow_run.thread_id is None:
            updated_run = await self._runs.update(
                tenant_id=tenant_id,
                run_id=workflow_run.id,
                changes={"thread_id": thread.id},
            )
            assert updated_run is not None
            workflow_run = updated_run
        elif workflow_run.thread_id != thread.id:
            raise ServiceError(
                status_code=409,
                error_code="request_id_conflict",
                message="X-Request-ID is already linked to a different conversation thread.",
            )

        thread_changes: dict[str, object | None] = {}
        if thread.current_run_id != workflow_run.id:
            thread_changes["current_run_id"] = workflow_run.id
        if thread.active_workflow != workflow_type.value:
            thread_changes["active_workflow"] = workflow_type.value
        if thread_changes:
            updated_thread = await self._threads.update(
                tenant_id=tenant_id,
                thread_id=thread.id,
                changes=thread_changes,
            )
            assert updated_thread is not None
            thread = updated_thread

        thread_messages = list(
            await self._messages.list_for_thread(
                tenant_id=tenant_id,
                thread_id=thread.id,
            )
        )
        run_messages = list(
            await self._messages.list_for_run(
                tenant_id=tenant_id,
                run_id=workflow_run.id,
            )
        )
        assistant_message = _find_run_message(
            run_messages=run_messages,
            role="assistant",
            message_type="assistant_reply",
        )
        message_time = _next_message_time(thread_messages[-1].created_at if thread_messages else None)
        if assistant_message is None:
            assistant_message = await self._messages.create(
                tenant_id=tenant_id,
                thread_id=thread.id,
                run_id=workflow_run.id,
                role="assistant",
                message_type="assistant_reply",
                content_text=_workflow_initial_assistant_reply(workflow_type=workflow_type),
                created_at=message_time,
            )

        queued_status_text = _workflow_status_message_text(
            workflow_type=workflow_type,
            status=WorkflowRunStatus.QUEUED,
        )
        if not _has_run_message(
            run_messages=run_messages,
            role="system",
            message_type="workflow_status",
            content_text=queued_status_text,
        ):
            await self._messages.create(
                tenant_id=tenant_id,
                thread_id=thread.id,
                run_id=workflow_run.id,
                role="system",
                message_type="workflow_status",
                content_text=queued_status_text,
                created_at=message_time + timedelta(microseconds=1),
            )

        await self._session.commit()
        await self._session.refresh(workflow_run)
        await self._session.refresh(assistant_message)
        return workflow_run, assistant_message

    async def _ensure_run_message(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        workflow_run_id: UUID,
        role: str,
        message_type: str,
        content_text: str,
    ) -> ConversationMessage:
        run_messages = list(
            await self._messages.list_for_run(
                tenant_id=tenant_id,
                run_id=workflow_run_id,
            )
        )
        existing_message = _find_run_message(
            run_messages=run_messages,
            role=role,
            message_type=message_type,
            content_text=content_text,
        )
        if existing_message is not None:
            return existing_message

        message = await self._messages.create(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=workflow_run_id,
            role=role,
            message_type=message_type,
            content_text=content_text,
        )
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def get_thread_for_tenant(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> ConversationThread | None:
        return await self._threads.get_for_tenant(tenant_id=tenant_id, thread_id=thread_id)

    async def list_messages_for_thread(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        return list(await self._messages.list_for_thread(tenant_id=tenant_id, thread_id=thread_id))

    async def find_response_message_for_turn(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        user_message_id: UUID,
    ) -> ConversationMessage | None:
        return await self._find_response_message_for_user_turn(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_message_id=user_message_id,
        )

    async def _get_or_create_thread_for_turn(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        thread_id: UUID | None,
        seller_profile_id: UUID | None,
        icp_profile_id: UUID | None,
        selected_account_id: UUID | None,
        selected_contact_id: UUID | None,
        active_workflow: WorkflowType | None,
        summary_text: str | None,
    ) -> ConversationThread:
        context_json = _build_context_json(
            icp_profile_id=icp_profile_id,
            selected_account_id=selected_account_id,
            selected_contact_id=selected_contact_id,
        )
        if thread_id is None:
            return await self._threads.create(
                tenant_id=tenant_id,
                created_by_user_id=created_by_user_id,
                seller_profile_id=seller_profile_id,
                active_workflow=active_workflow.value if active_workflow is not None else None,
                summary_text=summary_text,
                context_json=context_json,
            )

        thread = await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        changes: dict[str, object | None] = {}
        if seller_profile_id is not None and seller_profile_id != thread.seller_profile_id:
            changes["seller_profile_id"] = seller_profile_id
        if active_workflow is not None and active_workflow.value != thread.active_workflow:
            changes["active_workflow"] = active_workflow.value
        if summary_text is not None and summary_text != thread.summary_text:
            changes["summary_text"] = summary_text
        merged_context = _merge_context_json(
            current_context=thread.context_json,
            seller_profile_changed=seller_profile_id is not None
            and seller_profile_id != thread.seller_profile_id,
            icp_profile_id=icp_profile_id,
            selected_account_id=selected_account_id,
            selected_contact_id=selected_contact_id,
        )
        if merged_context != _normalize_context_json(thread.context_json):
            changes["context_json"] = merged_context or None

        if changes:
            updated_thread = await self._threads.update(
                tenant_id=tenant_id,
                thread_id=thread.id,
                changes=changes,
            )
            assert updated_thread is not None
            return updated_thread
        return thread

    async def _find_response_message_for_user_turn(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        user_message_id: UUID,
    ) -> ConversationMessage | None:
        messages = await self._messages.list_for_thread(
            tenant_id=tenant_id,
            thread_id=thread_id,
        )
        found_user_turn = False
        for message in messages:
            if not found_user_turn:
                if message.id == user_message_id:
                    found_user_turn = True
                continue

            if message.message_type == "user_turn":
                return None
            if message.role == "assistant" and message.message_type == "assistant_reply":
                return message
        return None

    async def _require_thread(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> ConversationThread:
        thread = await self._threads.get_for_tenant(tenant_id=tenant_id, thread_id=thread_id)
        if thread is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Conversation thread was not found in the requested tenant.",
            )
        return thread

    async def _resolve_seller_profile_id(
        self,
        *,
        tenant_id: UUID,
        explicit_seller_profile_id: UUID | None,
        persisted_seller_profile_id: UUID | None,
    ) -> UUID | None:
        if explicit_seller_profile_id is not None:
            await self._require_seller_profile(
                tenant_id=tenant_id,
                seller_profile_id=explicit_seller_profile_id,
            )
            return explicit_seller_profile_id

        if persisted_seller_profile_id is not None:
            await self._require_seller_profile(
                tenant_id=tenant_id,
                seller_profile_id=persisted_seller_profile_id,
            )
        return persisted_seller_profile_id

    async def _resolve_icp_profile_id(
        self,
        *,
        tenant_id: UUID,
        explicit_icp_profile_id: UUID | None,
        persisted_context: dict[str, str],
        seller_profile_id: UUID | None,
        explicit_seller_profile_id: UUID | None,
    ) -> UUID | None:
        if explicit_icp_profile_id is not None:
            icp_profile = await self._require_icp_profile(
                tenant_id=tenant_id,
                icp_profile_id=explicit_icp_profile_id,
            )
            if seller_profile_id is not None and icp_profile.seller_profile_id != seller_profile_id:
                raise ServiceError(
                    status_code=409,
                    error_code="ownership_conflict",
                    message="ICP profile does not belong to the selected seller profile.",
                )
            return explicit_icp_profile_id

        persisted_icp_profile_id = _get_uuid_from_context(
            persisted_context=persisted_context,
            field_name="icp_profile_id",
        )
        if persisted_icp_profile_id is None:
            return None

        persisted_icp_profile = await self._require_icp_profile(
            tenant_id=tenant_id,
            icp_profile_id=persisted_icp_profile_id,
        )
        if (
            explicit_seller_profile_id is not None
            and seller_profile_id is not None
            and persisted_icp_profile.seller_profile_id != seller_profile_id
        ):
            return None
        if (
            seller_profile_id is not None
            and explicit_seller_profile_id is None
            and persisted_icp_profile.seller_profile_id != seller_profile_id
        ):
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Persisted ICP profile does not belong to the selected seller profile.",
            )
        return persisted_icp_profile_id

    async def _resolve_account_id(
        self,
        *,
        tenant_id: UUID,
        explicit_account_id: UUID | None,
        persisted_context: dict[str, str],
    ) -> UUID | None:
        if explicit_account_id is not None:
            await self._require_account(
                tenant_id=tenant_id,
                account_id=explicit_account_id,
            )
            return explicit_account_id

        persisted_account_id = _get_uuid_from_context(
            persisted_context=persisted_context,
            field_name="selected_account_id",
        )
        if persisted_account_id is not None:
            await self._require_account(
                tenant_id=tenant_id,
                account_id=persisted_account_id,
            )
        return persisted_account_id

    async def _resolve_contact_id(
        self,
        *,
        tenant_id: UUID,
        explicit_contact_id: UUID | None,
        persisted_context: dict[str, str],
        selected_account_id: UUID | None,
        explicit_account_id: UUID | None,
    ) -> UUID | None:
        if explicit_contact_id is not None:
            contact = await self._require_contact(
                tenant_id=tenant_id,
                contact_id=explicit_contact_id,
            )
            if selected_account_id is not None and contact.account_id != selected_account_id:
                raise ServiceError(
                    status_code=409,
                    error_code="ownership_conflict",
                    message="Selected contact does not belong to the selected account.",
                )
            return explicit_contact_id

        persisted_contact_id = _get_uuid_from_context(
            persisted_context=persisted_context,
            field_name="selected_contact_id",
        )
        if persisted_contact_id is None:
            return None

        persisted_contact = await self._require_contact(
            tenant_id=tenant_id,
            contact_id=persisted_contact_id,
        )
        if (
            explicit_account_id is not None
            and selected_account_id is not None
            and persisted_contact.account_id != selected_account_id
        ):
            return None
        if (
            selected_account_id is not None
            and explicit_account_id is None
            and persisted_contact.account_id != selected_account_id
        ):
            raise ServiceError(
                status_code=409,
                error_code="ownership_conflict",
                message="Persisted contact does not belong to the selected account.",
            )
        return persisted_contact_id

    async def _require_seller_profile(
        self,
        *,
        tenant_id: UUID,
        seller_profile_id: UUID,
    ) -> Any:
        seller_profile = await self._seller_profiles.get_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=seller_profile_id,
        )
        if seller_profile is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Seller profile was not found in the requested tenant.",
            )
        return seller_profile

    async def _require_icp_profile(
        self,
        *,
        tenant_id: UUID,
        icp_profile_id: UUID,
    ) -> Any:
        icp_profile = await self._icp_profiles.get_for_tenant(
            tenant_id=tenant_id,
            icp_profile_id=icp_profile_id,
        )
        if icp_profile is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="ICP profile was not found in the requested tenant.",
            )
        return icp_profile

    async def _require_account(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
    ) -> Any:
        account = await self._accounts.get_for_tenant(
            tenant_id=tenant_id,
            account_id=account_id,
        )
        if account is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Account was not found in the requested tenant.",
            )
        return account

    async def _require_contact(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> Any:
        contact = await self._contacts.get_for_tenant(
            tenant_id=tenant_id,
            contact_id=contact_id,
        )
        if contact is None:
            raise ServiceError(
                status_code=404,
                error_code="resource_not_found",
                message="Contact was not found in the requested tenant.",
            )
        return contact


def _build_context_json(
    *,
    icp_profile_id: UUID | None,
    selected_account_id: UUID | None,
    selected_contact_id: UUID | None,
) -> dict[str, str] | None:
    context_json = {
        "icp_profile_id": str(icp_profile_id) if icp_profile_id is not None else None,
        "selected_account_id": (
            str(selected_account_id) if selected_account_id is not None else None
        ),
        "selected_contact_id": (
            str(selected_contact_id) if selected_contact_id is not None else None
        ),
    }
    normalized_context = {
        field_name: field_value
        for field_name, field_value in context_json.items()
        if field_value is not None
    }
    return normalized_context or None


def _merge_context_json(
    *,
    current_context: dict[str, Any] | None,
    seller_profile_changed: bool,
    icp_profile_id: UUID | None,
    selected_account_id: UUID | None,
    selected_contact_id: UUID | None,
) -> dict[str, str]:
    merged_context = _normalize_context_json(current_context)
    if seller_profile_changed and icp_profile_id is None:
        merged_context.pop("icp_profile_id", None)
    if icp_profile_id is not None:
        merged_context["icp_profile_id"] = str(icp_profile_id)
    if selected_account_id is not None:
        if merged_context.get("selected_account_id") != str(selected_account_id):
            merged_context.pop("selected_contact_id", None)
        merged_context["selected_account_id"] = str(selected_account_id)
    if selected_contact_id is not None:
        merged_context["selected_contact_id"] = str(selected_contact_id)
    return merged_context


def _normalize_context_json(context_json: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(context_json, dict):
        return {}
    return {
        field_name: str(field_value)
        for field_name, field_value in context_json.items()
        if field_name in THREAD_CONTEXT_FIELDS and field_value is not None
    }


def _get_uuid_from_context(
    *,
    persisted_context: dict[str, str],
    field_name: str,
) -> UUID | None:
    raw_value = persisted_context.get(field_name)
    if raw_value is None:
        return None
    return UUID(raw_value)


def normalize_chat_turn_request_payload(
    *,
    user_message: str,
    thread_id: UUID | str | None = None,
    seller_profile_id: UUID | str | None = None,
    icp_profile_id: UUID | str | None = None,
    selected_account_id: UUID | str | None = None,
    selected_contact_id: UUID | str | None = None,
    active_workflow: WorkflowType | str | None = None,
) -> dict[str, str | None]:
    normalized_workflow = (
        active_workflow.value if isinstance(active_workflow, WorkflowType) else active_workflow
    )
    return {
        "user_message": user_message,
        "thread_id": str(thread_id) if thread_id is not None else None,
        "seller_profile_id": (str(seller_profile_id) if seller_profile_id is not None else None),
        "icp_profile_id": str(icp_profile_id) if icp_profile_id is not None else None,
        "selected_account_id": (
            str(selected_account_id) if selected_account_id is not None else None
        ),
        "selected_contact_id": (
            str(selected_contact_id) if selected_contact_id is not None else None
        ),
        "active_workflow": normalized_workflow,
    }


def _find_run_message(
    *,
    run_messages: list[ConversationMessage],
    role: str,
    message_type: str,
    content_text: str | None = None,
) -> ConversationMessage | None:
    for message in run_messages:
        if message.role != role or message.message_type != message_type:
            continue
        if content_text is not None and message.content_text != content_text:
            continue
        return message
    return None


def _has_run_message(
    *,
    run_messages: list[ConversationMessage],
    role: str,
    message_type: str,
    content_text: str,
) -> bool:
    return (
        _find_run_message(
            run_messages=run_messages,
            role=role,
            message_type=message_type,
            content_text=content_text,
        )
        is not None
    )


def _build_workflow_requested_payload(
    *,
    workflow_type: WorkflowType,
    user_message: str,
    seller_profile_id: str | None,
    icp_profile_id: str | None,
    selected_account_id: str | None,
) -> dict[str, Any]:
    seller_uuid = _require_workflow_context_uuid(
        field_name="seller_profile_id",
        value=seller_profile_id,
        workflow_type=workflow_type,
    )
    if workflow_type is WorkflowType.ACCOUNT_SEARCH:
        icp_uuid = _require_workflow_context_uuid(
            field_name="icp_profile_id",
            value=icp_profile_id,
            workflow_type=workflow_type,
        )
        return AccountSearchWorkflowInput(
            seller_profile_id=seller_uuid,
            icp_profile_id=icp_uuid,
            search_objective=user_message,
        ).model_dump(mode="json")

    account_uuid = _require_workflow_context_uuid(
        field_name="selected_account_id",
        value=selected_account_id,
        workflow_type=workflow_type,
    )
    if workflow_type is WorkflowType.ACCOUNT_RESEARCH:
        return AccountResearchWorkflowInput(
            account_id=account_uuid,
            seller_profile_id=seller_uuid,
            icp_profile_id=UUID(icp_profile_id) if icp_profile_id is not None else None,
            research_objective=user_message,
        ).model_dump(mode="json")

    return ContactSearchWorkflowInput(
        account_id=account_uuid,
        seller_profile_id=seller_uuid,
        icp_profile_id=UUID(icp_profile_id) if icp_profile_id is not None else None,
        contact_objective=user_message,
    ).model_dump(mode="json")


def _require_workflow_context_uuid(
    *,
    field_name: str,
    value: str | None,
    workflow_type: WorkflowType,
) -> UUID:
    if value is None:
        raise ServiceError(
            status_code=409,
            error_code="workflow_context_missing",
            message=f"{field_name} is required to start {workflow_type.value}.",
        )
    return UUID(value)


def _workflow_dispatch_pending_message(*, workflow_type: WorkflowType) -> str:
    workflow_label = workflow_type.value.replace("_", " ")
    return (
        f"I saved the {workflow_label} request, but execution has not started yet. "
        "The workflow run remains queued for this thread."
    )


def _workflow_initial_assistant_reply(*, workflow_type: WorkflowType) -> str:
    workflow_label = workflow_type.value.replace("_", " ")
    return (
        f"I accepted your {workflow_label} request. "
        "I will keep this thread updated as the workflow progresses."
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _next_message_time(reference: datetime | None) -> datetime:
    candidate = _utc_now()
    if reference is None:
        return candidate
    reference_time = reference
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    else:
        reference_time = reference_time.astimezone(timezone.utc)
    return max(candidate, reference_time + timedelta(microseconds=1))


def _workflow_status_message_text(
    *,
    workflow_type: WorkflowType,
    status: WorkflowRunStatus,
) -> str:
    workflow_label = workflow_type.value.replace("_", " ")
    if status is WorkflowRunStatus.QUEUED:
        return f"I queued the {workflow_label} workflow for this thread."
    if status is WorkflowRunStatus.RUNNING:
        return f"I started the {workflow_label} workflow for this thread."
    if status is WorkflowRunStatus.AWAITING_REVIEW:
        return f"The {workflow_label} workflow is waiting for review."
    if status is WorkflowRunStatus.SUCCEEDED:
        return f"The {workflow_label} workflow finished successfully."
    if status is WorkflowRunStatus.FAILED:
        return f"The {workflow_label} workflow finished with a failure."
    return f"The {workflow_label} workflow was cancelled."
