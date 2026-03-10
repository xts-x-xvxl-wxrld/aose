# PLACEHOLDERS.md — Epic C

Placeholder ledger for unresolved decisions in Epic C.
Format: PH-EPIC-C-<nnn>

---

## PH-EPIC-C-002 — OutreachDraft idempotency key column (SCHEMA)
Status: OPEN
Epic: Epic C
Blocking: NO (guard accepts any replay-stable key; draft handler not yet implemented)
Decision needed: whether outreach_drafts needs an explicit idempotency_key column, or whether the draft_id derived from handler inputs is the canonical replay-stable key
Forbidden assumptions: do not add a column without a migration; do not invent a key formula not locked in a contract
Temporary default allowed: draft_lookup() guards by draft_id; handler must derive draft_id deterministically before calling guard
Acceptance stub: copy_generate handler uses guard(draft_lookup(session), deterministic_draft_id) with no duplicate drafts on replay

---

## PH-EPIC-C-001 — Stub handler business logic (HANDLER_IMPL)
Status: OPEN
Epic: Epic C
Blocking: NO (routing is fully testable with stubs; business logic is deferred to C2–C5)
Decision needed: full handler implementation for each canonical stage
Forbidden assumptions: do not implement business logic until the handler's SPEC is active
Temporary default allowed: `_stub_handler` no-op callable registered for all 9 canonical stages
Acceptance stub: registry keys exactly match canonical stages; stubs are callable without error
