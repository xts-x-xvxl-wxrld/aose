from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.orchestration.contracts import WorkflowRunStatus
from app.services.runtime import WorkflowExecutionRequest
from app.services.workflow_runs import WorkflowRunService


@dataclass(frozen=True)
class WorkflowExecutionResult:
    result_summary: str
    status: WorkflowRunStatus = WorkflowRunStatus.SUCCEEDED
    normalized_result_json: dict[str, Any] | None = None
    status_detail: str | None = None
    error_code: str | None = None
    review_reason: str | None = None
    artifact_id: UUID | None = None
    canonical_output_ids: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status in {WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING}:
            raise ValueError("WorkflowExecutionResult must use a terminal or review state.")
        if self.status is WorkflowRunStatus.FAILED and not self.error_code:
            raise ValueError("Failed workflow results require error_code.")
        if self.status is WorkflowRunStatus.AWAITING_REVIEW and not self.review_reason:
            raise ValueError("Awaiting-review workflow results require review_reason.")


class WorkflowExecutionError(Exception):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        status_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_detail = status_detail


WorkflowExecutionHandler = Callable[
    [WorkflowExecutionRequest],
    Awaitable[WorkflowExecutionResult],
]


async def execute_workflow_request(
    *,
    request: WorkflowExecutionRequest,
    run_service: WorkflowRunService,
    handler: WorkflowExecutionHandler,
) -> WorkflowExecutionResult:
    await run_service.mark_running(
        tenant_id=request.tenant_id,
        run_id=request.run_id,
        status_detail="Workflow execution started.",
    )

    try:
        result = await handler(request)
    except WorkflowExecutionError as exc:
        await run_service.mark_failed(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            error_code=exc.error_code,
            failure_summary=exc.message,
            status_detail=exc.status_detail,
        )
        return WorkflowExecutionResult(
            status=WorkflowRunStatus.FAILED,
            result_summary=exc.message,
            error_code=exc.error_code,
            status_detail=exc.status_detail,
        )
    except Exception:
        await run_service.mark_failed(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            error_code="workflow_execution_failed",
            failure_summary="Workflow execution raised an unexpected error.",
            status_detail="Unhandled workflow execution exception.",
        )
        raise

    if result.status is WorkflowRunStatus.AWAITING_REVIEW:
        await run_service.mark_awaiting_review(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            review_reason=result.review_reason or result.result_summary,
            artifact_id=result.artifact_id,
            status_detail=result.status_detail,
            normalized_result_json=result.normalized_result_json,
        )
        return result

    if result.status is WorkflowRunStatus.FAILED:
        await run_service.mark_failed(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            error_code=result.error_code or "workflow_execution_failed",
            failure_summary=result.result_summary,
            status_detail=result.status_detail,
        )
        return result

    await run_service.mark_succeeded(
        tenant_id=request.tenant_id,
        run_id=request.run_id,
        result_summary=result.result_summary,
        normalized_result_json=result.normalized_result_json,
        canonical_output_ids=result.canonical_output_ids,
        status_detail=result.status_detail,
    )
    return result
