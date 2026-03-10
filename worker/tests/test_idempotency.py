"""
Unit tests for SPEC-C3: idempotency guard.

Acceptance checks covered:
  1. Processing the same protected-write work item twice → only one persisted row.
  2. Reprocessing a draft-generation work item → no second draft for same key.
  3. Reprocessing an approval-request → reuses existing decision_key, no new row.
  4. Reprocessing sending-dispatch → no second SendAttempt for same key.
  5. Reprocessing handoff-producing work item → no duplicate next-stage enqueue.
  6. CI gate: rerunning the same WorkItem does not duplicate protected side effects.
  7. CI gate: replay preserves no-duplicate guarantees.

All tests use in-memory stores as the lookup backend (no DB required).
The guard logic is DB-agnostic; the lookup_fn is swappable for tests.
"""

from __future__ import annotations

from typing import Any

from aose_worker.idempotency import (
    IdempotencyResult,
    LookupFn,
    NoopResult,
    ProceedResult,
    guard,
    is_noop,
    is_proceed,
    make_memory_store,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_sentinel(key: str) -> dict[str, str]:
    """Minimal record sentinel to simulate an existing DB row."""
    return {"id": key}


def _simulate_protected_write(
    store: dict[str, Any],
    lookup: LookupFn,
    key: str,
) -> tuple[IdempotencyResult, list[str]]:
    """
    Simulate one full handler invocation that guards a protected write.

    Returns:
        (guard_result, written_keys) — written_keys tracks what was created.
    """
    written: list[str] = []
    result = guard(lookup, key)
    if is_proceed(result):
        store[key] = _make_sentinel(key)
        written.append(key)
    return result, written


# ── Acceptance check 1 ───────────────────────────────────────────────────────
# Two calls with the same key → first proceeds, second is noop.


def test_first_call_proceeds() -> None:
    store, lookup = make_memory_store()
    result = guard(lookup, "wi-key-001")
    assert is_proceed(result)
    assert isinstance(result, ProceedResult)
    assert result.lookup_key == "wi-key-001"


def test_second_call_is_noop_after_write() -> None:
    store, lookup = make_memory_store()
    # First processing: create the row
    first, written = _simulate_protected_write(store, lookup, "wi-key-001")
    assert is_proceed(first)
    assert written == ["wi-key-001"]

    # Second processing (duplicate / replay): must be a no-op
    second = guard(lookup, "wi-key-001")
    assert is_noop(second)
    assert isinstance(second, NoopResult)
    assert second.lookup_key == "wi-key-001"


def test_only_one_row_created_on_duplicate_processing() -> None:
    """Acceptance check 1: duplicate processing yields exactly one persisted row."""
    store, lookup = make_memory_store()

    for _ in range(5):  # simulate 5 identical processing attempts
        _simulate_protected_write(store, lookup, "wi-key-002")

    assert len(store) == 1
    assert "wi-key-002" in store


def test_noop_result_carries_correct_event_type() -> None:
    store, lookup = make_memory_store()
    store["wi-key-003"] = _make_sentinel("wi-key-003")

    result = guard(lookup, "wi-key-003")
    assert isinstance(result, NoopResult)
    assert result.event_type == "handler_noop_idempotent"
    assert result.outcome == "noop"


# ── Acceptance check 2 ───────────────────────────────────────────────────────
# Draft reuse: second call returns NoopResult; no second draft created.


def test_draft_guard_noop_on_replay() -> None:
    """Acceptance check 2: reprocessing draft-generation work item does not create duplicate."""
    store, lookup = make_memory_store()
    draft_key = "draft-idem-key-seller-001-account-001"

    # First run: no draft exists → proceed and create
    first, written = _simulate_protected_write(store, lookup, draft_key)
    assert is_proceed(first)
    assert len(written) == 1

    # Replay: draft already exists → no-op
    second, written2 = _simulate_protected_write(store, lookup, draft_key)
    assert is_noop(second)
    assert written2 == []

    # Still only one draft in store
    assert len(store) == 1


def test_different_draft_keys_proceed_independently() -> None:
    store, lookup = make_memory_store()

    _simulate_protected_write(store, lookup, "draft-key-A")
    _simulate_protected_write(store, lookup, "draft-key-B")

    assert len(store) == 2
    assert "draft-key-A" in store
    assert "draft-key-B" in store


# ── Acceptance check 3 ───────────────────────────────────────────────────────
# Approval decision reuse by decision_key.


def test_approval_decision_guard_reuses_existing_decision_key() -> None:
    """Acceptance check 3: existing decision_key → no-op, no new decision created."""
    store, lookup = make_memory_store()
    decision_key = "dec-key-draft-001-reviewer-001"

    # First approval: create the decision
    first, _ = _simulate_protected_write(store, lookup, decision_key)
    assert is_proceed(first)

    # Replay: same decision_key → must not create new decision
    second, written2 = _simulate_protected_write(store, lookup, decision_key)
    assert is_noop(second)
    assert written2 == []
    assert len(store) == 1


def test_approval_decision_noop_forbidden_fresh_decision() -> None:
    """Forbidden: invent a fresh decision when decision_key already exists."""
    store, lookup = make_memory_store()
    store["dec-key-001"] = {"decision_key": "dec-key-001", "status": "approved"}

    result = guard(lookup, "dec-key-001")
    assert is_noop(result)
    # Guard stopped us — store must not have been modified by this check
    assert len(store) == 1


# ── Acceptance check 4 ───────────────────────────────────────────────────────
# SendAttempt idempotency by idempotency_key.


def test_send_attempt_guard_noop_on_replay() -> None:
    """Acceptance check 4: reprocessing sending-dispatch does not create second SendAttempt."""
    store, lookup = make_memory_store()
    send_key = "send-idem-draft-001-channel-email"

    first, _ = _simulate_protected_write(store, lookup, send_key)
    assert is_proceed(first)

    second, written2 = _simulate_protected_write(store, lookup, send_key)
    assert is_noop(second)
    assert written2 == []
    assert len(store) == 1


def test_send_attempt_forbidden_duplicate() -> None:
    """Forbidden replay result: duplicate send_attempts for same key."""
    store, lookup = make_memory_store()
    store["send-key-001"] = {"idempotency_key": "send-key-001"}

    # Guard must prevent any second creation
    result = guard(lookup, "send-key-001")
    assert is_noop(result)


# ── Acceptance check 5 ───────────────────────────────────────────────────────
# Next-stage enqueue: deterministic idempotency_key prevents duplicate enqueue.


def test_next_stage_enqueue_not_duplicated() -> None:
    """Acceptance check 5: handoff WorkItem not enqueued twice for same key."""
    store, lookup = make_memory_store()
    enqueue_key = "wi-idem-stage-account_discovery-entity-acct-001"

    # Simulate first enqueue
    first, _ = _simulate_protected_write(store, lookup, enqueue_key)
    assert is_proceed(first)

    # Second attempt (e.g. worker crashed after enqueue but before ack)
    second, written2 = _simulate_protected_write(store, lookup, enqueue_key)
    assert is_noop(second)
    assert written2 == []
    assert len(store) == 1


# ── CI gate 6 & 7 ────────────────────────────────────────────────────────────
# Rerunning same WorkItem must not duplicate protected side effects.
# Replay preserves no-duplicate guarantees.


def test_ci_gate_rerun_work_item_no_duplicate_side_effects() -> None:
    """CI gate: rerunning the same WorkItem does not duplicate protected side effects."""
    store, lookup = make_memory_store()
    work_item_key = "wi-idem-key-run-001"

    # Run 1: creates the row
    r1, w1 = _simulate_protected_write(store, lookup, work_item_key)
    assert is_proceed(r1)
    assert len(w1) == 1

    # Run 2: replay — must be a deterministic no-op
    r2, w2 = _simulate_protected_write(store, lookup, work_item_key)
    assert is_noop(r2)
    assert w2 == []

    # Run 3: replay again — still no-op
    r3, w3 = _simulate_protected_write(store, lookup, work_item_key)
    assert is_noop(r3)
    assert w3 == []

    # Exactly one row despite three runs
    assert len(store) == 1


def test_ci_gate_replay_preserves_no_duplicate_guarantees() -> None:
    """CI gate: replay preserves no-duplicate guarantees across all protected types."""
    # Simulate three different protected writes in one "pipeline run"
    store_wi, lookup_wi = make_memory_store()
    store_draft, lookup_draft = make_memory_store()
    store_send, lookup_send = make_memory_store()

    wi_key = "wi-idem-replay-001"
    draft_key = "draft-idem-replay-001"
    send_key = "send-idem-replay-001"

    # First pass
    _simulate_protected_write(store_wi, lookup_wi, wi_key)
    _simulate_protected_write(store_draft, lookup_draft, draft_key)
    _simulate_protected_write(store_send, lookup_send, send_key)

    # Replay pass — all must be no-ops
    r_wi, w_wi = _simulate_protected_write(store_wi, lookup_wi, wi_key)
    r_draft, w_draft = _simulate_protected_write(store_draft, lookup_draft, draft_key)
    r_send, w_send = _simulate_protected_write(store_send, lookup_send, send_key)

    assert is_noop(r_wi) and w_wi == []
    assert is_noop(r_draft) and w_draft == []
    assert is_noop(r_send) and w_send == []

    assert len(store_wi) == 1
    assert len(store_draft) == 1
    assert len(store_send) == 1


# ── Guard invariants ─────────────────────────────────────────────────────────


def test_guard_returns_proceed_when_store_empty() -> None:
    _, lookup = make_memory_store()
    result = guard(lookup, "any-key")
    assert is_proceed(result)


def test_guard_returns_noop_when_store_has_record() -> None:
    store, lookup = make_memory_store()
    store["existing-key"] = {"data": "present"}
    result = guard(lookup, "existing-key")
    assert is_noop(result)


def test_guard_different_keys_independently_resolved() -> None:
    store, lookup = make_memory_store()
    store["key-A"] = _make_sentinel("key-A")

    result_a = guard(lookup, "key-A")
    result_b = guard(lookup, "key-B")

    assert is_noop(result_a)
    assert is_proceed(result_b)


def test_make_memory_store_returns_isolated_instances() -> None:
    store1, lookup1 = make_memory_store()
    store2, lookup2 = make_memory_store()

    store1["k"] = {"v": 1}

    assert is_noop(guard(lookup1, "k"))
    assert is_proceed(guard(lookup2, "k"))


# ── Allowed replay results ────────────────────────────────────────────────────
# CONTRACT.yaml idempotency.allowed_replay_results


def test_allowed_replay_noop_against_existing_output() -> None:
    store, lookup = make_memory_store()
    store["key"] = _make_sentinel("key")
    result = guard(lookup, "key")
    assert is_noop(result)  # noop against existing output — allowed


def test_allowed_replay_create_missing_output_exactly_once() -> None:
    store, lookup = make_memory_store()
    # No existing output → proceed (create exactly once)
    result = guard(lookup, "new-key")
    assert is_proceed(result)
    store["new-key"] = _make_sentinel("new-key")
    # Next call sees it exists
    result2 = guard(lookup, "new-key")
    assert is_noop(result2)


def test_allowed_replay_safe_rerun_when_no_protected_output_yet() -> None:
    store, lookup = make_memory_store()
    # Store is empty — safe to rerun
    for _ in range(3):
        result = guard(lookup, "unwritten-key")
        assert is_proceed(result)
        # (deliberately not writing — simulates handler crash before write)
    assert len(store) == 0
