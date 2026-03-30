from __future__ import annotations

from enum import StrEnum


class WorkflowType(StrEnum):
    SELLER_PROFILE_SETUP = "seller_profile_setup"
    ICP_PROFILE_SETUP = "icp_profile_setup"
    ACCOUNT_SEARCH = "account_search"
    ACCOUNT_RESEARCH = "account_research"
    CONTACT_SEARCH = "contact_search"


class WorkflowRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
