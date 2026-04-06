# Service Worker And Tool Boundaries

## Purpose And Scope

This document defines what belongs in agents, services, workers, tools, repositories, and connectors for the current milestone.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [03-orchestrator-and-run-contracts.md](./03-orchestrator-and-run-contracts.md)
- [04-api-auth-and-request-context.md](./04-api-auth-and-request-context.md)

## Decision Summary

- Agents reason.
- Services coordinate.
- Workers execute long-running workflows.
- Tools perform narrow actions.
- The first-pass tool catalog is explicit even before provider-specific implementations are complete.
- Repositories persist and retrieve.
- Connectors wrap vendor-specific integrations.
- The chat-first runtime split is `ConversationService`, `WorkflowRunService`, a thin `OrchestratorAdapter`, and `WorkflowExecutor`.
- `ConversationService` owns streamed chat-turn acceptance, tenant-scoped thread lookup, idempotent first-turn handling, and `OrchestratorInput` construction.
- Phase 1 workflow execution starts by creating a `queued` run and dispatching it immediately to an in-process executor entrypoint.
- Tool inputs and outputs use typed Python request and response contracts even when implementations are still stubs.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### Agents

Allowed responsibilities:

- interpret context
- choose strategy
- generate search angles
- compare account data to seller and ICP context
- rank or qualify noisy candidates

Forbidden responsibilities:

- direct DB reads and writes
- raw HTTP request handling
- bypassing tenant checks
- silent fabrication of missing evidence

### Services

Allowed responsibilities:

- accept or resume streamed chat turns
- build orchestrator input
- validate tenant and actor access
- resolve idempotent retry state for chat turns
- create and inspect workflow runs
- invoke agents
- validate structured outputs
- persist canonical records
- create artifacts
- handle review flows

Phase 1 concrete service split:

- `ConversationService` owns thread entry, tenant-member thread access, user-turn persistence, idempotent `X-Request-ID` handling, and `OrchestratorInput` construction
- `WorkflowRunService` owns run creation, run inspection, event emission, and executor dispatch
- `OrchestratorAdapter` is a thin contract that turns `OrchestratorInput` into `OrchestratorDecision`

### Workers

Allowed responsibilities:

- execute `WorkflowRun` units
- carry tenant and actor context through async execution
- emit `RunEvent`
- stop on cancellation

First-pass worker strategy:

- queue abstraction exists
- in-process implementation is used first
- Redis-backed or external queue implementation is deferred
- `WorkflowExecutor.dispatch(...)` is the Phase 1 executor entrypoint
- `InProcessWorkflowExecutor` is the default Phase 1 implementation

### Tools

First-pass tool catalog:

#### `web_search`

- purpose: find candidate public-web sources and provider search hits
- inputs: normalized query text, optional freshness hint, result limit
- outputs: ranked result records with title, url, snippet, and provider metadata
- common failures: provider unavailable, rate limited, zero relevant results

#### `page_fetch`

- purpose: fetch raw page content or provider documents for later parsing
- inputs: url or provider document reference
- outputs: status code or provider status, raw body or document bytes, content type, fetch metadata
- common failures: timeout, blocked fetch, unsupported content type

#### `page_scrape`

- purpose: extract structured or normalized text content from fetched pages
- inputs: fetched page content plus extraction hints when relevant
- outputs: normalized text, extracted headings, links, and lightweight metadata
- common failures: extraction ambiguity, unusable markup, insufficient content

#### `company_enrichment`

- purpose: resolve normalized company attributes from a provider or trusted source
- inputs: company name, domain, or provider key
- outputs: normalized company profile fragments and source references
- common failures: ambiguous company match, no match, provider quota issues

#### `contact_enrichment`

- purpose: resolve normalized person/contact attributes for a known account
- inputs: account identifiers plus contact name, title, or provider key
- outputs: normalized contact fragments and source references
- common failures: ambiguous person match, missing contact data, provider quota issues

#### `content_normalizer`

- purpose: convert noisy provider or scraped payloads into workflow-ready normalized structures
- inputs: raw provider fragments or extracted page content
- outputs: normalized dict or list payloads suitable for service validation
- common failures: missing required fields, unsupported payload shape

Phase 1 tool contract names:

- `WebSearchRequest` and `WebSearchResponse`
- `PageFetchRequest` and `PageFetchResponse`
- `PageScrapeRequest` and `PageScrapeResponse`
- `CompanyEnrichmentRequest` and `CompanyEnrichmentResponse`
- `ContactEnrichmentRequest` and `ContactEnrichmentResponse`
- `ContentNormalizerRequest` and `ContentNormalizerResponse`

Allowed responsibilities:

- web search
- page fetch
- page scrape
- provider enrichment calls
- deterministic parsing helpers

Forbidden responsibilities:

- persistence
- workflow lifecycle changes
- permission decisions
- direct run status transitions outside service/worker coordination

### Tool Access Matrix

Workflow-to-tool usage rules:

- seller and ICP setup do not require external tools by default
- account search may call `web_search`, `page_fetch`, `page_scrape`, `company_enrichment`, and `content_normalizer`
- account research may call `web_search`, `page_fetch`, `page_scrape`, `company_enrichment`, and `content_normalizer`
- contact search may call `web_search`, `page_fetch`, `page_scrape`, `contact_enrichment`, and `content_normalizer`
- the orchestrator chooses workflows and agents but does not call provider-specific tools directly in Phase 1

### Repositories

Repository responsibilities:

- tenant-scoped record retrieval
- persistence of canonical records
- dedupe support queries
- snapshot insertion

### Connectors

Connector responsibilities:

- vendor auth
- HTTP client wrappers
- provider-specific request/response translation
- retries and vendor-specific error interpretation

Connector versus tool rule:

- connectors speak vendor-specific protocols
- tools expose workflow-facing operations built on top of one or more connectors
- services and workers call tools, not raw connectors, unless a connector is being adapted into a tool implementation

## Data Flow / State Transitions

Workflow execution shape:

1. API passes `RequestContext` to a service
2. `ConversationService` validates tenant access, resolves chat-turn idempotency from `request_id`, and loads or creates required thread state
3. `ConversationService` builds `OrchestratorInput` when orchestration is required
4. `OrchestratorAdapter` returns a typed decision
5. request-time services translate the typed decision into durable records plus chat-facing stream frames
6. `WorkflowRunService` creates a `queued` run when workflow execution is required
7. `WorkflowRunService` hands the queued run to `WorkflowExecutor.dispatch(...)`
8. worker loads workflow context
9. worker invokes specialist agent where reasoning is needed
10. worker invokes tools and connectors for external data
11. service/repository logic validates and persists outputs

## Failure Modes And Edge-Case Rules

- If a provider is unavailable, workers may fail the run or preserve partial evidence depending on workflow stage.
- If an agent returns unstructured or invalid output, the service owns validation failure handling.
- If a tool returns ambiguous data, do not silently promote it to canonical business records without validation and normalization.
- If a tool returns provider-specific payloads that the workflow cannot normalize confidently, treat the call as incomplete rather than fabricating structured output.
- If tenant context is missing at worker startup, fail the run immediately.
- If a first streamed turn is retried with the same `(tenant_id, user_id, request_id)` after durable commit, `ConversationService` must resume from existing durable state instead of creating a duplicate thread.
- If stream delivery fails after durable persistence, route-layer recovery must come from persisted thread, message, run, and run-event state rather than executor-local memory.

## Validation, Ownership, And Permission Rules

- services own authorization-adjacent checks
- services own chat-turn idempotency and thread-visibility enforcement
- repositories never infer tenant from record ids alone; tenant must be explicit in read and write operations
- tools never decide whether a user is allowed to act
- workers must carry `tenant_id` and `created_by_user_id` from the run
- workers and executors do not own request-level SSE framing or request-id deduplication
- tool execution metadata must be recorded in stable run events without storing unnecessary raw provider blobs

## Persistence Impact

Services and repositories own persistence. Agents, tools, and connectors do not write canonical records directly.
- The durable user-turn record is the persistence boundary for chat-turn idempotency keyed by tenant, acting user, and request id.

## API / Events / Artifact Impact

- worker lifecycle emits stable run events
- services may create artifacts after canonical persistence succeeds
- API route behavior remains thin and delegates to services
- request-time services may translate canonical decisions into SSE text and meta frames; executors do not emit route-facing transport frames directly
- `tool.started` payloads should include `tool_name`, `provider_name` when relevant, `input_summary`, and a correlation key
- `tool.completed` payloads should include `tool_name`, `provider_name` when relevant, `output_summary`, `error_code` when present, and whether evidence-bearing results were produced

## Implementation Acceptance Criteria

- no agent, tool, or connector writes directly to the DB
- all async workflows preserve tenant and actor context
- service boundaries are explicit enough to test without invoking external providers
- the first-pass tool catalog is concrete enough to implement without re-deciding names and responsibilities
- the runtime split between streamed chat entry, run lifecycle, orchestration adapter, and executor dispatch is fixed for Phase 1
- idempotent first-turn handling and chat stream projection ownership are assigned to request-time services rather than workers or tools

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_service_boundary_doc_forbids_direct_persistence_outside_services`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_service_boundary_doc_freezes_phase_1_runtime_interfaces`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_service_boundary_doc_assigns_chat_idempotency_and_stream_projection_to_services`
- [tests/test_agent_contracts.py](../../tests/test_agent_contracts.py) `::test_skeleton_agents_keep_no_fabrication_guardrails_in_instructions`

## Deferred Items

- saga orchestration
- distributed worker locking
- multi-step retries with compensating actions
