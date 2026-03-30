from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.orchestration.contracts import (
    OrchestratorDecision,
    OrchestratorInput,
    WorkflowType,
)


@dataclass(frozen=True)
class WorkflowExecutionRequest:
    run_id: UUID
    tenant_id: UUID
    created_by_user_id: UUID
    workflow_type: WorkflowType
    thread_id: UUID | None
    request_id: str | None = None


class OrchestratorAdapter(Protocol):
    async def decide(self, orchestrator_input: OrchestratorInput) -> OrchestratorDecision: ...


class WorkflowExecutor(Protocol):
    async def dispatch(self, request: WorkflowExecutionRequest) -> None: ...


WorkflowExecutionHandler = Callable[[WorkflowExecutionRequest], Awaitable[None]]


class InProcessWorkflowExecutor:
    def __init__(
        self,
        handlers: Mapping[WorkflowType, WorkflowExecutionHandler] | None = None,
    ) -> None:
        self._handlers = dict(handlers or {})

    def register_handler(
        self,
        workflow_type: WorkflowType,
        handler: WorkflowExecutionHandler,
    ) -> None:
        self._handlers[workflow_type] = handler

    async def dispatch(self, request: WorkflowExecutionRequest) -> None:
        handler = self._handlers.get(request.workflow_type)
        if handler is None:
            raise LookupError(
                f"No workflow handler is registered for {request.workflow_type.value}."
            )
        await handler(request)


async def dispatch_workflow_run(
    executor: WorkflowExecutor,
    request: WorkflowExecutionRequest,
) -> WorkflowExecutionRequest:
    await executor.dispatch(request)
    return request
