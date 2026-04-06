from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ChatRequestIdDep,
    DbSessionDep,
    PersistedActorUserDep,
    TenantRequestContextDep,
    WorkflowExecutorDep,
)
from app.orchestration.contracts import (
    OrchestratorDecision,
    OrchestratorDecisionType,
    WorkflowRunStatus,
    WorkflowType,
)
from app.schemas.chat import (
    ChatEventListResponse,
    ChatMetaEventResponse,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatThreadResponse,
    ChatTurnStreamRequest,
)
from app.services.chat_event_projection import ChatEventProjectionService
from app.services.chat_orchestrator import RulesBasedChatOrchestrator, infer_chat_workflow
from app.services.conversation import ConversationService, normalize_chat_turn_request_payload
from app.services.errors import ServiceError

router = APIRouter(prefix="/tenants/{tenant_id}/chat")


@router.post("/stream")
async def stream_chat_turn(
    tenant_id: UUID,
    payload: ChatTurnStreamRequest,
    request_context: TenantRequestContextDep,
    request_id: ChatRequestIdDep,
    actor_user: PersistedActorUserDep,
    db_session: DbSessionDep,
    workflow_executor: WorkflowExecutorDep,
) -> StreamingResponse:
    service = ConversationService(db_session, orchestrator=RulesBasedChatOrchestrator())
    projection_service = ChatEventProjectionService(db_session)
    request_payload_json = normalize_chat_turn_request_payload(
        user_message=payload.user_message,
        thread_id=payload.thread_id,
        seller_profile_id=payload.seller_profile_id,
        icp_profile_id=payload.icp_profile_id,
        selected_account_id=payload.selected_account_id,
        selected_contact_id=payload.selected_contact_id,
        active_workflow=payload.active_workflow,
    )
    chat_context = {
        **request_context,
        "user_id": str(actor_user.id),
    }
    accepted_turn = await service.resolve_accepted_chat_turn(
        tenant_id=tenant_id,
        created_by_user_id=actor_user.id,
        request_id=request_id,
        request_payload_json=request_payload_json,
    )
    if accepted_turn is not None and accepted_turn.response_message is not None:
        current_run = await service.get_current_run_for_thread(
            tenant_id=tenant_id,
            thread_id=accepted_turn.thread.id,
        )
        meta_events = (
            await projection_service.project_stream_events_for_run(
                tenant_id=tenant_id,
                run_id=current_run.id,
            )
            if current_run is not None
            else []
        )
        return _build_streaming_response(
            reply_text=accepted_turn.response_message.content_text,
            thread_id=accepted_turn.thread.id,
            request_id=request_id,
            meta_events=meta_events,
        )
    if accepted_turn is not None and accepted_turn.response_message is None:
        repaired_outcome = await service.repair_accepted_workflow_turn(
            tenant_id=tenant_id,
            thread_id=accepted_turn.thread.id,
            request_id=request_id,
            executor=workflow_executor,
        )
        if repaired_outcome is not None:
            workflow_run, response_message = repaired_outcome
            meta_events = await projection_service.project_stream_events_for_run(
                tenant_id=tenant_id,
                run_id=workflow_run.id,
            )
            return _build_streaming_response(
                reply_text=response_message.content_text,
                thread_id=accepted_turn.thread.id,
                request_id=request_id,
                meta_events=meta_events,
            )

    orchestrator_input = await service.normalize_chat_turn_input(
        context=chat_context,
        user_message=payload.user_message,
        thread_id=accepted_turn.thread.id if accepted_turn is not None else payload.thread_id,
        active_workflow=payload.active_workflow,
        seller_profile_id=payload.seller_profile_id,
        icp_profile_id=payload.icp_profile_id,
        selected_account_id=payload.selected_account_id,
        selected_contact_id=payload.selected_contact_id,
    )
    requested_workflow = infer_chat_workflow(
        user_message=payload.user_message,
        active_workflow=orchestrator_input["active_workflow"],
    )

    if accepted_turn is None:
        thread, _user_message = await service.record_user_turn(
            tenant_id=tenant_id,
            created_by_user_id=actor_user.id,
            request_id=request_id,
            request_payload_json=request_payload_json,
            user_message=payload.user_message,
            thread_id=payload.thread_id,
            seller_profile_id=_to_uuid(orchestrator_input["seller_profile_id"]),
            icp_profile_id=_to_uuid(orchestrator_input["icp_profile_id"]),
            selected_account_id=_to_uuid(orchestrator_input["selected_account_id"]),
            selected_contact_id=_to_uuid(orchestrator_input["selected_contact_id"]),
            active_workflow=requested_workflow or orchestrator_input["active_workflow"],
            summary_text=orchestrator_input["conversation_summary"],
        )
    else:
        thread = accepted_turn.thread

    decision = await service.decide(
        context=chat_context,
        user_message=orchestrator_input["user_message"],
        thread_id=str(thread.id),
        active_workflow=orchestrator_input["active_workflow"],
        seller_profile_id=orchestrator_input["seller_profile_id"],
        icp_profile_id=orchestrator_input["icp_profile_id"],
        selected_account_id=orchestrator_input["selected_account_id"],
        selected_contact_id=orchestrator_input["selected_contact_id"],
        latest_run_status=orchestrator_input["latest_run_status"],
        conversation_summary=orchestrator_input["conversation_summary"],
    )
    response_message = accepted_turn.response_message if accepted_turn is not None else None
    workflow_run_id: UUID | None = None
    if response_message is None:
        if accepted_turn is not None:
            response_message = await service.find_response_message_for_turn(
                tenant_id=tenant_id,
                thread_id=thread.id,
                user_message_id=accepted_turn.user_message.id,
            )
        if (
            response_message is None
            and decision["decision_type"] is OrchestratorDecisionType.START_WORKFLOW_RUN
            and decision["workflow_type"] is not None
        ):
            workflow_type = decision["workflow_type"]
            workflow_run, response_message = await service.start_workflow_run(
                tenant_id=tenant_id,
                thread_id=thread.id,
                created_by_user_id=actor_user.id,
                request_id=request_id,
                workflow_type=workflow_type,
                user_message=orchestrator_input["user_message"],
                seller_profile_id=orchestrator_input["seller_profile_id"],
                icp_profile_id=orchestrator_input["icp_profile_id"],
                selected_account_id=orchestrator_input["selected_account_id"],
                executor=workflow_executor,
            )
            workflow_run_id = workflow_run.id
        elif response_message is None:
            reply_text = _reply_text_for_decision(decision=decision)
            response_message = await service.append_assistant_reply(
                tenant_id=tenant_id,
                thread_id=thread.id,
                reply_message=reply_text,
            )

    if workflow_run_id is None:
        current_run = await service.get_current_run_for_thread(
            tenant_id=tenant_id,
            thread_id=thread.id,
        )
        if current_run is not None:
            workflow_run_id = current_run.id

    meta_events = (
        await projection_service.project_stream_events_for_run(
            tenant_id=tenant_id,
            run_id=workflow_run_id,
        )
        if workflow_run_id is not None
        else []
    )

    return _build_streaming_response(
        reply_text=response_message.content_text,
        thread_id=thread.id,
        request_id=request_id,
        meta_events=meta_events,
    )


@router.get("/threads/{thread_id}", response_model=ChatThreadResponse)
async def get_chat_thread(
    tenant_id: UUID,
    thread_id: UUID,
    _request_context: TenantRequestContextDep,
    db_session: DbSessionDep,
) -> ChatThreadResponse:
    service = ConversationService(db_session, orchestrator=RulesBasedChatOrchestrator())
    thread = await service.get_thread_for_tenant(tenant_id=tenant_id, thread_id=thread_id)
    if thread is None:
        raise ServiceError(
            status_code=404,
            error_code="resource_not_found",
            message="Conversation thread was not found in the requested tenant.",
        )
    return _to_thread_response(thread=thread)


@router.get("/threads/{thread_id}/messages", response_model=ChatMessageListResponse)
async def list_chat_thread_messages(
    tenant_id: UUID,
    thread_id: UUID,
    _request_context: TenantRequestContextDep,
    db_session: DbSessionDep,
) -> ChatMessageListResponse:
    service = ConversationService(db_session, orchestrator=RulesBasedChatOrchestrator())
    messages = await service.list_messages_for_thread(tenant_id=tenant_id, thread_id=thread_id)
    return ChatMessageListResponse(
        thread_id=thread_id,
        messages=[_to_message_response(message=message) for message in messages],
    )


@router.get("/events", response_model=ChatEventListResponse)
async def list_chat_events(
    tenant_id: UUID,
    _request_context: TenantRequestContextDep,
    db_session: DbSessionDep,
    thread_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatEventListResponse:
    projection_service = ChatEventProjectionService(db_session)
    events = await projection_service.list_projected_events_for_tenant(
        tenant_id=tenant_id,
        thread_id=thread_id,
        limit=limit,
        offset=offset,
    )
    return ChatEventListResponse(
        events=[_to_chat_meta_event_response(event=event) for event in events],
        limit=limit,
        offset=offset,
    )


def _to_thread_response(*, thread: Any) -> ChatThreadResponse:
    return ChatThreadResponse(
        thread_id=thread.id,
        tenant_id=thread.tenant_id,
        created_by_user_id=thread.created_by_user_id,
        seller_profile_id=thread.seller_profile_id,
        active_workflow=thread.active_workflow,
        status=thread.status,
        current_run_id=thread.current_run_id,
        summary_text=thread.summary_text,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _to_message_response(*, message: Any) -> ChatMessageResponse:
    return ChatMessageResponse(
        message_id=message.id,
        thread_id=message.thread_id,
        workflow_run_id=message.run_id,
        role=message.role,
        message_type=message.message_type,
        content_text=message.content_text,
        created_by_user_id=message.created_by_user_id,
        created_at=message.created_at,
    )


def _to_chat_meta_event_response(*, event: Any) -> ChatMetaEventResponse:
    return ChatMetaEventResponse(**event.as_dict())


def _reply_text_for_decision(*, decision: OrchestratorDecision) -> str:
    if decision["reply_message"]:
        return decision["reply_message"]

    if decision["decision_type"] is OrchestratorDecisionType.START_WORKFLOW_RUN:
        workflow_type = decision["workflow_type"]
        workflow_name = workflow_type.value if workflow_type is not None else "workflow"
        return f"I normalized this turn into the `{workflow_name}` workflow contract."

    return "Chat turn accepted."


def _to_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    return UUID(value)


def _build_streaming_response(
    *,
    reply_text: str,
    thread_id: UUID,
    request_id: str,
    meta_events: list[Any] | None = None,
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        text_frame = json.dumps(
            {
                "text": reply_text,
                "thread_id": str(thread_id),
                "request_id": request_id,
            }
        )
        yield f"data: {text_frame}\n\n"
        for meta_event in meta_events or []:
            meta_frame = json.dumps(
                {
                    "meta": meta_event.as_dict()
                }
            )
            yield f"data: {meta_frame}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
