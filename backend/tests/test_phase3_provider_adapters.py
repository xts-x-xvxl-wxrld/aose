from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.tools.contracts import (
    ContactSearchProviderRequest,
    ContactEnrichmentRequest,
    ContentNormalizerRequest,
    WebSearchRequest,
)
from app.tools.provider_adapters import (
    FindymailContactEnrichmentTool,
    FindymailContactSearchProviderTool,
    FirecrawlWebSearchTool,
    GoogleLocalPlacesWebSearchTool,
    OpenAIContentNormalizerTool,
    TombaContactSearchProviderTool,
)


def _json_transport(handler):
    def _dispatch(request: httpx.Request) -> httpx.Response:
        status_code, payload = handler(request)
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(_dispatch)


@pytest.mark.asyncio
async def test_firecrawl_web_search_normalizes_v2_results() -> None:
    transport = _json_transport(
        lambda request: (
            200,
            {
                "data": {
                    "web": [
                        {
                            "url": "https://acme.example",
                            "title": "Acme Fintech",
                            "description": "Revenue operations tooling for fintech teams.",
                        }
                    ]
                }
            },
        )
    )
    tool = FirecrawlWebSearchTool(
        Settings(_env_file=None, firecrawl_api_key="firecrawl-key").firecrawl,
        transport=transport,
    )

    response = await tool.execute(WebSearchRequest(query_text="acme fintech", result_limit=3))

    assert response.error_code is None
    assert response.results[0].title == "Acme Fintech"
    assert response.results[0].provider_name == "firecrawl"


@pytest.mark.asyncio
async def test_google_local_places_search_normalizes_place_results() -> None:
    transport = _json_transport(
        lambda request: (
            200,
            {
                "places": [
                    {
                        "id": "place-123",
                        "displayName": {"text": "Acme Clinic"},
                        "formattedAddress": "123 Main St, Austin, TX",
                        "websiteUri": "https://acmeclinic.example",
                        "primaryType": "doctor",
                    }
                ]
            },
        )
    )
    tool = GoogleLocalPlacesWebSearchTool(
        Settings(_env_file=None, google_local_places_api_key="places-key").google_local_places,
        transport=transport,
    )

    response = await tool.execute(WebSearchRequest(query_text="acme clinic austin"))

    assert response.error_code is None
    assert response.results[0].title == "Acme Clinic"
    assert response.results[0].provider_name == "google_local_places"


@pytest.mark.asyncio
async def test_openai_content_normalizer_parses_structured_json_response() -> None:
    transport = _json_transport(
        lambda request: (
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "accepted_candidates": [
                                        {
                                            "name": "Acme Fintech",
                                            "domain": "acme.example",
                                        }
                                    ],
                                    "rejected_candidates": [],
                                    "missing_data_flags": [],
                                    "evidence_refs": [],
                                }
                            )
                        }
                    }
                ]
            },
        )
    )
    tool = OpenAIContentNormalizerTool(
        Settings(_env_file=None, openai_api_key="openai-key").openai,
        transport=transport,
    )

    response = await tool.execute(
        ContentNormalizerRequest(
            raw_payload={"results": []},
            schema_hint="account_search_candidates",
        )
    )

    assert response.error_code is None
    assert response.normalized_payload is not None
    assert response.normalized_payload["accepted_candidates"][0]["name"] == "Acme Fintech"


@pytest.mark.asyncio
async def test_openai_content_normalizer_supports_account_search_query_plan_schema() -> None:
    transport = _json_transport(
        lambda request: (
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "search_strategy": "Focus on B2B fintech operators with clear revops needs.",
                                    "query_ideas": [
                                        "B2B fintech revenue operations software companies United States",
                                        "payments infrastructure companies United States series B series C",
                                    ],
                                    "fit_criteria": ["industry: fintech", "geography: United States"],
                                    "clarification_questions": [],
                                }
                            )
                        }
                    }
                ]
            },
        )
    )
    tool = OpenAIContentNormalizerTool(
        Settings(_env_file=None, openai_api_key="openai-key").openai,
        transport=transport,
    )

    response = await tool.execute(
        ContentNormalizerRequest(
            raw_payload={"seller_profile": {}, "icp_profile": {}},
            schema_hint="account_search_query_plan",
        )
    )

    assert response.error_code is None
    assert response.normalized_payload is not None
    assert response.normalized_payload["query_ideas"][0].startswith("B2B fintech")


@pytest.mark.asyncio
async def test_firecrawl_web_search_retries_with_compatibility_profile_on_bad_request() -> None:
    request_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> tuple[int, dict[str, object]]:
        body = json.loads(request.content.decode())
        request_bodies.append(body)
        if "sources" in body:
            return (400, {"error": "unsupported sources field"})
        return (
            200,
            {
                "data": {
                    "web": [
                        {
                            "url": "https://compat.example",
                            "title": "Compat Account",
                            "description": "Returned after compatibility retry.",
                        }
                    ]
                }
            },
        )

    tool = FirecrawlWebSearchTool(
        Settings(_env_file=None, firecrawl_api_key="firecrawl-key").firecrawl,
        transport=_json_transport(handler),
    )

    response = await tool.execute(WebSearchRequest(query_text="compat account", result_limit=3))

    assert response.error_code is None
    assert len(request_bodies) == 2
    assert "sources" in request_bodies[0]
    assert "sources" not in request_bodies[1]
    assert response.results[0].title == "Compat Account"
    assert response.raw_result_summary is not None
    assert "compatibility retry" in response.raw_result_summary.lower()


@pytest.mark.asyncio
async def test_openai_content_normalizer_retries_with_json_object_profile_on_bad_request() -> None:
    request_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> tuple[int, dict[str, object]]:
        body = json.loads(request.content.decode())
        request_bodies.append(body)
        response_format = body.get("response_format") or {}
        if response_format.get("type") == "json_schema":
            return (400, {"error": "json_schema not supported for this model"})
        return (
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "accepted_candidates": [
                                        {
                                            "name": "Compat Fintech",
                                            "domain": "compat.example",
                                        }
                                    ],
                                    "rejected_candidates": [],
                                    "missing_data_flags": [],
                                    "evidence_refs": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    tool = OpenAIContentNormalizerTool(
        Settings(_env_file=None, openai_api_key="openai-key").openai,
        transport=_json_transport(handler),
    )

    response = await tool.execute(
        ContentNormalizerRequest(
            raw_payload={"results": []},
            schema_hint="account_search_candidates",
        )
    )

    assert response.error_code is None
    assert len(request_bodies) == 2
    assert request_bodies[0]["response_format"]["type"] == "json_schema"
    assert request_bodies[1]["response_format"]["type"] == "json_object"
    assert response.normalized_payload is not None
    assert response.normalized_payload["accepted_candidates"][0]["name"] == "Compat Fintech"
    assert response.raw_result_summary is not None
    assert "compatibility retry" in response.raw_result_summary.lower()


@pytest.mark.asyncio
async def test_findymail_search_and_enrichment_map_provider_payloads() -> None:
    def handler(request: httpx.Request) -> tuple[int, dict[str, object]]:
        if request.url.path.endswith("/api/search/domain"):
            return (
                200,
                {
                    "results": [
                        {
                            "name": "Pat Lee",
                            "email": "pat@example.com",
                            "jobTitle": "Director of Revenue Operations",
                            "linkedinUrl": "https://linkedin.com/in/pat-lee",
                            "verified": True,
                        }
                    ]
                },
            )
        if request.url.path.endswith("/api/search/reverse-email"):
            return (
                200,
                {
                    "data": {
                        "name": "Pat Lee",
                        "email": "pat@example.com",
                        "jobTitle": "Director of Revenue Operations",
                        "linkedinUrl": "https://linkedin.com/in/pat-lee",
                    }
                },
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    transport = _json_transport(handler)
    settings = Settings(_env_file=None, findymail_api_key="findymail-key")
    search_tool = FindymailContactSearchProviderTool(settings.findymail, transport=transport)
    enrichment_tool = FindymailContactEnrichmentTool(settings.findymail, transport=transport)

    search_response = await search_tool.search(
        ContactSearchProviderRequest(
            account_id=uuid4(),
            account_name="Acme",
            account_domain="acme.example",
            title_hints=["operations leader"],
        )
    )
    enrichment_response = await enrichment_tool.execute(
        ContactEnrichmentRequest(
            account_id=uuid4(),
            provider_key="pat@example.com",
        )
    )

    assert search_response.error_code is None
    assert search_response.candidates[0].source_provider == "findymail"
    assert search_response.candidates[0].acceptance_reason is not None
    assert enrichment_response.linkedin_url == "https://linkedin.com/in/pat-lee"


@pytest.mark.asyncio
async def test_tomba_domain_search_maps_candidates() -> None:
    transport = _json_transport(
        lambda request: (
            200,
            {
                "data": {
                    "emails": [
                        {
                            "first_name": "Jordan",
                            "last_name": "Smith",
                            "email": "jordan@example.com",
                            "title": "Head of Sales Operations",
                            "linkedin": "https://linkedin.com/in/jordan-smith",
                        }
                    ]
                }
            },
        )
    )
    tool = TombaContactSearchProviderTool(
        Settings(
            _env_file=None,
            tomba_api_key="tomba-key",
            tomba_api_secret="tomba-secret",
        ).tomba,
        transport=transport,
    )

    response = await tool.search(
        ContactSearchProviderRequest(
            account_id=uuid4(),
            account_domain="acme.example",
        )
    )

    assert response.error_code is None
    assert response.candidates[0].full_name == "Jordan Smith"
    assert response.candidates[0].source_provider == "tomba"
