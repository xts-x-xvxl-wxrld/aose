from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tools.contracts import (
    ContactSearchProviderCandidate,
    ContactSearchProviderResponse,
    ToolSourceReference,
    WebSearchResponse,
)
from app.workflows.contact_search import (
    ContactSearchToolset,
    ContactSearchWorkflow,
    ContactSearchWorkflowInput,
    NullContactEnrichmentTool,
    NullContentNormalizerTool,
    _select_terminal_assistant_summary,
)
from app.workflows.contracts import ContactSearchRunResultOutcome


class _RecordingRunService:
    def __init__(self) -> None:
        self.routing_decisions: list[dict[str, object]] = []
        self.progress_updates: list[str] = []

    async def emit_provider_routing_decision(self, **payload: object) -> None:
        self.routing_decisions.append(payload)

    async def emit_tool_started(self, **payload: object) -> None:
        _ = payload

    async def emit_tool_completed(self, **payload: object) -> None:
        _ = payload

    async def emit_assistant_progress_update(self, **payload: object) -> None:
        content_text = payload.get("content_text")
        if isinstance(content_text, str):
            self.progress_updates.append(content_text)


class _EmptyWebSearchTool:
    async def execute(self, request) -> WebSearchResponse:  # type: ignore[no-untyped-def]
        _ = request
        return WebSearchResponse(results=[])


class _BadResponseProviderSearchTool:
    provider_name = "findymail"

    async def search(self, request) -> ContactSearchProviderResponse:  # type: ignore[no-untyped-def]
        _ = request
        return ContactSearchProviderResponse(
            provider_name=self.provider_name,
            error_code="provider_bad_response",
            errors=["Provider returned an incompatible payload shape."],
        )


class _FallbackProviderSearchTool:
    provider_name = "tomba"

    async def search(self, request) -> ContactSearchProviderResponse:  # type: ignore[no-untyped-def]
        return ContactSearchProviderResponse(
            provider_name=self.provider_name,
            raw_result_summary=f"Retrieved fallback candidates for {request.account_name}.",
            candidates=[
                ContactSearchProviderCandidate(
                    full_name="Jordan Smith",
                    email="jordan@example.com",
                    linkedin_url="https://linkedin.com/in/jordan-smith",
                    job_title="Head of Sales Operations",
                    company_domain="acme-fintech.example",
                    source_provider=self.provider_name,
                    provider_key="jordan@example.com",
                    confidence_0_1=0.74,
                    missing_fields=[],
                    evidence_refs=[
                        ToolSourceReference(
                            provider_name=self.provider_name,
                            source_url="https://tomba.example/jordan-smith",
                            title="Jordan Smith fallback profile",
                        )
                    ],
                )
            ],
        )


@pytest.mark.asyncio
async def test_contact_search_provider_fallback_triggers_on_bad_response() -> None:
    run_service = _RecordingRunService()
    workflow = ContactSearchWorkflow(
        None,  # type: ignore[arg-type]
        run_service=run_service,  # type: ignore[arg-type]
        tools=ContactSearchToolset(
            web_search=_EmptyWebSearchTool(),
            content_normalizer=NullContentNormalizerTool(),
            contact_enrichment=NullContactEnrichmentTool(),
            provider_search=_BadResponseProviderSearchTool(),
            fallback_provider_search=_FallbackProviderSearchTool(),
        ),
    )

    execution = await workflow._run_provider_search(  # type: ignore[attr-defined]
        tenant_id=uuid4(),
        run_id=uuid4(),
        account=SimpleNamespace(
            id=uuid4(),
            name="Acme Fintech",
            domain="acme-fintech.example",
            normalized_domain="acme-fintech.example",
            hq_location="Austin, TX",
        ),
        seller_profile=SimpleNamespace(
            company_name="Acme Seller",
            target_market_summary="US fintech",
        ),
        icp_profile=None,
        workflow_input=ContactSearchWorkflowInput(
            account_id=uuid4(),
            seller_profile_id=uuid4(),
        ),
    )

    assert execution.response is not None
    assert execution.response.provider_name == "tomba"
    assert execution.primary_provider_name == "findymail"
    assert execution.fallback_provider_name == "tomba"
    assert execution.primary_provider_failed is True
    assert execution.fallback_attempted is True
    assert execution.fallback_used is True
    assert any(
        decision.get("trigger_reason") == "provider_bad_response"
        for decision in run_service.routing_decisions
    )
    assert any("backup source now" in update.lower() for update in run_service.progress_updates)


def test_contact_search_terminal_summary_selects_degraded_failure_text() -> None:
    assistant_summary, summary_selection_reason = _select_terminal_assistant_summary(
        outcome=ContactSearchRunResultOutcome.PROVIDER_FAILURE_WITH_FALLBACK_EXHAUSTED,
        contact_count=0,
        reason_summary="No credible contacts were identified.",
    )

    assert "backup source too" in assistant_summary.lower()
    assert "degraded-failure summary" in summary_selection_reason.lower()
