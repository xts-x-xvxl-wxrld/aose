from __future__ import annotations

from typing import Protocol

from app.config import Settings, get_settings
from app.tools.contracts import ContactSearchProviderRoutingPolicy
from app.tools.provider_adapters import (
    FindymailContactEnrichmentTool,
    FindymailContactSearchProviderTool,
    FirecrawlCompanyEnrichmentTool,
    FirecrawlPageFetchTool,
    FirecrawlPageScrapeTool,
    FirecrawlWebSearchTool,
    GoogleLocalPlacesWebSearchTool,
    OpenAIContentNormalizerTool,
    TombaContactEnrichmentTool,
    TombaContactSearchProviderTool,
)
from app.workflows.account_research import AccountResearchToolset
from app.workflows.account_search import AccountSearchToolset
from app.workflows.contact_search import ContactSearchToolset


class WorkflowToolFactory(Protocol):
    def build_account_search_toolset(self) -> AccountSearchToolset: ...

    def build_account_research_toolset(self) -> AccountResearchToolset: ...

    def build_contact_search_toolset(self) -> ContactSearchToolset: ...

    def build_google_local_places_search_tool(self) -> GoogleLocalPlacesWebSearchTool: ...

    def build_findymail_contact_enrichment_tool(self) -> FindymailContactEnrichmentTool: ...

    def build_tomba_contact_enrichment_tool(self) -> TombaContactEnrichmentTool: ...

    def build_contact_search_routing_policy(self) -> ContactSearchProviderRoutingPolicy: ...


class Phase3WorkflowToolFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._firecrawl_web_search: FirecrawlWebSearchTool | None = None
        self._google_local_places_search: GoogleLocalPlacesWebSearchTool | None = None
        self._firecrawl_page_fetch: FirecrawlPageFetchTool | None = None
        self._firecrawl_page_scrape: FirecrawlPageScrapeTool | None = None
        self._firecrawl_company_enrichment: FirecrawlCompanyEnrichmentTool | None = None
        self._openai_content_normalizer: OpenAIContentNormalizerTool | None = None
        self._findymail_contact_search: FindymailContactSearchProviderTool | None = None
        self._tomba_contact_search: TombaContactSearchProviderTool | None = None
        self._findymail_contact_enrichment: FindymailContactEnrichmentTool | None = None
        self._tomba_contact_enrichment: TombaContactEnrichmentTool | None = None

    def build_account_search_toolset(self) -> AccountSearchToolset:
        return AccountSearchToolset(
            web_search=self.build_firecrawl_web_search_tool(),
            fallback_web_search=self.build_google_local_places_search_tool(),
            content_normalizer=self.build_openai_content_normalizer_tool(),
            company_enrichment=self.build_firecrawl_company_enrichment_tool(),
        )

    def build_account_research_toolset(self) -> AccountResearchToolset:
        return AccountResearchToolset(
            web_search=self.build_firecrawl_web_search_tool(),
            page_fetch=self.build_firecrawl_page_fetch_tool(),
            page_scrape=self.build_firecrawl_page_scrape_tool(),
            content_normalizer=self.build_openai_content_normalizer_tool(),
            company_enrichment=self.build_firecrawl_company_enrichment_tool(),
        )

    def build_contact_search_toolset(self) -> ContactSearchToolset:
        return ContactSearchToolset(
            web_search=self.build_firecrawl_web_search_tool(),
            content_normalizer=self.build_openai_content_normalizer_tool(),
            provider_search=self.build_findymail_contact_search_tool(),
            fallback_provider_search=self.build_tomba_contact_search_tool(),
            provider_routing_policy=self.build_contact_search_routing_policy(),
            contact_enrichment=self.build_findymail_contact_enrichment_tool(),
        )

    def build_firecrawl_web_search_tool(self) -> FirecrawlWebSearchTool:
        if self._firecrawl_web_search is None:
            self._firecrawl_web_search = FirecrawlWebSearchTool(self._settings.firecrawl)
        return self._firecrawl_web_search

    def build_google_local_places_search_tool(self) -> GoogleLocalPlacesWebSearchTool:
        if self._google_local_places_search is None:
            self._google_local_places_search = GoogleLocalPlacesWebSearchTool(
                self._settings.google_local_places
            )
        return self._google_local_places_search

    def build_firecrawl_page_fetch_tool(self) -> FirecrawlPageFetchTool:
        if self._firecrawl_page_fetch is None:
            self._firecrawl_page_fetch = FirecrawlPageFetchTool(self._settings.firecrawl)
        return self._firecrawl_page_fetch

    def build_firecrawl_page_scrape_tool(self) -> FirecrawlPageScrapeTool:
        if self._firecrawl_page_scrape is None:
            self._firecrawl_page_scrape = FirecrawlPageScrapeTool(self._settings.firecrawl)
        return self._firecrawl_page_scrape

    def build_firecrawl_company_enrichment_tool(self) -> FirecrawlCompanyEnrichmentTool:
        if self._firecrawl_company_enrichment is None:
            self._firecrawl_company_enrichment = FirecrawlCompanyEnrichmentTool(
                self._settings.firecrawl
            )
        return self._firecrawl_company_enrichment

    def build_openai_content_normalizer_tool(self) -> OpenAIContentNormalizerTool:
        if self._openai_content_normalizer is None:
            self._openai_content_normalizer = OpenAIContentNormalizerTool(self._settings.openai)
        return self._openai_content_normalizer

    def build_findymail_contact_enrichment_tool(self) -> FindymailContactEnrichmentTool:
        if self._findymail_contact_enrichment is None:
            self._findymail_contact_enrichment = FindymailContactEnrichmentTool(
                self._settings.findymail
            )
        return self._findymail_contact_enrichment

    def build_findymail_contact_search_tool(self) -> FindymailContactSearchProviderTool:
        if self._findymail_contact_search is None:
            self._findymail_contact_search = FindymailContactSearchProviderTool(
                self._settings.findymail
            )
        return self._findymail_contact_search

    def build_tomba_contact_enrichment_tool(self) -> TombaContactEnrichmentTool:
        if self._tomba_contact_enrichment is None:
            self._tomba_contact_enrichment = TombaContactEnrichmentTool(self._settings.tomba)
        return self._tomba_contact_enrichment

    def build_tomba_contact_search_tool(self) -> TombaContactSearchProviderTool:
        if self._tomba_contact_search is None:
            self._tomba_contact_search = TombaContactSearchProviderTool(self._settings.tomba)
        return self._tomba_contact_search

    def build_contact_search_routing_policy(self) -> ContactSearchProviderRoutingPolicy:
        return ContactSearchProviderRoutingPolicy(
            primary_provider="findymail",
            fallback_provider="tomba",
            routing_basis="phase3_default_findymail_primary",
        )


def build_phase3_tool_factory(settings: Settings | None = None) -> Phase3WorkflowToolFactory:
    return Phase3WorkflowToolFactory(settings or get_settings())
