from __future__ import annotations

from uuid import uuid4

import pytest

from app.orchestration.contracts import (
    MissingInputCode,
    OrchestratorDecisionType,
    WorkflowRunStatus,
    WorkflowType,
)
from app.services.chat_orchestrator import RulesBasedChatOrchestrator, infer_chat_workflow


async def _decide(**overrides: object) -> dict[str, object]:
    orchestrator = RulesBasedChatOrchestrator()
    orchestrator_input: dict[str, object] = {
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "thread_id": None,
        "user_message": "Find companies matching my ICP.",
        "active_workflow": None,
        "seller_profile_id": None,
        "seller_profile_status": None,
        "icp_profile_id": None,
        "icp_profile_status": None,
        "selected_account_id": None,
        "selected_contact_id": None,
        "latest_run_status": None,
        "conversation_summary": None,
    }
    orchestrator_input.update(overrides)
    return await orchestrator.decide(orchestrator_input)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_rules_based_chat_orchestrator_returns_missing_inputs_for_account_search() -> None:
    decision = await _decide(
        user_message="Find companies matching my ICP.",
        seller_profile_id=str(uuid4()),
    )

    assert decision["decision_type"] is OrchestratorDecisionType.REPLY_INLINE
    assert decision["missing_inputs"] == [MissingInputCode.ICP_PROFILE_REQUIRED]


@pytest.mark.asyncio
async def test_rules_based_chat_orchestrator_continues_active_workflow_for_follow_up() -> None:
    decision = await _decide(
        user_message="go ahead",
        active_workflow=WorkflowType.ACCOUNT_RESEARCH,
        seller_profile_id=str(uuid4()),
        selected_account_id=str(uuid4()),
    )

    assert decision["decision_type"] is OrchestratorDecisionType.START_WORKFLOW_RUN
    assert decision["workflow_type"] is WorkflowType.ACCOUNT_RESEARCH


@pytest.mark.asyncio
async def test_rules_based_chat_orchestrator_replies_inline_for_status_checks() -> None:
    decision = await _decide(
        user_message="what's the status?",
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
        latest_run_status=WorkflowRunStatus.RUNNING,
    )

    assert decision["decision_type"] is OrchestratorDecisionType.REPLY_INLINE
    assert decision["missing_inputs"] == []
    assert "running" in str(decision["reply_message"]).lower()


@pytest.mark.asyncio
async def test_rules_based_chat_orchestrator_blocks_duplicate_run_while_active() -> None:
    decision = await _decide(
        user_message="Research this account.",
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
        latest_run_status=WorkflowRunStatus.QUEUED,
        seller_profile_id=str(uuid4()),
        selected_account_id=str(uuid4()),
    )

    assert decision["decision_type"] is OrchestratorDecisionType.REPLY_INLINE
    assert decision["missing_inputs"] == []
    assert "not starting another run" in str(decision["reply_message"]).lower()


def test_infer_chat_workflow_prioritizes_explicit_switch_over_active_context() -> None:
    workflow = infer_chat_workflow(
        user_message="research this account",
        active_workflow=WorkflowType.ACCOUNT_SEARCH,
    )

    assert workflow is WorkflowType.ACCOUNT_RESEARCH
