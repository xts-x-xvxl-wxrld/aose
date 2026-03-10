"""
Deterministic dedup and replay-safety helpers for Epic E account discovery.

Implements CONTRACT.yaml (epic-e) dedup_rules_v0 and provenance_and_trust rules.

Source trust ordering (provenance_and_trust.source_trust_order):
  registry/api > first-party site > official profiles > reputable directories
  > general web extracts

Account update rules (provenance_and_trust.merge_precedence):
  1. Higher-trust source wins.
  2. If equal trust, newer capture wins (ISO 8601 string comparison).
  3. If still tied, stable lexicographic tiebreak on source_ref.

These rules are deterministic: the same pair of inputs always produces the same
update decision, guaranteeing stable replay behavior regardless of execution order.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source trust hierarchy
# ---------------------------------------------------------------------------

# Numeric trust levels — higher value = higher trust.
# CONTRACT.yaml source_trust_order defines the ordering; exact integers are
# implementation-internal and must not be exposed in canonical records.
SOURCE_TRUST: dict[str, int] = {
    "registry/api": 5,
    "first_party_site": 4,
    "official_profiles": 3,
    "reputable_directories": 2,
    "general_web_extracts": 1,
}

_DEFAULT_TRUST = 0  # for unrecognized or absent source_type values


def trust_level(source_type: str | None) -> int:
    """
    Return the numeric trust level for a source_type string.

    Returns _DEFAULT_TRUST (0) for unknown or absent source types.
    """
    if not source_type:
        return _DEFAULT_TRUST
    return SOURCE_TRUST.get(source_type, _DEFAULT_TRUST)


# ---------------------------------------------------------------------------
# Update decision
# ---------------------------------------------------------------------------


def should_update_account(
    existing_source_type: str | None,
    existing_captured_at: str,
    existing_source_ref: str,
    new_source_type: str | None,
    new_captured_at: str,
    new_source_ref: str,
) -> bool:
    """
    Return True if the new source should overwrite existing mutable account fields.

    Decision rules (CONTRACT.yaml provenance_and_trust.merge_precedence):
      1. new trust > existing trust → update
      2. equal trust + new captured_at > existing captured_at → update
      3. equal trust + equal captured_at + new source_ref < existing source_ref → update
         (lexicographic stability: lower source_ref wins tiebreak, consistent across reruns)
      4. all else → no update

    Args:
        existing_source_type:  source_type stored in the existing account provenance.
        existing_captured_at:  ISO 8601 timestamp from existing account provenance.
        existing_source_ref:   source_ref from existing account provenance.
        new_source_type:       source_type from the new candidate's evidence.
        new_captured_at:       ISO 8601 observed_at from the new candidate.
        new_source_ref:        source_ref from the new candidate.

    Returns:
        True if new source should overwrite, False if existing should be preserved.
    """
    existing_trust = trust_level(existing_source_type)
    new_trust = trust_level(new_source_type)

    if new_trust > existing_trust:
        return True
    if new_trust < existing_trust:
        return False

    # Equal trust: newer capture wins
    if new_captured_at > existing_captured_at:
        return True
    if new_captured_at < existing_captured_at:
        return False

    # Still tied: lexicographic tiebreak on source_ref
    # Lower source_ref wins (stable, deterministic, consistent across reruns)
    return new_source_ref < existing_source_ref


# ---------------------------------------------------------------------------
# Evidence ID merge
# ---------------------------------------------------------------------------


def merge_evidence_ids(existing: list[str], new: list[str]) -> list[str]:
    """
    Return a deduplicated, order-preserving merge of two evidence ID lists.

    Existing IDs appear first, new unique IDs are appended in their original
    order. This ensures idempotent replay: merging the same IDs twice yields
    the same result.

    Args:
        existing: evidence_ids already stored on the Account row.
        new:      evidence_ids from the current discovery run.

    Returns:
        Merged list with no duplicates, existing order preserved.
    """
    seen: set[str] = set(existing)
    result: list[str] = list(existing)
    for eid in new:
        if eid not in seen:
            seen.add(eid)
            result.append(eid)
    return result


# ---------------------------------------------------------------------------
# Provenance extraction helper
# ---------------------------------------------------------------------------


def extract_account_trust_metadata(
    provenance: list[dict] | dict | None,
) -> tuple[str, str, str]:
    """
    Extract (source_type, captured_at, source_ref) from stored account provenance.

    Handles both list-of-entries format (used since E3) and legacy dict format.
    Returns ("unknown", "", "") if provenance is absent or malformed.
    """
    if not provenance:
        return ("unknown", "", "")

    entry: dict
    if isinstance(provenance, list):
        if not provenance:
            return ("unknown", "", "")
        entry = provenance[0]
    elif isinstance(provenance, dict):
        entry = provenance
    else:
        return ("unknown", "", "")

    return (
        entry.get("source_type", "unknown"),
        entry.get("captured_at", ""),
        entry.get("source_ref", ""),
    )
