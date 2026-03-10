# Known Issues

Global register of confirmed HIGH severity issues identified during code review.
Issues are left open and resolved only when work touches the affected area.
When resolving an issue, update its status and link the fixing commit/PR.

---

## Open Issues

### KI-001: `validate_reasons` not wired to Scorecard ORM
**Severity:** High
**Area:** Data integrity / evidence grounding
**Files:** `api/aose_api/models.py` (`validate_reasons` ~line 236, `Scorecard` ~line 260)
**Detail:** `validate_reasons()` is defined and unit-tested in isolation but is never invoked
when a Scorecard row is inserted or updated. Malformed reason objects (missing `text`,
missing `evidence_ids`, non-list `evidence_ids`) persist silently. This violates the
non-negotiable evidence-grounding invariant: "scorecards and drafts must link claims to
Evidence IDs â€” no free-floating claims."
**Fix when touched:** Add `@validates("fit_reasons_json", "intent_reasons_json")` hook
on the `Scorecard` class that calls `validate_reasons`.
**Status:** Fixed — `Scorecard` now validates `fit_reasons_json`/`intent_reasons_json` via ORM `@validates` hook

---

### KI-002: `validate_channels` not wired to Contact ORM
**Severity:** High
**Area:** Data integrity / contact validation
**Files:** `api/aose_api/models.py` (`validate_channels` ~line 310, `Contact.channels_json` ~line 363)
**Detail:** `validate_channels()` is defined and unit-tested but is never invoked on
Contact insert or update. Channel objects with invalid `validation_level` values for
their channel type (e.g. `profile_exists` on an email channel) persist without any
enforcement at the ORM layer.
**Fix when touched:** Add `@validates("channels_json")` hook on the `Contact` class
that calls `validate_channels`.
**Status:** Fixed — `Contact.channels_json` now validates via ORM `@validates` hook

---

### KI-003: `Account.confidence` has no range check constraint
**Severity:** High
**Area:** Data integrity
**Files:** `api/aose_api/models.py` (`Account` ~line 126), `api/migrations/versions/b4001_create_accounts_account_aliases.py`
**Detail:** `Evidence.confidence` has `ck_evidence_confidence_range` (0.0â€“1.0) and
`Scorecard` has four equivalent constraints, but `Account.confidence` has neither a
`CheckConstraint` in the ORM nor in the b4001 migration. Values outside [0, 1] (e.g.
`2.5`, `-1.0`) persist silently and could corrupt downstream scoring logic.
**Fix when touched:** Add `CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_accounts_confidence_range")` to `Account.__table_args__` and a new Alembic migration to add the constraint.
**Status:** Fixed — added ORM check constraint and migration `h1002` for DB enforcement

---

### KI-004: `OutreachDraft` missing `policy_pack_id`
**Severity:** High
**Area:** Auditability / contract violation
**Files:** `api/aose_api/models.py` (`OutreachDraft` ~line 430), `api/migrations/versions/b8001_create_outreach_drafts_personalization_anchors.py`
**Detail:** The data spine canonical shape (DATA-SPINE-v0.1.md section 4.7) explicitly
includes `policy_pack_id` on every OutreachDraft. It is present on every other audit
record (SellerProfile, Scorecard, ApprovalDecision, SendAttempt) but is absent from
OutreachDraft. Without it there is no way to audit which policy pack governed copy
generation for a given draft.
**Fix when touched:** Add `policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)` to `OutreachDraft`, add a migration to add the column (with `server_default` for existing rows), and include `policy_pack_id` in the b8 test fixtures.
**Status:** Fixed — added non-null `policy_pack_id` to model plus migration `h1002` with backfill-safe default

---

### KI-005: Worker is a bare RQ stub with no organ logic
**Severity:** High
**Area:** Architecture / replay safety / attempt budgets
**Files:** `worker/aose_worker/run_worker.py`
**Detail:** The worker is 19 lines â€” it starts an RQ worker and nothing else. There is
no job handler, no stage router, no attempt budget decrement, and no parking logic.
Per the architecture:
- Failed items must transition to `parked:<reason_code>` (not RQ's default failed queue)
- External calls must decrement `attempt_budget_remaining` before executing and park at zero
- Each stage must write structured events (inputs/outputs/metrics/outcome/error_code)

None of this exists. Any WorkItem that reaches the queue will be processed without
budget enforcement or failure routing.
**Fix when touched:** Implement a stage router that dispatches on `work_item.stage`,
wraps each organ handler in budget-check/decrement logic, and catches failures to
update the WorkItem stage to `parked:<reason_code>` with the appropriate error taxonomy
from DATA-SPINE-v0.1.md section 8.
**Status:** Stale (partially superseded) â€” worker now has stage routing + handler dispatch; re-scope as architecture-hardening follow-up if still needed

---

### KI-006: `AccountAlias.alias_type` has no enum enforcement
**Severity:** Medium
**Area:** Data integrity / contract
**Files:** `api/aose_api/models.py` (`AccountAlias`), `api/aose_api/main.py` (`create_account`)
**Detail:** The contract locks three allowed alias types (`registry`, `domain`,
`legal_name_normalized`). Nothing in the ORM model or API schema rejects other values.
An API caller can store an invented alias type and it will persist silently. The B4 spec
marks model-level validation as optional, so this is in-spec, but the guard test only
checks that the test setup didn't write a bad row â€” it does not prove the DB rejects one.
**Fix when touched:** Add a Pydantic `Literal` type or `@validates` on `alias_type` when
the alias type set is considered stable.
**Status:** Fixed — account/contact alias types now fail closed via API schema validation, ORM validators, and DB CHECK constraints

---

### KI-007: `create_account` uses lazy loading for alias serialization
**Severity:** Low
**Area:** API fragility
**Files:** `api/aose_api/main.py` (`create_account`)
**Detail:** After `session.refresh(account)`, `account.aliases` is not eagerly loaded.
The response serializes correctly because `get_session` keeps the session open for the
full request lifecycle. If the endpoint is ever refactored to close the session before
response serialization (async context, background task), `account.aliases` would silently
return an empty list rather than erroring.
**Fix when touched:** Add `selectinload(Account.aliases)` to the query on the POST
response path.
**Status:** Fixed — `create_account` now returns an eagerly loaded `Account` via `selectinload(Account.aliases)`

---

### KI-008: Duplicate `scorecards` assertion in test_account.py
**Severity:** Low
**Area:** Test noise
**Files:** `api/tests/test_account.py`
**Detail:** `test_no_evidence_scorecard_tables_from_b4` and the immediately following
`test_no_scorecard_table` both assert `"scorecards" not in tables`. Redundant but harmless.
**Fix when touched:** Collapse into one test or remove the duplicate assertion.
**Status:** Stale â€” duplicate assertion no longer present in current `api/tests/test_account.py`

---

### KI-009: Misleading test name in test_evidence.py
**Severity:** Low
**Area:** Test documentation
**Files:** `api/tests/test_evidence.py::test_none_and_empty_string_snippet_produce_same_id`
**Detail:** The test name says "differ" but the assertion is `assert eid_none == eid_empty`.
The assertion is correct â€” `None` is normalised to `""` before hashing so both produce
the same `evidence_id` â€” but the name states the opposite of the actual behaviour.
**Fix when touched:** Rename to `test_none_and_empty_string_snippet_produce_same_id`.
**Status:** Fixed — test renamed to match asserted behavior (`None` and `""` produce the same ID)

---

### KI-010: Evidence replay test hits SQLAlchemy identity map, not DB constraint
**Severity:** Low
**Area:** Test correctness
**Files:** `api/tests/test_evidence.py::test_replay_same_evidence_id_is_no_op`
**Detail:** The test adds a second `Evidence` with the same PK to the same open session.
SQLAlchemy raises a session-level identity map conflict (`SAWarning`) before the insert
reaches Postgres. The test passes but does not prove DB-level PK enforcement â€” it proves
SQLAlchemy's in-memory deduplication. All other replay tests in the suite correctly use
a second `Session` to hit the real DB constraint.
**Fix when touched:** Open a second `Session` for the second insert attempt.
**Status:** Fixed — replay test now uses a second SQLAlchemy `Session` to hit DB-level PK enforcement

---

### KI-011: `Account` and `Contact` have no `created_at` field
**Severity:** Medium
**Area:** Audit trail / data spine consistency
**Files:** `api/aose_api/models.py` (`Account` ~line 126, `Contact` ~line 352),
`api/migrations/versions/b4001_create_accounts_account_aliases.py`,
`api/migrations/versions/b7001_create_contacts_contact_aliases.py`
**Detail:** Every other canonical record has `created_at` (WorkItem, EvidenceContent,
SellerProfile, OutreachDraft, SendAttempt). Account and Contact do not, making it
impossible to audit when a record was first persisted. Inconsistent with the design
pattern across the rest of the data spine.
**Fix when touched:** Add `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)` to both models and a migration to add the columns.
**Status:** Fixed — added server-defaulted `created_at` columns to `accounts` and `contacts` via model + migration

---

### KI-012: `ApprovalDecision` has `decided_at` but no `created_at`
**Severity:** Medium
**Area:** Audit trail
**Files:** `api/aose_api/models.py` (`ApprovalDecision` ~line 506),
`api/migrations/versions/b9001_create_approval_decisions_send_attempts.py`
**Detail:** `decided_at` captures when the human/operator made the decision; `created_at`
would capture when the record was written to the DB. Without it, clock-skew between
decision time and storage time is undetectable, and the record is the only table in the
system without a system-insertion timestamp.
**Fix when touched:** Add `created_at` to the model and a migration.
**Status:** Fixed — added server-defaulted `created_at` to `approval_decisions` while preserving `decided_at` as event time

---

### KI-013: JSONB columns missing `Mapped[...]` type annotations
**Severity:** Medium
**Area:** Type safety / tooling
**Files:** `api/aose_api/models.py` â€” `Scorecard.fit_reasons_json`,
`Scorecard.intent_reasons_json`, `ApprovalDecision.overridden_gates_json`,
`OutreachDraft.risk_flags_json`, `PersonalizationAnchor.evidence_ids_json`,
`SellerProfile.offer_where/offer_who/offer_positioning/constraints_*`, etc.
**Detail:** SQLAlchemy 2.x declarative style requires `Mapped[T]` annotations for all
mapped columns. These JSONB columns use bare `mapped_column(JSONB, ...)` without
`Mapped[...]`, so mypy/pyright cannot type-check their usage and IDE autocomplete is
absent. Not a runtime bug in current CPython but a maintenance and tooling gap that will
compound as the models grow.
**Fix when touched:** Add `Mapped[list]` or `Mapped[dict]` annotations to all untyped
JSONB columns in the affected model.
**Status:** Fixed — JSON/JSONB mapped columns now use explicit `Mapped[...]` annotations across affected models

---

### KI-014: Epic F score scale mismatch (`0..100` contract vs `0..1` persisted)
**Severity:** High
**Area:** Contract compliance / scoring correctness
**Files:** `worker/aose_worker/handlers/intent_fit_scoring.py` (`_upsert_scorecard` score normalization), `api/aose_api/models.py` (`Scorecard` score constraints/mapped types)
**Detail:** Epic F locks fit/intent score scale to integer `0..100`, but the current
`intent_fit_scoring` handler divides by `100.0` before persistence to satisfy existing
`Scorecard` DB constraints (`0.0..1.0`). This stores a different scale than the Epic F
contract and creates semantic drift between scoring logic and persisted canonical record.
**Fix when touched:** Migrate `scorecards.fit_score` and `scorecards.intent_score` to
integer `0..100` contract shape, update ORM/check constraints, remove `/100.0` conversion
from worker writes, and backfill existing rows deterministically.
**Status:** Fixed — scorecards now persist integer `0..100` scores with migration-backed conversion from legacy `0..1` rows

---

### KI-015: Evidence category resolution likely drops valid scoring evidence
**Severity:** High
**Area:** Scoring input resolution / deterministic behavior
**Files:** `worker/aose_worker/services/intent_fit_scoring_service.py` (`resolve_evidence_category`), `worker/aose_worker/handlers/intent_fit_scoring.py` (`_resolve_used_evidence`), `worker/aose_worker/services/account_discovery_service.py` (`_write_evidence`)
**Detail:** F1 evidence filtering expects `provenance_json["category"]`, but current
discovery evidence writes do not populate a category field. As a result, valid account
evidence may be filtered out as unscoreable, producing empty or degraded evidence snapshots
and non-representative scorecard inputs.
**Fix when touched:** Persist canonical evidence category at write time (or derive from
stable existing fields), then align scoring resolver to that canonical source with tests
proving non-empty expected evidence selection.
**Status:** Fixed — evidence now stores canonical `category` at write time and scoring/gates read that canonical field first

---

### KI-016: Scorecard reason invariants still not fully enforced across write paths
**Severity:** High
**Area:** Data integrity / evidence grounding
**Files:** `api/aose_api/models.py` (`validate_reasons`, `Scorecard`), `worker/aose_worker/services/intent_fit_scoring_service.py` (`validate_reasons`)
**Detail:** Worker-side Epic F validation requires `code`, `text`, and non-empty
`evidence_ids` referencing existing evidence IDs, but ORM-level `validate_reasons`
still accepts weaker shape and is not wired to `Scorecard` insert/update hooks.
Non-worker write paths can persist malformed or weakly-grounded reason objects.
**Fix when touched:** Wire `@validates("fit_reasons_json", "intent_reasons_json")` on
`Scorecard`, strengthen model-level validation to Epic F invariant shape, and keep one
shared validator surface to avoid divergence.
**Status:** Fixed — API/ORM and worker now share the strict Epic F reason validator; ORM writes fail closed on missing evidence grounding

---

### KI-017: Missing handler-level/integration coverage for Epic F1 acceptance paths
**Severity:** Medium
**Area:** Test coverage / replay safety
**Files:** `worker/tests/test_intent_fit_scoring_service.py`, `worker/tests/test_intent_fit_scoring_handler.py`, `worker/aose_worker/handlers/intent_fit_scoring.py`
**Detail:** Current tests cover pure helper determinism, but not handler-level behavior:
contract-error parking, DB upsert replay/no-duplicate semantics, and evidence-set change
effects on snapshot/hash at execution level. This leaves high-risk integration behavior
unchecked.
**Fix when touched:** Add handler/integration tests that execute the full stage flow
against Postgres fixtures and assert: `parked:contract_error` routing, one-scorecard
upsert semantics under replay, and snapshot/hash changes when consumed evidence changes.
**Status:** Fixed — added `worker/tests/test_intent_fit_scoring_handler.py` covering contract-error parking, replay upsert semantics, and evidence snapshot/hash change behavior

---

### KI-018: `sending_dispatch` structured event refs can leak PII via `draft_id`/`send_id`
**Severity:** High
**Area:** Privacy / structured-event redaction
**Files:** `worker/aose_worker/handlers/sending_dispatch.py`, `worker/tests/test_sending_dispatch.py`
**Detail:** SPEC-I1 requires redacted structured events with no full email/phone/message
body. The handler currently writes `draft_id` and `send_id` into event refs on multiple
paths. Since `draft_id` embeds `contact_id`, and `contact_id` may embed normalized email,
this can leak PII into structured events.
**Fix when touched:** Remove raw `draft_id`/`send_id` from event refs (or replace with
redacted/hashed surrogates) and add tests that assert structured event payloads never
contain raw email-like identifiers.
**Status:** Fixed â€” handler refs are redacted and covered by `worker/tests/test_sending_dispatch.py::test_handler_refs_remain_redacted_no_raw_email_patterns`

---

### KI-019: `sending_dispatch` does not enforce cross-record linkage integrity
**Severity:** High
**Area:** Contract compliance / data integrity
**Files:** `worker/aose_worker/handlers/sending_dispatch.py`
**Detail:** The handler loads `OutreachDraft`, `ApprovalDecision`, `Contact`, and
`Account`, but does not validate required links between them (for example:
`approval_decisions.draft_id == payload.draft_id` / loaded draft, and
`contacts.account_id == outreach_drafts.account_id`). This allows inconsistent record
sets to pass precondition loading despite SPEC-I1 linked-record requirements.
**Fix when touched:** Add explicit linkage checks after loads and fail closed with
deterministic `contract_error` when links do not match.
**Status:** Fixed â€” handler enforces draft/approval/contact/account linkage checks with contract-error fail-closed routing

---

### KI-020: `sending_dispatch` does not explicitly enforce STOP-gate override rejection
**Severity:** Medium
**Area:** Policy contract enforcement
**Files:** `worker/aose_worker/handlers/sending_dispatch.py`
**Detail:** SPEC-I1 requires "no STOP-gate override behavior." Current approval loading
does not fetch override fields and no explicit check rejects override payloads. The
behavior is therefore implicit rather than contract-enforced.
**Fix when touched:** Load `overridden_gates_json` from `approval_decisions` and reject
any non-empty override set with deterministic fail-closed routing.
**Status:** Fixed â€” handler loads `overridden_gates_json` and rejects override payloads with deterministic fail-closed routing

---

### KI-021: Missing SPEC-I1 tests for key fail-closed edge cases
**Severity:** Medium
**Area:** Test coverage
**Files:** `worker/tests/test_sending_dispatch.py`
**Detail:** Current tests cover disabled send, missing draft/approval, and payload
contract checks, but do not cover missing `Contact`, missing `Account`, missing required
approval review fields, or STOP-gate override rejection. This leaves critical fail-closed
paths unverified.
**Fix when touched:** Add integration tests for those four scenarios and assert expected
terminal event type/error codes.
**Status:** Fixed â€” tests now cover missing Contact/Account, missing required approval fields, and override rejection paths

---

## Resolved Issues

### KI-R1: `Scorecard` missing `policy_pack_id` (was BR-N1)
**Resolved in:** migration `b10001`, models.py update
**Detail:** Added `policy_pack_id` field to `Scorecard` ORM model and b10001 migration.

### KI-R2: `work_items.idempotency_key` lacked unique constraint (was BR-N2)
**Resolved in:** migration `b10001`, `WorkItem.__table_args__` update
**Detail:** Added `UniqueConstraint("idempotency_key", name="uq_work_items_idempotency_key")` to ORM and b10001 migration.

### KI-R3: `validate_anchor_evidence_ids` never invoked (was BR-N3)
**Resolved in:** models.py `PersonalizationAnchor`
**Detail:** Added `@validates("evidence_ids_json")` hook that calls `validate_anchor_evidence_ids` on every insert/update.


