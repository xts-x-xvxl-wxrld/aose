from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountSearchRunResultOutcome(StrEnum):
    NO_RESULTS = "no_results"
    ACCOUNTS_FOUND = "accounts_found"
    ACCOUNTS_FOUND_VIA_FALLBACK = "accounts_found_via_fallback"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_FAILURE_WITH_FALLBACK_EXHAUSTED = "provider_failure_with_fallback_exhausted"


class AccountSearchRunResult(WorkflowResultModel):
    outcome: AccountSearchRunResultOutcome
    accepted_account_ids: list[UUID] = Field(default_factory=list)
    reason_summary: str
    search_attempt_count: int = Field(ge=1, le=2)
    assistant_summary: str | None = None
    summary_selection_reason: str | None = None
    primary_provider_name: str | None = None
    fallback_provider_name: str | None = None
    primary_provider_failed: bool = False
    fallback_attempted: bool = False
    fallback_used: bool = False


class AccountResearchRunResultOutcome(StrEnum):
    RESEARCH_COMPLETED = "research_completed"


class AccountResearchRunResult(WorkflowResultModel):
    outcome: AccountResearchRunResultOutcome
    snapshot_id: UUID
    snapshot_version: int = Field(ge=1)
    icp_context_present: bool
    reason_summary: str


class ContactMissingDataFlag(StrEnum):
    MISSING_EMAIL = "missing_email"
    MISSING_LINKEDIN = "missing_linkedin"
    MISSING_JOB_TITLE = "missing_job_title"
    LOW_SOURCE_CONFIDENCE = "low_source_confidence"
    ROLE_MATCH_UNCERTAIN = "role_match_uncertain"


class ContactSearchRunResultOutcome(StrEnum):
    CONTACTS_RANKED = "contacts_ranked"
    CONTACTS_RANKED_VIA_FALLBACK = "contacts_ranked_via_fallback"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_FAILURE_WITH_FALLBACK_EXHAUSTED = "provider_failure_with_fallback_exhausted"


class ContactSearchRunResult(WorkflowResultModel):
    outcome: ContactSearchRunResultOutcome
    contact_ids: list[UUID] = Field(default_factory=list)
    missing_data_flags: list[ContactMissingDataFlag] = Field(default_factory=list)
    used_research_snapshot_id: UUID | None = None
    reason_summary: str
    assistant_summary: str | None = None
    summary_selection_reason: str | None = None
    primary_provider_name: str | None = None
    fallback_provider_name: str | None = None
    primary_provider_failed: bool = False
    fallback_attempted: bool = False
    fallback_used: bool = False
