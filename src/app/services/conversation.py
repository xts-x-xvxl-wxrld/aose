from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.types import RequestContext
from app.models import ConversationMessage, ConversationThread
from app.orchestration.contracts import (
    OrchestratorDecision,
    OrchestratorInput,
    WorkflowRunStatus,
    WorkflowType,
)
from app.repositories.conversation_message_repository import ConversationMessageRepository
from app.repositories.conversation_thread_repository import ConversationThreadRepository
from app.services.errors import ServiceError
from app.services.runtime import OrchestratorAdapter


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
            WorkflowType(active_workflow)
            if isinstance(active_workflow, str)
            else active_workflow
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

    async def record_user_turn(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        user_message: str,
        thread_id: UUID | None = None,
        seller_profile_id: UUID | None = None,
        active_workflow: WorkflowType | str | None = None,
        summary_text: str | None = None,
    ) -> tuple[ConversationThread, ConversationMessage]:
        normalized_workflow = (
            WorkflowType(active_workflow)
            if isinstance(active_workflow, str)
            else active_workflow
        )
        thread = await self._get_or_create_thread_for_turn(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            thread_id=thread_id,
            seller_profile_id=seller_profile_id,
            active_workflow=normalized_workflow,
            summary_text=summary_text,
        )
        message = await self._messages.create(
            tenant_id=tenant_id,
            thread_id=thread.id,
            role="user",
            message_type="user_turn",
            content_text=user_message,
            created_by_user_id=created_by_user_id,
        )
        await self._session.commit()
        await self._session.refresh(thread)
        await self._session.refresh(message)
        return thread, message

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
            WorkflowType(active_workflow)
            if isinstance(active_workflow, str)
            else active_workflow
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

    async def _get_or_create_thread_for_turn(
        self,
        *,
        tenant_id: UUID,
        created_by_user_id: UUID,
        thread_id: UUID | None,
        seller_profile_id: UUID | None,
        active_workflow: WorkflowType | None,
        summary_text: str | None,
    ) -> ConversationThread:
        if thread_id is None:
            return await self._threads.create(
                tenant_id=tenant_id,
                created_by_user_id=created_by_user_id,
                seller_profile_id=seller_profile_id,
                active_workflow=active_workflow.value if active_workflow is not None else None,
                summary_text=summary_text,
            )

        thread = await self._require_thread(tenant_id=tenant_id, thread_id=thread_id)
        changes: dict[str, object | None] = {}
        if seller_profile_id is not None and seller_profile_id != thread.seller_profile_id:
            changes["seller_profile_id"] = seller_profile_id
        if active_workflow is not None and active_workflow.value != thread.active_workflow:
            changes["active_workflow"] = active_workflow.value
        if summary_text is not None and summary_text != thread.summary_text:
            changes["summary_text"] = summary_text

        if changes:
            updated_thread = await self._threads.update(
                tenant_id=tenant_id,
                thread_id=thread.id,
                changes=changes,
            )
            assert updated_thread is not None
            return updated_thread
        return thread

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
