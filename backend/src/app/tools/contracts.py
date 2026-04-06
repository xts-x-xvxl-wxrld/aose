from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchResultRecord(ToolContractModel):
    title: str
    url: str
    snippet: str | None = None
    provider_name: str | None = None
    provider_metadata: dict[str, Any] | None = None


class ToolSourceReference(ToolContractModel):
    provider_name: str | None = None
    source_url: str | None = None
    title: str | None = None


class WebSearchRequest(ToolContractModel):
    query_text: str = Field(min_length=1)
    freshness_hint: str | None = None
    result_limit: int = Field(default=10, ge=1, le=50)


class WebSearchResponse(ToolContractModel):
    results: list[SearchResultRecord] = Field(default_factory=list)
    raw_result_summary: str | None = None
    error_code: str | None = None


class PageFetchRequest(ToolContractModel):
    url: str | None = None
    provider_document_ref: str | None = None

    @model_validator(mode="after")
    def validate_identifier(self) -> PageFetchRequest:
        if self.url is None and self.provider_document_ref is None:
            raise ValueError("page fetch requires url or provider_document_ref")
        return self


class PageFetchResponse(ToolContractModel):
    status_code: int | None = None
    provider_status: str | None = None
    body_text: str | None = None
    document_bytes: bytes | None = None
    content_type: str | None = None
    fetch_metadata: dict[str, Any] | None = None
    error_code: str | None = None


class PageScrapeRequest(ToolContractModel):
    source_url: str | None = None
    body_text: str | None = None
    content_type: str | None = None
    extraction_hints: dict[str, Any] | None = None


class PageScrapeResponse(ToolContractModel):
    normalized_text: str | None = None
    headings: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    error_code: str | None = None


class CompanyEnrichmentRequest(ToolContractModel):
    company_name: str | None = None
    domain: str | None = None
    provider_key: str | None = None

    @model_validator(mode="after")
    def validate_identifier(self) -> CompanyEnrichmentRequest:
        if self.company_name is None and self.domain is None and self.provider_key is None:
            raise ValueError("company enrichment requires company_name, domain, or provider_key")
        return self


class CompanyEnrichmentResponse(ToolContractModel):
    normalized_company_name: str | None = None
    normalized_domain: str | None = None
    linkedin_url: str | None = None
    company_profile: dict[str, Any] | None = None
    source_references: list[ToolSourceReference] = Field(default_factory=list)
    error_code: str | None = None


class ContactEnrichmentRequest(ToolContractModel):
    account_id: UUID | None = None
    contact_name: str | None = None
    contact_title: str | None = None
    provider_key: str | None = None

    @model_validator(mode="after")
    def validate_identifier(self) -> ContactEnrichmentRequest:
        if self.account_id is None:
            raise ValueError("contact enrichment requires account_id")
        if self.contact_name is None and self.contact_title is None and self.provider_key is None:
            raise ValueError(
                "contact enrichment requires contact_name, contact_title, or provider_key"
            )
        return self


class ContactEnrichmentResponse(ToolContractModel):
    full_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    person_profile: dict[str, Any] | None = None
    source_references: list[ToolSourceReference] = Field(default_factory=list)
    error_code: str | None = None


class ContactSearchProviderRoutingPolicy(ToolContractModel):
    primary_provider: str
    fallback_provider: str | None = None
    routing_basis: str


class ContactSearchProviderRequest(ToolContractModel):
    account_id: UUID
    account_name: str | None = None
    account_domain: str | None = None
    account_country: str | None = None
    persona_hints: list[str] = Field(default_factory=list)
    title_hints: list[str] = Field(default_factory=list)
    region_hint: str | None = None
    selected_people: list[str] = Field(default_factory=list)
    linkedin_urls: list[str] = Field(default_factory=list)


class ContactSearchProviderCandidate(ToolContractModel):
    full_name: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    job_title: str | None = None
    company_domain: str | None = None
    source_provider: str
    provider_key: str | None = None
    confidence_0_1: float | None = Field(default=None, ge=0, le=1)
    acceptance_reason: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    evidence_refs: list[ToolSourceReference] = Field(default_factory=list)
    provider_metadata: dict[str, Any] | None = None


class ContactSearchProviderResponse(ToolContractModel):
    provider_name: str
    candidates: list[ContactSearchProviderCandidate] = Field(default_factory=list)
    raw_result_summary: str | None = None
    quota_state: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    error_code: str | None = None


class ContentNormalizerRequest(ToolContractModel):
    raw_payload: dict[str, Any] | list[dict[str, Any]] | str
    schema_hint: str | None = None
    instructions_override: str | None = None
    system_prompt_override: str | None = None
    model_override: str | None = None


class ContentNormalizerResponse(ToolContractModel):
    normalized_payload: dict[str, Any] | list[dict[str, Any]] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    raw_result_summary: str | None = None
    error_code: str | None = None
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)


class WebSearchTool(Protocol):
    async def execute(self, request: WebSearchRequest) -> WebSearchResponse: ...


class PageFetchTool(Protocol):
    async def execute(self, request: PageFetchRequest) -> PageFetchResponse: ...


class PageScrapeTool(Protocol):
    async def execute(self, request: PageScrapeRequest) -> PageScrapeResponse: ...


class CompanyEnrichmentTool(Protocol):
    async def execute(self, request: CompanyEnrichmentRequest) -> CompanyEnrichmentResponse: ...


class ContactEnrichmentTool(Protocol):
    async def execute(self, request: ContactEnrichmentRequest) -> ContactEnrichmentResponse: ...


class ContentNormalizerTool(Protocol):
    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse: ...


class ContactSearchProviderTool(Protocol):
    async def search(
        self,
        request: ContactSearchProviderRequest,
    ) -> ContactSearchProviderResponse: ...


def get_tool_provider_name(tool: object) -> str | None:
    provider_name = getattr(tool, "provider_name", None)
    if isinstance(provider_name, str) and provider_name.strip():
        return provider_name
    return None
