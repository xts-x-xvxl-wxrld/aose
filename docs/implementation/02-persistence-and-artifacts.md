# Persistence And Artifacts

## Purpose And Scope

This document defines the canonical persistence model for the current milestone, including database storage, JSONB usage, append-only rules, artifact handling, and markdown policy.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)

## Decision Summary

- Postgres is the operational system of record.
- Alembic owns schema evolution.
- Structured database records are canonical.
- Markdown is a human-readable artifact only.
- Conversation threads, conversation messages, workflow runs, and run events are first-class persisted models in Phase 1.
- Research snapshots are append-only.
- Evidence and artifacts must remain linkable to workflow runs.
- Flexible inputs and outputs may use `JSONB`; identity and ownership fields may not.
- `normalized_result_json` may summarize a workflow outcome, but it does not replace canonical downstream business records.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### Storage Strategy

Use normal columns for:

- primary keys and foreign keys
- tenant and user ownership
- statuses
- timestamps
- stable identity fields
- common filters and join keys

Use `JSONB` for:

- evolving workflow payloads
- provider payload fragments
- normalized result objects that are still being iterated on
- flexible evidence metadata
- artifact render metadata

### Canonical Persistence Models

#### User

- `id`
- `external_auth_subject`
- `email`
- `display_name`
- `status`
- `created_at`
- `updated_at`

#### Tenant

- `id`
- `name`
- `slug`
- `status`
- `created_at`
- `updated_at`

#### TenantMembership

- `id`
- `tenant_id`
- `user_id`
- `role`
- `status`
- `created_at`
- `updated_at`

#### ConversationThread

- `id`
- `tenant_id`
- `created_by_user_id`
- `seller_profile_id`
- `active_workflow`
- `status`
- `current_run_id`
- `summary_text`
- `created_at`
- `updated_at`

Rules:

- `status` is one of `active`, `closed`
- `active_workflow` stores one of the finite workflow types used by the current milestone or `null`
- `current_run_id` points to the latest non-terminal run when one exists; it may be `null` when the thread has no active run
- a thread belongs to exactly one tenant and may accumulate many messages and many workflow runs over time

#### ConversationMessage

- `id`
- `tenant_id`
- `thread_id`
- `run_id`
- `role`
- `message_type`
- `content_text`
- `created_by_user_id`
- `created_at`

Rules:

- `role` is one of `user`, `assistant`, `system`
- `message_type` is one of `user_turn`, `assistant_reply`, `system_note`, `workflow_status`
- `run_id` is `null` for ordinary user turns and may be populated for assistant or system messages produced by a workflow run
- `created_by_user_id` is required for `user_turn` messages and may be `null` for system-generated workflow status messages
- conversation messages are append-only; content is not updated in place after creation

#### WorkflowRun

- `id`
- `tenant_id`
- `thread_id`
- `created_by_user_id`
- `workflow_type`
- `status`
- `status_detail`
- `requested_payload_json`
- `normalized_result_json`
- `error_code`
- `correlation_id`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

Rules:

- `workflow_type` stores one of the finite workflow types used by the current milestone
- `status` stores one of the finite workflow statuses used by the current milestone
- `requested_payload_json` stores the normalized service-level workflow input after validation, not the raw HTTP request body
- `normalized_result_json` stores workflow outcome summary data, identifiers, and lightweight structured result fragments; canonical business outputs must still persist in their owning tables
- `correlation_id` is an optional idempotency and traceability key scoped to the tenant; when present it should be unique within the tenant
- each run belongs to exactly one tenant and one triggering user; `thread_id` may be `null` only for non-conversational workflow entrypoints if later introduced explicitly
- terminal runs set `finished_at`; non-terminal runs leave it `null`

#### RunEvent

- `id`
- `tenant_id`
- `run_id`
- `event_name`
- `payload_json`
- `created_at`

Rules:

- `event_name` stores one of the stable run-event names used by the current milestone
- run events are append-only inspection records and are never updated in place
- `payload_json` stores event-specific structured metadata only; it must not become a shadow canonical store for workflow outputs

#### SellerProfile

- `id`
- `tenant_id`
- `created_by_user_id`
- `updated_by_user_id`
- `name`
- `company_name`
- `company_domain`
- `product_summary`
- `value_proposition`
- `target_market_summary`
- `source_status`
- `profile_json`
- `created_at`
- `updated_at`

#### ICPProfile

- `id`
- `tenant_id`
- `seller_profile_id`
- `created_by_user_id`
- `updated_by_user_id`
- `name`
- `status`
- `criteria_json`
- `exclusions_json`
- `created_at`
- `updated_at`

#### Account

- `id`
- `tenant_id`
- `created_by_user_id`
- `updated_by_user_id`
- `source_workflow_run_id`
- `name`
- `domain`
- `normalized_domain`
- `linkedin_url`
- `hq_location`
- `employee_range`
- `industry`
- `status`
- `fit_summary`
- `fit_signals_json`
- `canonical_data_json`
- `created_at`
- `updated_at`

Rules:

- unique by `tenant_id + normalized_domain` when domain is present
- `normalized_domain` stores the canonical lowercased dedupe key derived from `domain`
- if `domain` is `null`, no domain-based uniqueness rule applies

#### AccountResearchSnapshot

- `id`
- `tenant_id`
- `account_id`
- `workflow_run_id`
- `created_by_user_id`
- `snapshot_version`
- `research_summary`
- `qualification_summary`
- `uncertainty_notes`
- `research_json`
- `created_at`

Rules:

- append-only
- never update a snapshot in place after creation

#### Contact

- `id`
- `tenant_id`
- `account_id`
- `created_by_user_id`
- `updated_by_user_id`
- `full_name`
- `job_title`
- `email`
- `linkedin_url`
- `phone`
- `status`
- `ranking_summary`
- `person_data_json`
- `created_at`
- `updated_at`

#### SourceEvidence

- `id`
- `tenant_id`
- `workflow_run_id`
- `account_id`
- `contact_id`
- `source_type`
- `provider_name`
- `source_url`
- `title`
- `snippet_text`
- `captured_at`
- `freshness_at`
- `confidence_score`
- `metadata_json`
- `created_at`

#### Artifact

- `id`
- `tenant_id`
- `workflow_run_id`
- `created_by_user_id`
- `artifact_type`
- `format`
- `title`
- `content_markdown`
- `content_json`
- `storage_url`
- `created_at`
- `updated_at`

Rules:

- `artifact_type` is one of `research_brief`, `seller_summary`, `icp_summary`, `run_summary`, `review_packet`, `outreach_draft`
- `format` is one of `markdown`, `json`, `external_pointer`
- `markdown` format requires `content_markdown`
- `json` format requires `content_json`
- `external_pointer` format requires `storage_url`
- the field required by `format` is the primary representation; secondary helper representations may exist, but the primary representation must always match `format`

#### ApprovalDecision

- `id`
- `tenant_id`
- `workflow_run_id`
- `artifact_id`
- `reviewed_by_user_id`
- `decision`
- `rationale`
- `reviewed_at`
- `created_at`

Rules:

- `decision` is one of `approved`, `rejected`, `needs_changes`
- `reviewed_at` is the canonical decision timestamp and should match `created_at` in the first implementation

## Data Flow / State Transitions

Persistence flow for workflows:

1. API resolves tenant and actor context
2. service creates or updates `ConversationThread`
3. service creates `ConversationMessage` for user turn
4. service creates `WorkflowRun` if async or reviewable work is needed
5. worker emits `RunEvent` rows during execution
6. workflow stores structured outputs in canonical records
7. workflow optionally emits `Artifact`
8. review process optionally adds `ApprovalDecision`

## Failure Modes And Edge-Case Rules

- If a workflow fails after partial evidence collection, keep collected `SourceEvidence` and mark the `WorkflowRun` as failed.
- If an artifact render fails but canonical structured data exists, workflow may succeed and emit an artifact failure event.
- If duplicate accounts or contacts are detected, merge only into the canonical mutable entity; never mutate historical research snapshots to hide that history.
- If provider payloads are too large, store only required fragments in `JSONB`; do not mirror full provider blobs by default.

## Validation, Ownership, And Permission Rules

- Every model except top-level identity tables must store `tenant_id`.
- `created_by_user_id` is required on all user-created or workflow-triggered business objects.
- Updates must set `updated_by_user_id` when the record is mutable.
- Snapshot tables are append-only and therefore do not use `updated_by_user_id`.
- Artifacts must be readable only within the owning tenant.

## Persistence Impact

This document is the owning spec for persistence shape. Later docs may only reference or refine usage of these models.

## API / Events / Artifact Impact

- workflow and resource APIs must expose only canonical data or artifact pointers
- APIs may return rendered markdown, but that does not replace structured records
- emitted run events should carry ids needed to resolve canonical persisted records

## Implementation Acceptance Criteria

- Every business record mentioned in the workflow docs has a canonical persistence home here.
- Ownership fields are unambiguous for all persisted business records.
- Markdown is explicitly non-canonical.
- Account research snapshots are append-only.
- Evidence remains linkable to runs and downstream outputs.

## Verification

Current automated enforcement for this document lives in:

- Runtime-backed implementation of this document is now present in the Phase 1 persistence slice.
- The current implementation includes SQLAlchemy models, tenant-scoped repositories, and Alembic migration coverage for `ConversationThread`, `ConversationMessage`, `WorkflowRun`, `RunEvent`, `Account`, `AccountResearchSnapshot`, `Contact`, `SourceEvidence`, `Artifact`, and `ApprovalDecision`.
- The current implementation also enforces append-only persistence for conversation messages, run events, research snapshots, and approval decisions, plus database-level constraints for tenant-scoped workflow correlation ids, tenant-scoped normalized account domains, artifact format/content consistency, and approval rationale requirements.

- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_core_business_entities_have_canonical_persistence_models`
- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_workflow_docs_only_reference_defined_persisted_models`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_phase_1_tables_are_registered_in_metadata`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_expected_phase_1_columns_exist`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_phase_1_unique_constraints_and_indexes_exist`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_phase_1_status_and_contract_checks_exist`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_json_fields_use_jsonb`
- [tests/test_model_metadata.py](../../tests/test_model_metadata.py) `::test_phase_1_foreign_keys_match_expected_delete_rules`
- [tests/db/test_repositories.py](../../tests/db/test_repositories.py) `::test_phase_1_workflow_repositories_enforce_tenant_scope_and_append_only_histories`
- [tests/db/test_repositories.py](../../tests/db/test_repositories.py) `::test_phase_1_mutable_repositories_track_updates`
- [tests/db/test_migrations.py](../../tests/db/test_migrations.py) `::test_migration_upgrade_creates_phase_1_tables`
- [tests/db/test_migrations.py](../../tests/db/test_migrations.py) `::test_migration_downgrade_returns_to_base_state`
- [tests/db/test_migrations.py](../../tests/db/test_migrations.py) `::test_migration_constraints_reject_invalid_and_duplicate_rows`

## Deferred Items

- partitioning strategy
- cross-tenant analytics store
- search indexes beyond normal relational indexing
- blob/object storage implementation choice
