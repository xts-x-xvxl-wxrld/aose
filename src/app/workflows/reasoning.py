from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ReasoningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountSearchReasoningCandidate(ReasoningModel):
    name: str = Field(min_length=1)
    domain: str | None = None
    website_url: str | None = None
    hq_location: str | None = None
    industry: str | None = None
    fit_summary: str | None = None
    fit_score_0_1: float | None = Field(default=None, ge=0, le=1)
    why_selected: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    linkedin_url: str | None = None
    employee_range: str | None = None
    fit_signals_json: dict[str, Any] | None = None
    canonical_data_json: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class AccountSearchReasoningOutput(ReasoningModel):
    query_summary: str | None = None
    accepted_candidates: list[AccountSearchReasoningCandidate] = Field(default_factory=list)
    rejected_candidates: list[AccountSearchReasoningCandidate] = Field(default_factory=list)
    no_result_reason: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    missing_data_flags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class AccountResearchReasoningOutput(ReasoningModel):
    overview_summary: str
    fit_summary: str
    key_findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)
    snapshot_quality: str
    missing_context_flags: list[str] = Field(default_factory=list)
    research_brief_markdown: str | None = None


class ContactSearchReasoningCandidate(ReasoningModel):
    full_name: str = Field(min_length=1)
    email: str | None = None
    linkedin_url: str | None = None
    job_title: str | None = None
    company_domain: str | None = None
    source_provider: str | None = None
    acceptance_reason: str | None = None
    confidence_0_1: float | None = Field(default=None, ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    phone: str | None = None
    ranking_summary: str | None = None
    persona_match_summary: str | None = None
    person_data_json: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ContactSearchReasoningOutput(ReasoningModel):
    accepted_contacts: list[ContactSearchReasoningCandidate] = Field(default_factory=list)
    rejected_contacts: list[ContactSearchReasoningCandidate] = Field(default_factory=list)
    ranking_notes: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    missing_data_flags: list[str] = Field(default_factory=list)
    target_personas: list[str] = Field(default_factory=list)
    selection_criteria: list[str] = Field(default_factory=list)


def build_account_search_prompt_spec() -> str:
    return (
        "Extract only defensible target accounts from gathered search evidence. "
        "Prefer precision over recall, keep missing fields explicit, and reject weak matches."
    )


def build_account_research_prompt_spec() -> str:
    return (
        "Synthesize a compact, evidence-backed research snapshot. "
        "State uncertainty directly and never imply ICP-fit certainty without supporting context."
    )


def build_contact_search_prompt_spec() -> str:
    return (
        "Rank provider-backed contact candidates for the selected account. "
        "Preserve acceptance reasons, confidence limits, and missing-data flags."
    )


def validate_account_search_reasoning(
    payload: dict[str, Any] | list[dict[str, Any]] | None,
) -> AccountSearchReasoningOutput | None:
    if payload is None:
        return None
    if isinstance(payload, list):
        normalized_payload: dict[str, Any] = {
            "accepted_candidates": payload,
            "rejected_candidates": [],
            "missing_data_flags": [],
            "evidence_refs": [],
        }
    elif isinstance(payload, dict):
        normalized_payload = dict(payload)
        if "candidates" in normalized_payload and "accepted_candidates" not in normalized_payload:
            normalized_payload["accepted_candidates"] = normalized_payload.pop("candidates")
        if "accepted_candidates" not in normalized_payload:
            normalized_payload["accepted_candidates"] = []
        if "rejected_candidates" not in normalized_payload:
            normalized_payload["rejected_candidates"] = []
    else:
        return None
    return _validate_model(AccountSearchReasoningOutput, normalized_payload)


def validate_account_research_reasoning(
    payload: dict[str, Any] | list[dict[str, Any]] | None,
) -> AccountResearchReasoningOutput | None:
    if not isinstance(payload, dict):
        return None
    normalized_payload = dict(payload)
    if "structured_research_summary" in normalized_payload:
        structured = normalized_payload.get("structured_research_summary") or {}
        if isinstance(structured, dict):
            normalized_payload = {
                "overview_summary": structured.get("account_overview"),
                "fit_summary": structured.get("fit_to_icp")
                or structured.get("fit_to_seller_proposition")
                or normalized_payload.get("qualification_summary"),
                "key_findings": list(structured.get("buying_relevance_signals") or []),
                "risks": list(structured.get("risks_or_disqualifiers") or []),
                "uncertainty_notes": list(normalized_payload.get("uncertainty_notes") or []),
                "evidence_ref_ids": [],
                "snapshot_quality": "high" if structured.get("buying_relevance_signals") else "medium",
                "missing_context_flags": [],
                "research_brief_markdown": normalized_payload.get("research_brief_markdown"),
            }
    return _validate_model(AccountResearchReasoningOutput, normalized_payload)


def validate_contact_search_reasoning(
    payload: dict[str, Any] | list[dict[str, Any]] | None,
) -> ContactSearchReasoningOutput | None:
    if payload is None:
        return None
    if isinstance(payload, list):
        normalized_payload: dict[str, Any] = {
            "accepted_contacts": payload,
            "rejected_contacts": [],
            "ranking_notes": "Ranked normalized contact candidates from provider-backed evidence.",
            "missing_data_flags": [],
            "target_personas": [],
            "selection_criteria": [],
        }
    elif isinstance(payload, dict):
        normalized_payload = dict(payload)
        if "contacts" in normalized_payload and "accepted_contacts" not in normalized_payload:
            normalized_payload["accepted_contacts"] = normalized_payload.pop("contacts")
        if "ranked_contact_rationale" in normalized_payload and "ranking_notes" not in normalized_payload:
            normalized_payload["ranking_notes"] = normalized_payload.pop("ranked_contact_rationale")
        if "accepted_contacts" not in normalized_payload:
            normalized_payload["accepted_contacts"] = []
        if "rejected_contacts" not in normalized_payload:
            normalized_payload["rejected_contacts"] = []
    else:
        return None
    normalized_payload["accepted_contacts"] = _normalize_contact_reasoning_candidates(
        normalized_payload.get("accepted_contacts")
    )
    normalized_payload["rejected_contacts"] = _normalize_contact_reasoning_candidates(
        normalized_payload.get("rejected_contacts")
    )
    return _validate_model(ContactSearchReasoningOutput, normalized_payload)


def _validate_model(model_cls: type[BaseModel], payload: dict[str, Any]) -> BaseModel | None:
    try:
        return model_cls.model_validate(payload)
    except ValidationError:
        return None


def _normalize_contact_reasoning_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized_candidates: list[dict[str, Any]] = []
    for candidate in value:
        if not isinstance(candidate, dict):
            continue
        normalized_candidate = dict(candidate)
        if (
            "missing_data_flags" in normalized_candidate
            and "missing_fields" not in normalized_candidate
        ):
            normalized_candidate["missing_fields"] = normalized_candidate.pop(
                "missing_data_flags"
            )
        if (
            "confidence_score" in normalized_candidate
            and "confidence_0_1" not in normalized_candidate
        ):
            normalized_candidate["confidence_0_1"] = normalized_candidate.pop(
                "confidence_score"
            )
        normalized_candidates.append(normalized_candidate)
    return normalized_candidates
