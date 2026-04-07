# Dev-Facing Debugging And Observability

## Purpose And Scope

- Record what the Phase 4 debug and observability layer now provides.
- Separate implemented debugging surfaces from smaller follow-up gaps.

## Implemented

### Debug Surface

- The repo now exposes a developer-facing debug endpoint:
  - `GET /api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug`
- That surface is backed by durable workflow state rather than ad hoc logs.
- The debug bundle currently includes:
  - `workflow_run_id`
  - `thread_id`
  - `workflow_type`
  - `workflow_status`
  - `requested_payload_json`
  - `normalized_result_json`
  - `provider_attempts`
  - `fallback_decisions`
  - `reasoning_validation`
  - `user_summary_snapshot`
  - `terminal_outcome_family`
  - `summary_selection_reason`

### Provider Attempt Inspection

- Provider attempts are derived from persisted run events.
- The current attempt records expose:
  - `provider_name`
  - `tool_name`
  - `operation`
  - `attempt_number`
  - `request_summary`
  - `outcome`
  - `error_code`
  - `output_summary`
  - `failure_summary`
  - `produced_evidence_results`

### Fallback Inspection

- Fallback decisions are already durable and queryable.
- The current fallback records expose:
  - `capability`
  - `from_provider`
  - `to_provider`
  - `fallback_provider`
  - `trigger_reason`
  - `routing_basis`
  - `allowed`
  - `decision_summary`

### Reasoning Inspection

- Reasoning validation is already surfaced in the debug bundle.
- This includes both:
  - `reasoning.validated`
  - `reasoning.failed_validation`
- That now applies to:
  - account-search candidate reasoning
  - account-search query planning
  - account-research synthesis
  - contact-search ranking

## Fixed From The Original Phase 4 Plan

- The debug endpoint is no longer hypothetical.
- Terminal outcome family and summary-selection provenance are no longer implicit.
- Fallback provenance no longer requires terminal logs or manual replay.

## Still Open

- `tool.failed` exists in the event contract and debug service, but the workflow implementations still mostly record failures through `tool.completed` with `error_code`.
- Dedicated `fallback.invoked` and `fallback.completed` events are still not part of the active workflow event stream.
- Dedicated `user_message.selected` summary-selection events are also still absent.
- Provider attempts do not yet include:
  - `http_status`
  - `duration_ms`

### Still Open In Standard Inspection

- Standard run debug does not yet expose planner/output telemetry at the same fidelity as admin `llm_calls` and `tool_calls`.
- Some smoke investigations still require jumping from the normal debug endpoint to admin inspection to explain:
  - LLM planning output
  - compatibility retries
  - provider-call details
- Successful runs with provider degradation are visible in telemetry, but that degraded provenance is not yet a first-class summarized concept in the standard debug bundle.

## Recommendation

- Keep the current debug bundle contract stable.
- Treat richer event taxonomy and attempt-level HTTP/timing detail as incremental observability work, not as blockers for current workflow operation.
