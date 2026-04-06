from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import (
    FirecrawlSettings,
    FindymailSettings,
    GoogleLocalPlacesSettings,
    OpenAIProviderSettings,
    TombaSettings,
)
from app.tools.contracts import (
    CompanyEnrichmentRequest,
    CompanyEnrichmentResponse,
    ContactSearchProviderCandidate,
    ContactSearchProviderRequest,
    ContactSearchProviderResponse,
    ContactEnrichmentRequest,
    ContactEnrichmentResponse,
    ContentNormalizerRequest,
    ContentNormalizerResponse,
    PageFetchRequest,
    PageFetchResponse,
    PageScrapeRequest,
    PageScrapeResponse,
    SearchResultRecord,
    ToolSourceReference,
    WebSearchRequest,
    WebSearchResponse,
)
from app.tools.provider_errors import (
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.workflows.reasoning import (
    AccountResearchReasoningOutput,
    AccountSearchQueryPlanOutput,
    AccountSearchReasoningOutput,
    ContactSearchReasoningOutput,
    build_account_research_prompt_spec,
    build_account_search_query_plan_prompt_spec,
    build_account_search_prompt_spec,
    build_contact_search_prompt_spec,
)


@dataclass(frozen=True)
class _SchemaSpec:
    prompt_spec: str
    schema_name: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class _RequestProfile:
    name: str
    json_body: dict[str, Any]


class _ProviderTool:
    provider_name: str

    def __init__(
        self,
        *,
        configured: bool,
        base_url: str,
        timeout_seconds: int,
        max_retries: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._configured = configured
        self._base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._transport = transport

    def _configuration_error_code(self) -> str | None:
        if self._configured:
            return None
        return ProviderAuthError(
            self.provider_name,
            f"{self.provider_name} credentials are not configured.",
        ).error_code

    def _auth_error(self) -> ProviderAuthError:
        return ProviderAuthError(
            self.provider_name,
            f"{self.provider_name} credentials are not configured.",
        )

    def _request_headers(self) -> dict[str, str]:
        return {}

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._configured:
            raise self._auth_error()

        merged_headers = {
            **self._request_headers(),
            **(headers or {}),
        }
        last_error: ProviderError | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self.timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.request(
                        method,
                        path,
                        json=json_body,
                        params=params,
                        headers=merged_headers,
                    )
            except httpx.TimeoutException as exc:
                last_error = ProviderUnavailableError(
                    self.provider_name,
                    f"{self.provider_name} request timed out: {exc}",
                )
            except httpx.RequestError as exc:
                last_error = ProviderUnavailableError(
                    self.provider_name,
                    f"{self.provider_name} request failed: {exc}",
                )
            else:
                if response.status_code in {401, 403}:
                    raise ProviderAuthError(
                        self.provider_name,
                        f"{self.provider_name} rejected the supplied credentials.",
                    )
                if response.status_code in {402, 423}:
                    raise ProviderQuotaError(
                        self.provider_name,
                        f"{self.provider_name} reported quota or billing exhaustion.",
                    )
                if response.status_code == 429:
                    last_error = ProviderRateLimitError(
                        self.provider_name,
                        f"{self.provider_name} rate limited the request.",
                    )
                elif response.status_code >= 500:
                    last_error = ProviderUnavailableError(
                        self.provider_name,
                        f"{self.provider_name} returned {response.status_code}.",
                    )
                elif response.status_code >= 400:
                    raise ProviderBadResponseError(
                        self.provider_name,
                        f"{self.provider_name} returned {response.status_code}.",
                    )
                else:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise ProviderBadResponseError(
                            self.provider_name,
                            f"{self.provider_name} returned invalid JSON: {exc}",
                        ) from exc
                    if isinstance(payload, dict):
                        return payload
                    raise ProviderBadResponseError(
                        self.provider_name,
                        f"{self.provider_name} returned a non-object JSON payload.",
                    )

            if attempt < self.max_retries:
                await asyncio.sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))

        raise last_error or ProviderUnavailableError(
            self.provider_name,
            f"{self.provider_name} request failed after retries.",
        )

    async def healthcheck(self) -> dict[str, object]:
        return {
            "provider_name": self.provider_name,
            "configured": self._configured,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "base_url": self._base_url,
        }


class FirecrawlWebSearchTool(_ProviderTool):
    provider_name = "firecrawl"

    def __init__(
        self,
        settings: FirecrawlSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.search_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return WebSearchResponse(results=[], error_code=error_code)

        request_profiles = _build_firecrawl_search_profiles(request)
        profile_failures: list[str] = []
        payload: dict[str, Any] | None = None
        selected_profile_name = request_profiles[0].name
        for index, profile in enumerate(request_profiles):
            try:
                payload = await self._request_json(
                    "POST",
                    "/v2/search",
                    json_body=profile.json_body,
                )
                selected_profile_name = profile.name
                break
            except ProviderBadResponseError as exc:
                profile_failures.append(f"{profile.name}: {exc}")
                if index < len(request_profiles) - 1:
                    continue
                return WebSearchResponse(
                    results=[],
                    raw_result_summary=_format_profile_failure_summary(
                        provider_name=self.provider_name,
                        profile_failures=profile_failures,
                    ),
                    error_code=exc.error_code,
                )
            except ProviderError as exc:
                return WebSearchResponse(
                    results=[],
                    raw_result_summary=f"{self.provider_name} search failed via `{profile.name}` profile: {exc}",
                    error_code=exc.error_code,
                )

        assert payload is not None
        raw_results = _extract_firecrawl_web_results(payload)
        results: list[SearchResultRecord] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = _normalize_optional_text(item.get("url"))
            title = _normalize_optional_text(item.get("title")) or url
            if url is None or title is None:
                continue
            snippet = (
                _normalize_optional_text(item.get("description"))
                or _normalize_optional_text(item.get("snippet"))
                or _normalize_optional_text(item.get("markdown"))
            )
            results.append(
                SearchResultRecord(
                    title=title,
                    url=url,
                    snippet=snippet,
                    provider_name=self.provider_name,
                    provider_metadata=_compact_metadata(
                        item,
                        keys=("source", "publishedDate", "metadata"),
                    ),
                )
            )
        return WebSearchResponse(
            results=results,
            raw_result_summary=_format_retry_success_summary(
                provider_name=self.provider_name,
                selected_profile_name=selected_profile_name,
                profile_failures=profile_failures,
                result_count=len(results),
            ),
        )


class GoogleLocalPlacesWebSearchTool(_ProviderTool):
    provider_name = "google_local_places"

    def __init__(
        self,
        settings: GoogleLocalPlacesSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.search_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    async def execute(self, request: WebSearchRequest) -> WebSearchResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return WebSearchResponse(results=[], error_code=error_code)

        try:
            payload = await self._request_json(
                "POST",
                "/v1/places:searchText",
                json_body={
                    "textQuery": request.query_text,
                    "pageSize": request.result_limit,
                },
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": (
                        "places.displayName,places.formattedAddress,places.websiteUri,"
                        "places.googleMapsUri,places.id,places.primaryType,places.rating,"
                        "places.userRatingCount"
                    ),
                },
            )
        except ProviderError as exc:
            return WebSearchResponse(results=[], error_code=exc.error_code)

        results: list[SearchResultRecord] = []
        for place in payload.get("places") or []:
            if not isinstance(place, dict):
                continue
            display_name = place.get("displayName") or {}
            title = _normalize_optional_text(display_name.get("text")) or "Unnamed place"
            url = _normalize_optional_text(place.get("websiteUri")) or _normalize_optional_text(
                place.get("googleMapsUri")
            )
            if url is None:
                continue
            results.append(
                SearchResultRecord(
                    title=title,
                    url=url,
                    snippet=_normalize_optional_text(place.get("formattedAddress")),
                    provider_name=self.provider_name,
                    provider_metadata=_compact_metadata(
                        place,
                        keys=("id", "primaryType", "rating", "userRatingCount"),
                    ),
                )
            )
        return WebSearchResponse(results=results)


class FirecrawlPageFetchTool(_ProviderTool):
    provider_name = "firecrawl"

    def __init__(
        self,
        settings: FirecrawlSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.research_fetch_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, request: PageFetchRequest) -> PageFetchResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return PageFetchResponse(error_code=error_code)

        target_url = _normalize_optional_text(request.url or request.provider_document_ref)
        if target_url is None:
            return PageFetchResponse(error_code=ProviderBadResponseError.error_code)

        try:
            payload = await self._request_json(
                "POST",
                "/v2/scrape",
                json_body={
                    "url": target_url,
                    "formats": ["markdown", "html"],
                },
            )
        except ProviderError as exc:
            return PageFetchResponse(error_code=exc.error_code)

        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        markdown = _normalize_optional_text(data.get("markdown"))
        html = _normalize_optional_text(data.get("html"))
        body_text = markdown or _html_to_text(html)
        content_type = "text/markdown" if markdown else "text/html" if html else None
        return PageFetchResponse(
            status_code=200 if body_text else None,
            provider_status="success" if body_text else None,
            body_text=body_text,
            content_type=content_type,
            fetch_metadata=_compact_metadata(data, keys=("metadata", "warning")),
        )


class FirecrawlPageScrapeTool(_ProviderTool):
    provider_name = "firecrawl"

    def __init__(
        self,
        settings: FirecrawlSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.research_fetch_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, request: PageScrapeRequest) -> PageScrapeResponse:
        body_text = _normalize_optional_text(request.body_text)
        source_url = _normalize_optional_text(request.source_url)
        if body_text is None and source_url is not None:
            try:
                payload = await self._request_json(
                    "POST",
                    "/v2/scrape",
                    json_body={
                        "url": source_url,
                        "formats": ["markdown", "html"],
                    },
                )
            except ProviderError as exc:
                return PageScrapeResponse(error_code=exc.error_code)
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            body_text = _normalize_optional_text(data.get("markdown")) or _html_to_text(
                _normalize_optional_text(data.get("html"))
            )

        return PageScrapeResponse(
            normalized_text=_normalize_scraped_text(body_text),
            headings=_extract_headings(body_text),
            links=_extract_links(body_text, source_url),
        )


class FirecrawlCompanyEnrichmentTool(_ProviderTool):
    provider_name = "firecrawl"

    def __init__(
        self,
        settings: FirecrawlSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.enrichment_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, request: CompanyEnrichmentRequest) -> CompanyEnrichmentResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return CompanyEnrichmentResponse(error_code=error_code)

        query = _build_company_enrichment_query(request)
        try:
            payload = await self._request_json(
                "POST",
                "/v2/search",
                json_body={
                    "query": query,
                    "limit": 3,
                    "sources": ["web"],
                },
            )
        except ProviderError as exc:
            return CompanyEnrichmentResponse(error_code=exc.error_code)

        raw_results = (((payload.get("data") or {}).get("web")) or payload.get("results") or [])
        source_references: list[ToolSourceReference] = []
        profile_snippets: list[str] = []
        normalized_domain = _normalize_domain(request.domain)
        normalized_company_name = _normalize_optional_text(request.company_name)
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = _normalize_optional_text(item.get("url"))
            title = _normalize_optional_text(item.get("title"))
            description = _normalize_optional_text(item.get("description"))
            if normalized_company_name is None:
                normalized_company_name = title
            if normalized_domain is None and url is not None:
                normalized_domain = _extract_domain_from_url(url)
            if description is not None:
                profile_snippets.append(description)
            source_references.append(
                ToolSourceReference(
                    provider_name=self.provider_name,
                    source_url=url,
                    title=title,
                )
            )

        company_profile = (
            {
                "summary": " ".join(profile_snippets[:2]),
                "search_query": query,
            }
            if profile_snippets
            else None
        )
        return CompanyEnrichmentResponse(
            normalized_company_name=normalized_company_name,
            normalized_domain=normalized_domain,
            company_profile=company_profile,
            source_references=source_references,
        )


class OpenAIContentNormalizerTool(_ProviderTool):
    provider_name = "openai"

    def __init__(
        self,
        settings: OpenAIProviderSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        self.model = settings.model
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.enrichment_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, request: ContentNormalizerRequest) -> ContentNormalizerResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return ContentNormalizerResponse(normalized_payload=None, error_code=error_code)

        schema_spec = _schema_spec_for_hint(request.schema_hint)
        if schema_spec is None:
            return ContentNormalizerResponse(
                normalized_payload=None,
                error_code=ProviderBadResponseError.error_code,
            )

        resolved_model = request.model_override or self.model
        raw_payload_json = json.dumps(request.raw_payload, ensure_ascii=True, sort_keys=True)
        request_profiles = _build_openai_normalizer_profiles(
            model=resolved_model,
            schema_spec=schema_spec,
            schema_hint=request.schema_hint,
            raw_payload_json=raw_payload_json,
            instructions_override=request.instructions_override,
            system_prompt_override=request.system_prompt_override,
        )
        profile_failures: list[str] = []
        normalized_payload: dict[str, Any] | list[dict[str, Any]] | None = None
        selected_profile_name = request_profiles[0].name
        response_usage: dict[str, Any] = {}
        for index, profile in enumerate(request_profiles):
            try:
                payload = await self._request_json(
                    "POST",
                    "/chat/completions",
                    json_body=profile.json_body,
                )
                normalized_payload = _parse_openai_normalizer_payload(payload)
                selected_profile_name = profile.name
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    response_usage = usage
                break
            except ProviderBadResponseError as exc:
                profile_failures.append(f"{profile.name}: {exc}")
                if index < len(request_profiles) - 1:
                    continue
                return ContentNormalizerResponse(
                    normalized_payload=None,
                    raw_result_summary=_format_profile_failure_summary(
                        provider_name=self.provider_name,
                        profile_failures=profile_failures,
                    ),
                    error_code=exc.error_code,
                    raw_metadata_json={
                        "request_profile": profile.name,
                        "profile_failures": profile_failures,
                        "model": resolved_model,
                    },
                )
            except ProviderError as exc:
                return ContentNormalizerResponse(
                    normalized_payload=None,
                    raw_result_summary=f"{self.provider_name} normalizer failed via `{profile.name}` profile: {exc}",
                    error_code=exc.error_code,
                    raw_metadata_json={
                        "request_profile": profile.name,
                        "model": resolved_model,
                    },
                )

        if not isinstance(normalized_payload, dict | list):
            return ContentNormalizerResponse(
                normalized_payload=None,
                error_code=ProviderBadResponseError.error_code,
                raw_metadata_json={"model": resolved_model},
            )
        count = len(normalized_payload) if isinstance(normalized_payload, list) else 1
        return ContentNormalizerResponse(
            normalized_payload=normalized_payload,
            raw_result_summary=_format_retry_success_summary(
                provider_name=self.provider_name,
                selected_profile_name=selected_profile_name,
                profile_failures=profile_failures,
                result_count=count,
            ),
            raw_metadata_json={
                "request_profile": selected_profile_name,
                "profile_failures": profile_failures,
                "usage": response_usage,
                "model": resolved_model,
            },
        )


class FindymailContactEnrichmentTool(_ProviderTool):
    provider_name = "findymail"

    def __init__(
        self,
        settings: FindymailSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.enrichment_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, request: ContactEnrichmentRequest) -> ContactEnrichmentResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return ContactEnrichmentResponse(error_code=error_code)

        email = _extract_email_identifier(request.provider_key)
        if email is None:
            return ContactEnrichmentResponse()

        try:
            payload = await self._request_json(
                "POST",
                "/api/search/reverse-email",
                json_body={"email": email},
            )
        except ProviderError as exc:
            return ContactEnrichmentResponse(error_code=exc.error_code)
        item = _extract_single_record(payload)
        return _map_contact_enrichment_response(self.provider_name, item, fallback_email=email)


class TombaContactEnrichmentTool(_ProviderTool):
    provider_name = "tomba"

    def __init__(
        self,
        settings: TombaSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        self._api_secret = settings.api_secret
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.enrichment_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "X-Tomba-Key": self._api_key,
            "X-Tomba-Secret": self._api_secret,
        }

    async def execute(self, request: ContactEnrichmentRequest) -> ContactEnrichmentResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return ContactEnrichmentResponse(error_code=error_code)

        email = _extract_email_identifier(request.provider_key)
        if email is None:
            return ContactEnrichmentResponse()

        source_references: list[ToolSourceReference] = []
        person_profile: dict[str, Any] = {}
        full_name: str | None = None
        job_title: str | None = None
        linkedin_url: str | None = None
        phone: str | None = None
        try:
            enrichment_payload = await self._request_json(
                "GET",
                "/v1/enrich",
                params={"email": email},
            )
            person_item = _extract_single_record(enrichment_payload)
            mapped = _map_contact_enrichment_response(
                self.provider_name,
                person_item,
                fallback_email=email,
            )
            person_profile = dict(mapped.person_profile or {})
            source_references.extend(mapped.source_references)
            full_name = mapped.full_name
            job_title = mapped.job_title
            linkedin_url = mapped.linkedin_url
            phone = mapped.phone
        except ProviderBadResponseError:
            pass
        except ProviderError as exc:
            return ContactEnrichmentResponse(error_code=exc.error_code)

        try:
            sources_payload = await self._request_json(
                "GET",
                "/v1/email-sources",
                params={"email": email},
            )
        except ProviderBadResponseError:
            sources_payload = {}
        except ProviderError as exc:
            return ContactEnrichmentResponse(error_code=exc.error_code)

        for source in _extract_list_records(sources_payload):
            source_references.append(
                ToolSourceReference(
                    provider_name=self.provider_name,
                    source_url=_normalize_optional_text(source.get("source_url"))
                    or _normalize_optional_text(source.get("url")),
                    title=_normalize_optional_text(source.get("title"))
                    or _normalize_optional_text(source.get("domain")),
                )
            )
        return ContactEnrichmentResponse(
            full_name=full_name,
            job_title=job_title,
            email=email,
            linkedin_url=linkedin_url,
            phone=phone,
            person_profile=person_profile or None,
            source_references=_dedupe_source_references(source_references),
        )


class FindymailContactSearchProviderTool(_ProviderTool):
    provider_name = "findymail"

    def __init__(
        self,
        settings: FindymailSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.search_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def search(
        self,
        request: ContactSearchProviderRequest,
    ) -> ContactSearchProviderResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return ContactSearchProviderResponse(
                provider_name=self.provider_name,
                error_code=error_code,
                errors=["Missing Findymail credentials."],
            )

        try:
            candidates = await self._run_findymail_search(request)
        except ProviderError as exc:
            return ContactSearchProviderResponse(
                provider_name=self.provider_name,
                error_code=exc.error_code,
                errors=[str(exc)],
            )
        return ContactSearchProviderResponse(
            provider_name=self.provider_name,
            candidates=candidates,
            raw_result_summary=f"Retrieved {len(candidates)} Findymail candidate(s).",
        )

    async def _run_findymail_search(
        self,
        request: ContactSearchProviderRequest,
    ) -> list[ContactSearchProviderCandidate]:
        candidates: list[ContactSearchProviderCandidate] = []
        if request.account_domain:
            candidates.extend(await self._search_domain(request))
        if request.selected_people:
            for person_name in request.selected_people[:3]:
                candidates.extend(await self._search_name(request, person_name))
        if request.linkedin_urls:
            for linkedin_url in request.linkedin_urls[:3]:
                candidates.extend(await self._search_business_profile(request, linkedin_url))
        return _dedupe_provider_candidates(candidates)

    async def _search_domain(
        self,
        request: ContactSearchProviderRequest,
    ) -> list[ContactSearchProviderCandidate]:
        roles = request.title_hints[:3]
        payload = {
            "domain": request.account_domain,
            "roles": roles,
        }
        try:
            response = await self._request_json("POST", "/api/search/domain", json_body=payload)
        except ProviderBadResponseError:
            response = await self._request_json(
                "POST",
                "/api/search/employees",
                json_body={"domain": request.account_domain, "job_titles": roles},
            )
        return _map_provider_candidate_records(
            provider_name=self.provider_name,
            records=_extract_list_records(response),
            fallback_domain=request.account_domain,
            match_reason="Matched the target account domain and normalized role hints.",
        )

    async def _search_name(
        self,
        request: ContactSearchProviderRequest,
        person_name: str,
    ) -> list[ContactSearchProviderCandidate]:
        response = await self._request_json(
            "POST",
            "/api/search/name",
            json_body={
                "name": person_name,
                "domain": request.account_domain,
                "company_name": request.account_name,
            },
        )
        return _map_provider_candidate_records(
            provider_name=self.provider_name,
            records=_extract_list_records(response),
            fallback_domain=request.account_domain,
            match_reason="Resolved a named contact against the target account.",
        )

    async def _search_business_profile(
        self,
        request: ContactSearchProviderRequest,
        linkedin_url: str,
    ) -> list[ContactSearchProviderCandidate]:
        response = await self._request_json(
            "POST",
            "/api/search/business-profile",
            json_body={"url": linkedin_url, "domain": request.account_domain},
        )
        return _map_provider_candidate_records(
            provider_name=self.provider_name,
            records=_extract_list_records(response),
            fallback_domain=request.account_domain,
            match_reason="Resolved a LinkedIn-backed business profile for the account.",
        )


class TombaContactSearchProviderTool(_ProviderTool):
    provider_name = "tomba"

    def __init__(
        self,
        settings: TombaSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = settings.api_key
        self._api_secret = settings.api_secret
        super().__init__(
            configured=settings.is_configured,
            base_url=settings.base_url,
            timeout_seconds=settings.timeouts.search_seconds,
            max_retries=settings.retry.max_attempts,
            transport=transport,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            "X-Tomba-Key": self._api_key,
            "X-Tomba-Secret": self._api_secret,
        }

    async def search(
        self,
        request: ContactSearchProviderRequest,
    ) -> ContactSearchProviderResponse:
        error_code = self._configuration_error_code()
        if error_code is not None:
            return ContactSearchProviderResponse(
                provider_name=self.provider_name,
                error_code=error_code,
                errors=["Missing Tomba credentials."],
            )

        try:
            candidates = await self._run_tomba_search(request)
        except ProviderError as exc:
            return ContactSearchProviderResponse(
                provider_name=self.provider_name,
                error_code=exc.error_code,
                errors=[str(exc)],
            )
        return ContactSearchProviderResponse(
            provider_name=self.provider_name,
            candidates=candidates,
            raw_result_summary=f"Retrieved {len(candidates)} Tomba candidate(s).",
        )

    async def _run_tomba_search(
        self,
        request: ContactSearchProviderRequest,
    ) -> list[ContactSearchProviderCandidate]:
        candidates: list[ContactSearchProviderCandidate] = []
        if request.account_domain:
            response = await self._request_json(
                "GET",
                "/v1/domain-search",
                params={"domain": request.account_domain, "limit": 5},
            )
            candidates.extend(
                _map_provider_candidate_records(
                    provider_name=self.provider_name,
                    records=_extract_list_records(response),
                    fallback_domain=request.account_domain,
                    match_reason="Matched the target account through Tomba domain search.",
                )
            )
        if request.account_domain and request.selected_people:
            for person_name in request.selected_people[:3]:
                first_name, last_name = _split_full_name(person_name)
                response = await self._request_json(
                    "GET",
                    "/v1/email-finder",
                    params={
                        "domain": request.account_domain,
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                )
                candidates.extend(
                    _map_provider_candidate_records(
                        provider_name=self.provider_name,
                        records=_extract_list_records(response),
                        fallback_domain=request.account_domain,
                        match_reason="Resolved a named contact through Tomba email finder.",
                    )
                )
        if request.linkedin_urls:
            for linkedin_url in request.linkedin_urls[:3]:
                response = await self._request_json(
                    "GET",
                    "/v1/linkedin",
                    params={"url": linkedin_url},
                )
                candidates.extend(
                    _map_provider_candidate_records(
                        provider_name=self.provider_name,
                        records=_extract_list_records(response),
                        fallback_domain=request.account_domain,
                        match_reason="Resolved a LinkedIn-backed contact through Tomba.",
                    )
                )
        return _dedupe_provider_candidates(candidates)


def _schema_spec_for_hint(schema_hint: str | None) -> _SchemaSpec | None:
    if schema_hint == "account_search_query_plan":
        return _SchemaSpec(
            prompt_spec=build_account_search_query_plan_prompt_spec(),
            schema_name=schema_hint,
            schema=AccountSearchQueryPlanOutput.model_json_schema(),
        )
    if schema_hint == "account_search_candidates":
        return _SchemaSpec(
            prompt_spec=build_account_search_prompt_spec(),
            schema_name=schema_hint,
            schema=AccountSearchReasoningOutput.model_json_schema(),
        )
    if schema_hint == "account_research_summary":
        return _SchemaSpec(
            prompt_spec=build_account_research_prompt_spec(),
            schema_name=schema_hint,
            schema=AccountResearchReasoningOutput.model_json_schema(),
        )
    if schema_hint == "contact_search_candidates":
        return _SchemaSpec(
            prompt_spec=build_contact_search_prompt_spec(),
            schema_name=schema_hint,
            schema=ContactSearchReasoningOutput.model_json_schema(),
        )
    return None


def _build_company_enrichment_query(request: CompanyEnrichmentRequest) -> str:
    normalized_domain = _normalize_domain(request.domain)
    normalized_name = _normalize_optional_text(request.company_name)
    if normalized_domain is not None and normalized_name is not None:
        return f"{normalized_name} {normalized_domain} company overview"
    if normalized_domain is not None:
        return f"{normalized_domain} company overview"
    if normalized_name is not None:
        return f"{normalized_name} company overview"
    return _normalize_optional_text(request.provider_key) or "company overview"


def _compact_metadata(payload: dict[str, Any], *, keys: tuple[str, ...]) -> dict[str, Any] | None:
    compacted = {key: payload[key] for key in keys if key in payload and payload[key] is not None}
    return compacted or None


def _extract_list_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    direct_candidates = _coerce_dict_list(payload)
    if direct_candidates:
        return direct_candidates

    candidates: list[dict[str, Any]] = []
    for key in ("data", "results", "contacts", "employees", "people", "emails", "sources"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(_coerce_dict_list(value))
        elif isinstance(value, dict):
            nested = _extract_list_records(value)
            if nested:
                return nested
    return candidates


def _extract_single_record(payload: dict[str, Any]) -> dict[str, Any]:
    records = _extract_list_records(payload)
    if records:
        return records[0]
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _coerce_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _map_provider_candidate_records(
    *,
    provider_name: str,
    records: list[dict[str, Any]],
    fallback_domain: str | None,
    match_reason: str,
) -> list[ContactSearchProviderCandidate]:
    mapped: list[ContactSearchProviderCandidate] = []
    for item in records:
        full_name = (
            _normalize_optional_text(item.get("full_name"))
            or _normalize_optional_text(item.get("name"))
            or _build_name_from_parts(item)
        )
        email = _normalize_email(item.get("email"))
        linkedin_url = (
            _normalize_optional_text(item.get("linkedin_url"))
            or _normalize_optional_text(item.get("linkedin"))
            or _normalize_optional_text(item.get("linkedinUrl"))
        )
        job_title = (
            _normalize_optional_text(item.get("job_title"))
            or _normalize_optional_text(item.get("title"))
            or _normalize_optional_text(item.get("jobTitle"))
        )
        company_domain = (
            _normalize_domain(item.get("company_domain"))
            or _normalize_domain(item.get("domain"))
            or _normalize_domain(item.get("companyDomain"))
            or _normalize_domain(fallback_domain)
            or _extract_domain_from_email(email)
        )
        provider_key = (
            _normalize_optional_text(item.get("id"))
            or _normalize_optional_text(item.get("provider_key"))
            or email
            or linkedin_url
        )
        acceptance_reason = (
            _normalize_optional_text(item.get("acceptance_reason"))
            or _normalize_optional_text(item.get("reason"))
            or match_reason
        )
        confidence = _coerce_confidence(
            item.get("confidence_0_1")
            or item.get("confidence")
            or item.get("score")
            or (0.95 if item.get("verified") else None)
        )
        evidence_refs = _build_provider_evidence_refs(provider_name, item)
        missing_fields = [
            field_name
            for field_name, value in (
                ("full_name", full_name),
                ("email", email),
                ("linkedin_url", linkedin_url),
                ("job_title", job_title),
            )
            if value is None
        ]
        if full_name is None and email is None and linkedin_url is None:
            continue
        mapped.append(
            ContactSearchProviderCandidate(
                full_name=full_name,
                email=email,
                linkedin_url=linkedin_url,
                job_title=job_title,
                company_domain=company_domain,
                source_provider=provider_name,
                provider_key=provider_key,
                confidence_0_1=confidence,
                acceptance_reason=acceptance_reason,
                missing_fields=missing_fields,
                evidence_refs=evidence_refs,
                provider_metadata=_compact_metadata(
                    item,
                    keys=("id", "verified", "department", "seniority", "company"),
                ),
            )
        )
    return mapped


def _map_contact_enrichment_response(
    provider_name: str,
    payload: dict[str, Any],
    *,
    fallback_email: str | None = None,
) -> ContactEnrichmentResponse:
    linkedin_url = (
        _normalize_optional_text(payload.get("linkedin_url"))
        or _normalize_optional_text(payload.get("linkedin"))
        or _normalize_optional_text(payload.get("linkedinUrl"))
    )
    source_references = _build_provider_evidence_refs(provider_name, payload)
    person_profile = _compact_metadata(
        payload,
        keys=("company", "department", "seniority", "verified"),
    )
    return ContactEnrichmentResponse(
        full_name=(
            _normalize_optional_text(payload.get("full_name"))
            or _normalize_optional_text(payload.get("name"))
            or _build_name_from_parts(payload)
        ),
        job_title=(
            _normalize_optional_text(payload.get("job_title"))
            or _normalize_optional_text(payload.get("title"))
            or _normalize_optional_text(payload.get("jobTitle"))
        ),
        email=_normalize_email(payload.get("email")) or fallback_email,
        linkedin_url=linkedin_url,
        phone=_normalize_optional_text(payload.get("phone")),
        person_profile=person_profile,
        source_references=source_references,
    )


def _build_firecrawl_search_profiles(request: WebSearchRequest) -> list[_RequestProfile]:
    primary_body = {
        "query": request.query_text,
        "limit": request.result_limit,
        "sources": ["web"],
    }
    if request.freshness_hint:
        primary_body["tbs"] = request.freshness_hint

    compatibility_body = {
        "query": request.query_text,
        "limit": request.result_limit,
    }
    if request.freshness_hint:
        compatibility_body["tbs"] = request.freshness_hint

    minimal_body = {"query": request.query_text}

    return [
        _RequestProfile(name="strict_web_search", json_body=primary_body),
        _RequestProfile(name="compatibility_without_sources", json_body=compatibility_body),
        _RequestProfile(name="minimal_query_only", json_body=minimal_body),
    ]


def _extract_firecrawl_web_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        for candidate_key in ("web", "results"):
            candidate_results = data.get(candidate_key)
            if isinstance(candidate_results, list):
                return candidate_results
            if isinstance(candidate_results, dict):
                return [candidate_results]

    for candidate_key in ("results", "web"):
        candidate_results = payload.get(candidate_key)
        if isinstance(candidate_results, list):
            return candidate_results
        if isinstance(candidate_results, dict):
            return [candidate_results]
    return []


def _build_openai_normalizer_profiles(
    *,
    model: str,
    schema_spec: _SchemaSpec,
    schema_hint: str | None,
    raw_payload_json: str,
    instructions_override: str | None = None,
    system_prompt_override: str | None = None,
) -> list[_RequestProfile]:
    system_prompt_prefix = " ".join(
        value.strip()
        for value in (system_prompt_override, instructions_override, schema_spec.prompt_spec)
        if isinstance(value, str) and value.strip()
    )
    messages = [
        {
            "role": "system",
            "content": (
                f"{system_prompt_prefix} "
                "Return only valid JSON that exactly matches the supplied schema."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Normalize this workflow payload for `{schema_hint}`.\n"
                f"Payload:\n{raw_payload_json}"
            ),
        },
    ]
    compatibility_messages = [
        {
            "role": "system",
            "content": (
                f"{system_prompt_prefix} "
                "Return a JSON object only. Follow this schema exactly.\n"
                f"Schema:\n{json.dumps(schema_spec.schema, ensure_ascii=True, sort_keys=True)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Normalize this workflow payload for `{schema_hint}`.\n"
                f"Payload:\n{raw_payload_json}"
            ),
        },
    ]
    return [
        _RequestProfile(
            name="strict_json_schema",
            json_body={
                "model": model,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_spec.schema_name,
                        "strict": True,
                        "schema": schema_spec.schema,
                    },
                },
            },
        ),
        _RequestProfile(
            name="compatibility_json_object",
            json_body={
                "model": model,
                "messages": compatibility_messages,
                "response_format": {"type": "json_object"},
            },
        ),
    ]


def _parse_openai_normalizer_payload(
    payload: dict[str, Any],
) -> dict[str, Any] | list[dict[str, Any]]:
    message = ((payload.get("choices") or [{}])[0]).get("message") or {}
    refusal = _normalize_optional_text(message.get("refusal"))
    if refusal is not None:
        raise ProviderBadResponseError(
            "openai",
            f"OpenAI refused the structured-output request: {refusal}",
        )
    content = _extract_openai_message_text(message)
    if not isinstance(content, str) or not content.strip():
        raise ProviderBadResponseError(
            "openai",
            "OpenAI returned an empty structured-output payload.",
        )
    try:
        normalized_payload = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ProviderBadResponseError(
            "openai",
            f"OpenAI returned invalid structured JSON: {exc}",
        ) from exc
    if not isinstance(normalized_payload, dict | list):
        raise ProviderBadResponseError(
            "openai",
            "OpenAI returned structured data in an unexpected shape.",
        )
    return normalized_payload


def _extract_openai_message_text(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        normalized = content.strip()
        return normalized or None
    if not isinstance(content, list):
        return None
    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = _normalize_optional_text(item.get("type"))
        if item_type not in {"text", "output_text"}:
            continue
        text_value = _normalize_optional_text(item.get("text"))
        if text_value is not None:
            text_parts.append(text_value)
    if not text_parts:
        return None
    return "".join(text_parts)


def _format_profile_failure_summary(
    *,
    provider_name: str,
    profile_failures: list[str],
) -> str:
    if not profile_failures:
        return f"{provider_name} request failed without a compatibility profile summary."
    joined_failures = "; ".join(profile_failures)
    return f"{provider_name} request failed across compatibility profiles: {joined_failures}"


def _format_retry_success_summary(
    *,
    provider_name: str,
    selected_profile_name: str,
    profile_failures: list[str],
    result_count: int,
) -> str | None:
    if not profile_failures:
        return None
    failed_profiles = ", ".join(profile_failures)
    return (
        f"{provider_name} succeeded with `{selected_profile_name}` after compatibility retry. "
        f"Prior failures: {failed_profiles}. Result count: {result_count}."
    )


def _build_provider_evidence_refs(
    provider_name: str,
    payload: dict[str, Any],
) -> list[ToolSourceReference]:
    references: list[ToolSourceReference] = []
    for value in (
        payload.get("source_url"),
        payload.get("url"),
        payload.get("linkedin_url"),
        payload.get("linkedin"),
        payload.get("linkedinUrl"),
    ):
        normalized_url = _normalize_optional_text(value)
        if normalized_url is None:
            continue
        references.append(
            ToolSourceReference(
                provider_name=provider_name,
                source_url=normalized_url,
                title=_normalize_optional_text(payload.get("title"))
                or _normalize_optional_text(payload.get("name")),
            )
        )
    return _dedupe_source_references(references)


def _dedupe_provider_candidates(
    candidates: list[ContactSearchProviderCandidate],
) -> list[ContactSearchProviderCandidate]:
    deduped: list[ContactSearchProviderCandidate] = []
    seen_keys: set[tuple[str | None, str | None, str | None]] = set()
    for candidate in candidates:
        key = (
            _normalize_email(candidate.email),
            _normalize_optional_text(candidate.linkedin_url),
            _normalize_optional_text(candidate.full_name),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(candidate)
    return deduped


def _dedupe_source_references(
    references: list[ToolSourceReference],
) -> list[ToolSourceReference]:
    deduped: list[ToolSourceReference] = []
    seen_keys: set[tuple[str | None, str | None, str | None]] = set()
    for reference in references:
        key = (
            _normalize_optional_text(reference.provider_name),
            _normalize_optional_text(reference.source_url),
            _normalize_optional_text(reference.title),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(reference)
    return deduped


def _build_name_from_parts(payload: dict[str, Any]) -> str | None:
    first_name = _normalize_optional_text(payload.get("first_name")) or _normalize_optional_text(
        payload.get("firstName")
    )
    last_name = _normalize_optional_text(payload.get("last_name")) or _normalize_optional_text(
        payload.get("lastName")
    )
    if first_name and last_name:
        return f"{first_name} {last_name}"
    return first_name or last_name


def _extract_email_identifier(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None or "@" not in normalized:
        return None
    return normalized.lower()


def _split_full_name(value: str) -> tuple[str, str]:
    parts = [part for part in value.split() if part]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    if parts:
        return parts[0], ""
    return "", ""


def _extract_domain_from_url(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    hostname = parsed.netloc or parsed.path
    if not hostname:
        return None
    return _normalize_domain(hostname)


def _extract_domain_from_email(value: str | None) -> str | None:
    normalized = _normalize_email(value)
    if normalized is None or "@" not in normalized:
        return None
    return _normalize_domain(normalized.split("@", maxsplit=1)[1])


def _normalize_domain(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if "://" in normalized:
        normalized = _extract_domain_from_url(normalized) or normalized
    normalized = normalized.removeprefix("www.")
    return normalized.rstrip("/")


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


def _coerce_confidence(value: Any) -> float | None:
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


def _normalize_scraped_text(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _extract_headings(body_text: str | None) -> list[str]:
    normalized = _normalize_optional_text(body_text)
    if normalized is None:
        return []
    headings: list[str] = []
    for match in re.finditer(r"(?m)^#{1,6}\s+(.+)$", normalized):
        heading = _normalize_optional_text(match.group(1))
        if heading is not None:
            headings.append(heading)
    return headings[:10]


def _extract_links(body_text: str | None, source_url: str | None) -> list[str]:
    normalized = _normalize_optional_text(body_text)
    if normalized is None:
        return [source_url] if source_url is not None else []
    links = re.findall(r"https?://[^\s)>\]]+", normalized)
    if source_url is not None:
        links.insert(0, source_url)
    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        normalized_link = _normalize_optional_text(link)
        if normalized_link is None or normalized_link in seen:
            continue
        seen.add(normalized_link)
        deduped.append(normalized_link)
    return deduped[:20]


def _html_to_text(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    without_tags = re.sub(r"<[^>]+>", " ", normalized)
    without_entities = without_tags.replace("&nbsp;", " ").replace("&amp;", "&")
    return _normalize_scraped_text(without_entities)
