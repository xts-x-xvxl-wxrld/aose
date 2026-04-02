from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AccountResearchSnapshot,
    Contact,
    ICPProfile,
    SellerProfile,
    WorkflowRun,
)
from app.repositories.account_repository import AccountRepository
from app.repositories.account_research_snapshot_repository import AccountResearchSnapshotRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.icp_profile_repository import ICPProfileRepository
from app.repositories.seller_profile_repository import SellerProfileRepository
from app.repositories.source_evidence_repository import SourceEvidenceRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.workflow_runs import WorkflowRunService
from app.tools.contracts import (
    ContactSearchProviderRequest,
    ContactSearchProviderResponse,
    ContactSearchProviderRoutingPolicy,
    ContactSearchProviderTool,
    ContactEnrichmentRequest,
    ContactEnrichmentResponse,
    ContactEnrichmentTool,
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
from app.workflows.contracts import (
    ContactMissingDataFlag,
    ContactSearchRunResult,
    ContactSearchRunResultOutcome,
)
from app.workflows.reasoning import validate_contact_search_reasoning

MAX_CONTACT_SEARCH_RESULTS = 5


class ContactSearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContactSearchWorkflowInput(ContactSearchModel):
    account_id: UUID
    seller_profile_id: UUID
    icp_profile_id: UUID | None = None
    contact_objective: str | None = None


class ContactCandidateEvidenceRecord(ContactSearchModel):
    source_type: str = "web"
    provider_name: str | None = None
    source_url: str | None = None
    title: str | None = None
    snippet_text: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    metadata_json: dict[str, Any] | None = None


class ContactCandidateRecord(ContactSearchModel):
    full_name: str = Field(min_length=1)
    job_title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    company_domain: str | None = None
    source_provider: str | None = None
    acceptance_reason: str | None = None
    ranking_summary: str | None = None
    persona_match_summary: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    missing_data_flags: list[ContactMissingDataFlag] = Field(default_factory=list)
    person_data_json: dict[str, Any] | None = None
    evidence: list[ContactCandidateEvidenceRecord] = Field(default_factory=list)


class ContactSearchRecord(ContactSearchModel):
    target_personas: list[str] = Field(default_factory=list)
    selection_criteria: list[str] = Field(default_factory=list)
    ranked_contact_rationale: str
    missing_data_flags: list[ContactMissingDataFlag] = Field(default_factory=list)
    contacts: list[ContactCandidateRecord] = Field(default_factory=list)


@dataclass(frozen=True)
class ContactSearchToolset:
    web_search: WebSearchTool
    content_normalizer: ContentNormalizerTool
    contact_enrichment: ContactEnrichmentTool | None = None
    provider_search: ContactSearchProviderTool | None = None
    fallback_provider_search: ContactSearchProviderTool | None = None
    provider_routing_policy: ContactSearchProviderRoutingPolicy | None = None


class NullWebSearchTool:
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        _ = request
        return WebSearchResponse(results=[])


class NullContentNormalizerTool:
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        _ = request
        return ContentNormalizerResponse(normalized_payload=None)


class NullContactEnrichmentTool:
    async def execute(self, request: ContactEnrichmentRequest) -> ContactEnrichmentResponse:
        _ = request
        return ContactEnrichmentResponse()


class ContactSearchWorkflow:
    def __init__(
        self,
        session: AsyncSession,
        *,
        run_service: WorkflowRunService | None = None,
        tools: ContactSearchToolset | None = None,
    ) -> None:
        self._session = session
        self._runs = WorkflowRunRepository(session)
        self._accounts = AccountRepository(session)
        self._seller_profiles = SellerProfileRepository(session)
        self._icp_profiles = ICPProfileRepository(session)
        self._snapshots = AccountResearchSnapshotRepository(session)
        self._contacts = ContactRepository(session)
        self._source_evidence = SourceEvidenceRepository(session)
        self._run_service = run_service or WorkflowRunService(session)
        self._tools = tools or ContactSearchToolset(
            web_search=NullWebSearchTool(),
            content_normalizer=NullContentNormalizerTool(),
            contact_enrichment=NullContactEnrichmentTool(),
        )

    async def execute(self, request: Any) -> WorkflowExecutionResult:
        run = await self._require_run(tenant_id=request.tenant_id, run_id=request.run_id)
        workflow_input = self._load_workflow_input(run)
        account, seller_profile, icp_profile, latest_snapshot = await self._load_prerequisites(
            tenant_id=request.tenant_id,
            workflow_input=workflow_input,
        )

        await self._run_service.emit_agent_handoff(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            from_agent="orchestrator_agent",
            to_agent="contact_search_agent",
            reason="Starting seller-aware contact search and ranking.",
        )

        provider_response = await self._run_provider_search(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
        )
        search_results = await self._run_web_search(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            latest_snapshot=latest_snapshot,
        )
        search_record = await self._build_contact_search_record(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            latest_snapshot=latest_snapshot,
            provider_response=provider_response,
            search_results=search_results,
        )
        enriched_candidates = await self._maybe_enrich_candidates(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            account=account,
            candidates=search_record.contacts,
        )
        finalized_candidates = [_finalize_candidate(candidate) for candidate in enriched_candidates]
        missing_data_flags = _dedupe_missing_data_flags(
            [
                *search_record.missing_data_flags,
                *[
                    flag
                    for candidate in finalized_candidates
                    for flag in candidate.missing_data_flags
                ],
            ]
        )
        contact_ids, evidence_ids = await self._persist_candidates(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            created_by_user_id=request.created_by_user_id,
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            latest_snapshot=latest_snapshot,
            target_personas=search_record.target_personas,
            selection_criteria=search_record.selection_criteria,
            candidates=finalized_candidates,
        )

        result = ContactSearchRunResult(
            outcome=ContactSearchRunResultOutcome.CONTACTS_RANKED,
            contact_ids=contact_ids,
            missing_data_flags=missing_data_flags,
            used_research_snapshot_id=latest_snapshot.id if latest_snapshot is not None else None,
            reason_summary=search_record.ranked_contact_rationale,
        )
        await self._run_service.emit_agent_completed(
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            agent_name="contact_search_agent",
            result_summary=result.reason_summary,
        )

        canonical_output_ids = {
            "contact_ids": [str(contact_id) for contact_id in contact_ids],
        }
        if evidence_ids:
            canonical_output_ids["evidence_ids"] = [
                str(evidence_id) for evidence_id in evidence_ids
            ]

        return WorkflowExecutionResult(
            result_summary=result.reason_summary,
            normalized_result_json=result.model_dump(mode="json"),
            status_detail=(
                f"Contact search completed with {len(contact_ids)} ranked contact candidate(s)."
            ),
            canonical_output_ids=canonical_output_ids,
        )

    async def _run_provider_search(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        workflow_input: ContactSearchWorkflowInput,
    ) -> ContactSearchProviderResponse | None:
        provider_search = self._tools.provider_search
        if provider_search is None:
            return None

        routing_policy = self._tools.provider_routing_policy or ContactSearchProviderRoutingPolicy(
            primary_provider=get_tool_provider_name(provider_search) or "findymail",
            fallback_provider=get_tool_provider_name(self._tools.fallback_provider_search),
            routing_basis="phase3_default_findymail_primary",
        )
        await self._run_service.emit_provider_routing_decision(
            tenant_id=tenant_id,
            run_id=run_id,
            capability="contact_search_provider",
            selected_provider=routing_policy.primary_provider,
            fallback_provider=routing_policy.fallback_provider,
            routing_basis=routing_policy.routing_basis,
            reason_summary="Selecting the default primary provider for Phase 3 contact search.",
        )

        request = _build_provider_search_request(
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
        )
        primary_provider_name = get_tool_provider_name(provider_search)
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="contact_provider_search",
            provider_name=primary_provider_name,
            input_summary=(
                f"Searching provider-backed contacts for {account.name} "
                f"with {len(request.title_hints)} normalized role hint(s)."
            ),
            correlation_key=f"contact-search-{run_id}-provider-search-primary",
        )
        response = await provider_search.search(request)
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="contact_provider_search",
            provider_name=response.provider_name,
            output_summary=response.raw_result_summary
            or f"Retrieved {len(response.candidates)} provider candidate(s).",
            error_code=response.error_code,
            produced_evidence_results=bool(response.candidates),
        )

        should_fallback = (
            self._tools.fallback_provider_search is not None
            and (
                response.error_code in {
                    "provider_auth_error",
                    "provider_rate_limit",
                    "provider_quota_exceeded",
                    "provider_unavailable",
                }
                or not response.candidates
            )
        )
        if not should_fallback:
            return response

        fallback_provider_name = get_tool_provider_name(self._tools.fallback_provider_search)
        await self._run_service.emit_provider_routing_decision(
            tenant_id=tenant_id,
            run_id=run_id,
            capability="contact_search_provider",
            selected_provider=fallback_provider_name or "tomba",
            fallback_provider=None,
            routing_basis="phase3_explicit_fallback_rule",
            reason_summary=(
                "Primary provider triggered fallback due to "
                f"{response.error_code or 'explicit no-results'}."
            ),
        )
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="contact_provider_search",
            provider_name=fallback_provider_name,
            input_summary=f"Falling back to provider-backed contact search for {account.name}.",
            correlation_key=f"contact-search-{run_id}-provider-search-fallback",
        )
        fallback_response = await self._tools.fallback_provider_search.search(request)
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="contact_provider_search",
            provider_name=fallback_response.provider_name,
            output_summary=fallback_response.raw_result_summary
            or f"Retrieved {len(fallback_response.candidates)} provider candidate(s).",
            error_code=fallback_response.error_code,
            produced_evidence_results=bool(fallback_response.candidates),
        )
        return fallback_response

    async def _run_web_search(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        workflow_input: ContactSearchWorkflowInput,
        latest_snapshot: AccountResearchSnapshot | None,
    ) -> list[SearchResultRecord]:
        search_results: list[SearchResultRecord] = []
        web_search_provider = get_tool_provider_name(self._tools.web_search)
        for query_index, query in enumerate(
            _build_search_queries(
                account=account,
                seller_profile=seller_profile,
                icp_profile=icp_profile,
                workflow_input=workflow_input,
                latest_snapshot=latest_snapshot,
            ),
            start=1,
        ):
            correlation_key = f"contact-search-{run_id}-web-search-{query_index}"
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="web_search",
                provider_name=web_search_provider,
                input_summary=f"Searching for contacts with query: {query}",
                correlation_key=correlation_key,
            )
            response = await self._tools.web_search.execute(
                WebSearchRequest(query_text=query, result_limit=MAX_CONTACT_SEARCH_RESULTS)
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
        return _dedupe_search_results(search_results)

    async def _build_contact_search_record(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        workflow_input: ContactSearchWorkflowInput,
        latest_snapshot: AccountResearchSnapshot | None,
        provider_response: ContactSearchProviderResponse | None,
        search_results: Sequence[SearchResultRecord],
    ) -> ContactSearchRecord:
        fallback_record = _build_fallback_contact_search_record(
            account=account,
            seller_profile=seller_profile,
            icp_profile=icp_profile,
            workflow_input=workflow_input,
            latest_snapshot=latest_snapshot,
            provider_response=provider_response,
            search_results=search_results,
        )

        content_normalizer_provider = get_tool_provider_name(self._tools.content_normalizer)
        await self._run_service.emit_tool_started(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            input_summary=(
                "Normalizing and ranking contact candidates from "
                f"{len(search_results)} search result(s)."
            ),
            correlation_key=f"contact-search-{run_id}-normalize",
        )
        response = await self._tools.content_normalizer.execute(
            ContentNormalizerRequest(
                raw_payload={
                    "account": _account_payload(account),
                    "seller_profile": _seller_profile_payload(seller_profile),
                    "icp_profile": (
                        _icp_profile_payload(icp_profile) if icp_profile is not None else None
                    ),
                    "workflow_input": workflow_input.model_dump(mode="json"),
                    "provider_response": (
                        provider_response.model_dump(mode="json")
                        if provider_response is not None
                        else None
                    ),
                    "latest_research_snapshot": (
                        _research_snapshot_payload(latest_snapshot)
                        if latest_snapshot is not None
                        else None
                    ),
                    "search_results": [result.model_dump(mode="json") for result in search_results],
                },
                schema_hint="contact_search_candidates",
            )
        )
        reasoning_output = validate_contact_search_reasoning(response.normalized_payload)
        if reasoning_output is None:
            await self._run_service.emit_reasoning_failed_validation(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="contact_search_candidates",
                provider_name=content_normalizer_provider,
                failure_summary="Structured contact-search ranking output did not match schema.",
                fallback_summary="Falling back to provider-backed deterministic ranking.",
            )
        else:
            await self._run_service.emit_reasoning_validated(
                tenant_id=tenant_id,
                run_id=run_id,
                schema_name="contact_search_candidates",
                provider_name=content_normalizer_provider,
                output_summary=(
                    f"Validated {len(reasoning_output.accepted_contacts)} accepted and "
                    f"{len(reasoning_output.rejected_contacts)} rejected contact candidates."
                ),
            )
        parsed_record = _parse_contact_search_record(response.normalized_payload)
        merged_record = _merge_contact_search_records(
            parsed_record=parsed_record,
            fallback_record=fallback_record,
        )
        accepted_keys = {
            (_normalize_optional_text(candidate.full_name) or "", _normalize_email(candidate.email) or "")
            for candidate in merged_record.contacts
        }
        if reasoning_output is not None:
            for candidate in reasoning_output.rejected_contacts:
                await self._run_service.emit_candidate_rejected(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    entity_type="contact",
                    candidate_label=candidate.full_name,
                    reason_summary=candidate.acceptance_reason
                    or "Candidate was rejected by structured ranking.",
                    provider_name=candidate.source_provider,
                )
            for candidate in reasoning_output.accepted_contacts:
                candidate_key = (
                    _normalize_optional_text(candidate.full_name) or "",
                    _normalize_email(candidate.email) or "",
                )
                if candidate_key not in accepted_keys:
                    continue
                await self._run_service.emit_candidate_accepted(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    entity_type="contact",
                    candidate_label=candidate.full_name,
                    reason_summary=candidate.acceptance_reason,
                    provider_name=candidate.source_provider,
                )
        await self._run_service.emit_tool_completed(
            tenant_id=tenant_id,
            run_id=run_id,
            tool_name="content_normalizer",
            provider_name=content_normalizer_provider,
            output_summary=(
                f"Ranked {len(merged_record.contacts)} normalized contact candidate(s)."
            ),
            error_code=response.error_code,
            produced_evidence_results=bool(merged_record.contacts),
        )
        return merged_record

    async def _maybe_enrich_candidates(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account: Account,
        candidates: Sequence[ContactCandidateRecord],
    ) -> list[ContactCandidateRecord]:
        if self._tools.contact_enrichment is None:
            return list(candidates)

        enriched_candidates: list[ContactCandidateRecord] = []
        contact_enrichment_provider = get_tool_provider_name(self._tools.contact_enrichment)
        for candidate_index, candidate in enumerate(candidates, start=1):
            provider_key = _extract_provider_key(candidate.person_data_json)
            contact_name = _normalize_optional_text(candidate.full_name)
            contact_title = _normalize_optional_text(candidate.job_title)
            if contact_name is None and contact_title is None and provider_key is None:
                enriched_candidates.append(candidate)
                continue

            correlation_key = f"contact-search-{run_id}-contact-enrichment-{candidate_index}"
            await self._run_service.emit_tool_started(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="contact_enrichment",
                provider_name=contact_enrichment_provider,
                input_summary=f"Enriching contact candidate {candidate.full_name}.",
                correlation_key=correlation_key,
            )
            response = await self._tools.contact_enrichment.execute(
                ContactEnrichmentRequest(
                    account_id=account.id,
                    contact_name=contact_name,
                    contact_title=contact_title,
                    provider_key=provider_key,
                )
            )
            await self._run_service.emit_tool_completed(
                tenant_id=tenant_id,
                run_id=run_id,
                tool_name="contact_enrichment",
                provider_name=contact_enrichment_provider,
                output_summary=(
                    "Resolved provider-backed contact data."
                    if any(
                        [
                            response.full_name,
                            response.job_title,
                            response.email,
                            response.linkedin_url,
                            response.phone,
                            response.person_profile,
                        ]
                    )
                    else "No provider-backed contact data was resolved."
                ),
                error_code=response.error_code,
                produced_evidence_results=bool(response.source_references),
            )
            enriched_candidates.append(
                _apply_contact_enrichment(candidate=candidate, response=response)
            )
        return enriched_candidates

    async def _persist_candidates(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        created_by_user_id: UUID,
        account: Account,
        seller_profile: SellerProfile,
        icp_profile: ICPProfile | None,
        latest_snapshot: AccountResearchSnapshot | None,
        target_personas: Sequence[str],
        selection_criteria: Sequence[str],
        candidates: Sequence[ContactCandidateRecord],
    ) -> tuple[list[UUID], list[UUID]]:
        existing_contacts = list(
            await self._contacts.list_for_account(tenant_id=tenant_id, account_id=account.id)
        )
        email_index: dict[str, Contact] = {}
        linkedin_index: dict[str, Contact] = {}
        for existing_contact in existing_contacts:
            normalized_email = _normalize_email(existing_contact.email)
            if normalized_email is not None:
                email_index[normalized_email] = existing_contact
            normalized_linkedin = _normalize_profile_url(existing_contact.linkedin_url)
            if normalized_linkedin is not None:
                linkedin_index[normalized_linkedin] = existing_contact

        persisted_contact_ids: list[UUID] = []
        evidence_ids: list[UUID] = []
        for candidate in candidates:
            normalized_email = _normalize_email(candidate.email)
            normalized_linkedin = _normalize_profile_url(candidate.linkedin_url)
            existing_contact = (
                email_index.get(normalized_email) if normalized_email is not None else None
            )
            if existing_contact is None and normalized_linkedin is not None:
                existing_contact = linkedin_index.get(normalized_linkedin)

            if existing_contact is None:
                contact = await self._contacts.create(
                    tenant_id=tenant_id,
                    account_id=account.id,
                    created_by_user_id=created_by_user_id,
                    full_name=candidate.full_name,
                    job_title=_normalize_optional_text(candidate.job_title),
                    email=normalized_email,
                    linkedin_url=_normalize_optional_text(candidate.linkedin_url),
                    phone=_normalize_optional_text(candidate.phone),
                    status="candidate",
                    ranking_summary=_normalize_optional_text(candidate.ranking_summary),
                    person_data_json=_build_contact_person_data(
                        candidate=candidate,
                        seller_profile=seller_profile,
                        icp_profile=icp_profile,
                        latest_snapshot=latest_snapshot,
                        target_personas=target_personas,
                        selection_criteria=selection_criteria,
                    ),
                )
            else:
                contact = existing_contact
                changes = _build_contact_merge_changes(
                    existing=existing_contact,
                    candidate=candidate,
                    seller_profile=seller_profile,
                    icp_profile=icp_profile,
                    latest_snapshot=latest_snapshot,
                    target_personas=target_personas,
                    selection_criteria=selection_criteria,
                )
                if changes:
                    updated_contact = await self._contacts.update(
                        tenant_id=tenant_id,
                        contact_id=existing_contact.id,
                        updated_by_user_id=created_by_user_id,
                        changes=changes,
                    )
                    assert updated_contact is not None
                    contact = updated_contact

            if normalized_email is not None:
                email_index[normalized_email] = contact
            normalized_linkedin = _normalize_profile_url(contact.linkedin_url)
            if normalized_linkedin is not None:
                linkedin_index[normalized_linkedin] = contact

            persisted_contact_ids = _merge_unique_ids(persisted_contact_ids, [contact.id])
            evidence_ids.extend(
                await self._persist_candidate_evidence(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    account_id=account.id,
                    contact_id=contact.id,
                    candidate=candidate,
                )
            )

        await self._session.flush()
        return persisted_contact_ids, _merge_unique_ids([], evidence_ids)

    async def _persist_candidate_evidence(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        account_id: UUID,
        contact_id: UUID,
        candidate: ContactCandidateRecord,
    ) -> list[UUID]:
        evidence_ids: list[UUID] = []
        for evidence in candidate.evidence:
            evidence_row = await self._source_evidence.create(
                tenant_id=tenant_id,
                workflow_run_id=run_id,
                account_id=account_id,
                contact_id=contact_id,
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

    def _load_workflow_input(self, run: WorkflowRun) -> ContactSearchWorkflowInput:
        try:
            return ContactSearchWorkflowInput.model_validate(run.requested_payload_json)
        except ValidationError as exc:
            raise WorkflowExecutionError(
                error_code="validation_error",
                message="Workflow run payload is invalid for contact search.",
                status_detail=str(exc),
            ) from exc

    async def _load_prerequisites(
        self,
        *,
        tenant_id: UUID,
        workflow_input: ContactSearchWorkflowInput,
    ) -> tuple[Account, SellerProfile, ICPProfile | None, AccountResearchSnapshot | None]:
        account = await self._accounts.get_for_tenant(
            tenant_id=tenant_id,
            account_id=workflow_input.account_id,
        )
        seller_profile = await self._seller_profiles.get_for_tenant(
            tenant_id=tenant_id,
            seller_profile_id=workflow_input.seller_profile_id,
        )
        icp_profile = None
        if workflow_input.icp_profile_id is not None:
            icp_profile = await self._icp_profiles.get_for_tenant(
                tenant_id=tenant_id,
                icp_profile_id=workflow_input.icp_profile_id,
            )

        if account is None or seller_profile is None:
            raise WorkflowExecutionError(
                error_code="workflow_prerequisites_missing",
                message="Contact search requires account and seller context.",
                status_detail="Account or seller profile was not found for this run.",
            )
        if icp_profile is not None and icp_profile.seller_profile_id != seller_profile.id:
            raise WorkflowExecutionError(
                error_code="ownership_conflict",
                message="ICP profile does not belong to the requested seller profile.",
            )
        latest_snapshot = await self._snapshots.get_latest_for_account(
            tenant_id=tenant_id,
            account_id=account.id,
        )
        return account, seller_profile, icp_profile, latest_snapshot


def _build_search_queries(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    workflow_input: ContactSearchWorkflowInput,
    latest_snapshot: AccountResearchSnapshot | None,
) -> list[str]:
    queries: list[str] = []
    if workflow_input.contact_objective:
        queries.append(f"{account.name} {workflow_input.contact_objective}")

    queries.append(f"{account.name} leadership team")
    if account.domain:
        queries.append(f"{account.domain} leadership team")

    if seller_profile.company_name:
        queries.append(f"{account.name} {seller_profile.company_name} champion")

    if icp_profile is not None:
        icp_values = _extract_string_values(icp_profile.criteria_json)
        if icp_values:
            queries.append(f"{account.name} {icp_values[0]} operations leader")

    if latest_snapshot is not None and latest_snapshot.research_summary:
        first_phrase = latest_snapshot.research_summary.split(".")[0]
        queries.append(f"{account.name} {first_phrase}")

    deduped_queries: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            continue
        dedupe_key = normalized_query.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_queries.append(normalized_query)
    return deduped_queries[:2] or [f"{account.name} leadership team"]


def _parse_contact_search_record(
    payload: dict[str, Any] | list[dict[str, Any]] | None,
) -> ContactSearchRecord | None:
    if payload is None:
        return None

    normalized_payload: dict[str, Any]
    if isinstance(payload, list):
        normalized_payload = {
            "target_personas": [],
            "selection_criteria": [],
            "ranked_contact_rationale": (
                "Ranked normalized contact candidates from public evidence."
            ),
            "missing_data_flags": [],
            "contacts": payload,
        }
    elif isinstance(payload, dict):
        normalized_payload = dict(payload)
    else:
        return None

    for list_field in ("target_personas", "selection_criteria", "missing_data_flags"):
        if isinstance(normalized_payload.get(list_field), str):
            normalized_payload[list_field] = [normalized_payload[list_field]]

    raw_contacts = normalized_payload.get("contacts")
    if isinstance(raw_contacts, dict):
        normalized_payload["contacts"] = [raw_contacts]
    elif raw_contacts is None:
        normalized_payload["contacts"] = []

    if not normalized_payload.get("ranked_contact_rationale"):
        normalized_payload["ranked_contact_rationale"] = (
            "Ranked normalized contact candidates from public evidence."
        )

    contacts = normalized_payload.get("contacts", [])
    if isinstance(contacts, list):
        normalized_contacts: list[dict[str, Any]] = []
        for item in contacts:
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            if isinstance(normalized_item.get("missing_data_flags"), str):
                normalized_item["missing_data_flags"] = [normalized_item["missing_data_flags"]]
            normalized_contacts.append(normalized_item)
        normalized_payload["contacts"] = normalized_contacts

    try:
        return ContactSearchRecord.model_validate(normalized_payload)
    except ValidationError:
        return None


def _merge_contact_search_records(
    *,
    parsed_record: ContactSearchRecord | None,
    fallback_record: ContactSearchRecord,
) -> ContactSearchRecord:
    if parsed_record is None:
        return fallback_record

    return ContactSearchRecord(
        target_personas=_dedupe_strings(
            [*parsed_record.target_personas, *fallback_record.target_personas]
        ),
        selection_criteria=_dedupe_strings(
            [*parsed_record.selection_criteria, *fallback_record.selection_criteria]
        ),
        ranked_contact_rationale=(
            parsed_record.ranked_contact_rationale or fallback_record.ranked_contact_rationale
        ),
        missing_data_flags=_dedupe_missing_data_flags(
            [*parsed_record.missing_data_flags, *fallback_record.missing_data_flags]
        ),
        contacts=parsed_record.contacts or fallback_record.contacts,
    )


def _build_fallback_contact_search_record(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    workflow_input: ContactSearchWorkflowInput,
    latest_snapshot: AccountResearchSnapshot | None,
    provider_response: ContactSearchProviderResponse | None,
    search_results: Sequence[SearchResultRecord],
) -> ContactSearchRecord:
    target_personas = _build_target_personas(
        seller_profile=seller_profile,
        icp_profile=icp_profile,
    )
    selection_criteria = _build_selection_criteria(
        workflow_input=workflow_input,
        latest_snapshot=latest_snapshot,
    )
    missing_data_flags: list[ContactMissingDataFlag] = []
    if not search_results:
        missing_data_flags.append(ContactMissingDataFlag.LOW_SOURCE_CONFIDENCE)
    if provider_response is not None and not provider_response.candidates:
        missing_data_flags.append(ContactMissingDataFlag.LOW_SOURCE_CONFIDENCE)

    fallback_contacts = _provider_response_to_contact_candidates(provider_response)

    rationale = (
        f"Ranked contact candidates for {account.name} using {seller_profile.company_name} context."
        if search_results or fallback_contacts
        else (
            f"No credible contacts were identified for {account.name}; "
            "public evidence remains limited."
        )
    )

    return ContactSearchRecord(
        target_personas=target_personas,
        selection_criteria=selection_criteria,
        ranked_contact_rationale=rationale,
        missing_data_flags=missing_data_flags,
        contacts=fallback_contacts,
    )


def _build_target_personas(
    *,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
) -> list[str]:
    personas: list[str] = []
    company_context = _normalize_optional_text(seller_profile.target_market_summary)
    if company_context:
        personas.append(f"Operators aligned to {company_context}")

    if icp_profile is not None:
        for criterion in _extract_string_values(icp_profile.criteria_json):
            personas.append(f"Contacts tied to {criterion}")

    personas.extend(
        [
            "Revenue operations leaders",
            "Sales operations leaders",
        ]
    )
    return _dedupe_strings(personas)[:4]


def _build_selection_criteria(
    *,
    workflow_input: ContactSearchWorkflowInput,
    latest_snapshot: AccountResearchSnapshot | None,
) -> list[str]:
    criteria: list[str] = []
    if workflow_input.contact_objective:
        criteria.append(workflow_input.contact_objective)
    if latest_snapshot is not None and latest_snapshot.qualification_summary:
        criteria.append(latest_snapshot.qualification_summary)
    criteria.extend(
        [
            "Prefer contacts with clear operational ownership.",
            "Preserve missing-data flags instead of inflating certainty.",
        ]
    )
    return _dedupe_strings(criteria)


def _finalize_candidate(candidate: ContactCandidateRecord) -> ContactCandidateRecord:
    missing_data_flags = list(candidate.missing_data_flags)
    if _normalize_email(candidate.email) is None:
        missing_data_flags.append(ContactMissingDataFlag.MISSING_EMAIL)
    if _normalize_profile_url(candidate.linkedin_url) is None:
        missing_data_flags.append(ContactMissingDataFlag.MISSING_LINKEDIN)
    if _normalize_optional_text(candidate.job_title) is None:
        missing_data_flags.append(ContactMissingDataFlag.MISSING_JOB_TITLE)
    if candidate.confidence_score is not None and candidate.confidence_score < 0.5:
        missing_data_flags.append(ContactMissingDataFlag.LOW_SOURCE_CONFIDENCE)

    return candidate.model_copy(
        update={
            "email": _normalize_email(candidate.email),
            "linkedin_url": _normalize_optional_text(candidate.linkedin_url),
            "phone": _normalize_optional_text(candidate.phone),
            "job_title": _normalize_optional_text(candidate.job_title),
            "ranking_summary": _normalize_optional_text(candidate.ranking_summary),
            "persona_match_summary": _normalize_optional_text(candidate.persona_match_summary),
            "missing_data_flags": _dedupe_missing_data_flags(missing_data_flags),
            "evidence": _dedupe_evidence(candidate.evidence),
        }
    )


def _apply_contact_enrichment(
    *,
    candidate: ContactCandidateRecord,
    response: ContactEnrichmentResponse,
) -> ContactCandidateRecord:
    replacement_person_data = dict(candidate.person_data_json or {})
    if response.person_profile:
        replacement_person_data = _merge_json_payloads(
            replacement_person_data, response.person_profile
        )

    evidence = list(candidate.evidence)
    for source_reference in response.source_references:
        evidence.append(
            ContactCandidateEvidenceRecord(
                source_type="provider",
                provider_name=source_reference.provider_name,
                source_url=source_reference.source_url,
                title=source_reference.title,
            )
        )

    return candidate.model_copy(
        update={
            "full_name": response.full_name or candidate.full_name,
            "job_title": response.job_title or candidate.job_title,
            "email": response.email or candidate.email,
            "linkedin_url": response.linkedin_url or candidate.linkedin_url,
            "phone": response.phone or candidate.phone,
            "company_domain": candidate.company_domain,
            "source_provider": candidate.source_provider,
            "acceptance_reason": candidate.acceptance_reason,
            "person_data_json": replacement_person_data or None,
            "evidence": evidence,
        }
    )


def _build_contact_person_data(
    *,
    candidate: ContactCandidateRecord,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    latest_snapshot: AccountResearchSnapshot | None,
    target_personas: Sequence[str],
    selection_criteria: Sequence[str],
) -> dict[str, Any] | None:
    base_payload = dict(candidate.person_data_json or {})
    context_payload = {
        "seller_profile_id": str(seller_profile.id),
        "icp_profile_id": str(icp_profile.id) if icp_profile is not None else None,
        "used_research_snapshot_id": (
            str(latest_snapshot.id) if latest_snapshot is not None else None
        ),
        "target_personas": list(target_personas),
        "selection_criteria": list(selection_criteria),
        "persona_match_summary": candidate.persona_match_summary,
        "source_provider": candidate.source_provider,
        "acceptance_reason": candidate.acceptance_reason,
        "company_domain": candidate.company_domain,
        "missing_data_flags": [flag.value for flag in candidate.missing_data_flags],
        "confidence_score": candidate.confidence_score,
    }
    merged_payload = _merge_json_payloads(base_payload, context_payload)
    return merged_payload or None


def _build_contact_merge_changes(
    *,
    existing: Contact,
    candidate: ContactCandidateRecord,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    latest_snapshot: AccountResearchSnapshot | None,
    target_personas: Sequence[str],
    selection_criteria: Sequence[str],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    replacement_values = {
        "full_name": candidate.full_name,
        "job_title": _normalize_optional_text(candidate.job_title),
        "email": _normalize_email(candidate.email),
        "linkedin_url": _normalize_optional_text(candidate.linkedin_url),
        "phone": _normalize_optional_text(candidate.phone),
        "ranking_summary": _normalize_optional_text(candidate.ranking_summary),
        "status": "candidate",
    }
    for field_name, replacement_value in replacement_values.items():
        if (
            _is_non_empty_value(replacement_value)
            and getattr(existing, field_name) != replacement_value
        ):
            changes[field_name] = replacement_value

    replacement_person_data = _build_contact_person_data(
        candidate=candidate,
        seller_profile=seller_profile,
        icp_profile=icp_profile,
        latest_snapshot=latest_snapshot,
        target_personas=target_personas,
        selection_criteria=selection_criteria,
    )
    if replacement_person_data:
        merged_person_data = _merge_json_payloads(
            existing.person_data_json or {}, replacement_person_data
        )
        if merged_person_data != (existing.person_data_json or {}):
            changes["person_data_json"] = merged_person_data

    return changes


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


def _build_provider_search_request(
    *,
    account: Account,
    seller_profile: SellerProfile,
    icp_profile: ICPProfile | None,
    workflow_input: ContactSearchWorkflowInput,
) -> ContactSearchProviderRequest:
    target_personas = _build_target_personas(seller_profile=seller_profile, icp_profile=icp_profile)
    title_hints = _normalize_role_hints(target_personas, workflow_input.contact_objective)
    selected_people = _extract_selected_people_hint(workflow_input.contact_objective)
    return ContactSearchProviderRequest(
        account_id=account.id,
        account_name=account.name,
        account_domain=account.domain or account.normalized_domain,
        account_country=account.hq_location,
        persona_hints=target_personas,
        title_hints=title_hints,
        region_hint=_normalize_optional_text(account.hq_location),
        selected_people=selected_people,
        linkedin_urls=[],
    )


def _normalize_role_hints(personas: Sequence[str], contact_objective: str | None) -> list[str]:
    normalized_roles: list[str] = []
    raw_values = [*personas]
    if contact_objective:
        raw_values.append(contact_objective)
    joined = " ".join(raw_values).lower()
    if "founder" in joined:
        normalized_roles.append("founder")
    if "executive" in joined or "chief" in joined or "vp" in joined:
        normalized_roles.append("executive")
    if "sales" in joined:
        normalized_roles.append("sales leader")
    if "marketing" in joined:
        normalized_roles.append("marketing leader")
    if "operations" in joined or "ops" in joined or "revops" in joined:
        normalized_roles.append("operations leader")
    if not normalized_roles:
        normalized_roles.append("operations leader")
    return _dedupe_strings(normalized_roles)[:3]


def _extract_selected_people_hint(contact_objective: str | None) -> list[str]:
    objective = _normalize_optional_text(contact_objective)
    if objective is None:
        return []
    words = objective.split()
    likely_name_parts = [part for part in words if part[:1].isupper()]
    if len(likely_name_parts) >= 2:
        return [" ".join(likely_name_parts[:2])]
    return []


def _provider_response_to_contact_candidates(
    response: ContactSearchProviderResponse | None,
) -> list[ContactCandidateRecord]:
    if response is None:
        return []
    candidates: list[ContactCandidateRecord] = []
    for candidate in response.candidates:
        full_name = _normalize_optional_text(candidate.full_name)
        if full_name is None:
            continue
        person_data = dict(candidate.provider_metadata or {})
        if candidate.provider_key:
            person_data["provider_key"] = candidate.provider_key
        candidates.append(
            ContactCandidateRecord(
                full_name=full_name,
                email=_normalize_email(candidate.email),
                linkedin_url=_normalize_optional_text(candidate.linkedin_url),
                job_title=_normalize_optional_text(candidate.job_title),
                company_domain=_normalize_domain(candidate.company_domain),
                source_provider=candidate.source_provider,
                acceptance_reason=_normalize_optional_text(candidate.acceptance_reason),
                confidence_score=candidate.confidence_0_1,
                person_data_json=person_data or None,
                evidence=[
                    ContactCandidateEvidenceRecord(
                        source_type="provider",
                        provider_name=source_reference.provider_name,
                        source_url=source_reference.source_url,
                        title=source_reference.title,
                    )
                    for source_reference in candidate.evidence_refs
                ],
                missing_data_flags=_dedupe_missing_data_flags(
                    _map_missing_field_flags(candidate.missing_fields)
                ),
            )
        )
    return candidates


def _map_missing_field_flags(missing_fields: Sequence[str]) -> list[ContactMissingDataFlag]:
    mapped: list[ContactMissingDataFlag] = []
    for field_name in missing_fields:
        normalized = field_name.strip().lower()
        if normalized == "email":
            mapped.append(ContactMissingDataFlag.MISSING_EMAIL)
        elif normalized in {"linkedin", "linkedin_url"}:
            mapped.append(ContactMissingDataFlag.MISSING_LINKEDIN)
        elif normalized in {"job_title", "title"}:
            mapped.append(ContactMissingDataFlag.MISSING_JOB_TITLE)
    return mapped


def _dedupe_evidence(
    evidence_records: Sequence[ContactCandidateEvidenceRecord],
) -> list[ContactCandidateEvidenceRecord]:
    deduped: list[ContactCandidateEvidenceRecord] = []
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


def _dedupe_missing_data_flags(
    values: Sequence[ContactMissingDataFlag | str],
) -> list[ContactMissingDataFlag]:
    deduped: list[ContactMissingDataFlag] = []
    seen: set[ContactMissingDataFlag] = set()
    for value in values:
        try:
            normalized = (
                value
                if isinstance(value, ContactMissingDataFlag)
                else ContactMissingDataFlag(value)
            )
        except ValueError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _merge_json_payloads(existing: dict[str, Any], replacement: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in replacement.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_json_payloads(merged[key], value)
            continue
        if isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _merge_list_values(merged[key], value)
            continue
        if _is_non_empty_value(value):
            merged[key] = value
    return merged


def _merge_list_values(existing: list[Any], replacement: list[Any]) -> list[Any]:
    merged: list[Any] = list(existing)
    seen_scalars = {
        _normalize_optional_text(value).lower()
        for value in existing
        if isinstance(value, str) and _normalize_optional_text(value) is not None
    }
    for value in replacement:
        if isinstance(value, str):
            normalized = _normalize_optional_text(value)
            if normalized is None:
                continue
            dedupe_key = normalized.lower()
            if dedupe_key in seen_scalars:
                continue
            seen_scalars.add(dedupe_key)
            merged.append(normalized)
            continue
        if value not in merged:
            merged.append(value)
    return merged


def _merge_unique_ids(existing_ids: Sequence[UUID], new_ids: Sequence[UUID]) -> list[UUID]:
    seen = set(existing_ids)
    merged = list(existing_ids)
    for record_id in new_ids:
        if record_id in seen:
            continue
        seen.add(record_id)
        merged.append(record_id)
    return merged


def _extract_provider_key(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    for key in ("provider_key", "provider_id", "contact_provider_key"):
        normalized = _normalize_optional_text(payload.get(key))
        if normalized is not None:
            return normalized
    return None


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
    if isinstance(value, list | tuple | set):
        values: list[str] = []
        for child in value:
            values.extend(_flatten_string_values(child))
        return values
    return [str(value)]


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_email(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    return normalized.lower()


def _normalize_profile_url(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    return normalized.rstrip("/").lower()


def _is_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_is_non_empty_value(child) for child in value.values())
    if isinstance(value, list | tuple | set):
        return any(_is_non_empty_value(child) for child in value)
    return True


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


def _research_snapshot_payload(snapshot: AccountResearchSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.id),
        "snapshot_version": snapshot.snapshot_version,
        "research_summary": snapshot.research_summary,
        "qualification_summary": snapshot.qualification_summary,
        "uncertainty_notes": snapshot.uncertainty_notes,
        "research_json": snapshot.research_json,
    }
