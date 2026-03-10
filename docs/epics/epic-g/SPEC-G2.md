md
# docs/epics/epic-g/spec-g2.md

# G2. Manual contact import

## Goal

Implement manual CSV import as the first working entry path for contacts, producing canonical `Contact` and `ContactAlias` records from a strict, replay-safe CSV contract.

## Scope boundary

### In scope
- CSV upload or ingestion endpoint or admin action
- Row validation
- Canonicalization
- Alias upsert
- Defaults for manual provenance
- Import summary
- Deterministic replay behavior

### Out of scope
- Heuristic row repair
- Free-form spreadsheet guessing
- Fuzzy account lookup
- Third identity fallback
- Mailbox verification
- Provider-verified automation
- Human-verified automation

CSV rows that do not match the contract are rejected or parked. They are not silently coerced.

## Contract touchpoints

### Canonical records
- `Account`
- `Contact`
- `ContactAlias`

### Stages
This spec may create contacts directly from a UI or admin import flow and then enqueue `contact_enrichment` work items, or it may route through `people_search` with `source_mode=manual_csv`.

Either way, downstream work must honor `contact_enrichment` payload version `1`.

## Deliverables
- `api/manual_imports/contacts.py` or equivalent import endpoint or service
- CSV parser and schema validator
- Import result model or summary object
- Canonical contact upsert service reuse from G1
- Tests for row rejection, deterministic defaults, replay, and downstream enqueue behavior
- Optional small UI or upload action if the project already has admin screens

## CSV contract

### Required columns
- `account_id`
- `full_name`

### One-of required column sets
- `email`
- `linkedin_url`

### Optional columns
- `role_title`
- `role_cluster`
- `role_confidence`
- `source_provider`
- `source_ref`
- `observed_at`
- `confidence`

### Forbidden rows
- Missing `account_id`
- Missing `full_name`
- Missing both `email` and `linkedin_url`
- Unknown `account_id`

### Defaults
- `source_provider = "MANUAL_CSV"`
- `source_ref = "csv_row:<row_number>"`
- `observed_at = import_timestamp`

## Row mapping
- `account_id -> account_id`
- `full_name -> full_name`
- `role_title -> role.title`
- `role_cluster -> role.cluster`
- `role_confidence -> role.confidence`
- `email -> email channel value`
- `linkedin_url -> linkedin alias value`

## Import behavior
1. Validate header set before processing rows.
2. For each row, verify referenced `account_id` exists. Unknown accounts are rejected as contract failures.
3. Apply Epic B normalization to email and LinkedIn.
4. Reject row when both normalized identities are null.
5. Build deterministic provenance fields using explicit row defaults where omitted.
6. Use the same canonical `contact_id` precedence as G1.
7. Upsert `Contact` and `ContactAlias` idempotently.
8. On replay of the same file or same logical row, produce no duplicates.
9. Emit a per-import summary:
   - `rows_total`
   - `rows_accepted`
   - `rows_rejected`
   - `contacts_created`
   - `contacts_updated`
   - `aliases_created`
   - `parked_count`
10. Enqueue `contact_enrichment` once per surviving contact unless an equivalent pending or enqueued work item already exists under the locked idempotency rule.

## Error and parking rules
- Unknown account → reject row and mark `contract_error`
- Missing identity after normalization → reject row and mark `contract_error`
- Ambiguous role or title with no LinkedIn URL → accept contact creation if identity exists, but park downstream as `parked:needs_human`
- Import-level schema mismatch → fail import before row processing
- Do not silently create placeholder accounts
- Do not silently invent provider refs or timestamps beyond the locked defaults

## Acceptance checks
- Uploading a valid CSV with one row per contact produces canonical `Contact` and `ContactAlias` rows
- Replaying the identical CSV produces zero duplicate contacts and zero duplicate aliases
- Row with unknown `account_id` is rejected
- Row with both email and LinkedIn missing is rejected
- Omitted source metadata falls back to `MANUAL_CSV`, `csv_row:<n>`, and import timestamp
- Accepted rows enqueue `contact_enrichment` exactly once per surviving canonical contact
- Import summary counts are deterministic on replay