# docs/epics/epic-g/spec-g4.md

# G4. Deterministic caps and runaway prevention

## Goal

Enforce the Epic G caps and budget behavior so people discovery and enrichment remain bounded, deterministic, and replay-safe.

Cap enforcement is contract-level, not optional tuning.

## Scope boundary

### In scope
- Cap checks
- Deterministic survivor selection
- Provider-count accounting
- Retry exhaustion handling
- Budget-based parking
- Per-run accounting hooks
- Tests proving no runaway expansion

### Out of scope
- Dynamic optimization
- Probabilistic sampling
- Adaptive rankers
- Provider-selection heuristics
- Any expansion beyond the configured cap surfaces

## Contract touchpoints

### Policy pack caps
- `max_contacts_total_per_run = 60`
- `max_contacts_per_account = 3`
- `max_enrich_attempts_per_contact = 2`
- `max_providers_per_contact = 2`
- `max_drafts_per_contact = 2`

These are authoritative defaults under `safe_v0_1`.

Epic G specifically relies on the per-account and per-contact limits for contacts and enrichment.

## Deliverables
- Cap enforcement helpers usable by both `people_search` and `contact_enrichment`
- Deterministic ranking or survivor selector for candidate contacts
- Provider-attempt accounting per contact
- Tests for caps on contact creation, enrichment retries, and provider count
- Structured event fields for cap-triggered parking

## Enforcement rules

### 1. Contacts per account
After normalization and dedup, keep only the highest-confidence surviving contacts per account, up to `max_contacts_per_account`.

Deterministic sort order:
1. Higher `confidence`
2. Higher `role_confidence`
3. Candidate with normalized email over LinkedIn-only candidate
4. Lexicographic tie-break on `contact_id`

Candidates beyond the cap must not be persisted once the cap is reached.

Park the work item as `parked:budget_exhausted`.

This keeps the result stable across replays and parallel execution.

### 2. Total contacts per run
Maintain run-level accounting so `max_contacts_total_per_run` is not exceeded across all accounts in the run.

Once reached, subsequent contact creation attempts must stop and the relevant work items park as `parked:budget_exhausted`.

### 3. Enrichment attempts per contact
Retry transient enrichment failures only while the total attempt count for that contact remains below `max_enrich_attempts_per_contact`.

Once the cap is hit, park as `parked:budget_exhausted`.

Contract errors do not retry.

### 4. Providers per contact
Do not query or apply more than `max_providers_per_contact` across people search plus enrichment for a single contact.

If the current contact has already consumed the provider budget, stop and park as `parked:budget_exhausted`.

Provider identity remains stable placeholder IDs only.

Do not add vendor-specific selection logic in Epic G.

### 5. Idempotent accounting
Cap counters must be replay-safe:
- Replay of the same work item must not double-count created contacts
- Retry of a transient failure increments only on meaningful attempt boundaries
- Already-persisted canonical contacts count as existing survivors, not new creations
- Downstream `contact_enrichment` work items must not duplicate when contact already exists and equivalent work key exists

## Parking semantics

Use only locked parked reasons:
- `parked:budget_exhausted`
- `parked:no_signal`
- `parked:needs_human`
- `parked:policy_blocked`

Use locked error taxonomy:
- `budget_exhausted`
- `transient_error`
- `contract_error`
- `policy_blocked`
- `needs_human`
- `no_signal`

## Acceptance checks
- People search returning five valid candidates for one account persists exactly three deterministic survivors
- Replay of that same work item persists the same three survivors and no additional aliases or work items
- Enrichment transient failure retries at most twice, then parks
- A third provider path for the same contact is refused and parked
- Total run cap of sixty contacts is respected across accounts
- Budget-triggered events show deterministic reason codes and counters
- No cap is bypassed by switching from manual CSV to adapter mode
