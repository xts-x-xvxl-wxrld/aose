from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Artifact, ICPProfile, SellerProfile, WorkflowRun
from app.repositories.account_repository import AccountRepository
from app.repositories.account_research_snapshot_repository import AccountResearchSnapshotRepository
from app.repositories.artifact_repository import ArtifactRepository
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
    PageFetchRequest,
    PageFetchResponse,
    PageFetchTool,
    PageScrapeRequest,
    PageScrapeResponse,
    PageScrapeTool,
    SearchResultRecord,
    ToolSourceReference,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchTool,
    get_tool_provider_name,
)
from app.workers.runtime import WorkflowExecutionError, WorkflowExecutionResult
from app.workflows.contracts import AccountResearchRunResult, AccountResearchRunResultOutcome
from app.workflows.reasoning import (
    is_provider_failure_without_payload,
    validate_account_research_reasoning,
)

MAX_RESEARCH_SEARCH_RESULTS = 3


class AccountResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountResearchWorkflowInput(AccountResearchModel):
    account_id: UUID
    seller_profile_id: UUID
    icp_profile_id: UUID | None = None
    research_objective: str | None = None


class AccountResearchPlan(AccountResearchModel):
    research_strategy: str
    focus_areas: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)


class ResearchEvidenceRecord(AccountResearchModel):
    source_type: str = "web"
    provider_name: str | None = None
    source_url: str | None = None
    title: str | None = None
    snippet_text: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    metadata_json: dict[str, Any] | None = None


class ResearchTopicSummary(AccountResearchModel):
    account_overview: str
    fit_to_seller_proposition: str
    fit_to_icp: str | None = None
    buying_relevance_signals: list[str] = Field(default_factory=list)
    risks_or_disqualifiers: list[str] = Field(default_factory=list)
    linked_evidence_ids: list[UUID] = Field(default_factory=list)


class AccountResearchRecord(AccountResearchModel):
    research_plan: dict[str, Any] = Field(default_factory=dict)
    evidence_categories: list[str] = Field(default_factory=list)
    structured_research_summary: ResearchTopicSummary
    uncertainty_notes: list[str] = Field(default_factory=list)
    research_summary: str
    qualification_summary: str | None = None
    research_brief_markdown: str | None = None
    evidence: list[ResearchEvidenceRecord] = Field(default_factory=list)


@dataclass(frozen=True)
class GatheredResearchContext:
    company_profile: dict[str, Any] | None
    search_results: list[SearchResultRecord]
    scraped_pages: list[dict[str, Any]]
    evidence: list[ResearchEvidenceRecord]
    evidence_categories: list[str]


@dataclass(frozen=True)
class AccountResearchToolset:
    web_search: WebSearchTool
    page_fetch: PageFetchTool
    page_scrape: PageScrapeTool
    content_normalizer: ContentNormalizerTool
    company_enrichment: CompanyEnrichmentTool | None = None


class NullWebSearchTool:
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        _ = request
        return WebSearchResponse(results=[])


class NullPageFetchTool:
    async def execute(self, request: PageFetchRequest) -> PageFetchResponse:
        _ = request
        return PageFetchResponse()


class NullPageScrapeTool:
    async def execute(self, request: PageScrapeRequest) -> PageScrapeResponse:
        _ = request
        return PageScrapeResponse()


class NullContentNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=None)


class NullCompanyEnrichmentTool:
    async def execute(self, request: CompanyEnrichmentRequest) -> CompanyEnrichmentResponse:
        _ = request
        return CompanyEnrichmentResponse()


class AccountResearchWorkflow:
    def __init__(
        self,
        session: AsyncSession,
        *,
        run_service: WorkflowRunService | None = None,
        tools: AccountResearchToolset | None = None,
    ) -> None:
        self._session = session
        self._runs = WorkflowRunRepository(session)
        self._accounts = AccountRepository(session)
        self._seller_profiles = SellerProfileRepository(session)
        self._icp_profiles = ICPProfileRepository(session)
        self._source_evidence = SourceEvidenceRepository(session)
        self._snapshots = AccountResearchSnapshotRepository(session)
        self._artifacts = ArtifactRepository(session)
        self._run_service = run_service or WorkflowRunService(session)
        self._tools = tools or AccountResearchToolset(
            web_search=NullWebSearchTool(),
            page_fetch=NullPageFetchTool(),
            page_scrape=NullPageScrapeTool(),
            content_normalizer=NullContentNormalizerTool(),
            company_enrichment=NullCompanyEnrichmentTool(),
        )

    async def execute(self, request: Any) -> WorkflowExecutionResult:
        run = await self._require_run(tenant_id=request.tenant_id, run_id=request.run_id)
        workflow_input = self._load_workflow_input(run)
        account, seller_profile, icp_profile = await self._load_prerequisites(
            tenant_id=request.tenant_id,
            workflow_input=workflow_input,
        )
        icp_context_present = icp_profile is not None

        await self._run_service.emit_agent_handoff(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            from_agent="orchestrator_agent",
            to_agent="account_research_agent",
            reason="Starting seller-aware account research and evidence gathering.",
        )

        plan = _build_research_plan(
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
        )
        gathered_context = await self._gather_context(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            plan=plan,
        )
        research_record = await self._build_research_record(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            plan=plan,
            gathered_context=gathered_context,
        )

        evidence_records = _dedupe_evidence(
            [*gathered_context.evidence, *research_record.evidence]
        )
        persisted_evidence_ids = await self._persist_evidence(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account_id=account.id,
            evidence_records=evidence_records,
        )

        latest_snapshot = await self._snapshots.get_latest_for_account(
            tenant_id=request.tenant_id,
            account_id=account.id,
        )
        snapshot_version = 1 if latest_snapshot is None else latest_snapshot.snapshot_version + 1
        research_json = _build_snapshot_payload(
            research_record=research_record,
            evidence_ids=persisted_evidence_ids,
            icp_context_present=icp_context_present,
        )
        snapshot = await self._snapshots.create(
            tenant_id=request.tenant_id,
            account_id=account.id,
            workflow_run_id=request.run_id,
            created_by_user_id=request.created_by_user_id,
            snapshot_version=snapshot_version,
            research_json=research_json,
            research_summary=research_record.research_summary,
            qualification_summary=research_record.qualification_summary,
            uncertainty_notes=_join_uncertainty_notes(research_record.uncertainty_notes),
        )
        artifact = await self._maybe_create_research_brief(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            created_by_user_id=request.created_by_user_id,
            account=account,
            research_record=research_record,
        )

        result = AccountResearchRunResult(
            outcome=AccountResearchRunResultOutcome.RESEARCH_COMPLETED,
            snapshot_id=snapshot.id,
            snapshot_version=snapshot.snapshot_version,
            icp_context_present=icp_context_present,
            reason_summary=research_record.research_summary,
        )
        await self._run_service.emit_agent_completed(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            agent_name="account_research_agent",
            result_summary=result.reason_summary,
        )

        canonical_output_ids = {
            "snapshot_ids": [str(snapshot.id)],
            "evidence_ids": [str(evidence_id) for evidence_id in persisted_evidence_ids],
        }
        if artifact is not None:
            canonical_output_ids["artifact_ids"] = [str(artifact.id)]

        return WorkflowExecutionResult(
            result_summary=result.reason_summary,
            normalized_result_json=result.model_dump(mode="json"),
            status_detail=(
                f"Account research completed with snapshot version {snapshot.snapshot_version}."
            ),
            canonical_output_ids=canonical_output_ids,
        )

    async def _gather_context(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        workflow_input: AccountResearchWorkflowInput,
        plan: AccountResearchPlan,
    ) -> GatheredResearchContext:
        evidence: list[ResearchEvidenceRecord] = []
        evidence_categories = ["account_record"]
        company_profile: dict[str, Any] | None = None

        enrichment_response = await self._run_company_enrichment(
            tenant_id=tenant_id,
            run_id=run_id,
            account=account,
        )
        if enrichment_response.company_profile:
            company_profile = enrichment_response.company_profile
            evidence_categories.append("company_enrichment")
        evidence.extend(_build_enrichment_evidence(enrichment_response.source_references))

        search_results = await self._run_web_search(
            tenant_id=tenant_id,
            run_id=run_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            plan=plan,
        )
        if search_results:
            evidence_categories.append("public_web")
        evidence.extend(_build_search_result_evidence(search_results))

        scraped_pages = await self._fetch_and_scrape_pages(
            tenant_id=tenant_id,
            run_id=run_id,
            search_results=search_results,
        )
        if scraped_pages:
            evidence_categories.append("page_content")
            evidence.extend(_build_scraped_page_evidence(scraped_pages))

        return GatheredResearchContext(
            company_profile=company_profile,
            search_results=search_results,
            scraped_pages=scraped_pages,
            evidence=_dedupe_evidence(evidence),
            evidence_categories=_dedupe_strings(evidence_categories),
        )

    async def _run_company_enrichment(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
    ) -> CompanyEnrichmentResponse:
        company_enrichment = self._tools.company_enrichment
        if company_enrichment is None:
            return CompanyEnrichmentResponse()

        request = CompanyEnrichmentRequest(
            domain=account.domain or account.normalized_domain,
            company_name=account.name,
        )
        company_enrichment_provider = get_tool_provider_name(company_enrichment)
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="company_enrichment",
            provider_name=company_enrichment_provider,
            input_summary=f"Enriching account context for {account.name}.",
            correlation_key=f"account-research-{run_id}-company-enrichment",
        )
        response = await company_enrichment.execute(request)
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="company_enrichment",
            provider_name=company_enrichment_provider,
            output_summary=(
                "Resolved provider-backed company context."
                if response.company_profile
                else "No provider-backed company context was resolved."
            ),
            error_code=response.error_code,
            produced_evidence_results=bool(response.source_references),
        )
        return response

    async def _run_web_search(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        workflow_input: AccountResearchWorkflowInput,
        plan: AccountResearchPlan,
    ) -> list[SearchResultRecord]:
        query = _select_primary_query(
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            plan=plan,
        )
        web_search_provider = get_tool_provider_name(self._tools.web_search)
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="web_search",
            provider_name=web_search_provider,
            input_summary=f"Researching public evidence with query: {query}",
            correlation_key=f"account-research-{run_id}-web-search",
        )
        response = await self._tools.web_search.execute(
            WebSearchRequest(query_text=query, result_limit=MAX_RESEARCH_SEARCH_RESULTS)
        )
        search_results = _dedupe_search_results(response.results)
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="web_search",
            provider_name=web_search_provider,
            output_summary=f"Collected {len(search_results)} search result(s).",
            error_code=response.error_code,
            produced_evidence_results=bool(search_results),
        )
        return search_results

    async def _fetch_and_scrape_pages(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        search_results: Sequence[SearchResultRecord],
    ) -> list[dict[str, Any]]:
        scraped_pages: list[dict[str, Any]] = []
        for index, result in enumerate(search_results[:MAX_RESEARCH_SEARCH_RESULTS], start=1):
            correlation_key = f"account-research-{run_id}-page-fetch-{index}"
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="page_fetch",
                provider_name=result.provider_name,
                input_summary=f"Fetching supporting page content from {result.url}",
                correlation_key=correlation_key,
            )
            fetch_response = await self._tools.page_fetch.execute(PageFetchRequest(url=result.url))
            await self._run_service.emit_tool_completed(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="page_fetch",
                provider_name=result.provider_name,
                output_summary=(
                    "Fetched supporting page content."
                    if fetch_response.body_text
                    else "Supporting page content was unavailable."
                ),
                error_code=fetch_response.error_code,
                produced_evidence_results=bool(fetch_response.body_text),
            )
            if not fetch_response.body_text:
                continue

            scrape_key = f"account-research-{run_id}-page-scrape-{index}"
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="page_scrape",
                provider_name=result.provider_name,
                input_summary=f"Extracting normalized page text from {result.url}",
                correlation_key=scrape_key,
            )
            scrape_response = await self._tools.page_scrape.execute(
                PageScrapeRequest(
                    source_url=result.url,
                    body_text=fetch_response.body_text,
                    content_type=fetch_response.content_type,
                )
            )
            normalized_text = _normalize_optional_text(
                scrape_response.normalized_text or fetch_response.body_text
            )
            await self._run_service.emit_tool_completed(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="page_scrape",
                provider_name=result.provider_name,
                output_summary=(
                    "Extracted normalized page content."
                    if normalized_text
                    else "No normalized page content was extracted."
                ),
                error_code=scrape_response.error_code,
                produced_evidence_results=bool(normalized_text),
            )
            if not normalized_text:
                continue

            scraped_pages.append(
                {
                    "title": result.title,
                    "source_url": result.url,
                    "provider_name": result.provider_name,
                    "normalized_text": normalized_text,
                    "headings": scrape_response.headings,
                    "links": scrape_response.links,
                    "metadata": scrape_response.metadata,
                }
            )
        return scraped_pages

    async def _build_research_record(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        workflow_input: AccountResearchWorkflowInput,
        plan: AccountResearchPlan,
        gathered_context: GatheredResearchContext,
    ) -> AccountResearchRecord:
        fallback_record = _build_fallback_research_record(
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            plan=plan,
            gathered_context=gathered_context,
        )

        content_normalizer_provider = get_tool_provider_name(self._tools.content_normalizer)
        agent_config = _resolve_run_agent_config(
            run=await self._require_run(tenant_id=tenant_id, run_id=run_id),
            agent_name="account_research_agent",
        )
        normalizer_payload = {
            "account": _account_payload(account),
            "seller_profile": _seller_profile_payload(seller_profile),
            "icp_profile": (
                _icp_profile_payload(icp_profile) if icp_profile is not None else None
            ),
            "workflow_input": workflow_input.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json"),
            "company_profile": gathered_context.company_profile,
            "search_results": [
                result.model_dump(mode="json") for result in gathered_context.search_results
            ],
            "scraped_pages": gathered_context.scraped_pages,
            "collected_evidence": [
                evidence_record.model_dump(mode="json")
                for evidence_record in gathered_context.evidence
            ],
        }
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            input_summary=f"Normalizing research context for {account.name}.",
            correlation_key=f"account-research-{run_id}-content-normalizer",
        )
        llm_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        response = await self._tools.content_normalizer.execute(
            ContentNormalizerRequest(
                raw_payload=normalizer_payload,
                schema_hint="account_research_summary",
                instructions_override=agent_config.get("instructions"),
                system_prompt_override=agent_config.get("system_prompt"),
                model_override=agent_config.get("model"),
            )
        )
        llm_finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._run_service.record_llm_call(
            tenant_id=tenant_id,
            run_id=run_id,
            agent_name="account_research_agent",
            provider_name=content_normalizer_provider or "openai",
            model_name=(response.raw_metadata_json or {}).get("model") or agent_config.get("model"),
            schema_hint="account_research_summary",
            input_payload=normalizer_payload,
            output_payload=response.normalized_payload,
            status="failed" if response.error_code else "completed",
            latency_ms=max(int((llm_finished_at - llm_started_at).total_seconds() * 1000), 0),
            error_code=response.error_code,
            raw_metadata_json=response.raw_metadata_json,
        )
        reasoning_output = validate_account_research_reasoning(response.normalized_payload)
        provider_failure_without_payload = is_provider_failure_without_payload(
            error_code=response.error_code,
            payload=response.normalized_payload,
        )
        if reasoning_output is None and not provider_failure_without_payload:
            await self._run_service.emit_reasoning_failed_validation(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="account_research_summary",
                provider_name=content_normalizer_provider,
                failure_summary="Structured account-research synthesis did not match schema.",
                fallback_summary="Falling back to deterministic research synthesis.",
            )
        elif reasoning_output is not None:
            await self._run_service.emit_reasoning_validated(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="account_research_summary",
                provider_name=content_normalizer_provider,
                output_summary=(
                    f"Validated account research synthesis with "
                    f"{len(reasoning_output.key_findings)} key findings."
                ),
            )
        parsed_record = _parse_research_record(response.normalized_payload)
        research_record = _merge_research_records(
            parsed_record=parsed_record,
            fallback_record=fallback_record,
            icp_context_present=icp_profile is not None,
        )
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            output_summary="Produced normalized account research output.",
            error_code=response.error_code,
            produced_evidence_results=bool(research_record.evidence),
        )
        return research_record

    async def _persist_evidence(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account_id: UUID,
        evidence_records: Sequence[ResearchEvidenceRecord],
    ) -> list[UUID]:
        persisted_ids: list[UUID] = []
        for evidence_record in evidence_records:
            evidence = await self._source_evidence.create(
                tenant_id=tenant_id,
                workflow_run_id=run_id,
                account_id=account_id,
                source_type=evidence_record.source_type,
                provider_name=evidence_record.provider_name,
                source_url=evidence_record.source_url,
                title=evidence_record.title,
                snippet_text=evidence_record.snippet_text,
                confidence_score=evidence_record.confidence_score,
                metadata_json=evidence_record.metadata_json,
            )
            persisted_ids.append(evidence.id)
        return persisted_ids

    async def _maybe_create_research_brief(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        created_by_user_id: UUID,
        account: Account,
        research_record: AccountResearchRecord,
    ) -> Artifact | None:
        content_markdown = _normalize_optional_text(research_record.research_brief_markdown)
        if content_markdown is None:
            return None
        return await self._artifacts.create(
            tenant_id=tenant_id,
            workflow_run_id=run_id,
            created_by_user_id=created_by_user_id,
            artifact_type="research_brief",
            format="markdown",
            title=f"Research Brief: {account.name}",
            content_markdown=content_markdown,
        )

    async def _require_run(self, *, tenant_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self._runs.get_for_tenant(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise WorkflowExecutionError(
                error_code="resource_not_found",
                message="Workflow run was not found in the requested tenant.",
            )
        return run

    def _load_workflow_input(self, run: WorkflowRun) -> AccountResearchWorkflowInput:
        try:
            return AccountResearchWorkflowInput.model_validate(run.requested_payload_json)
        except ValidationError as exc:
            raise WorkflowExecutionError(
                error_code="validation_error",
                message="Workflow run payload is invalid for account research.",
                status_detail=str(exc),
            ) from exc

    async def _load_prerequisites(
        self,
        *,
        tenant_id: UUID,
        workflow_input: AccountResearchWorkflowInput,
    ) -> tuple[Account, SellerProfile, ICPProfile | None]:
        account = await self._accounts.get_for_tenant(
            tenant_id=tenant_id,
            account_id=workflow_input.account_id,
        )
        seller_profile = await self._seller_profiles.get_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=workflow_input.seller_profile_id,
        )
        icp_profile: ICPProfile | None = None
        if workflow_input.icp_profile_id is not None:
            icp_profile = await self._icp_profiles.get_for_tenant(
                tenant_id=tenant_id,
                icp_profile_id=workflow_input.icp_profile_id,
            )
        if account is None:
            raise WorkflowExecutionError(
                error_code="resource_not_found",
                message="Account was not found in the requested tenant.",
            )
        if seller_profile is None:
            raise WorkflowExecutionError(
                error_code="workflow_prerequisites_missing",
                message="Account research requires seller context.",
                status_detail="Seller profile was not found for this run.",
            )
        if workflow_input.icp_profile_id is not None and icp_profile is None:
            raise WorkflowExecutionError(
                error_code="workflow_prerequisites_missing",
                message="Account research could not load the requested ICP context.",
                status_detail="ICP profile was not found for this run.",
            )
        if icp_profile is not None and icp_profile.seller_profile_id != seller_profile.id:
            raise WorkflowExecutionError(
                error_code="ownership_conflict",
                message="ICP profile does not belong to the requested seller profile.",
            )
        return account, seller_profile, icp_profile


def _build_research_plan(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    workflow_input: AccountResearchWorkflowInput,
) -> AccountResearchPlan:
    focus_areas = [
        "account overview",
        "fit to seller proposition",
        "buying relevance signals",
        "risks or disqualifiers",
    ]
    if icp_profile is not None:
        focus_areas.append("fit to ICP")
    search_queries = [
        _select_primary_query(
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            plan=None,
        )
    ]
    research_strategy = (
        f"Evaluate {account.name} against {seller_profile.company_name}'s seller context"
        " using sourced public evidence."
    )
    if workflow_input.research_objective:
        research_strategy = f"{research_strategy} Objective: {workflow_input.research_objective}"
    return AccountResearchPlan(
        research_strategy=research_strategy,
        focus_areas=_dedupe_strings(focus_areas),
        search_queries=_dedupe_strings(search_queries),
    )


def _select_primary_query(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    workflow_input: AccountResearchWorkflowInput,
    plan: AccountResearchPlan | None,
) -> str:
    if plan is not None and plan.search_queries:
        return plan.search_queries[0]

    parts = [
        workflow_input.research_objective,
        account.name,
        account.domain or account.normalized_domain,
        seller_profile.target_market_summary,
    ]
    if icp_profile is not None:
        parts.extend(_extract_string_values(icp_profile.criteria_json))
    query = " ".join(part for part in parts if part)
    return " ".join(query.split()) or account.name


def _build_enrichment_evidence(
    source_references: Sequence[ToolSourceReference],
) -> list[ResearchEvidenceRecord]:
    evidence: list[ResearchEvidenceRecord] = []
    for source_reference in source_references:
        evidence.append(
            ResearchEvidenceRecord(
                source_type="provider",
                provider_name=source_reference.provider_name,
                source_url=source_reference.source_url,
                title=source_reference.title,
            )
        )
    return evidence


def _build_search_result_evidence(
    search_results: Sequence[SearchResultRecord],
) -> list[ResearchEvidenceRecord]:
    evidence: list[ResearchEvidenceRecord] = []
    for result in search_results:
        evidence.append(
            ResearchEvidenceRecord(
                source_type="web",
                provider_name=result.provider_name,
                source_url=result.url,
                title=result.title,
                snippet_text=_normalize_optional_text(result.snippet),
                metadata_json=result.provider_metadata,
            )
        )
    return evidence


def _build_scraped_page_evidence(scraped_pages: Sequence[dict[str, Any]]) -> list[ResearchEvidenceRecord]:
    evidence: list[ResearchEvidenceRecord] = []
    for page in scraped_pages:
        evidence.append(
            ResearchEvidenceRecord(
                source_type="web",
                provider_name=_normalize_optional_text(page.get("provider_name")),
                source_url=_normalize_optional_text(page.get("source_url")),
                title=_normalize_optional_text(page.get("title")),
                snippet_text=_normalize_optional_text(page.get("normalized_text")),
                metadata_json={
                    "headings": page.get("headings") or [],
                    "links": page.get("links") or [],
                    "metadata": page.get("metadata"),
                },
            )
        )
    return evidence


def _parse_research_record(payload: dict[str, Any] | list[dict[str, Any]] | None) -> AccountResearchRecord | None:
    if not isinstance(payload, dict):
        return None

    normalized_payload = dict(payload)
    uncertainty_notes = normalized_payload.get("uncertainty_notes")
    if isinstance(uncertainty_notes, str):
        normalized_payload["uncertainty_notes"] = [uncertainty_notes]

    evidence_categories = normalized_payload.get("evidence_categories")
    if isinstance(evidence_categories, str):
        normalized_payload["evidence_categories"] = [evidence_categories]

    structured_summary = normalized_payload.get("structured_research_summary")
    if isinstance(structured_summary, dict):
        if isinstance(structured_summary.get("buying_relevance_signals"), str):
            structured_summary["buying_relevance_signals"] = [
                structured_summary["buying_relevance_signals"]
            ]
        if isinstance(structured_summary.get("risks_or_disqualifiers"), str):
            structured_summary["risks_or_disqualifiers"] = [
                structured_summary["risks_or_disqualifiers"]
            ]
    try:
        return AccountResearchRecord.model_validate(normalized_payload)
    except ValidationError:
        return None


def _merge_research_records(
    *,
    parsed_record: AccountResearchRecord | None,
    fallback_record: AccountResearchRecord,
    icp_context_present: bool,
) -> AccountResearchRecord:
    if parsed_record is None:
        return _strip_icp_fit_if_missing_context(
            research_record=fallback_record,
            icp_context_present=icp_context_present,
        )

    parsed_summary = parsed_record.structured_research_summary
    fallback_summary = fallback_record.structured_research_summary
    merged_summary = ResearchTopicSummary(
        account_overview=parsed_summary.account_overview or fallback_summary.account_overview,
        fit_to_seller_proposition=(
            parsed_summary.fit_to_seller_proposition or fallback_summary.fit_to_seller_proposition
        ),
        fit_to_icp=parsed_summary.fit_to_icp or fallback_summary.fit_to_icp,
        buying_relevance_signals=_dedupe_strings(
            [*parsed_summary.buying_relevance_signals, *fallback_summary.buying_relevance_signals]
        ),
        risks_or_disqualifiers=_dedupe_strings(
            [*parsed_summary.risks_or_disqualifiers, *fallback_summary.risks_or_disqualifiers]
        ),
        linked_evidence_ids=[],
    )
    merged_record = AccountResearchRecord(
        research_plan=parsed_record.research_plan or fallback_record.research_plan,
        evidence_categories=_dedupe_strings(
            [*parsed_record.evidence_categories, *fallback_record.evidence_categories]
        ),
        structured_research_summary=merged_summary,
        uncertainty_notes=_dedupe_strings(
            [*parsed_record.uncertainty_notes, *fallback_record.uncertainty_notes]
        ),
        research_summary=parsed_record.research_summary or fallback_record.research_summary,
        qualification_summary=(
            parsed_record.qualification_summary or fallback_record.qualification_summary
        ),
        research_brief_markdown=(
            parsed_record.research_brief_markdown or fallback_record.research_brief_markdown
        ),
        evidence=_dedupe_evidence([*parsed_record.evidence, *fallback_record.evidence]),
    )
    return _strip_icp_fit_if_missing_context(
        research_record=merged_record,
        icp_context_present=icp_context_present,
    )


def _strip_icp_fit_if_missing_context(
    *,
    research_record: AccountResearchRecord,
    icp_context_present: bool,
) -> AccountResearchRecord:
    if icp_context_present:
        return research_record
    return research_record.model_copy(
        update={
            "structured_research_summary": research_record.structured_research_summary.model_copy(
                update={"fit_to_icp": None}
            )
        }
    )


def _build_fallback_research_record(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    workflow_input: AccountResearchWorkflowInput,
    plan: AccountResearchPlan,
    gathered_context: GatheredResearchContext,
) -> AccountResearchRecord:
    account_overview = _build_account_overview(account=account, gathered_context=gathered_context)
    fit_to_seller = _build_fit_to_seller_summary(account=account, seller_profile=seller_profile)
    fit_to_icp = _build_fit_to_icp_summary(account=account, icp_profile=icp_profile)
    buying_relevance_signals = _build_buying_signals(
        account=account,
        gathered_context=gathered_context,
    )
    risks = _build_risks(
        account=account,
        icp_profile=icp_profile,
        gathered_context=gathered_context,
    )
    uncertainty_notes = _build_uncertainty_notes(
        account=account,
        icp_profile=icp_profile,
        gathered_context=gathered_context,
    )
    evidence_categories = _dedupe_strings(
        [*gathered_context.evidence_categories, "seller_fit_assessment"]
    )
    research_summary = _build_research_summary(
        account=account,
        seller_profile=seller_profile,
        fit_to_seller=fit_to_seller,
        fit_to_icp=fit_to_icp,
        uncertainty_notes=uncertainty_notes,
    )
    qualification_summary = fit_to_icp or fit_to_seller
    research_brief_markdown = _render_research_brief(
        account=account,
        seller_profile=seller_profile,
        icp_profile=icp_profile,
        account_overview=account_overview,
        fit_to_seller=fit_to_seller,
        fit_to_icp=fit_to_icp,
        buying_relevance_signals=buying_relevance_signals,
        risks=risks,
        uncertainty_notes=uncertainty_notes,
        evidence_count=len(gathered_context.evidence),
    )
    return AccountResearchRecord(
        research_plan={
            "research_strategy": plan.research_strategy,
            "focus_areas": plan.focus_areas,
            "search_queries": plan.search_queries,
            "research_objective": workflow_input.research_objective,
        },
        evidence_categories=evidence_categories,
        structured_research_summary=ResearchTopicSummary(
            account_overview=account_overview,
            fit_to_seller_proposition=fit_to_seller,
            fit_to_icp=fit_to_icp,
            buying_relevance_signals=buying_relevance_signals,
            risks_or_disqualifiers=risks,
            linked_evidence_ids=[],
        ),
        uncertainty_notes=uncertainty_notes,
        research_summary=research_summary,
        qualification_summary=qualification_summary,
        research_brief_markdown=research_brief_markdown,
        evidence=[],
    )


def _build_snapshot_payload(
    *,
    research_record: AccountResearchRecord,
    evidence_ids: Sequence[UUID],
    icp_context_present: bool,
) -> dict[str, Any]:
    structured_summary = research_record.structured_research_summary.model_copy(
        update={"linked_evidence_ids": list(evidence_ids)}
    )
    structured_summary_payload = structured_summary.model_dump(mode="json", exclude_none=True)
    if not icp_context_present:
        structured_summary_payload.pop("fit_to_icp", None)

    return {
        "research_plan": research_record.research_plan,
        "evidence_categories": research_record.evidence_categories,
        "structured_research_summary": structured_summary_payload,
        "uncertainty_notes": research_record.uncertainty_notes,
        "research_summary": research_record.research_summary,
        "qualification_summary": research_record.qualification_summary,
        "icp_context_present": icp_context_present,
    }


def _build_account_overview(
    *,
    account: Account,
    gathered_context: GatheredResearchContext,
) -> str:
    profile_summary = _extract_profile_summary(gathered_context.company_profile)
    overview_parts = [
        account.name,
        account.industry,
        account.hq_location,
        account.employee_range,
        profile_summary,
    ]
    return ". ".join(part for part in overview_parts if part) or account.name


def _build_fit_to_seller_summary(
    *,
    account: Account,
    seller_profile: SellerProfile,
) -> str:
    if account.fit_summary:
        return account.fit_summary
    if account.industry:
        return (
            f"{account.name} shows relevance to {seller_profile.company_name}'s proposition"
            f" through its {account.industry} footprint."
        )
    return (
        f"{account.name} should be evaluated against {seller_profile.company_name}'s value"
        " proposition using the limited public context available."
    )


def _build_fit_to_icp_summary(
    *,
    account: Account,
    icp_profile: ICPProfile | None,
) -> str | None:
    if icp_profile is None:
        return None

    matched_criteria: list[str] = []
    searchable_text = " ".join(
        value
        for value in [
            account.name,
            account.domain,
            account.hq_location,
            account.employee_range,
            account.industry,
            account.fit_summary,
        ]
        if value
    ).lower()
    for criterion in _extract_string_values(icp_profile.criteria_json):
        if criterion.lower() in searchable_text:
            matched_criteria.append(criterion)

    if matched_criteria:
        return f"Observed overlap with ICP signals: {', '.join(_dedupe_strings(matched_criteria))}."
    return "ICP fit remains directional because the available evidence does not confirm core criteria."


def _build_buying_signals(
    *,
    account: Account,
    gathered_context: GatheredResearchContext,
) -> list[str]:
    signals = _flatten_signal_values(account.fit_signals_json)
    if gathered_context.company_profile:
        signals.extend(_extract_interesting_profile_values(gathered_context.company_profile))
    for result in gathered_context.search_results:
        if result.snippet:
            signals.append(result.snippet)
    return _dedupe_strings(signals)[:4]


def _build_risks(
    *,
    account: Account,
    icp_profile: ICPProfile | None,
    gathered_context: GatheredResearchContext,
) -> list[str]:
    risks: list[str] = []
    if icp_profile is not None:
        exclusion_values = _extract_string_values(icp_profile.exclusions_json or {})
        searchable_text = " ".join(
            value
            for value in [
                account.name,
                account.domain,
                account.hq_location,
                account.employee_range,
                account.industry,
                account.fit_summary,
            ]
            if value
        ).lower()
        for exclusion in exclusion_values:
            if exclusion.lower() in searchable_text:
                risks.append(f"Potential ICP exclusion match: {exclusion}.")
    if not gathered_context.search_results:
        risks.append("Limited public-source coverage makes the account harder to qualify.")
    if account.domain is None and account.linkedin_url is None:
        risks.append("Key canonical company identifiers are incomplete and require manual validation.")
    return _dedupe_strings(risks)


def _build_uncertainty_notes(
    *,
    account: Account,
    icp_profile: ICPProfile | None,
    gathered_context: GatheredResearchContext,
) -> list[str]:
    notes: list[str] = []
    if icp_profile is None:
        notes.append("ICP context was not provided, so ICP-fit claims were intentionally omitted.")
    if not gathered_context.evidence:
        notes.append("Public evidence is sparse; conclusions should be treated as provisional.")
    if account.domain is None:
        notes.append("The account domain is missing, which limits provider-based enrichment confidence.")
    return _dedupe_strings(notes)


def _build_research_summary(
    *,
    account: Account,
    seller_profile: SellerProfile,
    fit_to_seller: str,
    fit_to_icp: str | None,
    uncertainty_notes: Sequence[str],
) -> str:
    if fit_to_icp:
        return (
            f"Completed seller-aware research for {account.name} against"
            f" {seller_profile.company_name}. {fit_to_seller} {fit_to_icp}"
        )
    if uncertainty_notes:
        return (
            f"Completed seller-aware research for {account.name} against"
            f" {seller_profile.company_name} with explicit uncertainty preserved."
        )
    return f"Completed seller-aware research for {account.name} against {seller_profile.company_name}."


def _render_research_brief(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    account_overview: str,
    fit_to_seller: str,
    fit_to_icp: str | None,
    buying_relevance_signals: Sequence[str],
    risks: Sequence[str],
    uncertainty_notes: Sequence[str],
    evidence_count: int,
) -> str:
    lines = [
        f"# Research Brief: {account.name}",
        "",
        f"Seller context: {seller_profile.company_name}",
        f"Evidence items captured: {evidence_count}",
        "",
        "## Account Overview",
        account_overview,
        "",
        "## Fit To Seller Proposition",
        fit_to_seller,
    ]
    if icp_profile is not None and fit_to_icp:
        lines.extend(["", f"## Fit To ICP ({icp_profile.name})", fit_to_icp])
    if buying_relevance_signals:
        lines.extend(["", "## Buying Relevance Signals"])
        lines.extend(f"- {signal}" for signal in buying_relevance_signals)
    if risks:
        lines.extend(["", "## Risks Or Disqualifiers"])
        lines.extend(f"- {risk}" for risk in risks)
    if uncertainty_notes:
        lines.extend(["", "## Uncertainty Notes"])
        lines.extend(f"- {note}" for note in uncertainty_notes)
    return "\n".join(lines)


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


def _dedupe_evidence(evidence_records: Sequence[ResearchEvidenceRecord]) -> list[ResearchEvidenceRecord]:
    deduped: list[ResearchEvidenceRecord] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for evidence_record in evidence_records:
        key = (
            evidence_record.source_type,
            evidence_record.provider_name,
            evidence_record.source_url,
            evidence_record.title,
            evidence_record.snippet_text,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(evidence_record)
    return deduped


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(normalized)
    return deduped


def _flatten_signal_values(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    values: list[str] = []
    for key, value in payload.items():
        flattened = _extract_string_values({key: value})
        if flattened:
            values.append(f"{key}: {', '.join(flattened)}")
        elif isinstance(value, bool) and value:
            values.append(key.replace("_", " "))
    return values


def _extract_interesting_profile_values(payload: dict[str, Any]) -> list[str]:
    interesting: list[str] = []
    for key, value in payload.items():
        if key.lower() in {"summary", "description", "category", "industry", "stage", "headcount"}:
            interesting.extend(_extract_string_values({key: value}))
    return interesting


def _extract_profile_summary(company_profile: dict[str, Any] | None) -> str | None:
    if not company_profile:
        return None
    for key in ("summary", "description", "company_summary"):
        value = company_profile.get(key)
        normalized = _normalize_optional_text(value)
        if normalized is not None:
            return normalized
    values = _extract_string_values(company_profile)
    return values[0] if values else None


def _extract_string_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in payload.values():
        values.extend(_flatten_string_values(value))
    return values


def _flatten_string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, dict):
        values: list[str] = []
        for child in value.values():
            values.extend(_flatten_string_values(child))
        return values
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for child in value:
            values.extend(_flatten_string_values(child))
        return values
    return [str(value)]


def _join_uncertainty_notes(notes: Sequence[str]) -> str | None:
    normalized = _dedupe_strings(notes)
    if not normalized:
        return None
    return "\n".join(normalized)


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _account_payload(account: Account) -> dict[str, Any]:
    return {
        "account_id": str(account.id),
        "name": account.name,
        "domain": account.domain,
        "normalized_domain": account.normalized_domain,
        "linkedin_url": account.linkedin_url,
        "hq_location": account.hq_location,
        "employee_range": account.employee_range,
        "industry": account.industry,
        "status": account.status,
        "fit_summary": account.fit_summary,
        "fit_signals_json": account.fit_signals_json,
        "canonical_data_json": account.canonical_data_json,
    }


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
