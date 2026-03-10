# docs/epics/epic-g/spec-g1.md

# G1. PeopleSearch adapter interface

## Goal

Define a stable `PeopleSearchAdapter` contract that produces replay-safe `ContactCandidate` outputs with required provenance, normalized identity inputs, and deterministic downstream routing into canonical `Contact` and `ContactAlias` records.

## Scope boundary

### In scope
- Adapter interface
- Candidate schema
- Normalization entry rules
- Deterministic canonicalization
- Provenance requirements
- Worker-stage input/output contract for `people_search`

### Out of scope
- Provider-specific scraping logic
- Mailbox probing
- Provider-verified email checks
- Human-verified automation
- Heuristic merge logic beyond canonical ID plus alias rules
- Any third fallback identity beyond normalized email or normalized LinkedIn URL

## Contract touchpoints

### Canonical records
- `Contact`
- `ContactAlias`
- Optional provider-attributed channel metadata on `Contact.channels[]`
- Structured events from Epic C

### Stages
Consumes `people_search` with payload version `1`.

Produces:
- `contact_enrichment` with payload version `1`
- `parked:no_signal`
- `parked:budget_exhausted`
- `parked:needs_human`
- `parked:policy_blocked`

Stage payloads remain versioned and routing must stay deterministic.

## Deliverables
- `worker/people_search/interfaces.py` defining `PeopleSearchAdapter`
- `worker/people_search/types.py` defining `ContactCandidate`
- `worker/people_search/service.py` for candidate normalization, canonical contact creation, alias upsert, and work-item fanout
- Tests covering replay, dedup, invalid candidates, and parking behavior
- Module manifest entry for the `people_search` organ

## Required interface

```python
class PeopleSearchAdapter(Protocol):
    def search_people(
        self,
        account_id: str,
        role_targets: list[str] | None = None,
    ) -> list[ContactCandidate]:
        ...
ContactCandidate contract
Required fields

account_id

full_name

provenance

At least one identity field

email

linkedin_url

Optional fields

role_title

role_cluster

role_confidence

source_provider

source_ref

observed_at

confidence

Provenance requirements

source_provider

source_ref

observed_at

Validation rules

Reject candidate if account_id does not match the consuming work item

Reject candidate if both email and linkedin_url normalize to null

Reject candidate if provider confidence exists and is outside 0.0..1.0

Do not persist candidate-only rows; persist only canonical Contact and ContactAlias outputs after normalization and dedup

No adapter may create provider-specific canonical enums or provider-specific statuses

Deterministic processing rules

Normalize email using the Epic B email normalization rules.

Normalize LinkedIn URL using the Epic B LinkedIn normalization rules.

Compute contact_id by precedence only:

contact:<account_id>:<normalized_email>

contact:<account_id>:<sha256(normalized_linkedin_url)>

If neither normalized identity exists, do not create a canonical contact. Route to parked:needs_human with contract_error.

Upsert aliases only from the locked alias set:

email_normalized

linkedin_url_normalized

Create or update Contact idempotently on contact_id.

Create or update ContactAlias idempotently on (account_id, alias_type, alias_value).

Reprocessing identical adapter output must be a no-op or deterministic overwrite, never duplicate creation.

Persist source trace fields on every provider-derived field:

source_provider

source_ref

observed_at

confidence

Role handling rules
Allowed role clusters

economic_buyer

influencer

gatekeeper

referrer

If role or title is ambiguous and no LinkedIn URL exists, route the item to parked:needs_human.

Do not invent role clusters outside the locked set.

Worker behavior

For one people_search work item:

Read account_id and optional role_targets, adapter_plan, source_mode

Call one configured adapter path at a time

Normalize and dedup candidates

Persist only surviving canonical contacts

Enqueue exactly one contact_enrichment work item per surviving contact with payload {v: 1, contact_id: ...}

If no surviving contacts remain, park as parked:no_signal

If policy or budget blocks execution, park with the contract stage reason

Emit structured events without raw email addresses in logs or events; use contact_id or redacted fragments only

Acceptance checks

Dummy adapter returning two identical candidates with the same normalized email creates one Contact

Identical replay of the same people_search work item creates no duplicate Contact, ContactAlias, or downstream work items

Candidate with neither email nor LinkedIn normalized value is rejected and parked deterministically

Candidate with invalid confidence less than 0 or greater than 1 fails contract validation

Candidate with ambiguous role and no LinkedIn URL routes to parked:needs_human

Successful run emits one contact_enrichment work item per surviving contact

Structured events contain IDs and counters, not full email strings