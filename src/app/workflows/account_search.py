from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ICPProfile, SellerProfile, WorkflowRun
from app.repositories.account_repository import AccountRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.workflow_runs import WorkflowRunService
from app.tools.contracts import (
    CompanyEnrichmentRequest,
    CompanyEnrichmentResponse,
    CompanyEnrichmentTool,
    ContentNormalizerRequest,
    ContentNormalizerResponse,
    ContentNormalizerTool,
    SearchResultRecord,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchTool,
    get_tool_provider_name,
)
from app.workers.runtime import WorkflowExecutionError, WorkflowExecutionResult
from app.workflows.reasoning import validate_account_search_reasoning
from app.workflows.contracts import AccountSearchRunResult, AccountSearchRunResultOutcome

MAX_ACCOUNT_SEARCH_ATTEMPTS = 2


class AccountSearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountSearchWorkflowInput(AccountSearchModel):
    seller_profile_id: UUID
    icp_profile_id: UUID
    search_objective: str | None = None
    user_targeting_constraints: dict[str, Any] | None = None


class AccountSearchAttemptRecord(AccountSearchModel):
    attempt_number: int = Field(ge=1, le=MAX_ACCOUNT_SEARCH_ATTEMPTS)
    search_strategy: str
    query_ideas: list[str] = Field(default_factory=list)
    candidate_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    reason_summary: str


class AccountSearchPlan(AccountSearchModel):
    search_strategy: str
    query_ideas: list[str] = Field(default_factory=list)
    fit_criteria: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class CandidateEvidenceRecord(AccountSearchModel):
    source_type: str = "web"
    provider_name: str | None = None
    source_url: str | None = None
    title: str | None = None
    snippet_text: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    metadata_json: dict[str, Any] | None = None


class AccountCandidateRecord(AccountSearchModel):
    name: str = Field(min_length=1)
    domain: str | None = None
    linkedin_url: str | None = None
    hq_location: str | None = None
    employee_range: str | None = None
    industry: str | None = None
    fit_summary: str | None = None
    fit_signals_json: dict[str, Any] | None = None
    canonical_data_json: dict[str, Any] | None = None
    evidence: list[CandidateEvidenceRecord] = Field(default_factory=list)


class AccountSearchSelection(AccountSearchModel):
    accepted_candidates: list[AccountCandidateRecord] = Field(default_factory=list)
    reason_summary: str
    credible_search_space_exhausted: bool = False


class AccountSearchPlanner(Protocol):
    async def build_plan(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile,
        attempt_number: int,
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchPlan: ...

    async def select_candidates(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile,
        attempt_number: int,
        plan: AccountSearchPlan,
        candidates: Sequence[AccountCandidateRecord],
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchSelection: ...


@dataclass(frozen=True)
class AccountSearchToolset:
    web_search: WebSearchTool
    content_normalizer: ContentNormalizerTool
    company_enrichment: CompanyEnrichmentTool | None = None


class NullWebSearchTool:
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        _ = request
        return WebSearchResponse(results=[])


class NullContentNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=[])


class NullCompanyEnrichmentTool:
    async def execute(self, request: CompanyEnrichmentRequest) -> CompanyEnrichmentResponse:
        _ = request
        return CompanyEnrichmentResponse()


class DeterministicAccountSearchPlanner:
    async def build_plan(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile,
        attempt_number: int,
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchPlan:
        query_ideas = _build_query_ideas(
            workflow_input=workflow_input,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            attempt_number=attempt_number,
        )
        fit_criteria = _build_fit_criteria(icp_profile)
        if not query_ideas:
            query_ideas = [seller_profile.company_name]
        strategy = (
            "Search for public account candidates that fit the seller and ICP context."
            if attempt_number == 1
            else "Refine the search using the prior attempt and narrower ICP cues."
        )
        if prior_attempts and attempt_number > 1:
            strategy = f"{strategy} Prior outcome: {prior_attempts[-1].reason_summary}"
        return AccountSearchPlan(
            search_strategy=strategy,
            query_ideas=query_ideas[:3],
            fit_criteria=fit_criteria,
            clarification_questions=[],
        )

    async def select_candidates(
        self,
        *,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile,
        attempt_number: int,
        plan: AccountSearchPlan,
        candidates: Sequence[AccountCandidateRecord],
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchSelection:
        _ = workflow_input
        _ = plan
        _ = prior_attempts
        scored_candidates = [
            (candidate, _score_candidate(candidate, seller_profile=seller_profile, icp_profile=icp_profile))
            for candidate in candidates
        ]
        accepted_candidates = [
            candidate for candidate, score in scored_candidates if score > 0
        ]
        if accepted_candidates:
            return AccountSearchSelection(
                accepted_candidates=accepted_candidates,
                reason_summary=(
                    f"Accepted {len(accepted_candidates)} account candidate(s) after "
                    f"attempt {attempt_number}."
                ),
                credible_search_space_exhausted=True,
            )

        return AccountSearchSelection(
            accepted_candidates=[],
            reason_summary="No credible account candidates matched the current seller and ICP context.",
            credible_search_space_exhausted=attempt_number >= MAX_ACCOUNT_SEARCH_ATTEMPTS or not candidates,
        )


class AccountSearchWorkflow:
    def __init__(
        self,
        session: AsyncSession,
        *,
        run_service: WorkflowRunService | None = None,
        planner: AccountSearchPlanner | None = None,
        tools: AccountSearchToolset | None = None,
    ) -> None:
        self._session = session
        self._runs = WorkflowRunRepository(session)
        self._seller_profiles = SellerProfileRepository(session)
        self._icp_profiles = ICPProfileRepository(session)
        self._accounts = AccountRepository(session)
        self._source_evidence = SourceEvidenceRepository(session)
        self._run_service = run_service or WorkflowRunService(session)
        self._planner = planner or DeterministicAccountSearchPlanner()
        self._tools = tools or AccountSearchToolset(
            web_search=NullWebSearchTool(),
            content_normalizer=NullContentNormalizerTool(),
            company_enrichment=NullCompanyEnrichmentTool(),
        )

    async def execute(self, request: Any) -> WorkflowExecutionResult:
        run = await self._require_run(tenant_id=request.tenant_id, run_id=request.run_id)
        workflow_input = self._load_workflow_input(run)
        seller_profile, icp_profile = await self._load_prerequisites(
            tenant_id=request.tenant_id,
            workflow_input=workflow_input,
        )

        await self._run_service.emit_agent_handoff(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            from_agent="orchestrator_agent",
            to_agent="account_search_agent",
            reason="Starting account search strategy and fit evaluation.",
        )

        accepted_account_ids: list[UUID] = []
        evidence_ids: list[UUID] = []
        prior_attempts: list[AccountSearchAttemptRecord] = []
        final_reason_summary = "No credible account candidates were accepted."

        for attempt_number in range(1, MAX_ACCOUNT_SEARCH_ATTEMPTS + 1):
            plan = await self._planner.build_plan(
                workflow_input=workflow_input,
                seller_profile=seller_profile,
                icp_profile=icp_profile,
                attempt_number=attempt_number,
                prior_attempts=prior_attempts,
            )
            normalized_candidates = await self._run_attempt(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                seller_profile=seller_profile,
                icp_profile=icp_profile,
                workflow_input=workflow_input,
                attempt_number=attempt_number,
                plan=plan,
            )
            selection = await self._planner.select_candidates(
                workflow_input=workflow_input,
                seller_profile=seller_profile,
                icp_profile=icp_profile,
                attempt_number=attempt_number,
                plan=plan,
                candidates=normalized_candidates,
                prior_attempts=prior_attempts,
            )
            selected_keys = {
                (_normalize_optional_text(candidate.name) or "", _normalize_domain(candidate.domain) or "")
                for candidate in selection.accepted_candidates
            }
            for candidate in selection.accepted_candidates:
                await self._run_service.emit_candidate_accepted(
                    tenant_id=request.tenant_id,
                    run_id=request.run_id,
                    entity_type="account",
                    candidate_label=candidate.name,
                    reason_summary=selection.reason_summary,
                    provider_name=_candidate_provider_name(candidate),
                )
            for candidate in normalized_candidates:
                candidate_key = (
                    _normalize_optional_text(candidate.name) or "",
                    _normalize_domain(candidate.domain) or "",
                )
                if candidate_key in selected_keys:
                    continue
                await self._run_service.emit_candidate_rejected(
                    tenant_id=request.tenant_id,
                    run_id=request.run_id,
                    entity_type="account",
                    candidate_label=candidate.name,
                    reason_summary="Candidate did not meet precision-first acceptance rules.",
                    provider_name=_candidate_provider_name(candidate),
                )
            persisted_account_ids, persisted_evidence_ids = await self._persist_candidates(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                created_by_user_id=request.created_by_user_id,
                candidates=selection.accepted_candidates,
            )
            accepted_account_ids = _merge_unique_ids(accepted_account_ids, persisted_account_ids)
            evidence_ids = _merge_unique_ids(evidence_ids, persisted_evidence_ids)
            final_reason_summary = selection.reason_summary
            prior_attempts.append(
                AccountSearchAttemptRecord(
                    attempt_number=attempt_number,
                    search_strategy=plan.search_strategy,
                    query_ideas=plan.query_ideas,
                    candidate_count=len(normalized_candidates),
                    accepted_count=len(persisted_account_ids),
                    reason_summary=selection.reason_summary,
                )
            )
            if selection.credible_search_space_exhausted or persisted_account_ids:
                break

        outcome = (
            AccountSearchRunResultOutcome.ACCOUNTS_FOUND
            if accepted_account_ids
            else AccountSearchRunResultOutcome.NO_RESULTS
        )
        result = AccountSearchRunResult(
            outcome=outcome,
            accepted_account_ids=accepted_account_ids,
            reason_summary=final_reason_summary,
            search_attempt_count=len(prior_attempts),
        )
        await self._run_service.emit_agent_completed(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            agent_name="account_search_agent",
            result_summary=result.reason_summary,
        )
        canonical_output_ids = {
            "account_ids": [str(account_id) for account_id in accepted_account_ids]
        }
        if evidence_ids:
            canonical_output_ids["evidence_ids"] = [
                str(evidence_id) for evidence_id in evidence_ids
            ]

        return WorkflowExecutionResult(
            result_summary=result.reason_summary,
            normalized_result_json=result.model_dump(mode="json"),
            status_detail=f"Account search completed after {result.search_attempt_count} attempt(s).",
            canonical_output_ids=canonical_output_ids,
        )

    async def _run_attempt(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile,
        workflow_input: AccountSearchWorkflowInput,
        attempt_number: int,
        plan: AccountSearchPlan,
    ) -> list[AccountCandidateRecord]:
        search_results: list[SearchResultRecord] = []
        web_search_provider = get_tool_provider_name(self._tools.web_search)
        for query_index, query in enumerate(plan.query_ideas or [seller_profile.company_name], start=1):
            correlation_key = f"account-search-{run_id}-{attempt_number}-search-{query_index}"
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="web_search",
                provider_name=web_search_provider,
                input_summary=f"Searching for account candidates with query: {query}",
                correlation_key=correlation_key,
            )
            response = await self._tools.web_search.execute(
                WebSearchRequest(query_text=query, result_limit=10)
            )
            await self._run_service.emit_tool_completed(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="web_search",
                provider_name=web_search_provider,
                output_summary=f"Collected {len(response.results)} search result(s).",
                error_code=response.error_code,
                produced_evidence_results=bool(response.results),
            )
            if response.error_code is None:
                search_results.extend(response.results)

        search_results = _dedupe_search_results(search_results)
        content_normalizer_provider = get_tool_provider_name(self._tools.content_normalizer)
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            input_summary=f"Normalizing {len(search_results)} account candidate search result(s).",
            correlation_key=f"account-search-{run_id}-{attempt_number}-normalize",
        )
        response = await self._tools.content_normalizer.execute(
            ContentNormalizerRequest(
                raw_payload={
                    "seller_profile": _seller_profile_payload(seller_profile),
                    "icp_profile": _icp_profile_payload(icp_profile),
                    "workflow_input": workflow_input.model_dump(mode="json"),
                    "search_strategy": plan.model_dump(mode="json"),
                    "search_results": [result.model_dump(mode="json") for result in search_results],
                },
                schema_hint="account_search_candidates",
            )
        )
        reasoning_output = validate_account_search_reasoning(response.normalized_payload)
        if reasoning_output is None:
            await self._run_service.emit_reasoning_failed_validation(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="account_search_candidates",
                provider_name=content_normalizer_provider,
                failure_summary="Structured account-search reasoning output did not match schema.",
                fallback_summary="Falling back to deterministic candidate parsing.",
            )
            normalized_candidates = _parse_candidates(response.normalized_payload)
        else:
            await self._run_service.emit_reasoning_validated(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="account_search_candidates",
                provider_name=content_normalizer_provider,
                output_summary=(
                    f"Validated {len(reasoning_output.accepted_candidates)} accepted and "
                    f"{len(reasoning_output.rejected_candidates)} rejected account candidates."
                ),
            )
            normalized_candidates = [
                _account_candidate_from_reasoning(candidate)
                for candidate in reasoning_output.accepted_candidates
            ]
        normalized_candidates = await self._maybe_enrich_candidates(
            tenant_id=tenant_id,
            run_id=run_id,
            attempt_number=attempt_number,
            candidates=normalized_candidates,
        )
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            output_summary=f"Normalized {len(normalized_candidates)} account candidate(s).",
            error_code=response.error_code,
            produced_evidence_results=bool(normalized_candidates),
        )
        return normalized_candidates

    async def _maybe_enrich_candidates(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        attempt_number: int,
        candidates: Sequence[AccountCandidateRecord],
    ) -> list[AccountCandidateRecord]:
        if self._tools.company_enrichment is None:
            return list(candidates)

        enriched_candidates: list[AccountCandidateRecord] = []
        company_enrichment_provider = get_tool_provider_name(self._tools.company_enrichment)
        for candidate_index, candidate in enumerate(candidates, start=1):
            if not candidate.domain:
                enriched_candidates.append(candidate)
                continue
            correlation_key = f"account-search-{run_id}-{attempt_number}-enrich-{candidate_index}"
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="company_enrichment",
                provider_name=company_enrichment_provider,
                input_summary=f"Enriching company data for {candidate.domain}.",
                correlation_key=correlation_key,
            )
            response = await self._tools.company_enrichment.execute(
                CompanyEnrichmentRequest(domain=candidate.domain)
            )
            await self._run_service.emit_tool_completed(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="company_enrichment",
                provider_name=company_enrichment_provider,
                output_summary=(
                    "Resolved provider company data."
                    if response.company_profile
                    else "No provider company data was resolved."
                ),
                error_code=response.error_code,
                produced_evidence_results=bool(response.source_references),
            )
            enriched_candidates.append(
                _apply_company_enrichment(candidate=candidate, response=response)
            )
        return enriched_candidates

    async def _persist_candidates(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        created_by_user_id: UUID,
        candidates: Sequence[AccountCandidateRecord],
    ) -> tuple[list[UUID], list[UUID]]:
        persisted_account_ids: list[UUID] = []
        evidence_ids: list[UUID] = []
        for candidate in candidates:
            normalized_domain = _normalize_domain(candidate.domain)
            existing = None
            if normalized_domain is not None:
                existing = await self._accounts.get_by_normalized_domain(
                    tenant_id=tenant_id,
                    normalized_domain=normalized_domain,
                )
            if existing is None:
                account = await self._accounts.create(
                    tenant_id=tenant_id,
                    created_by_user_id=created_by_user_id,
                    source_workflow_run_id=run_id,
                    name=candidate.name,
                    domain=_normalize_optional_text(candidate.domain),
                    normalized_domain=normalized_domain,
                    linkedin_url=_normalize_optional_text(candidate.linkedin_url),
                    hq_location=_normalize_optional_text(candidate.hq_location),
                    employee_range=_normalize_optional_text(candidate.employee_range),
                    industry=_normalize_optional_text(candidate.industry),
                    status="accepted",
                    fit_summary=_normalize_optional_text(candidate.fit_summary),
                    fit_signals_json=candidate.fit_signals_json,
                    canonical_data_json=candidate.canonical_data_json,
                )
            else:
                account = existing
                changes = _build_account_merge_changes(existing=existing, candidate=candidate)
                if changes:
                    updated_account = await self._accounts.update(
                        tenant_id=tenant_id,
                        account_id=existing.id,
                        updated_by_user_id=created_by_user_id,
                        changes=changes,
                    )
                    assert updated_account is not None
                    account = updated_account
            evidence_ids.extend(
                await self._persist_candidate_evidence(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    account_id=account.id,
                    candidate=candidate,
                )
            )
            persisted_account_ids.append(account.id)
        await self._session.flush()
        return persisted_account_ids, _merge_unique_ids([], evidence_ids)

    async def _persist_candidate_evidence(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account_id: UUID,
        candidate: AccountCandidateRecord,
    ) -> list[UUID]:
        evidence_ids: list[UUID] = []
        for evidence in candidate.evidence:
            evidence_row = await self._source_evidence.create(
                tenant_id=tenant_id,
                workflow_run_id=run_id,
                account_id=account_id,
                source_type=evidence.source_type,
                provider_name=evidence.provider_name,
                source_url=evidence.source_url,
                title=evidence.title,
                snippet_text=evidence.snippet_text,
                confidence_score=evidence.confidence_score,
                metadata_json=evidence.metadata_json,
            )
            evidence_ids.append(evidence_row.id)
        return evidence_ids

    async def _require_run(self, *, tenant_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise WorkflowExecutionError(
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        return run

    def _load_workflow_input(self, run: WorkflowRun) -> AccountSearchWorkflowInput:
        try:
            return AccountSearchWorkflowInput.model_validate(run.requested_payload_json)
        except ValidationError as exc:
            raise WorkflowExecutionError(
                error_code="validation_error",
                message="Workflow run payload is invalid for account search.",
                status_detail=str(exc),
            ) from exc

    async def _load_prerequisites(
        self,
        *,
        tenant_id: UUID,
        workflow_input: AccountSearchWorkflowInput,
    ) -> tuple[SellerProfile, ICPProfile]:
        seller_profile = await self._seller_profiles.get_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=workflow_input.seller_profile_id,
        )
        icp_profile = await self._icp_profiles.get_for_tenant(
            tenant_id=tenant_id,
            icp_profile_id=workflow_input.icp_profile_id,
        )
        if seller_profile is None or icp_profile is None:
            raise WorkflowExecutionError(
                error_code="workflow_prerequisites_missing",
                message="Account search requires seller and ICP context.",
                status_detail="Seller profile or ICP profile was not found for this run.",
            )
        if icp_profile.seller_profile_id != seller_profile.id:
            raise WorkflowExecutionError(
                error_code="ownership_conflict",
                message="ICP profile does not belong to the requested seller profile.",
            )
        return seller_profile, icp_profile


def _dedupe_search_results(results: Iterable[SearchResultRecord]) -> list[SearchResultRecord]:
    deduped: list[SearchResultRecord] = []
    seen_keys: set[tuple[str, str]] = set()
    for result in results:
        key = (result.url.strip().lower(), result.title.strip().lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(result)
    return deduped


def _parse_candidates(payload: dict[str, Any] | list[dict[str, Any]] | None) -> list[AccountCandidateRecord]:
    if payload is None:
        return []
    raw_candidates: Any = payload
    if isinstance(payload, dict):
        raw_candidates = payload.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []

    parsed_candidates: list[AccountCandidateRecord] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        try:
            parsed_candidates.append(AccountCandidateRecord.model_validate(item))
        except ValidationError:
            continue
    return parsed_candidates


def _apply_company_enrichment(
    *,
    candidate: AccountCandidateRecord,
    response: CompanyEnrichmentResponse,
    ) -> AccountCandidateRecord:
    replacement_data = dict(candidate.canonical_data_json or {})
    if response.company_profile:
        replacement_data = _merge_json_payloads(replacement_data, response.company_profile)
    evidence = list(candidate.evidence)
    for source_reference in response.source_references:
        evidence.append(
            CandidateEvidenceRecord(
                source_type="provider",
                provider_name=source_reference.provider_name,
                source_url=source_reference.source_url,
                title=source_reference.title,
            )
        )
    return candidate.model_copy(
        update={
            "domain": response.normalized_domain or candidate.domain,
            "linkedin_url": response.linkedin_url or candidate.linkedin_url,
            "canonical_data_json": replacement_data or None,
            "evidence": evidence,
        }
    )


def _candidate_provider_name(candidate: AccountCandidateRecord) -> str | None:
    for evidence in candidate.evidence:
        if evidence.provider_name:
            return evidence.provider_name
    return None


def _account_candidate_from_reasoning(candidate: Any) -> AccountCandidateRecord:
    return AccountCandidateRecord(
        name=candidate.name,
        domain=_normalize_domain(candidate.website_url or candidate.domain),
        linkedin_url=_normalize_optional_text(candidate.linkedin_url),
        hq_location=_normalize_optional_text(candidate.hq_location),
        employee_range=_normalize_optional_text(candidate.employee_range),
        industry=_normalize_optional_text(candidate.industry),
        fit_summary=_normalize_optional_text(candidate.fit_summary or candidate.why_selected),
        fit_signals_json=candidate.fit_signals_json,
        canonical_data_json=candidate.canonical_data_json,
        evidence=[
            CandidateEvidenceRecord.model_validate(evidence)
            for evidence in candidate.evidence
            if isinstance(evidence, dict)
        ],
    )


def _build_account_merge_changes(*, existing: Any, candidate: AccountCandidateRecord) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    replacement_values = {
        "name": candidate.name,
        "domain": _normalize_optional_text(candidate.domain),
        "normalized_domain": _normalize_domain(candidate.domain),
        "linkedin_url": _normalize_optional_text(candidate.linkedin_url),
        "hq_location": _normalize_optional_text(candidate.hq_location),
        "employee_range": _normalize_optional_text(candidate.employee_range),
        "industry": _normalize_optional_text(candidate.industry),
        "fit_summary": _normalize_optional_text(candidate.fit_summary),
        "status": "accepted",
    }
    for field_name, replacement_value in replacement_values.items():
        if _is_non_empty_value(replacement_value) and getattr(existing, field_name) != replacement_value:
            changes[field_name] = replacement_value

    if _is_non_empty_value(candidate.fit_signals_json):
        merged_fit_signals = _merge_json_payloads(
            existing.fit_signals_json or {},
            candidate.fit_signals_json or {},
        )
        if merged_fit_signals != (existing.fit_signals_json or {}):
            changes["fit_signals_json"] = merged_fit_signals

    if _is_non_empty_value(candidate.canonical_data_json):
        merged_canonical_data = _merge_json_payloads(
            existing.canonical_data_json or {},
            candidate.canonical_data_json or {},
        )
        if merged_canonical_data != (existing.canonical_data_json or {}):
            changes["canonical_data_json"] = merged_canonical_data

    return changes


def _merge_json_payloads(existing: dict[str, Any], replacement: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in replacement.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_json_payloads(merged[key], value)
            continue
        if _is_non_empty_value(value):
            merged[key] = value
    return merged


def _merge_unique_ids(existing_ids: Sequence[UUID], new_ids: Sequence[UUID]) -> list[UUID]:
    seen = set(existing_ids)
    merged = list(existing_ids)
    for account_id in new_ids:
        if account_id in seen:
            continue
        seen.add(account_id)
        merged.append(account_id)
    return merged


def _normalize_domain(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    return normalized.lower().removeprefix("https://").removeprefix("http://").strip("/")


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _is_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_is_non_empty_value(child) for child in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_is_non_empty_value(child) for child in value)
    return True


def _seller_profile_payload(seller_profile: SellerProfile) -> dict[str, Any]:
    return {
        "seller_profile_id": str(seller_profile.id),
        "name": seller_profile.name,
        "company_name": seller_profile.company_name,
        "company_domain": seller_profile.company_domain,
        "product_summary": seller_profile.product_summary,
        "value_proposition": seller_profile.value_proposition,
        "target_market_summary": seller_profile.target_market_summary,
        "profile_json": seller_profile.profile_json,
    }


def _icp_profile_payload(icp_profile: ICPProfile) -> dict[str, Any]:
    return {
        "icp_profile_id": str(icp_profile.id),
        "seller_profile_id": str(icp_profile.seller_profile_id),
        "name": icp_profile.name,
        "status": icp_profile.status,
        "criteria_json": icp_profile.criteria_json,
        "exclusions_json": icp_profile.exclusions_json,
    }


def _build_query_ideas(
    *,
    workflow_input: AccountSearchWorkflowInput,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile,
    attempt_number: int,
) -> list[str]:
    query_ideas: list[str] = []
    if workflow_input.search_objective:
        query_ideas.append(workflow_input.search_objective)

    industries = _extract_string_values(icp_profile.criteria_json, {"industries", "industry"})
    company_sizes = _extract_string_values(
        icp_profile.criteria_json,
        {"company_size", "company_sizes", "employee_range", "employee_ranges"},
    )
    geographies = _extract_string_values(
        icp_profile.criteria_json,
        {"geography", "geographies", "regions", "locations"},
    )

    parts = [
        industries[0] if industries else None,
        company_sizes[0] if company_sizes else None,
        geographies[0] if geographies else None,
        seller_profile.target_market_summary,
    ]
    synthetic_query = " ".join(part for part in parts if part)
    if synthetic_query:
        query_ideas.append(synthetic_query)

    if attempt_number > 1 and seller_profile.value_proposition:
        query_ideas.append(f"{seller_profile.value_proposition} companies")

    deduped_queries: list[str] = []
    seen: set[str] = set()
    for query in query_ideas:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            continue
        dedupe_key = normalized_query.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_queries.append(normalized_query)
    return deduped_queries


def _build_fit_criteria(icp_profile: ICPProfile) -> list[str]:
    criteria: list[str] = []
    for key, value in icp_profile.criteria_json.items():
        extracted_values = _extract_string_values({key: value}, {key})
        if not extracted_values:
            continue
        criteria.append(f"{key}: {', '.join(extracted_values)}")
    return criteria


def _extract_string_values(payload: dict[str, Any], keys: set[str]) -> list[str]:
    results: list[str] = []
    for key, value in payload.items():
        if key not in keys:
            continue
        results.extend(_flatten_string_values(value))
    return results


def _flatten_string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, dict):
        results: list[str] = []
        for child in value.values():
            results.extend(_flatten_string_values(child))
        return results
    if isinstance(value, (list, tuple, set)):
        results: list[str] = []
        for child in value:
            results.extend(_flatten_string_values(child))
        return results
    return [str(value)]


def _score_candidate(
    candidate: AccountCandidateRecord,
    *,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile,
) -> int:
    searchable_text = " ".join(
        value
        for value in [
            candidate.name,
            candidate.domain,
            candidate.industry,
            candidate.hq_location,
            candidate.employee_range,
            candidate.fit_summary,
            seller_profile.target_market_summary,
        ]
        if value
    ).lower()
    score = 0
    for industry in _extract_string_values(icp_profile.criteria_json, {"industries", "industry"}):
        if industry.lower() in searchable_text:
            score += 2
    for geography in _extract_string_values(
        icp_profile.criteria_json,
        {"geography", "geographies", "regions", "locations"},
    ):
        if geography.lower() in searchable_text:
            score += 1
    if candidate.fit_summary:
        score += 1
    if candidate.fit_signals_json:
        score += 1
    return score
