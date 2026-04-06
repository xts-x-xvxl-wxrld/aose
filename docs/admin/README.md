# Admin System

## Purpose

This directory is dedicated to the admin system: platform operations visibility, tenant-scoped operational visibility, runtime agent configuration, telemetry, and admin auditability.

This document records what has been implemented so far and what exists in the admin today.

## What Was Built

### Admin foundations

- Added platform-admin capability on `User` via `is_platform_admin`.
- Extended `/api/v1/me` to return `is_platform_admin`.
- Kept tenant admin authority tied to tenant membership roles `owner` and `admin`.
- Enforced platform and tenant admin access in service-layer permission checks, not just in the frontend.

### Versioned runtime agent configuration

- Added versioned agent config storage with global and tenant scope.
- Added editable runtime-safe fields:
  - `instructions`
  - `system_prompt`
  - `model`
  - `model_settings_json`
  - `feature_flags_json`
  - `change_note`
- Added activation-based rollout instead of in-place mutation.
- Added rollback by re-activating an older version.
- Added audit logging for config create and activation actions.

### Immutable workflow config snapshots

- Added `config_snapshot_json` on workflow runs.
- Runtime now resolves effective agent config at run start.
- Effective precedence is:
  1. active tenant override
  2. active global override
  3. code default
- Each run stores the resolved snapshot so later prompt/config edits do not rewrite history.

### Workflow visibility and recording

- Reused `workflow_runs` and `run_events` as the canonical run timeline.
- Added structured telemetry tables for:
  - `llm_call_logs`
  - `tool_call_logs`
- Recorded tenant, run, thread, agent, workflow, provider/model/tool, status, latency, redacted excerpts, hashes, and metadata.
- Added run-start visibility for resolved config version ids.

### Frontend admin workspace

- Added a real `/admin` route.
- Exposed admin entry from the workspace for platform admins and tenant owners/admins.
- Replaced the stale admin page with a working admin workspace backed by the real API.

## What Exists In The Admin Today

### Platform admin view

Platform admins can access:

- platform overview
- cross-tenant tenant list
- global agent config list
- global config version creation
- audit log access across tenants

### Tenant admin view

Tenant owners and tenant admins can access:

- tenant ops overview
- workflow run list
- workflow run detail
- run event timeline
- LLM telemetry list
- tool telemetry list
- tenant-scoped config versions
- config activation and rollback
- tenant-scoped audit logs

### Config editing behavior

The admin currently supports:

- creating config versions
- activating versions
- rolling back by activating an older version
- viewing global configs
- viewing tenant configs

The current editable fields are:

- instructions
- system prompt
- model
- model settings JSON
- feature flags JSON
- change note

### Runtime behavior

The current runtime uses admin config in:

- account search workflow
- account research workflow
- contact search workflow

Those workflows resolve the recorded run snapshot and pass prompt/model overrides into the provider-backed content normalizer. LLM calls and tool calls are also recorded for admin inspection.

## API Surface

Current admin routes:

- `GET /api/v1/admin/overview`
- `GET /api/v1/admin/tenants`
- `GET /api/v1/admin/tenants/{tenant_id}/ops/overview`
- `GET /api/v1/admin/tenants/{tenant_id}/ops/runs`
- `GET /api/v1/admin/tenants/{tenant_id}/ops/runs/{run_id}`
- `GET /api/v1/admin/tenants/{tenant_id}/ops/runs/{run_id}/events`
- `GET /api/v1/admin/tenants/{tenant_id}/ops/llm-calls`
- `GET /api/v1/admin/tenants/{tenant_id}/ops/tool-calls`
- `GET /api/v1/admin/agent-configs/global`
- `GET /api/v1/admin/tenants/{tenant_id}/agent-configs`
- `POST /api/v1/admin/agent-configs/global/versions`
- `POST /api/v1/admin/tenants/{tenant_id}/agent-configs/versions`
- `POST /api/v1/admin/agent-configs/{version_id}/activate`
- `POST /api/v1/admin/agent-configs/{version_id}/rollback`
- `GET /api/v1/admin/audit-logs`

## Persistence Added

Added or extended persistence for admin/runtime config:

- `users.is_platform_admin`
- `workflow_runs.config_snapshot_json`
- `agent_config_versions`
- `llm_call_logs`
- `tool_call_logs`
- `admin_audit_logs`

The migration for this work is:

- `alembic/versions/0006_admin_runtime_config_and_telemetry.py`

## Main Code Locations

Backend and runtime:

- `src/app/api/v1/endpoints/admin.py`
- `src/app/services/admin_access.py`
- `src/app/services/admin_ops.py`
- `src/app/services/agent_configs.py`
- `src/app/services/workflow_runs.py`
- `src/app/services/runtime_wiring.py`
- `src/app/models/agent_config_version.py`
- `src/app/models/llm_call_log.py`
- `src/app/models/tool_call_log.py`
- `src/app/models/admin_audit_log.py`

Frontend:

- `frontend/src/pages/AdminPage.jsx`
- `frontend/src/lib/api.js`
- `frontend/src/App.jsx`
- `frontend/src/pages/WorkspacePage.jsx`

## Current Limitations

- The frontend does not yet show a richer diff view between code default, global override, and tenant override.
- Platform-admin management for granting or revoking `is_platform_admin` is not exposed in the UI yet.
- Telemetry stores redacted excerpts and hashes, not full raw payload retention.
- The current runtime-config coverage is focused on the provider-backed workflow paths already wired into the system.

## Verification

Verified during implementation with:

- `pytest tests/docs/test_implementation_doc_structure.py -q`
- `pytest tests/test_identity_api.py tests/test_admin_api.py -q`
- `pytest tests/test_identity_api.py tests/test_admin_api.py tests/db/test_agent_config_service.py -q`
- `npm run build` in `frontend`
