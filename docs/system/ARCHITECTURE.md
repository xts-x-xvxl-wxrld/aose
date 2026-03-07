# ARCHITECTURE.md — System Overview

## System purpose

AOSE (AI Outbound Support Engine) automates the research and outreach pipeline for a B2B seller. It discovers target accounts, scores their fit and intent, finds contacts, generates evidence-grounded outreach drafts, routes them through human approval, and sends them — with sending gated behind a feature flag.

---

## Service topology

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Compose                       │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │ postgres │    │  redis   │    │       api        │  │
│  │  :5432   │    │  :6379   │    │  FastAPI :8000   │  │
│  └──────────┘    └──────────┘    │  GET /healthz    │  │
│       ▲               ▲          └────────┬─────────┘  │
│       │               │                   │             │
│       │          ┌────┴─────────────────┐ │             │
│       └──────────┤       worker         ├─┘             │
│                  │  RQ consumer         │               │
│                  │  organ stage router  │               │
│                  └──────────────────────┘               │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  web  (stub — no dev server yet)  :5173          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Data flow

```
 Seller input
     │
     ▼
┌─────────────────────┐
│  seller_profile_build│  Builds SellerProfile record in Postgres
└────────┬────────────┘
         │ enqueue WorkItem
         ▼
┌─────────────────────────┐
│  query_objects_generate  │  Creates QueryObject records
└────────┬────────────────┘
         │ enqueue WorkItem (one per QueryObject)
         ▼
┌─────────────────────┐
│  account_discovery   │  Discovers Account candidates via adapters
│                      │  Writes Account + Evidence records
└────────┬────────────┘
         │ enqueue WorkItem (one per candidate)
         ▼
┌─────────────────────┐
│  intent_fit_scoring  │  Reads Account + Evidence
│                      │  Writes Scorecard (fit + intent, evidence-linked)
└────────┬────────────┘
         │ enqueue WorkItem (if score passes threshold)
         ▼
┌─────────────────────┐
│  people_search       │  Finds ContactCandidates for the Account
│                      │  Writes Contact records
└────────┬────────────┘
         │ enqueue WorkItem (one per contact)
         ▼
┌─────────────────────┐
│  contact_enrichment  │  Validates contact channels (email: domain_ok minimum)
└────────┬────────────┘
         │ enqueue WorkItem
         ▼
┌─────────────────────┐
│  copy_generate       │  Generates OutreachDraft with personalization anchors
│                      │  Each anchor references Evidence IDs (no free claims)
└────────┬────────────┘
         │ enqueue WorkItem
         ▼
┌─────────────────────┐
│  approval_request    │  Parks draft for human review
│                      │  Writes ApprovalDecision on response
└────────┬────────────┘
         │ enqueue WorkItem (if approved)
         ▼
┌─────────────────────┐
│  sending_dispatch    │  Creates SendAttempt record
│                      │  GATED: SEND_ENABLED=false → park, no side effects
└─────────────────────┘
```

---

## Queue mechanics

- **Transport:** Redis (RQ)
- **Envelope:** Every job payload is a `WorkItem` (see `docs/data-spine/DATA-SPINE-v0.1.md` §2)
- **Routing:** Worker reads `WorkItem.stage` and dispatches to the correct organ handler
- **Replay safety:** `idempotency_key` on side-effect tables; reprocessing is a no-op or deterministic overwrite
- **Budget:** `attempt_budget.remaining` decremented on each external call; organ parks at zero

---

## Persistence model

```
PostgreSQL (canonical system of record)
├── work_items          — queue envelope + audit trail
├── seller_profiles     — SellerProfile
├── query_objects       — QueryObject
├── accounts            — Account + aliases
├── evidence            — Evidence (pointer-first)
├── evidence_content    — EvidenceContent (full extract, optional)
├── scorecards          — Scorecard (fit + intent, evidence-linked)
├── contacts            — Contact + aliases + channel validation
├── drafts              — OutreachDraft + personalization anchors
├── approval_decisions  — ApprovalDecision (explicit state transition)
├── send_attempts       — SendAttempt (highest-risk side effect)
└── structured_events   — StructuredEvent (redacted audit trail)

Redis (transient)
└── rq:queue:default    — WorkItem payloads in flight
```

Unique indexes required on: `work_items.idempotency_key`, `send_attempts.idempotency_key`, all canonical IDs.

---

## Canonical ID format

```
seller:<slug>
account:<country>-<registry_id>            (preferred)
account:<normalized_domain>                (fallback)
contact:<account_id>:<normalized_email>    (preferred)
evidence:<hash(source_type+url+captured_at+snippet_hash)>
score:<entity_ref>:<date_or_hash>
draft:<contact_id>:<sequence_id>:<variant>
decision:<draft_id>:<timestamp_or_hash>
send:<draft_id>:<channel>
```

---

## Governance gates (safe_v0_1 defaults)

Each gate returns `PASS | REVIEW | STOP`.

Hard STOPs include: missing domain + no registry ID, free email domains for send, suppression hit, any cap exceeded, `SEND_ENABLED=false`.

PolicyPack `safe_v0_1` controls all caps, thresholds, and send enablement. Referenced via `policy_pack_id` on every WorkItem and output record.

---

## Error taxonomy

| Code | Behaviour |
|------|-----------|
| `contract_error` | Park immediately, no retries |
| `transient_error` | Retry while budget remains |
| `budget_exhausted` | Park with reason |
| `no_signal` | Park with reason |
| `policy_blocked` | Park with flags (STOP gates are not overridable) |
| `needs_human` | Park into review lane |

---

## Current implementation status (Epic A complete)

| Layer | Status |
|-------|--------|
| Repo structure + Docker Compose | Done |
| API scaffold (`/healthz`) | Done |
| Worker scaffold (RQ bootstrap) | Done |
| CI (lint + format + test) | Done |
| DB schema (Data Spine tables) | Not yet — Epic B |
| Organ handlers | Not yet — Epic B+ |
| Web UI | Stub only — future epic |
| Send provider | Placeholder PH-001 |
