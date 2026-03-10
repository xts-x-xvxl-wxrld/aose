"""
Idempotency guard for the AOSE worker pipeline.

Implements CONTRACT.yaml idempotency rules:
  - before any protected side effect, look up existing output by idempotency_key
    or another replay-stable unique key defined by the canonical model
  - if output exists: become deterministic no-op, do not duplicate rows,
    emit handler_noop_idempotent, return success-compatible outcome
  - if no output: proceed with exactly-once creation
  - guard must survive worker restart — lookup must be DB-backed, not in-memory

Protected side effects minimum (CONTRACT.yaml idempotency.protected_side_effects_minimum):
  - WorkItem rows (next-stage enqueue) — keyed by idempotency_key
  - outreach_drafts                    — keyed by idempotency_key (replay-stable)
  - approval_decisions                 — keyed by decision_key
  - send_attempts                      — keyed by idempotency_key
  - any other derivative writes owned by a handler

Handlers call guard() before every protected write.  They must not rely on
process-local caches or prior-run knowledge for correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

# lookup_fn: takes a string key, returns the existing record or None.
# Production callers pass a DB-backed function; tests use a dict-backed stub.
LookupFn = Callable[[str], Optional[Any]]


# ── Guard result types ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class NoopResult:
    """
    Existing protected output was found — handler must become a no-op.

    Contract requirements (idempotency.required_guard_behavior.if_output_exists):
      - do not create duplicate rows
      - emit handler_noop_idempotent
      - return a success-compatible outcome
    """

    lookup_key: str
    event_type: str = "handler_noop_idempotent"
    outcome: str = "noop"


@dataclass(frozen=True)
class ProceedResult:
    """No existing output found — safe to create protected output exactly once."""

    lookup_key: str


# Union type for type hints
IdempotencyResult = NoopResult | ProceedResult


# ── Core guard ───────────────────────────────────────────────────────────────


def guard(lookup_fn: LookupFn, key: str) -> IdempotencyResult:
    """
    Pre-side-effect idempotency guard.

    Must be called before every protected create side effect.
    lookup_fn must query the durable store (DB) — never in-memory only.

    Args:
        lookup_fn: callable(key) -> existing record or None.
                   Must be backed by a durable store (Postgres).
        key:       the idempotency_key or replay-stable unique key for the
                   protected output being guarded.

    Returns:
        NoopResult  — output already exists; handler must not create duplicate.
        ProceedResult — no output found; safe to create exactly once.
    """
    existing = lookup_fn(key)
    if existing is not None:
        return NoopResult(lookup_key=key)
    return ProceedResult(lookup_key=key)


def is_noop(result: IdempotencyResult) -> bool:
    """True if the guard found existing output and the handler must no-op."""
    return isinstance(result, NoopResult)


def is_proceed(result: IdempotencyResult) -> bool:
    """True if no existing output was found and creation may proceed."""
    return isinstance(result, ProceedResult)


# ── DB lookup factory ────────────────────────────────────────────────────────
#
# Produces a LookupFn backed by a SQLAlchemy session and a raw SQL query.
# Using text() avoids importing aose_api models into the worker package.
# Each protected table has its own factory so the key column is explicit.


def make_db_lookup(session: Any, table: str, key_column: str) -> LookupFn:
    """
    Build a DB-backed LookupFn for any protected table.

    Args:
        session:    SQLAlchemy Session or Connection.
        table:      canonical table name (e.g. "work_items").
        key_column: column to match (e.g. "idempotency_key").

    Returns:
        LookupFn that returns the first matching row or None.
    """
    from sqlalchemy import text  # noqa: PLC0415 — deferred to avoid import cost

    sql = text(f"SELECT 1 FROM {table} WHERE {key_column} = :key LIMIT 1")  # noqa: S608

    def lookup(key: str) -> Any:
        result = session.execute(sql, {"key": key}).first()
        return result

    return lookup


# ── Named lookup factories for each protected side effect ────────────────────
# These are the canonical production lookup_fn builders.
# Pass the returned LookupFn to guard().


def work_item_lookup(session: Any) -> LookupFn:
    """Guard next-stage WorkItem enqueue by idempotency_key."""
    return make_db_lookup(session, "work_items", "idempotency_key")


def draft_lookup(session: Any) -> LookupFn:
    """
    Guard outreach_draft creation by the handler's replay-stable key.

    The key must be derived deterministically from the source WorkItem
    (e.g. the WorkItem idempotency_key or a content-hash of inputs).
    The caller is responsible for computing the stable key before calling.

    Note: outreach_drafts has no idempotency_key column in the schema.
    The handler must pass a replay-stable unique key that maps one-to-one
    with the draft it intends to create. See PH-EPIC-C-002.
    """
    return make_db_lookup(session, "outreach_drafts", "draft_id")


def approval_decision_lookup(session: Any) -> LookupFn:
    """Guard ApprovalDecision creation by decision_key (canonical unique key)."""
    return make_db_lookup(session, "approval_decisions", "decision_key")


def send_attempt_lookup(session: Any) -> LookupFn:
    """Guard SendAttempt creation by idempotency_key."""
    return make_db_lookup(session, "send_attempts", "idempotency_key")


# ── In-memory store helper (for tests only) ──────────────────────────────────


def make_memory_store() -> tuple[dict[str, Any], LookupFn]:
    """
    Create an in-memory store and its LookupFn for use in unit tests.

    Returns:
        (store, lookup_fn) — store is a plain dict that tests may mutate
        to simulate existing or absent records.

    Example:
        store, lookup = make_memory_store()
        store["key-abc"] = {"id": "key-abc"}   # simulate existing record
        result = guard(lookup, "key-abc")        # → NoopResult
    """
    store: dict[str, Any] = {}

    def lookup(key: str) -> Any:
        return store.get(key)

    return store, lookup
