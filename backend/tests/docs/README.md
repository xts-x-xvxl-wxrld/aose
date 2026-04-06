# Implementation Verification Suite

This directory holds the first-pass verification suite for the implementation docs.

The goal at this stage is not to pretend the whole product is already built. Instead, the suite gives us two lightweight safety rails:

- doc verification tests that keep the implementation spec internally consistent
- smoke tests that prove the current FastAPI and agent skeleton still boot with the documented public surface

## Current Coverage

The tests in this folder currently validate:

- implementation docs are numbered and ordered from `00` through `11`
- child docs keep the shared section template defined by the orchestrator doc
- dependency links only point backward to earlier implementation docs
- core business entities in the ownership doc have canonical persistence homes
- workflow and evidence docs only reference persisted models defined in the persistence doc
- orchestrator workflow types, statuses, transitions, and event names stay explicit and finite
- API route groups keep tenant-scoped routes explicit
- service boundary rules continue to forbid direct persistence in agents and tools
- seller/ICP, account search, account research, contact search, and evidence docs keep their current acceptance criteria stable
- deferred RAG remains optional and non-blocking for the current milestone

## Smoke Coverage Outside This Folder

The companion smoke tests in `tests/` currently validate:

- app boot succeeds
- the current OpenAPI schema is exposed
- the health and agents routes remain available
- the agent registry and skeleton guardrails remain stable enough for inspection

## How To Run

Run the full suite with:

```bash
pytest -q
```

Run only the implementation-doc checks with:

```bash
pytest -q tests/docs
```

## Extension Rule

As each workflow becomes real code, move its strongest guarantees out of doc-only tests and into executable feature tests for services, repositories, workers, and API routes. Doc verification should stay focused on contract integrity and milestone boundaries.
