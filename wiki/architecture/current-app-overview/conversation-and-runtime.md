---
title: Current App Overview - Conversation and Runtime
category: spec
agent: Codex
date: 2026-04-07
status: reference
sources:
  - frontend/src/workspace/hooks/useChat.js
  - frontend/src/lib/sse.js
  - backend/src/app/api/v1/endpoints/chat.py
  - backend/src/app/services/chat_orchestrator.py
  - backend/src/app/services/conversation.py
  - backend/src/app/services/chat_event_projection.py
  - backend/src/app/services/runtime_wiring.py
  - backend/src/app/workers/runtime.py
  - backend/src/app/orchestration/contracts.py
---

# Current App Overview - Conversation and Runtime

## Summary

The chat surface is backed by a durable conversation service plus an in-process workflow executor. A chat turn can either produce an inline reply or launch one of the three main workflow types, and the user sees both assistant text and structured progress events.

See also [[Current App Overview - Domain Model]], [[Current App Overview - Account Search]], [[Current App Overview - Account Research]], and [[Current App Overview - Contact Search]].

## Transport Model

The canonical chat entrypoint is:

- `POST /api/v1/tenants/{tenant_id}/chat/stream`

The frontend submits:

- user message
- optional thread id
- pinned seller/ICP/account/contact ids
- current active workflow

The backend responds as SSE with:

- text frames for assistant content
- meta frames for projected run events
- a final `[DONE]` frame

The frontend then rehydrates thread state from the durable read APIs rather than trusting only the streamed frames.

## Thread Lifecycle

The conversation service handles:

- new thread creation
- reuse of an existing thread
- persistence of user and assistant messages
- durable thread summary state
- lookup of the current run for the thread

This makes the chat experience resumable. When the frontend remembers a thread id for a tenant, it can fetch the thread, messages, and events back from the backend on reload.

## Orchestration Model

The current orchestrator is rules-based. It does not use a model to interpret user intent. Instead, it classifies turns into:

- inline response
- start account search
- start account research
- start contact search

It also blocks unsafe or ambiguous execution by checking required context before launching a run.

Examples of enforced workflow requirements:

- account search requires seller profile plus ICP
- account research requires seller profile plus selected account
- contact search requires seller profile plus selected account

If required context is missing, the assistant replies with a clarification instead of guessing.

## Runtime Wiring

The app starts an in-process workflow executor at FastAPI startup. That executor registers handlers for:

- `account_search`
- `account_research`
- `contact_search`

When the orchestrator decides to start a workflow run, the conversation service creates the run, links it to the thread, and dispatches it through the executor.

## Event and Status Projection

Workflows emit durable run events such as:

- `run.started`
- `agent.handoff`
- `tool.started`
- `tool.completed`
- `run.awaiting_review`
- `run.completed`
- `run.failed`

The chat event projection service then maps those durable run events into the compact meta event stream used by the frontend sidebar and post-turn refresh flows.

## Current Runtime Shape

This is a durable workflow runtime, not a long freeform conversation loop. The chat system is optimized to:

- normalize user requests into workflow-safe execution
- keep one clear run lifecycle per thread state
- preserve inspectable execution artifacts
- feed visible progress back into the same conversation surface

That is why the current product feels structured and operational rather than open-ended.
