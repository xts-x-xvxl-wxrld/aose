KI-014 — canonical score scale

Persist Scorecard.fit_score and Scorecard.intent_score as integer 0..100. That is the better canonical choice now. The decisive reason is that your operational policy already thinks in 0..100: fit thresholds are pass_gte: 75, review_gte: 65, and the default rubric is explicitly 0–100. The older spine example that shows 0.78 / 0.32 should be treated as an outdated illustrative example, not the authority.

Backfill rule should be deterministic and fail-closed: if stored value is within [0.0, 1.0], convert with one explicit rule such as round_half_up(value * 100); if the stored value is already an integer-like 0..100, keep it; otherwise mark the row invalid for manual review or recomputation rather than guessing. Remove the worker’s /100.0 normalization and change DB/model constraints to 0 <= score <= 100. Compatibility window should be short: one release of dual-read, single-write is enough. After migration, write only 0..100 and reject fractional writes.

KI-015 — evidence category resolution

The canonical source should be a write-time stored field on Evidence, not deterministic derivation at read/scoring time. The allowed set should be exactly:

firmographic

persona_fit

trigger

technographic

Use deterministic derivation only as an ingestion helper or one-time backfill mechanism, not as the long-term source of truth. The canonical field should be stored on write, validated against the locked set, and used by scoring and gates directly. Rows that cannot be categorized deterministically from stable existing fields should not silently default; they should remain uncategorized and fail category-dependent progression until repaired. That keeps evidence-gate behavior auditable and stable.

KI-016 — reason invariants

Require the stricter Epic F reason shape on all new write paths immediately. The clean decision is: for scorecards, the canonical reason object is now:

{code, text, evidence_ids[]}

evidence_ids must be non-empty and resolvable to existing evidence rows. Reject weaker new writes.

Do not broadly auto-normalize legacy/weaker rows because that invents semantics you do not actually have. Allow only lossless normalization for legacy data, such as trimming strings, deduping/sorting evidence_ids, or converting scalar-to-list when the meaning is unambiguous. Any row missing real evidence grounding or missing a meaningful code should be quarantined or recomputed, not “fixed” heuristically. Also document explicitly that Epic F supersedes the looser Epic B scorecard-reason wording.

KI-006 — alias_type enum enforcement

Yes. Alias types are locked enough to enforce now.

Exact allowed account alias values:

registry

domain

legal_name_normalized

address_normalized remains deferred and should stay invalid until a future contract change.

Exact allowed contact alias values:

email_normalized

linkedin_url_normalized

Enforce this at three layers: API schema validation, ORM validation, and a DB CHECK constraint. CHECK is preferable to a database enum because it is easier to evolve under controlled migration while still fail-closing bad writes.

KI-005 — stale worker hardening issue

Do not reopen KI-005 as-is. Close it as superseded and, only if real gaps remain, open one or more new scoped issues with precise acceptance criteria. A stale umbrella issue is no longer actionable. It hides what is actually missing.

Replacement issues should be concrete, for example: handler budget-decrement coverage, structured-event completeness, replay/no-op guarantees for specific stages, or parking taxonomy gaps. That gives you testable work instead of a vague architecture complaint that has already been partially overtaken.

KI-011 / KI-012 — created_at default policy

Use server-side now() / CURRENT_TIMESTAMP defaults as the canonical policy for created_at. That is the safer choice for migration consistency, multi-writer consistency, and replay safety.

For semantics, keep decided_at as the human/event time and created_at as the DB insertion time. For backfill, use existing trustworthy event timestamps only when the semantic match is exact; otherwise use migration-time server timestamp. For ApprovalDecision, decided_at can be copied into created_at only if you explicitly accept “written_at unavailable, approximate with decided_at” as a one-time migration rule. Otherwise prefer now() and preserve the distinction.

Lock set:

KI-014: persisted scores are INT 0..100; one-release dual-read/single-write migration.
KI-015: evidence category is a stored canonical field; allowed set is firmographic | persona_fit | trigger | technographic.
KI-016: strict reason shape required on every new write path now; reject weak new writes; only lossless normalization for legacy rows, else recompute/quarantine.
KI-006: alias enums are locked and enforceable now.
KI-005: close as superseded; replace only with narrowly scoped follow-ups.
KI-011/KI-012: created_at defaults are server-side now().