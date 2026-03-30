from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountSearchRunResultOutcome(StrEnum):
    NO_RESULTS = "no_results"
    ACCOUNTS_FOUND = "accounts_found"


class AccountSearchRunResult(WorkflowResultModel):
    outcome: AccountSearchRunResultOutcome
    accepted_account_ids: list[UUID] = Field(default_factory=list)
    reason_summary: str
    search_attempt_count: int = Field(ge=1, le=2)


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


class ContactSearchRunResult(WorkflowResultModel):
    outcome: ContactSearchRunResultOutcome
    contact_ids: list[UUID] = Field(default_factory=list)
    missing_data_flags: list[ContactMissingDataFlag] = Field(default_factory=list)
    used_research_snapshot_id: UUID | None = None
    reason_summary: str
