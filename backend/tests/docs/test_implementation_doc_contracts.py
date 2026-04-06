from tests.docs.helpers import (
    extract_backticked_model_names,
    extract_list_after_label,
    extract_persistence_models,
    extract_route_groups,
    get_doc,
    get_section_body,
    get_section_bullets,
)

ALLOWED_NON_TENANT_ROUTE_PATHS = {
    "/api/v1/healthz",
    "/api/v1/agents",
    "/api/v1/me",
    "/api/v1/tenants",
}


def test_core_business_entities_have_canonical_persistence_models() -> None:
    ownership_doc = get_doc("01")
    persistence_doc = get_doc("02")

    core_entities = set(get_section_bullets(ownership_doc, "Core Business Entities", level=3))
    persistence_models = extract_persistence_models(persistence_doc)

    assert core_entities <= persistence_models


def test_workflow_docs_only_reference_defined_persisted_models() -> None:
    persistence_models = extract_persistence_models(get_doc("02"))

    for doc_id in ["07", "08", "09", "10"]:
        doc = get_doc(doc_id)
        referenced_models = extract_backticked_model_names(doc)

        assert referenced_models <= persistence_models, (
            f"{doc.path.name} references models that do not exist in the persistence spec: "
            f"{sorted(referenced_models - persistence_models)}"
        )


def test_orchestrator_contract_lists_stable_workflow_status_and_event_values() -> None:
    orchestrator_doc = get_doc("03")

    workflow_types = get_section_bullets(orchestrator_doc, "Workflow Types", level=3)
    workflow_status_body = get_section_body(orchestrator_doc, "WorkflowRun Statuses", level=3)
    allowed_statuses = extract_list_after_label(workflow_status_body, "Allowed statuses:")
    allowed_transitions = extract_list_after_label(workflow_status_body, "Transition rules:")
    allowed_events = get_section_bullets(orchestrator_doc, "Run Events", level=3)

    assert workflow_types == [
        "seller_profile_setup",
        "icp_profile_setup",
        "account_search",
        "account_research",
        "contact_search",
    ]
    assert allowed_statuses == [
        "queued",
        "running",
        "awaiting_review",
        "succeeded",
        "failed",
        "cancelled",
    ]
    assert allowed_transitions == [
        "queued -> running",
        "running -> awaiting_review",
        "running -> succeeded",
        "running -> failed",
        "running -> cancelled",
        "awaiting_review -> succeeded",
        "awaiting_review -> failed",
        "awaiting_review -> cancelled",
    ]
    assert allowed_events == [
        "run.started",
        "agent.handoff",
        "agent.completed",
        "tool.started",
        "tool.completed",
        "run.awaiting_review",
        "run.completed",
        "run.failed",
    ]


def test_orchestrator_doc_freezes_chat_stream_contract_and_active_workflow_semantics() -> None:
    orchestrator_doc = get_doc("03")
    decision_summary = get_section_body(orchestrator_doc, "Decision Summary")
    request_body = get_section_body(orchestrator_doc, "ChatTurnStreamRequest", level=3)
    framing_body = get_section_body(orchestrator_doc, "Chat Stream Framing", level=3)
    orchestrator_input_body = get_section_body(orchestrator_doc, "OrchestratorInput", level=3)

    assert "POST /api/v1/tenants/{tenant_id}/chat/stream" in decision_summary
    assert "streaming is the primary chat transport" in decision_summary.lower()
    assert "active_workflow" in request_body
    assert "selected_account_id" in request_body
    assert "selected_contact_id" in request_body
    assert 'data: {"text":"<chunk>","thread_id":"<uuid>"}' in framing_body
    assert "data: [DONE]" in framing_body
    assert "current-turn normalization hint" in orchestrator_input_body


def test_api_route_groups_keep_tenant_scoping_explicit() -> None:
    api_doc = get_doc("04")
    routes = extract_route_groups(api_doc)

    assert routes, "API doc must enumerate route groups"

    for _method, path in routes:
        if path in ALLOWED_NON_TENANT_ROUTE_PATHS:
            continue
        assert path.startswith("/api/v1/tenants/{tenant_id}/"), (
            f"Tenant-scoped path must carry explicit tenant context: {path}"
        )


def test_api_doc_freezes_chat_route_inventory_and_alias_policy() -> None:
    api_doc = get_doc("04")
    routes = extract_route_groups(api_doc)
    route_paths = {path for _method, path in routes}
    decision_summary = get_section_body(api_doc, "Decision Summary")
    validation_body = get_section_body(api_doc, "Validation, Ownership, And Permission Rules")
    failure_modes = get_section_body(api_doc, "Failure Modes And Edge-Case Rules")

    assert "/api/v1/tenants/{tenant_id}/chat/stream" in route_paths
    assert "/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}" in route_paths
    assert "/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages" in route_paths
    assert "/api/v1/tenants/{tenant_id}/chat/events" not in route_paths
    assert "/api/v1/tenants/{tenant_id}/conversations" not in route_paths
    assert "transitional compatibility aliases" in decision_summary
    assert "visible to all active tenant members" in validation_body
    assert "must not create a duplicate thread" in failure_modes


def test_service_boundary_doc_forbids_direct_persistence_outside_services() -> None:
    boundary_doc = get_doc("05")
    agent_forbidden = get_section_bullets(boundary_doc, "Agents", level=3)
    tool_forbidden = get_section_bullets(boundary_doc, "Tools", level=3)
    persistence_impact = get_section_body(boundary_doc, "Persistence Impact")

    assert "direct DB reads and writes" in agent_forbidden
    assert "persistence" in tool_forbidden
    assert "do not write canonical records directly" in persistence_impact


def test_service_boundary_doc_freezes_phase_1_runtime_interfaces() -> None:
    boundary_doc = get_doc("05")
    decision_summary = get_section_body(boundary_doc, "Decision Summary")
    services_body = get_section_body(boundary_doc, "Services", level=3)
    workers_body = get_section_body(boundary_doc, "Workers", level=3)
    tools_body = get_section_body(boundary_doc, "Tools", level=3)

    assert "ConversationService" in decision_summary
    assert "WorkflowRunService" in decision_summary
    assert "WorkflowExecutor" in decision_summary
    assert "ConversationService" in services_body
    assert "WorkflowRunService" in services_body
    assert "OrchestratorAdapter" in services_body
    assert "WorkflowExecutor.dispatch(...)" in workers_body
    assert "InProcessWorkflowExecutor" in workers_body
    assert "WebSearchRequest" in tools_body
    assert "ContentNormalizerResponse" in tools_body


def test_service_boundary_doc_assigns_chat_idempotency_and_stream_projection_to_services() -> None:
    boundary_doc = get_doc("05")
    decision_summary = get_section_body(boundary_doc, "Decision Summary")
    services_body = get_section_body(boundary_doc, "Services", level=3)
    validation_body = get_section_body(boundary_doc, "Validation, Ownership, And Permission Rules")
    api_impact = get_section_body(boundary_doc, "API / Events / Artifact Impact")

    assert "streamed chat-turn acceptance" in decision_summary
    assert "idempotent `X-Request-ID` handling" in services_body
    assert "chat-turn idempotency" in validation_body
    assert "SSE text and meta frames" in api_impact


def test_setup_doc_freezes_inline_mode_and_explicit_icp_selection() -> None:
    setup_doc = get_doc("06")
    decision_summary = get_section_body(setup_doc, "Decision Summary")
    failure_modes = get_section_body(setup_doc, "Failure Modes And Edge-Case Rules")
    api_impact = get_section_body(setup_doc, "API / Events / Artifact Impact")

    assert "inline-only" in decision_summary
    assert "explicit `icp_profile_id`" in decision_summary
    assert "explicit `icp_profile_id`" in failure_modes
    assert "do not create `WorkflowRun` rows in Phase 1" in api_impact


def test_account_search_doc_freezes_result_shape_merge_policy_and_iteration_limit() -> None:
    search_doc = get_doc("07")
    result_body = get_section_body(search_doc, "Account Search Run Result", level=3)
    failure_modes = get_section_body(search_doc, "Failure Modes And Edge-Case Rules")
    iterative_body = get_section_body(search_doc, "Data Flow / State Transitions")

    assert "accepted_account_ids" in result_body
    assert "outcome = no_results" in result_body
    assert "search_attempt_count" in result_body
    assert "at most 2 completed search/refine cycles per run" in iterative_body
    assert "preserve existing canonical field values" in failure_modes


def test_account_research_doc_freezes_optional_icp_result_shape_and_versioning() -> None:
    research_doc = get_doc("08")
    decision_summary = get_section_body(research_doc, "Decision Summary")
    result_body = get_section_body(research_doc, "Account Research Run Result", level=3)
    failure_modes = get_section_body(research_doc, "Failure Modes And Edge-Case Rules")

    assert "may run without an ICP" in decision_summary
    assert "icp_context_present" in result_body
    assert "omit unsupported ICP-fit claims" in result_body
    assert "latest persisted version plus one" in failure_modes


def test_contact_search_doc_freezes_dedupe_precedence_and_missing_data_flags() -> None:
    contact_doc = get_doc("09")
    decision_summary = get_section_body(contact_doc, "Decision Summary")
    flags = get_section_bullets(contact_doc, "Missing Data Flags", level=3)
    result_body = get_section_body(contact_doc, "Contact Search Run Result", level=3)
    failure_modes = get_section_body(contact_doc, "Failure Modes And Edge-Case Rules")

    assert "optional in Phase 1" in decision_summary
    assert flags == [
        "missing_email",
        "missing_linkedin",
        "missing_job_title",
        "low_source_confidence",
        "role_match_uncertain",
    ]
    assert "used_research_snapshot_id" in result_body
    assert "exact email match" in failure_modes
    assert "exact LinkedIn URL" in failure_modes
    assert "not enough for automatic merge" in failure_modes


def test_rag_stays_optional_and_deferred_for_the_current_milestone() -> None:
    rag_doc = get_doc("11")
    decision_summary = get_section_bullets(rag_doc, "Decision Summary")
    acceptance_checks = get_section_bullets(rag_doc, "Implementation Acceptance Criteria")
    persistence_impact = get_section_body(rag_doc, "Persistence Impact")

    assert "RAG is not part of the first implementation milestone." in decision_summary
    assert (
        "RAG must not replace live search, live research, or provider enrichment."
        in decision_summary
    )
    assert (
        "The current implementation must not require vector infrastructure "
        "to complete current milestone workflows."
        in persistence_impact
    )
    assert acceptance_checks == [
        "no implementation step depends on RAG",
        "docs clearly state where RAG could help later",
        "docs clearly forbid using RAG as a replacement for live account and contact evidence",
    ]
