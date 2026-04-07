# Deferred RAG And Future Extensions

## Purpose And Scope

This document defines the boundaries for deferred RAG work and other future extensions so the current implementation does not overbuild or misuse them.

## Dependencies On Earlier Docs

- [00-implementation-orchestrator.md](./00-implementation-orchestrator.md)
- [01-core-domain-and-ownership.md](./01-core-domain-and-ownership.md)
- [02-persistence-and-artifacts.md](./02-persistence-and-artifacts.md)
- [10-evidence-approval-and-artifacts.md](./10-evidence-approval-and-artifacts.md)

## Decision Summary

- RAG is not part of the first implementation milestone.
- When introduced later, RAG will support workflows with tenant-scoped internal knowledge.
- RAG must not replace live search, live research, or provider enrichment.
- Outreach generation is deferred.

## Canonical Models / Types / Interfaces Introduced Or Consumed

### Future RAG Models

Potential later models:

- `KnowledgeDocument`
- `KnowledgeChunk`
- `KnowledgeSyncJob`

Expected concepts:

- tenant ownership
- source document metadata
- chunk text
- embedding metadata
- sync state

## Data Flow / State Transitions

Deferred future RAG flow:

1. tenant uploads or syncs stable knowledge assets
2. ingestion job stores document metadata
3. chunking and embedding pipeline creates retrievable chunks
4. later workflows retrieve tenant-scoped chunks as supporting context

## Failure Modes And Edge-Case Rules

- stale retrieved context must not override fresher live evidence
- retrieval without attribution is not acceptable
- cross-tenant retrieval leakage is unacceptable
- RAG should not be used to fabricate current company research

## Validation, Ownership, And Permission Rules

- all future RAG records must be tenant-scoped
- ingestion permissions should be limited to users who can manage seller and tenant knowledge assets
- retrieved chunks must include source references

## Persistence Impact

RAG persistence is deferred. The current implementation must not require vector infrastructure to complete current milestone workflows.

## API / Events / Artifact Impact

Future APIs may include:

- tenant knowledge document upload
- ingestion job inspection
- retrieval debug endpoints

These are explicitly deferred.

## Implementation Acceptance Criteria

For the current milestone:

- no implementation step depends on RAG
- docs clearly state where RAG could help later
- docs clearly forbid using RAG as a replacement for live account and contact evidence

## Verification

Current automated enforcement for this document lives in:

- [tests/docs/test_implementation_doc_contracts.py](../../tests/docs/test_implementation_doc_contracts.py) `::test_rag_stays_optional_and_deferred_for_the_current_milestone`
- [tests/docs/test_implementation_doc_structure.py](../../tests/docs/test_implementation_doc_structure.py) `::test_child_doc_dependencies_only_point_to_existing_earlier_docs`

## Deferred Items

- tenant knowledge ingestion pipeline
- vector database choice
- prompt-time retrieval policies
- outreach generation workflow
- outreach approval flow
