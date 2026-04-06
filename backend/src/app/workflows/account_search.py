from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
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
from app.workflows.reasoning import (
    is_provider_failure_without_payload,
    validate_account_search_query_plan,
    validate_account_search_reasoning,
)
from app.workflows.contracts import AccountSearchRunResult, AccountSearchRunResultOutcome

MAX_ACCOUNT_SEARCH_ATTEMPTS = 2
MAX_ACCOUNT_SEARCH_PLANNER_ATTEMPTS = 5
_ACCOUNT_SEARCH_FALLBACK_TRIGGER_ERROR_CODES = frozenset(
    {
        "provider_bad_response",
        "provider_unavailable",
        "provider_rate_limit",
        "provider_quota_exceeded",
    }
)
_ACCOUNT_SEARCH_PLANNER_ERROR_CODE = "account_search_planner_failed"
_ACCOUNT_SEARCH_PLANNER_FAILURE_SUMMARY = (
    "I couldn't build a reliable account-search plan after repeated planning retries."
)


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
        tenant_id: UUID,
        run: WorkflowRun,
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
    fallback_web_search: WebSearchTool | None = None
    company_enrichment: CompanyEnrichmentTool | None = None


@dataclass(frozen=True)
class AccountSearchAttemptExecution:
    candidates: list[AccountCandidateRecord]
    primary_provider_name: str | None
    fallback_provider_name: str | None
    provider_failure_detected: bool = False
    primary_provider_failed: bool = False
    fallback_attempted: bool = False
    fallback_used: bool = False


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


class LLMAccountSearchPlanner:
    def __init__(
        self,
        *,
        content_normalizer: ContentNormalizerTool,
        run_service: WorkflowRunService,
    ) -> None:
        self._content_normalizer = content_normalizer
        self._run_service = run_service

    async def build_plan(
        self,
        *,
        tenant_id: UUID,
        run: WorkflowRun,
        workflow_input: AccountSearchWorkflowInput,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile,
        attempt_number: int,
        prior_attempts: Sequence[AccountSearchAttemptRecord],
    ) -> AccountSearchPlan:
        fit_criteria = _build_fit_criteria(icp_profile)
        content_normalizer_provider = get_tool_provider_name(self._content_normalizer)
        agent_config = _resolve_run_agent_config(run=run, agent_name="account_search_agent")
        prior_failure_summary: str | None = None

        for planner_attempt_number in range(1, MAX_ACCOUNT_SEARCH_PLANNER_ATTEMPTS + 1):
            planner_payload = {
                "seller_profile": _seller_profile_payload(seller_profile),
                "icp_profile": _icp_profile_payload(icp_profile),
                "workflow_input": workflow_input.model_dump(mode="json"),
                "attempt_number": attempt_number,
                "prior_attempts": [attempt.model_dump(mode="json") for attempt in prior_attempts],
                "recommended_fit_criteria": fit_criteria,
                "planner_attempt_number": planner_attempt_number,
                "prior_planner_failure_summary": prior_failure_summary,
            }
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run.id,
                tool_name="query_planner",
                provider_name=content_normalizer_provider,
                input_summary=(
                    f"Planning account-search queries for workflow attempt {attempt_number} "
                    f"(planner try {planner_attempt_number})."
                ),
                correlation_key=(
                    f"account-search-{run.id}-{attempt_number}-query-planner-"
                    f"{planner_attempt_number}"
                ),
            )
            llm_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            response = await self._content_normalizer.execute(
                ContentNormalizerRequest(
                    raw_payload=planner_payload,
                    schema_hint="account_search_query_plan",
                    instructions_override=_build_account_search_planner_instructions(
                        base_instructions=agent_config.get("instructions"),
                        prior_failure_summary=prior_failure_summary,
                    ),
                    system_prompt_override=agent_config.get("system_prompt"),
                    model_override=agent_config.get("model"),
                )
            )
            llm_finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self._run_service.record_llm_call(
                tenant_id=tenant_id,
                run_id=run.id,
                agent_name="account_search_agent",
                provider_name=content_normalizer_provider or "openai",
                model_name=(response.raw_metadata_json or {}).get("model")
                or agent_config.get("model"),
                schema_hint="account_search_query_plan",
                input_payload=planner_payload,
                output_payload=response.normalized_payload,
                status="failed" if response.error_code else "completed",
                latency_ms=max(int((llm_finished_at - llm_started_at).total_seconds() * 1000), 0),
                error_code=response.error_code,
                raw_metadata_json=response.raw_metadata_json,
            )

            reasoning_output = validate_account_search_query_plan(response.normalized_payload)
            provider_failure_without_payload = is_provider_failure_without_payload(
                error_code=response.error_code,
                payload=response.normalized_payload,
            )
            plan = _account_search_plan_from_reasoning_output(
                reasoning_output=reasoning_output,
                fallback_fit_criteria=fit_criteria,
            )
            if plan is not None:
                await self._run_service.emit_reasoning_validated(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    schema_name="account_search_query_plan",
                    provider_name=content_normalizer_provider,
                    output_summary=(
                        f"Generated {len(plan.query_ideas)} account-search query idea(s) "
                        f"for workflow attempt {attempt_number}."
                    ),
                )
                await self._run_service.emit_tool_completed(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    tool_name="query_planner",
                    provider_name=content_normalizer_provider,
                    output_summary=response.raw_result_summary
                    or f"Generated query plan with {len(plan.query_ideas)} query idea(s).",
                    error_code=response.error_code,
                    produced_evidence_results=bool(plan.query_ideas),
                )
                return plan

            if not provider_failure_without_payload:
                await self._run_service.emit_reasoning_failed_validation(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    schema_name="account_search_query_plan",
                    provider_name=content_normalizer_provider,
                    failure_summary=(
                        "Structured account-search planner output did not match schema "
                        "or did not contain usable query ideas."
                    ),
                    fallback_summary="Retrying planner with failure context.",
                )

            prior_failure_summary = _planner_failure_summary(
                response=response,
                provider_failure_without_payload=provider_failure_without_payload,
                reasoning_output_present=reasoning_output is not None,
            )
            await self._run_service.emit_tool_completed(
                tenant_id=tenant_id,
                run_id=run.id,
                tool_name="query_planner",
                provider_name=content_normalizer_provider,
                output_summary=response.raw_result_summary
                or prior_failure_summary,
                error_code=response.error_code,
                produced_evidence_results=False,
            )

        raise WorkflowExecutionError(
            error_code=_ACCOUNT_SEARCH_PLANNER_ERROR_CODE,
            message=_ACCOUNT_SEARCH_PLANNER_FAILURE_SUMMARY,
            status_detail=prior_failure_summary,
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
        self._tools = tools or AccountSearchToolset(
            web_search=NullWebSearchTool(),
            fallback_web_search=None,
            content_normalizer=NullContentNormalizerTool(),
            company_enrichment=NullCompanyEnrichmentTool(),
        )
        self._planner = planner or LLMAccountSearchPlanner(
            content_normalizer=self._tools.content_normalizer,
            run_service=self._run_service,
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
        primary_provider_name = get_tool_provider_name(self._tools.web_search)
        fallback_provider_name = get_tool_provider_name(self._tools.fallback_web_search)
        provider_failure_detected = False
        primary_provider_failed = False
        fallback_attempted = False
        fallback_used = False

        for attempt_number in range(1, MAX_ACCOUNT_SEARCH_ATTEMPTS + 1):
            plan = await self._planner.build_plan(
                tenant_id=request.tenant_id,
                run=run,
                workflow_input=workflow_input,
                seller_profile=seller_profile,
                icp_profile=icp_profile,
                attempt_number=attempt_number,
                prior_attempts=prior_attempts,
            )
            attempt_execution = await self._run_attempt(
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                seller_profile=seller_profile,
                icp_profile=icp_profile,
                workflow_input=workflow_input,
                attempt_number=attempt_number,
                plan=plan,
            )
            normalized_candidates = attempt_execution.candidates
            provider_failure_detected = (
                provider_failure_detected or attempt_execution.provider_failure_detected
            )
            primary_provider_failed = (
                primary_provider_failed or attempt_execution.primary_provider_failed
            )
            fallback_attempted = fallback_attempted or attempt_execution.fallback_attempted
            fallback_used = fallback_used or attempt_execution.fallback_used
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

        if accepted_account_ids:
            outcome = (
                AccountSearchRunResultOutcome.ACCOUNTS_FOUND_VIA_FALLBACK
                if fallback_used
                else AccountSearchRunResultOutcome.ACCOUNTS_FOUND
            )
        elif provider_failure_detected and fallback_attempted:
            outcome = AccountSearchRunResultOutcome.PROVIDER_FAILURE_WITH_FALLBACK_EXHAUSTED
        elif provider_failure_detected:
            outcome = AccountSearchRunResultOutcome.PROVIDER_FAILURE
        else:
            outcome = AccountSearchRunResultOutcome.NO_RESULTS

        assistant_summary, summary_selection_reason = _select_terminal_assistant_summary(
            outcome=outcome,
            fallback_attempted=fallback_attempted,
            fallback_used=fallback_used,
            primary_provider_name=primary_provider_name,
            fallback_provider_name=fallback_provider_name,
            reason_summary=final_reason_summary,
        )
        result = AccountSearchRunResult(
            outcome=outcome,
            accepted_account_ids=accepted_account_ids,
            reason_summary=final_reason_summary,
            search_attempt_count=len(prior_attempts),
            assistant_summary=assistant_summary,
            summary_selection_reason=summary_selection_reason,
            primary_provider_name=primary_provider_name,
            fallback_provider_name=fallback_provider_name,
            primary_provider_failed=primary_provider_failed,
            fallback_attempted=fallback_attempted,
            fallback_used=fallback_used,
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
    ) -> AccountSearchAttemptExecution:
        search_results: list[SearchResultRecord] = []
        web_search_provider = get_tool_provider_name(self._tools.web_search)
        fallback_provider_name = get_tool_provider_name(self._tools.fallback_web_search)
        primary_error_codes: list[str] = []
        await self._run_service.emit_provider_routing_decision(
            tenant_id=tenant_id,
            run_id=run_id,
            capability="account_search_web_search",
            selected_provider=web_search_provider or "firecrawl",
            fallback_provider=fallback_provider_name,
            routing_basis="phase3_default_firecrawl_primary",
            allowed=self._tools.fallback_web_search is not None,
            reason_summary="Selecting the default primary provider for Phase 3 account search.",
        )
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
                output_summary=response.raw_result_summary
                or f"Collected {len(response.results)} search result(s).",
                error_code=response.error_code,
                produced_evidence_results=bool(response.results),
            )
            if response.error_code is None:
                search_results.extend(response.results)
            else:
                primary_error_codes.append(response.error_code)

        primary_provider_failed = any(
            error_code in _ACCOUNT_SEARCH_FALLBACK_TRIGGER_ERROR_CODES
            for error_code in primary_error_codes
        )
        fallback_attempted = False
        fallback_used = False
        if not search_results and primary_provider_failed and self._tools.fallback_web_search is not None:
            fallback_attempted = True
            trigger_reason = primary_error_codes[0]
            await self._run_service.emit_provider_routing_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                capability="account_search_web_search",
                from_provider=web_search_provider,
                selected_provider=fallback_provider_name or "google_local_places",
                fallback_provider=None,
                routing_basis="phase3_account_search_resilience_fallback",
                trigger_reason=trigger_reason,
                allowed=True,
                reason_summary=(
                    "Primary account-search provider triggered fallback due to "
                    f"{trigger_reason}."
                ),
            )
            await self._run_service.emit_assistant_progress_update(
                tenant_id=tenant_id,
                run_id=run_id,
                content_text="Hmm, looks like one of our sources is down. I'm trying a backup source now.",
            )
            for query_index, query in enumerate(
                _build_fallback_query_ideas(
                    workflow_input=workflow_input,
                    seller_profile=seller_profile,
                    icp_profile=icp_profile,
                    plan=plan,
                ),
                start=1,
            ):
                correlation_key = f"account-search-{run_id}-{attempt_number}-search-fallback-{query_index}"
                await self._run_service.emit_tool_started(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    tool_name="web_search",
                    provider_name=fallback_provider_name,
                    input_summary=f"Trying fallback account search with query: {query}",
                    correlation_key=correlation_key,
                )
                fallback_response = await self._tools.fallback_web_search.execute(
                    WebSearchRequest(query_text=query, result_limit=10)
                )
                await self._run_service.emit_tool_completed(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    tool_name="web_search",
                    provider_name=fallback_provider_name,
                    output_summary=fallback_response.raw_result_summary or (
                        f"Collected {len(fallback_response.results)} fallback search result(s)."
                    ),
                    error_code=fallback_response.error_code,
                    produced_evidence_results=bool(fallback_response.results),
                )
                if fallback_response.error_code is None:
                    search_results.extend(fallback_response.results)
            fallback_used = bool(search_results)

        search_results = _dedupe_search_results(search_results)
        content_normalizer_provider = get_tool_provider_name(self._tools.content_normalizer)
        agent_config = _resolve_run_agent_config(
            run=await self._require_run(tenant_id=tenant_id, run_id=run_id),
            agent_name="account_search_agent",
        )
        normalizer_payload = {
            "seller_profile": _seller_profile_payload(seller_profile),
            "icp_profile": _icp_profile_payload(icp_profile),
            "workflow_input": workflow_input.model_dump(mode="json"),
            "search_strategy": plan.model_dump(mode="json"),
            "search_results": [result.model_dump(mode="json") for result in search_results],
        }
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            input_summary=f"Normalizing {len(search_results)} account candidate search result(s).",
            correlation_key=f"account-search-{run_id}-{attempt_number}-normalize",
        )
        llm_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        response = await self._tools.content_normalizer.execute(
            ContentNormalizerRequest(
                raw_payload=normalizer_payload,
                schema_hint="account_search_candidates",
                instructions_override=agent_config.get("instructions"),
                system_prompt_override=agent_config.get("system_prompt"),
                model_override=agent_config.get("model"),
            )
        )
        llm_finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._run_service.record_llm_call(
            tenant_id=tenant_id,
            run_id=run_id,
            agent_name="account_search_agent",
            provider_name=content_normalizer_provider or "openai",
            model_name=(response.raw_metadata_json or {}).get("model") or agent_config.get("model"),
            schema_hint="account_search_candidates",
            input_payload=normalizer_payload,
            output_payload=response.normalized_payload,
            status="failed" if response.error_code else "completed",
            latency_ms=max(int((llm_finished_at - llm_started_at).total_seconds() * 1000), 0),
            error_code=response.error_code,
            raw_metadata_json=response.raw_metadata_json,
        )
        reasoning_output = validate_account_search_reasoning(response.normalized_payload)
        provider_failure_without_payload = is_provider_failure_without_payload(
            error_code=response.error_code,
            payload=response.normalized_payload,
        )
        provider_failure_detected = primary_provider_failed or provider_failure_without_payload
        if reasoning_output is None and not provider_failure_without_payload:
            await self._run_service.emit_reasoning_failed_validation(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="account_search_candidates",
                provider_name=content_normalizer_provider,
                failure_summary="Structured account-search reasoning output did not match schema.",
                fallback_summary="Falling back to deterministic candidate parsing.",
            )
            normalized_candidates = _parse_candidates(response.normalized_payload)
        elif reasoning_output is not None:
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
        else:
            normalized_candidates = _fallback_candidates_from_search_results(search_results)
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
            output_summary=response.raw_result_summary
            or f"Normalized {len(normalized_candidates)} account candidate(s).",
            error_code=response.error_code,
            produced_evidence_results=bool(normalized_candidates),
        )
        return AccountSearchAttemptExecution(
            candidates=normalized_candidates,
            primary_provider_name=web_search_provider,
            fallback_provider_name=fallback_provider_name,
            provider_failure_detected=provider_failure_detected,
            primary_provider_failed=primary_provider_failed,
            fallback_attempted=fallback_attempted,
            fallback_used=fallback_used,
        )

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


def _build_fallback_query_ideas(
    *,
    workflow_input: AccountSearchWorkflowInput,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile,
    plan: AccountSearchPlan,
) -> list[str]:
    geography_hints = _extract_string_values(
        icp_profile.criteria_json,
        {"geography", "geographies", "regions", "locations"},
    )
    industry_hints = _extract_string_values(icp_profile.criteria_json, {"industries", "industry"})
    base_queries = list(plan.query_ideas or [])
    if workflow_input.search_objective:
        base_queries.insert(0, workflow_input.search_objective)

    fallback_queries: list[str] = []
    for query in base_queries or [seller_profile.company_name]:
        query_parts = [query]
        if industry_hints:
            query_parts.append(industry_hints[0])
        if geography_hints:
            query_parts.append(geography_hints[0])
        fallback_queries.append(" ".join(part for part in query_parts if part))

    if not fallback_queries:
        fallback_queries.append(
            " ".join(
                part
                for part in [
                    seller_profile.company_name,
                    seller_profile.target_market_summary,
                    geography_hints[0] if geography_hints else None,
                ]
                if part
            )
        )

    deduped_queries: list[str] = []
    seen: set[str] = set()
    for query in fallback_queries:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            continue
        dedupe_key = normalized_query.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_queries.append(normalized_query)
    return deduped_queries[:3]


def _fallback_candidates_from_search_results(
    search_results: Sequence[SearchResultRecord],
) -> list[AccountCandidateRecord]:
    fallback_candidates: list[AccountCandidateRecord] = []
    for result in search_results:
        normalized_domain = _normalize_domain(result.url)
        candidate_name = _normalize_optional_text(result.title)
        if candidate_name is None and normalized_domain is None:
            continue
        fallback_candidates.append(
            AccountCandidateRecord(
                name=candidate_name or normalized_domain or "Unknown account",
                domain=normalized_domain,
                fit_summary=_normalize_optional_text(result.snippet),
                evidence=[
                    CandidateEvidenceRecord(
                        source_type="web",
                        provider_name=result.provider_name,
                        source_url=result.url,
                        title=result.title,
                        snippet_text=result.snippet,
                        metadata_json=result.provider_metadata,
                    )
                ],
            )
        )
    deduped_candidates: list[AccountCandidateRecord] = []
    seen_keys: set[tuple[str, str]] = set()
    for candidate in fallback_candidates:
        candidate_key = (
            (_normalize_optional_text(candidate.name) or "").lower(),
            (_normalize_domain(candidate.domain) or "").lower(),
        )
        if candidate_key in seen_keys:
            continue
        seen_keys.add(candidate_key)
        deduped_candidates.append(candidate)
    return deduped_candidates


def _select_terminal_assistant_summary(
    *,
    outcome: AccountSearchRunResultOutcome,
    fallback_attempted: bool,
    fallback_used: bool,
    primary_provider_name: str | None,
    fallback_provider_name: str | None,
    reason_summary: str,
) -> tuple[str, str]:
    _ = primary_provider_name
    _ = fallback_provider_name
    _ = fallback_attempted
    _ = fallback_used
    if outcome is AccountSearchRunResultOutcome.ACCOUNTS_FOUND_VIA_FALLBACK:
        return (
            "I had trouble with one of our main sources, but I was able to continue with a backup search and found a smaller set of candidates.",
            "Selected degraded-success summary because the primary provider failed and fallback produced accepted candidates.",
        )
    if outcome is AccountSearchRunResultOutcome.PROVIDER_FAILURE_WITH_FALLBACK_EXHAUSTED:
        return (
            "Hmm, looks like one of our sources is down. I tried a backup source too, but I couldn't confirm any reliable matches from the available data.",
            "Selected degraded-failure summary because the primary provider failed, fallback ran, and no reliable candidates were accepted.",
        )
    if outcome is AccountSearchRunResultOutcome.PROVIDER_FAILURE:
        return (
            "Hmm, looks like one of our sources is down, and I couldn't continue with a reliable search path from the available data.",
            "Selected provider-failure summary because an upstream provider failure prevented a trustworthy ordinary no-results outcome.",
        )
    if outcome is AccountSearchRunResultOutcome.NO_RESULTS:
        return (
            f"I finished the account search workflow. {reason_summary.strip()}",
            "Selected true no-results summary because the workflow exhausted the search space without a known upstream provider outage.",
        )
    return (
        f"I finished the account search workflow. {reason_summary.strip()}",
        "Selected normal success summary because accepted account candidates were found on the primary path.",
    )


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
            CandidateEvidenceRecord.model_validate(_normalize_reasoning_evidence_record(evidence))
            for evidence in candidate.evidence
            if isinstance(evidence, dict)
        ],
    )


def _normalize_reasoning_evidence_record(evidence: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "source_type": _normalize_optional_text(evidence.get("source_type")) or "web",
        "provider_name": _normalize_optional_text(
            evidence.get("provider_name") or evidence.get("provider")
        ),
        "source_url": _normalize_optional_text(
            evidence.get("source_url") or evidence.get("url")
        ),
        "title": _normalize_optional_text(evidence.get("title")),
        "snippet_text": _normalize_optional_text(
            evidence.get("snippet_text") or evidence.get("snippet")
        ),
        "metadata_json": (
            evidence.get("metadata_json")
            if isinstance(evidence.get("metadata_json"), dict)
            else evidence.get("metadata")
            if isinstance(evidence.get("metadata"), dict)
            else None
        ),
    }
    confidence_value = (
        evidence.get("confidence_score")
        if evidence.get("confidence_score") is not None
        else evidence.get("confidence_0_1")
        if evidence.get("confidence_0_1") is not None
        else evidence.get("confidence")
    )
    normalized["confidence_score"] = _normalize_confidence_score(confidence_value)
    return normalized


def _normalize_confidence_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence < 0:
        return None
    if confidence > 1:
        confidence = confidence / 100 if confidence <= 100 else 1.0
    return max(0.0, min(confidence, 1.0))


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


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidate_values: Iterable[Any] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, dict):
        candidate_values = value
    else:
        return []

    normalized_values: list[str] = []
    seen: set[str] = set()
    for candidate in candidate_values:
        if not isinstance(candidate, str):
            continue
        normalized = " ".join(candidate.split())
        if not normalized:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_values.append(normalized)
    return normalized_values


def _normalize_query_ideas(value: Any) -> list[str]:
    normalized_queries = _normalize_string_list(value)
    usable_queries: list[str] = []
    for query in normalized_queries:
        lowered = query.lower()
        if lowered.startswith("find ") and len(query.split()) <= 6:
            continue
        usable_queries.append(query)
    return usable_queries[:4]


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


def _resolve_run_agent_config(*, run: WorkflowRun, agent_name: str) -> dict[str, Any]:
    snapshot = run.config_snapshot_json or {}
    agents = snapshot.get("agents") if isinstance(snapshot, dict) else {}
    payload = agents.get(agent_name) if isinstance(agents, dict) else None
    return payload if isinstance(payload, dict) else {}


def _build_account_search_planner_instructions(
    *,
    base_instructions: Any,
    prior_failure_summary: str | None,
) -> str:
    instruction_parts = [
        _normalize_optional_text(base_instructions),
        (
            "Plan account-search queries before any provider search runs. "
            "Generate 2 to 4 precise, web-search-ready query strings that can discover "
            "B2B target accounts from seller and ICP context. "
            "Do not restate the user's request as an instruction. "
            "Prefer concise keyword phrases, market categories, buyer/problem terms, and "
            "company descriptors over vague prose. "
            "Use prior attempt outcomes to refine later attempts."
        ),
    ]
    if prior_failure_summary:
        instruction_parts.append(f"Retry context: {prior_failure_summary}")
    return " ".join(part for part in instruction_parts if part)


def _planner_failure_summary(
    *,
    response: ContentNormalizerResponse,
    provider_failure_without_payload: bool,
    reasoning_output_present: bool,
) -> str:
    if provider_failure_without_payload:
        return (
            "Account-search planner could not produce a usable plan because the provider "
            f"returned `{response.error_code}` without a payload."
        )
    if reasoning_output_present:
        return (
            "Account-search planner returned a schema-valid payload, but it did not contain "
            "usable non-empty query ideas."
        )
    return "Account-search planner returned invalid structured output."


def _account_search_plan_from_reasoning_output(
    *,
    reasoning_output: Any,
    fallback_fit_criteria: Sequence[str],
) -> AccountSearchPlan | None:
    if reasoning_output is None:
        return None
    query_ideas = _normalize_query_ideas(reasoning_output.query_ideas)
    search_strategy = _normalize_optional_text(reasoning_output.search_strategy)
    if search_strategy is None or not query_ideas:
        return None
    fit_criteria = _normalize_string_list(reasoning_output.fit_criteria)
    clarification_questions = _normalize_string_list(reasoning_output.clarification_questions)
    return AccountSearchPlan(
        search_strategy=search_strategy,
        query_ideas=query_ideas,
        fit_criteria=fit_criteria or list(fallback_fit_criteria),
        clarification_questions=clarification_questions,
    )


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
