---
title: Current App Overview - Admin Ops and Runtime Config
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - frontend/src/pages/AdminPage.jsx
  - backend/src/app/api/v1/endpoints/admin.py
  - backend/src/app/services/admin_ops.py
  - backend/src/app/services/agent_configs.py
  - backend/src/app/services/runtime_wiring.py
  - backend/src/app/models/agent_config_version.py
  - backend/src/app/models/llm_call_log.py
  - backend/src/app/models/tool_call_log.py
  - backend/src/app/models/admin_audit_log.py
  - wiki/specs/admin-system/README.md
---

# Current App Overview - Admin Ops and Runtime Config

## Summary

The admin system is a real part of the current product. It provides operations visibility across workflow runs and also exposes runtime agent configuration as versioned, activatable state.

See also [[Current App Overview - Providers and Tools]] and [[Current App Overview - Review and Approvals]].

## Admin Surface

The `/admin` route supports two scopes of visibility:

- platform-admin scope
  cross-tenant metrics and tenant list
- tenant-admin scope
  tenant run history, telemetry, config versions, and audit logs

The current frontend already exposes this as a working admin workspace rather than a placeholder page.

## Telemetry and Run Visibility

The admin backend exposes:

- platform overview
- tenant overview
- workflow run list
- workflow run detail
- run event timeline
- LLM call logs
- tool call logs
- audit logs

This makes the runtime inspectable at the run level, tool level, and prompt/config level.

## Runtime Agent Config Versions

The system stores versioned config rows in `agent_config_versions`. Editable override fields include:

- instructions
- system prompt
- model
- model settings json
- feature flags json
- change note

Activation is version-based. There is no in-place mutation of the active config row.

## Config Precedence

Effective runtime config is resolved in this order:

1. code default
2. active global override
3. active tenant override

At workflow start, the resolved configuration is frozen into the run’s `config_snapshot_json`. This is important because it preserves historical truth even if prompts or models change later.

## Operational Importance

This is one of the most mature subsystems in the app because it ties together:

- runtime visibility
- prompt/config governance
- auditability
- historical reproducibility of runs

That combination is central to operating provider-backed workflows safely in a tenant-scoped product.
