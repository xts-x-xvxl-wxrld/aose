"""
Deterministic helpers for Epic F1 intent_fit_scoring.

Scope for this module:
  - payload validation
  - evidence resolution helpers
  - deterministic hashing/id formulas
  - scorecard shape assembly + reason invariants

Rule scoring itself is out of scope for F1 and is added in F2.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aose_api.scorecard_contract import (
    ALLOWED_EVIDENCE_CATEGORIES,
    normalize_and_validate_reasons,
)

SCORING_VERSION = "fit_intent_rules_v0_1"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_join(*parts: str) -> str:
    return _sha256("|".join(parts))


@dataclass(frozen=True)
class ValidatedScoringPayload:
    account_id: str
    evidence_ids: list[str] | None


def validate_scoring_payload(
    *,
    payload_json: dict[str, Any] | None,
    payload_version: int,
) -> ValidatedScoringPayload:
    """Validate WorkItem payload for intent_fit_scoring (v1 only)."""
    if payload_version != 1:
        raise ValueError(f"Unsupported payload_version: {payload_version!r}")

    payload = payload_json or {}
    if payload.get("v", 1) != 1:
        raise ValueError(f"Unsupported payload v field: {payload.get('v')!r}")

    data = payload.get("data") or {}
    account_id = data.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("payload.data.account_id is required")

    evidence_ids = data.get("evidence_ids")
    if evidence_ids is None:
        return ValidatedScoringPayload(account_id=account_id, evidence_ids=None)
    if not isinstance(evidence_ids, list) or not all(
        isinstance(eid, str) and eid for eid in evidence_ids
    ):
        raise ValueError(
            "payload.data.evidence_ids must be a list of non-empty strings"
        )
    return ValidatedScoringPayload(account_id=account_id, evidence_ids=evidence_ids)


def resolve_evidence_category(evidence_row: dict[str, Any]) -> str | None:
    """Resolve normalized evidence category from the canonical stored field."""
    category = evidence_row.get("category")
    if isinstance(category, str):
        category = category.strip().lower()
        if category in ALLOWED_EVIDENCE_CATEGORIES:
            return category

    provenance = evidence_row.get("provenance_json") or {}
    if not isinstance(provenance, dict):
        return None
    # Short compatibility fallback for older rows that stored category only in provenance_json.
    category = provenance.get("category")
    if not isinstance(category, str):
        return None
    category = category.strip().lower()
    if category in ALLOWED_EVIDENCE_CATEGORIES:
        return category
    return None


def build_evidence_snapshot_hash(used_evidence_ids: list[str]) -> str:
    """sha256(sorted_used_evidence_ids_joined_by_|)."""
    sorted_ids = sorted(used_evidence_ids)
    return _sha256("|".join(sorted_ids))


def make_scorecard_id(
    *,
    account_id: str,
    scoring_version: str,
    evidence_snapshot_hash: str,
    policy_pack_id: str,
) -> str:
    digest = _sha256_join(scoring_version, evidence_snapshot_hash, policy_pack_id)
    return f"scorecard:{account_id}:{digest}"


def make_effective_scoring_input_key(
    *,
    account_id: str,
    scoring_version: str,
    evidence_snapshot_hash: str,
    policy_pack_id: str,
) -> str:
    return _sha256_join(
        account_id,
        scoring_version,
        evidence_snapshot_hash,
        policy_pack_id,
    )


def validate_reasons(
    *,
    reasons: list[dict[str, Any]],
    existing_evidence_ids: set[str],
) -> None:
    """Validate Epic F reason invariants."""
    normalize_and_validate_reasons(
        reasons,
        existing_evidence_ids=existing_evidence_ids,
    )


@dataclass(frozen=True)
class ScoreValue:
    score: int
    confidence: float
    reasons: list[dict[str, Any]]


@dataclass(frozen=True)
class ScorecardUpsertInput:
    scorecard_id: str
    account_id: str
    policy_pack_id: str
    scoring_version: str
    evidence_snapshot_hash: str
    effective_input_key: str
    fit: ScoreValue
    intent: ScoreValue
    computed_at: datetime


def build_scorecard_upsert_input(
    *,
    account_id: str,
    policy_pack_id: str,
    used_evidence_ids: list[str],
    fit: ScoreValue,
    intent: ScoreValue,
    scoring_version: str = SCORING_VERSION,
) -> ScorecardUpsertInput:
    """Build deterministic scorecard identity and validate score/reason invariants."""
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("account_id is required")
    if not isinstance(policy_pack_id, str) or not policy_pack_id:
        raise ValueError("policy_pack_id is required")
    if not (0 <= fit.score <= 100 and 0 <= intent.score <= 100):
        raise ValueError("fit.score and intent.score must be in 0..100")
    if not (0.0 <= fit.confidence <= 1.0 and 0.0 <= intent.confidence <= 1.0):
        raise ValueError("fit.confidence and intent.confidence must be in 0.0..1.0")

    used_set = set(used_evidence_ids)
    fit_reasons = normalize_and_validate_reasons(
        fit.reasons,
        existing_evidence_ids=used_set,
    )
    intent_reasons = normalize_and_validate_reasons(
        intent.reasons,
        existing_evidence_ids=used_set,
    )

    evidence_snapshot_hash = build_evidence_snapshot_hash(used_evidence_ids)
    scorecard_id = make_scorecard_id(
        account_id=account_id,
        scoring_version=scoring_version,
        evidence_snapshot_hash=evidence_snapshot_hash,
        policy_pack_id=policy_pack_id,
    )
    effective_input_key = make_effective_scoring_input_key(
        account_id=account_id,
        scoring_version=scoring_version,
        evidence_snapshot_hash=evidence_snapshot_hash,
        policy_pack_id=policy_pack_id,
    )
    return ScorecardUpsertInput(
        scorecard_id=scorecard_id,
        account_id=account_id,
        policy_pack_id=policy_pack_id,
        scoring_version=scoring_version,
        evidence_snapshot_hash=evidence_snapshot_hash,
        effective_input_key=effective_input_key,
        fit=ScoreValue(
            score=fit.score,
            confidence=fit.confidence,
            reasons=fit_reasons,
        ),
        intent=ScoreValue(
            score=intent.score,
            confidence=intent.confidence,
            reasons=intent_reasons,
        ),
        computed_at=datetime.now(tz=timezone.utc),
    )
