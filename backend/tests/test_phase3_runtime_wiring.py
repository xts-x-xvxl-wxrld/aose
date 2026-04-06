from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.orchestration.contracts import WorkflowType
from app.services.runtime import WorkflowExecutionRequest
from app.services.runtime_wiring import build_workflow_executor
from app.tools.contracts import (
    CompanyEnrichmentRequest,
    ContentNormalizerRequest,
    WebSearchRequest,
    get_tool_provider_name,
)
from app.tools.provider_adapters import FirecrawlWebSearchTool, OpenAIContentNormalizerTool
from app.tools.provider_errors import ProviderAuthError, ProviderUnavailableError
from app.tools.provider_factory import build_phase3_tool_factory
from app.workflows.account_research import AccountResearchToolset
from app.workflows.account_search import AccountSearchToolset
from app.workflows.contact_search import ContactSearchToolset


def test_settings_expose_phase3_provider_config_objects() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="openai-key",
        firecrawl_api_key="firecrawl-key",
        google_local_places_api_key="places-key",
        findymail_api_key="findymail-key",
        tomba_api_key="tomba-key",
        tomba_api_secret="tomba-secret",
        provider_search_timeout_seconds=11,
        provider_enrichment_timeout_seconds=16,
        provider_research_fetch_timeout_seconds=21,
        provider_max_retry_attempts=3,
    )

    assert settings.firecrawl.api_key == "firecrawl-key"
    assert settings.firecrawl.base_url == "https://api.firecrawl.dev"
    assert settings.firecrawl.timeouts.search_seconds == 11
    assert settings.google_local_places.api_key == "places-key"
    assert settings.google_local_places.base_url == "https://places.googleapis.com"
    assert settings.findymail.api_key == "findymail-key"
    assert settings.findymail.base_url == "https://app.findymail.com"
    assert settings.tomba.api_key == "tomba-key"
    assert settings.tomba.api_secret == "tomba-secret"
    assert settings.openai.api_key == "openai-key"
    assert settings.openai.base_url == "https://api.openai.com/v1"
    assert settings.openai.model == settings.openai_agent_model
    assert settings.openai.retry.max_attempts == 3


def test_phase3_tool_factory_builds_provider_backed_toolsets_and_routing() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="openai-key",
        firecrawl_api_key="firecrawl-key",
        google_local_places_api_key="places-key",
        findymail_api_key="findymail-key",
        tomba_api_key="tomba-key",
        tomba_api_secret="tomba-secret",
    )
    factory = build_phase3_tool_factory(settings)

    account_search_tools = factory.build_account_search_toolset()
    account_research_tools = factory.build_account_research_toolset()
    contact_search_tools = factory.build_contact_search_toolset()
    routing = factory.build_contact_search_routing_policy()

    assert get_tool_provider_name(account_search_tools.web_search) == "firecrawl"
    assert get_tool_provider_name(account_search_tools.fallback_web_search) == "google_local_places"
    assert get_tool_provider_name(account_search_tools.content_normalizer) == "openai"
    assert get_tool_provider_name(account_search_tools.company_enrichment) == "firecrawl"
    assert get_tool_provider_name(account_research_tools.page_fetch) == "firecrawl"
    assert get_tool_provider_name(contact_search_tools.provider_search) == "findymail"
    assert get_tool_provider_name(contact_search_tools.fallback_provider_search) == "tomba"
    assert get_tool_provider_name(contact_search_tools.contact_enrichment) == "findymail"
    assert get_tool_provider_name(factory.build_google_local_places_search_tool()) == (
        "google_local_places"
    )
    assert get_tool_provider_name(factory.build_tomba_contact_enrichment_tool()) == "tomba"
    assert routing.primary_provider == "findymail"
    assert routing.fallback_provider == "tomba"


@pytest.mark.asyncio
async def test_provider_backed_tools_fail_clearly_without_credentials() -> None:
    factory = build_phase3_tool_factory(
        Settings(
            _env_file=None,
            openai_api_key="",
            firecrawl_api_key="",
            google_local_places_api_key="",
            findymail_api_key="",
            tomba_api_key="",
            tomba_api_secret="",
        )
    )

    web_search_response = await factory.build_account_search_toolset().web_search.execute(
        WebSearchRequest(query_text="acme fintech")
    )
    normalizer_response = await factory.build_account_search_toolset().content_normalizer.execute(
        ContentNormalizerRequest(raw_payload={"results": []}, schema_hint="account_search_candidates")
    )
    company_enrichment_response = await factory.build_account_search_toolset().company_enrichment.execute(
        CompanyEnrichmentRequest(domain="acme.com")
    )

    assert web_search_response.error_code == ProviderAuthError.error_code
    assert normalizer_response.error_code == ProviderAuthError.error_code
    assert company_enrichment_response.error_code == ProviderAuthError.error_code


@pytest.mark.asyncio
async def test_provider_backed_tools_use_normalized_unavailable_error_when_configured() -> None:
    failing_transport = httpx.MockTransport(
        lambda request: httpx.Response(503, json={"error": "provider unavailable"})
    )
    settings = Settings(
        _env_file=None,
        openai_api_key="openai-key",
        firecrawl_api_key="firecrawl-key",
    )
    firecrawl_tool = FirecrawlWebSearchTool(settings.firecrawl, transport=failing_transport)
    openai_tool = OpenAIContentNormalizerTool(settings.openai, transport=failing_transport)

    web_search_response = await firecrawl_tool.execute(
        WebSearchRequest(query_text="acme fintech")
    )
    normalizer_response = await openai_tool.execute(
        ContentNormalizerRequest(raw_payload={"results": []}, schema_hint="account_search_candidates")
    )

    assert web_search_response.error_code == ProviderUnavailableError.error_code
    assert normalizer_response.error_code == ProviderUnavailableError.error_code


class _SpyWorkflowFactory:
    def __init__(self) -> None:
        self.account_search_tools = AccountSearchToolset(
            web_search=SimpleNamespace(provider_name="spy-account-search-web"),
            fallback_web_search=SimpleNamespace(provider_name="spy-account-search-fallback"),
            content_normalizer=SimpleNamespace(provider_name="spy-account-search-normalizer"),
            company_enrichment=SimpleNamespace(provider_name="spy-account-search-enrichment"),
        )
        self.account_research_tools = AccountResearchToolset(
            web_search=SimpleNamespace(provider_name="spy-account-research-web"),
            page_fetch=SimpleNamespace(provider_name="spy-account-research-fetch"),
            page_scrape=SimpleNamespace(provider_name="spy-account-research-scrape"),
            content_normalizer=SimpleNamespace(provider_name="spy-account-research-normalizer"),
            company_enrichment=SimpleNamespace(provider_name="spy-account-research-enrichment"),
        )
        self.contact_search_tools = ContactSearchToolset(
            web_search=SimpleNamespace(provider_name="spy-contact-search-web"),
            content_normalizer=SimpleNamespace(provider_name="spy-contact-search-normalizer"),
            contact_enrichment=SimpleNamespace(provider_name="spy-contact-search-enrichment"),
        )

    def build_account_search_toolset(self) -> AccountSearchToolset:
        return self.account_search_tools

    def build_account_research_toolset(self) -> AccountResearchToolset:
        return self.account_research_tools

    def build_contact_search_toolset(self) -> ContactSearchToolset:
        return self.contact_search_tools

    def build_google_local_places_search_tool(self) -> SimpleNamespace:
        return SimpleNamespace(provider_name="spy-google-local-places")

    def build_findymail_contact_enrichment_tool(self) -> SimpleNamespace:
        return SimpleNamespace(provider_name="spy-findymail")

    def build_tomba_contact_enrichment_tool(self) -> SimpleNamespace:
        return SimpleNamespace(provider_name="spy-tomba")

    def build_contact_search_routing_policy(self) -> SimpleNamespace:
        return SimpleNamespace(primary_provider="findymail", fallback_provider="tomba")


class _AsyncSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        _ = exc_type
        _ = exc
        _ = tb
        return False


class _SessionFactory:
    def __call__(self) -> _AsyncSessionContext:
        return _AsyncSessionContext()


@pytest.mark.asyncio
async def test_build_workflow_executor_injects_tool_factory_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_tools: dict[str, object] = {}
    tool_factory = _SpyWorkflowFactory()

    class _FakeWorkflowRunService:
        def __init__(self, session: object) -> None:
            self.session = session

    class _FakeAccountSearchWorkflow:
        def __init__(self, session: object, *, run_service: object, tools: object) -> None:
            _ = session
            _ = run_service
            captured_tools["account_search"] = tools

        async def execute(self, request: WorkflowExecutionRequest) -> None:
            _ = request

    class _FakeAccountResearchWorkflow:
        def __init__(self, session: object, *, run_service: object, tools: object) -> None:
            _ = session
            _ = run_service
            captured_tools["account_research"] = tools

        async def execute(self, request: WorkflowExecutionRequest) -> None:
            _ = request

    class _FakeContactSearchWorkflow:
        def __init__(self, session: object, *, run_service: object, tools: object) -> None:
            _ = session
            _ = run_service
            captured_tools["contact_search"] = tools

        async def execute(self, request: WorkflowExecutionRequest) -> None:
            _ = request

    async def _fake_execute_workflow_request(
        *,
        request: WorkflowExecutionRequest,
        run_service: object,
        handler,
    ) -> None:
        _ = run_service
        await handler(request)

    monkeypatch.setattr(
        "app.services.runtime_wiring.WorkflowRunService",
        _FakeWorkflowRunService,
    )
    monkeypatch.setattr(
        "app.services.runtime_wiring.AccountSearchWorkflow",
        _FakeAccountSearchWorkflow,
    )
    monkeypatch.setattr(
        "app.services.runtime_wiring.AccountResearchWorkflow",
        _FakeAccountResearchWorkflow,
    )
    monkeypatch.setattr(
        "app.services.runtime_wiring.ContactSearchWorkflow",
        _FakeContactSearchWorkflow,
    )
    monkeypatch.setattr(
        "app.services.runtime_wiring.execute_workflow_request",
        _fake_execute_workflow_request,
    )

    executor = build_workflow_executor(
        _SessionFactory(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None),
        tool_factory=tool_factory,
    )

    for workflow_type in (
        WorkflowType.ACCOUNT_SEARCH,
        WorkflowType.ACCOUNT_RESEARCH,
        WorkflowType.CONTACT_SEARCH,
    ):
        await executor.dispatch(
            WorkflowExecutionRequest(
                run_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                workflow_type=workflow_type,
                thread_id=None,
            )
        )

    await executor.wait_for_all()

    assert captured_tools["account_search"] is tool_factory.account_search_tools
    assert captured_tools["account_research"] is tool_factory.account_research_tools
    assert captured_tools["contact_search"] is tool_factory.contact_search_tools
