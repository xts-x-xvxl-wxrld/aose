---
title: Current App Overview - Domain Model
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - backend/src/app/models/conversation_thread.py
  - backend/src/app/models/conversation_message.py
  - backend/src/app/models/workflow_run.py
  - backend/src/app/models/run_event.py
  - backend/src/app/models/source_evidence.py
  - backend/src/app/models/artifact.py
  - backend/src/app/models/approval_decision.py
  - backend/src/app/models/tenant.py
  - backend/src/app/models/tenant_membership.py
  - wiki/specs/backend-domain/01-core-domain-and-ownership.md
  - wiki/specs/backend-domain/02-persistence-and-artifacts.md
---

# Current App Overview - Domain Model

## Summary

The app stores chat, workflow execution, evidence, artifacts, and review state as durable tenant-scoped records. The key design choice is that the chat interface is backed by business entities rather than a transient conversation log.

See also [[Current App Overview - Conversation and Runtime]] and [[Current App Overview - Review and Approvals]].

## Ownership Foundation

Every important business record belongs to exactly one tenant. User-attributable records also keep actor ids so the system can answer:

- which tenant owns this record
- which user created or reviewed it
- which workflow run produced it

The base ownership entities are:

- `User`
- `Tenant`
- `TenantMembership`

## Conversation Entities

The core chat persistence model is:

- `ConversationThread`
- `ConversationMessage`

`ConversationThread` stores long-lived thread state such as:

- `tenant_id`
- `created_by_user_id`
- `seller_profile_id`
- `active_workflow`
- `current_run_id`
- `summary_text`
- `context_json`

`ConversationMessage` stores the actual user and assistant turns, optionally linked back to a workflow run.

## Workflow Entities

The execution model centers on `WorkflowRun`. It captures:

- tenant and actor ownership
- linked thread
- workflow type
- run status and status detail
- normalized requested payload
- frozen config snapshot
- normalized result payload
- terminal error code when relevant

That record is the durable center of execution state. Everything else around runtime observability and review hangs off it.

`RunEvent` stores the immutable event timeline for a run, including milestones like:

- run started
- agent handoff
- tool started/completed
- run awaiting review
- run completed
- run failed

## Evidence and Output Entities

The main output-bearing entities are:

- `SourceEvidence`
- `Artifact`
- `ApprovalDecision`

`SourceEvidence` stores captured provider/public-source references, snippets, confidence signals, and optional links to accounts or contacts.

`Artifact` stores user-visible outputs such as:

- research briefs
- run summaries
- review packets
- externally stored pointers

`ApprovalDecision` records review outcomes against a run and optionally a specific artifact.

## Domain Records Produced by Workflows

The workflows also persist business records that become reusable workspace state:

- `SellerProfile`
- `ICPProfile`
- `Account`
- `AccountResearchSnapshot`
- `Contact`

This is why the data browser and chat can reinforce each other. Workflows do not only emit text; they also grow the tenant's durable business dataset.

## Relationship Pattern

The important relationship chain is:

tenant -> thread -> workflow run -> run events / evidence / artifacts / approvals

And, depending on workflow type:

workflow run -> accounts
workflow run -> research snapshots
workflow run -> contacts

This structure is what makes the current product feel more like an operator console or workflow system than a plain chat assistant.
