from __future__ import annotations

import re

from app.orchestration.contracts import (
    MissingInputCode,
    OrchestratorDecision,
    OrchestratorDecisionType,
    OrchestratorInput,
    WorkflowRunStatus,
    WorkflowType,
)

_STATUS_PATTERNS = (
    r"\bstatus\b",
    r"\bprogress\b",
    r"\bupdate\b",
    r"\bwhat(?:'s| is) happening\b",
    r"\bhow(?:'s| is) it going\b",
)
_ACCOUNT_SEARCH_PATTERNS = (
    r"\bfind\b.*\b(accounts|companies|targets)\b",
    r"\bsearch\b.*\b(accounts|companies|targets)\b",
    r"\bdiscover\b.*\b(accounts|companies|targets)\b",
    r"\bmatching my icp\b",
)
_ACCOUNT_RESEARCH_PATTERNS = (
    r"\bresearch\b",
    r"\banaly[sz]e\b",
    r"\bprofile\b",
)
_CONTACT_SEARCH_PATTERNS = (
    r"\bfind\b.*\b(contacts|people|buyers|champions|stakeholders)\b",
    r"\bcontacts?\b",
    r"\bbuyers?\b",
    r"\bstakeholders?\b",
    r"\bchampions?\b",
)
_FOLLOW_UP_PATTERNS = (
    r"^go ahead[.!]?$",
    r"^continue[.!]?$",
    r"^do it[.!]?$",
    r"^run it[.!]?$",
    r"^yes[.!]?$",
    r"^sounds good[.!]?$",
)
_ACTIVE_RUN_STATUSES = {
    WorkflowRunStatus.QUEUED,
    WorkflowRunStatus.RUNNING,
}


class RulesBasedChatOrchestrator:
    async def decide(self, orchestrator_input: OrchestratorInput) -> OrchestratorDecision:
        user_message = orchestrator_input["user_message"].strip()
        active_workflow = orchestrator_input["active_workflow"]
        latest_run_status = orchestrator_input["latest_run_status"]
        requested_workflow = _infer_requested_workflow(
            user_message=user_message,
            active_workflow=active_workflow,
        )

        if latest_run_status in _ACTIVE_RUN_STATUSES:
            if _matches_any(user_message, _STATUS_PATTERNS):
                return _inline_decision(
                    reply_message=(
                        f"The current {active_workflow.value if active_workflow else 'workflow'} "
                        f"run is still {latest_run_status.value}. "
                        "I am using the durable thread state instead of starting duplicate work."
                    ),
                    reasoning_summary="reply_with_active_run_status",
                )

            if requested_workflow is not None:
                return _inline_decision(
                    reply_message=(
                        f"There is already a {latest_run_status.value} "
                        f"{active_workflow.value if active_workflow else 'workflow'} run on this thread. "
                        "I am keeping the one-active-run-per-thread rule and not starting another run yet."
                    ),
                    reasoning_summary="block_duplicate_run_while_active",
                )

        if requested_workflow is None:
            return _inline_decision(
                reply_message=(
                    "I can help find target accounts, research a selected account, "
                    "or find contacts for a selected account. "
                    "Tell me which of those you want to do next."
                ),
                reasoning_summary="reply_inline_for_ambiguous_request",
            )

        missing_inputs = _missing_inputs_for_workflow(
            workflow_type=requested_workflow,
            orchestrator_input=orchestrator_input,
        )
        if missing_inputs:
            return _inline_decision(
                reply_message=_clarification_message(
                    workflow_type=requested_workflow,
                    missing_inputs=missing_inputs,
                ),
                reasoning_summary="reply_inline_with_missing_inputs",
                missing_inputs=missing_inputs,
            )

        return {
            "decision_type": OrchestratorDecisionType.START_WORKFLOW_RUN,
            "workflow_type": requested_workflow,
            "target_agent": None,
            "reply_message": None,
            "reasoning_summary": "start_workflow_run_from_chat_contract",
            "requires_persistence": True,
            "missing_inputs": [],
            "handoff_payload": None,
            "confidence": 1.0,
        }


def infer_chat_workflow(
    *,
    user_message: str,
    active_workflow: WorkflowType | None,
) -> WorkflowType | None:
    return _infer_requested_workflow(
        user_message=user_message,
        active_workflow=active_workflow,
    )


def _infer_requested_workflow(
    *,
    user_message: str,
    active_workflow: WorkflowType | None,
) -> WorkflowType | None:
    normalized_message = user_message.strip().lower()

    if _matches_any(normalized_message, _CONTACT_SEARCH_PATTERNS):
        return WorkflowType.CONTACT_SEARCH

    if _matches_any(normalized_message, _ACCOUNT_SEARCH_PATTERNS):
        return WorkflowType.ACCOUNT_SEARCH

    if _matches_any(normalized_message, _ACCOUNT_RESEARCH_PATTERNS):
        return WorkflowType.ACCOUNT_RESEARCH

    if active_workflow is not None and _matches_any(normalized_message, _FOLLOW_UP_PATTERNS):
        return active_workflow

    return None


def _missing_inputs_for_workflow(
    *,
    workflow_type: WorkflowType,
    orchestrator_input: OrchestratorInput,
) -> list[MissingInputCode]:
    missing_inputs: list[MissingInputCode] = []

    if orchestrator_input["seller_profile_id"] is None:
        missing_inputs.append(MissingInputCode.SELLER_PROFILE_REQUIRED)

    if workflow_type is WorkflowType.ACCOUNT_SEARCH:
        if orchestrator_input["icp_profile_id"] is None:
            missing_inputs.append(MissingInputCode.ICP_PROFILE_REQUIRED)

    if workflow_type in {
        WorkflowType.ACCOUNT_RESEARCH,
        WorkflowType.CONTACT_SEARCH,
    } and orchestrator_input["selected_account_id"] is None:
        missing_inputs.append(MissingInputCode.SELECTED_ACCOUNT_REQUIRED)

    return missing_inputs


def _clarification_message(
    *,
    workflow_type: WorkflowType,
    missing_inputs: list[MissingInputCode],
) -> str:
    if workflow_type is WorkflowType.ACCOUNT_SEARCH:
        return _missing_input_message(
            missing_inputs=missing_inputs,
            closing_text="I need that context before I can start account search.",
        )
    if workflow_type is WorkflowType.ACCOUNT_RESEARCH:
        return _missing_input_message(
            missing_inputs=missing_inputs,
            closing_text="I need that context before I can start account research.",
        )
    return _missing_input_message(
        missing_inputs=missing_inputs,
        closing_text="I need that context before I can start contact search.",
    )


def _missing_input_message(
    *,
    missing_inputs: list[MissingInputCode],
    closing_text: str,
) -> str:
    fragments = [
        _missing_input_fragment(missing_input)
        for missing_input in missing_inputs
    ]
    return f"{' '.join(fragments)} {closing_text}"


def _missing_input_fragment(missing_input: MissingInputCode) -> str:
    if missing_input is MissingInputCode.SELLER_PROFILE_REQUIRED:
        return "Select the seller profile to use for this thread."
    if missing_input is MissingInputCode.ICP_PROFILE_REQUIRED:
        return "Select the ICP profile you want me to use."
    if missing_input is MissingInputCode.SELECTED_ACCOUNT_REQUIRED:
        return "Select the account you want me to use."
    return "Provide the missing context."


def _inline_decision(
    *,
    reply_message: str,
    reasoning_summary: str,
    missing_inputs: list[MissingInputCode] | None = None,
) -> OrchestratorDecision:
    return {
        "decision_type": OrchestratorDecisionType.REPLY_INLINE,
        "workflow_type": None,
        "target_agent": None,
        "reply_message": reply_message,
        "reasoning_summary": reasoning_summary,
        "requires_persistence": True,
        "missing_inputs": list(missing_inputs or []),
        "handoff_payload": None,
        "confidence": 1.0,
    }


def _matches_any(user_message: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, user_message, re.IGNORECASE) for pattern in patterns)
