"""
Evidence digest builder for Epic H1.

Builds a compact, renderable evidence digest DTO from canonical records:
  SellerProfile, Account, Contact, Evidence (Scorecard is optional/read-only).

CONTRACT.yaml evidence_digest section defines the required shape and ordering rules.

Invariants:
  - Digest contains only facts already present in canonical records.
  - Digest does not invent claims, scores, or persona facts.
  - Digest does not mutate canonical Evidence records.
  - Digest does not include secrets or raw provider credentials.
  - No new canonical EvidenceDigest table is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Source trust order (CONTRACT.yaml evidence_digest.ordering_rules)
# Locked order: higher number = higher trust.
# ---------------------------------------------------------------------------

_SOURCE_TRUST_ORDER: dict[str, int] = {
    "registry/api": 4,
    "first-party site": 3,
    "official profiles": 2,
    "reputable directories": 1,
    "general web extracts": 0,
}
_DEFAULT_TRUST: int = -1  # unknown source_type sorts last


def _source_trust(source_type: str) -> int:
    return _SOURCE_TRUST_ORDER.get(source_type, _DEFAULT_TRUST)


# ---------------------------------------------------------------------------
# Digest shape dataclasses (CONTRACT.yaml evidence_digest.required_shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SellerSummary:
    seller_id: str
    offer: dict
    constraints: dict


@dataclass(frozen=True)
class AccountSummary:
    account_id: str
    name: str
    domain: str | None
    country: str | None


@dataclass(frozen=True)
class ContactSummary:
    contact_id: str
    full_name: str | None
    role: dict | None
    channels: list


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    source_type: str
    url: str
    captured_at: str  # ISO 8601 string
    claim_frame: str
    snippet: str


@dataclass(frozen=True)
class DraftingConstraints:
    policy_pack_id: str
    avoid_claims: list
    allowed_channels: list
    language: str


@dataclass
class EvidenceDigest:
    seller_summary: SellerSummary
    account_summary: AccountSummary
    contact_summary: ContactSummary
    evidence_items: list[EvidenceItem]
    drafting_constraints: DraftingConstraints


# ---------------------------------------------------------------------------
# Contract error — callers must park as parked:contract_error
# ---------------------------------------------------------------------------


class DigestContractError(ValueError):
    """
    Raised when a required canonical record is missing or payload is invalid.
    Callers must park the WorkItem as parked:contract_error.
    """


# ---------------------------------------------------------------------------
# DB read helpers (read-only, no mutation)
# ---------------------------------------------------------------------------


def _load_seller(session: Session, seller_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT seller_id,
               offer_what, offer_where, offer_who, offer_positioning,
               constraints_avoid_claims, constraints_allowed_channels,
               constraints_languages, policy_pack_id
        FROM seller_profiles
        WHERE seller_id = :id
        """
    )
    row = session.execute(sql, {"id": seller_id}).mappings().first()
    if row is None:
        raise DigestContractError(f"SellerProfile not found: {seller_id!r}")
    return dict(row)


def _load_account(session: Session, account_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT account_id, name, domain, country
        FROM accounts
        WHERE account_id = :id
        """
    )
    row = session.execute(sql, {"id": account_id}).mappings().first()
    if row is None:
        raise DigestContractError(f"Account not found: {account_id!r}")
    return dict(row)


def _load_contact(session: Session, contact_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT contact_id, full_name, role_json, channels_json
        FROM contacts
        WHERE contact_id = :id
        """
    )
    row = session.execute(sql, {"id": contact_id}).mappings().first()
    if row is None:
        raise DigestContractError(f"Contact not found: {contact_id!r}")
    return dict(row)


def _load_evidence_row(session: Session, evidence_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT evidence_id, source_type, canonical_url, captured_at,
               claim_frame, snippet
        FROM evidence
        WHERE evidence_id = :id
        """
    )
    row = session.execute(sql, {"id": evidence_id}).mappings().first()
    if row is None:
        raise DigestContractError(f"Evidence not found: {evidence_id!r}")
    return dict(row)


# ---------------------------------------------------------------------------
# Ordering helpers (CONTRACT.yaml ordering_rules)
# ---------------------------------------------------------------------------


def _row_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    """
    Deterministic three-key sort for evidence rows.

    1. source trust descending  (higher trust sorts earlier → negate)
    2. captured_at descending   (more recent sorts earlier → negate timestamp)
    3. evidence_id ascending    (lexicographic tiebreak)
    """
    trust = _source_trust(row["source_type"])
    captured_at = row["captured_at"]
    if isinstance(captured_at, datetime):
        ts = captured_at.timestamp()
    else:
        try:
            ts = datetime.fromisoformat(str(captured_at)).timestamp()
        except (ValueError, TypeError):
            ts = 0.0
    return (-trust, -ts, row["evidence_id"])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_evidence_digest(
    *,
    session: Session,
    seller_id: str,
    account_id: str,
    contact_id: str,
    evidence_ids: list[str],
    language: str = "en",
    channel: str = "email",
) -> EvidenceDigest:
    """
    Build and return an EvidenceDigest derived solely from canonical records.

    Raises DigestContractError (ValueError subclass) if:
      - seller_id / account_id / contact_id not found
      - any evidence_id in evidence_ids not found
      - evidence_ids is empty

    Does NOT mutate any canonical record.
    Does NOT create any new canonical table.

    Args:
        session:      SQLAlchemy Session (caller manages transactions).
        seller_id:    Canonical SellerProfile ID.
        account_id:   Canonical Account ID.
        contact_id:   Canonical Contact ID.
        evidence_ids: Non-empty list of canonical Evidence IDs.
        language:     Draft language hint (default: "en").
        channel:      Draft channel hint (default: "email").

    Returns:
        EvidenceDigest with all required fields populated.
    """
    if not evidence_ids:
        raise DigestContractError("evidence_ids must be a non-empty list")

    # Load canonical records — any missing record raises DigestContractError.
    seller = _load_seller(session, seller_id)
    account = _load_account(session, account_id)
    contact = _load_contact(session, contact_id)

    evidence_rows: list[dict[str, Any]] = [
        _load_evidence_row(session, eid) for eid in evidence_ids
    ]

    # --- seller_summary ---
    seller_summary = SellerSummary(
        seller_id=seller["seller_id"],
        offer={
            "what": seller["offer_what"],
            "where": seller["offer_where"],
            "who": seller["offer_who"],
            "positioning": seller["offer_positioning"],
        },
        constraints={
            "avoid_claims": seller["constraints_avoid_claims"],
            "allowed_channels": seller["constraints_allowed_channels"],
            "languages": seller["constraints_languages"],
        },
    )

    # --- account_summary ---
    account_summary = AccountSummary(
        account_id=account["account_id"],
        name=account["name"],
        domain=account.get("domain"),
        country=account.get("country"),
    )

    # --- contact_summary ---
    channels: list = contact.get("channels_json") or []
    if not isinstance(channels, list):
        channels = []
    contact_summary = ContactSummary(
        contact_id=contact["contact_id"],
        full_name=contact.get("full_name"),
        role=contact.get("role_json"),
        channels=channels,
    )

    # --- evidence_items (deterministic ordering) ---
    sorted_rows = sorted(evidence_rows, key=_row_sort_key)

    evidence_items: list[EvidenceItem] = []
    for row in sorted_rows:
        captured_at = row["captured_at"]
        if isinstance(captured_at, datetime):
            captured_at_str = captured_at.isoformat()
        else:
            captured_at_str = str(captured_at)
        evidence_items.append(
            EvidenceItem(
                evidence_id=row["evidence_id"],
                source_type=row["source_type"],
                url=row["canonical_url"],
                captured_at=captured_at_str,
                claim_frame=row["claim_frame"],
                snippet=row["snippet"],
            )
        )

    # --- drafting_constraints ---
    drafting_constraints = DraftingConstraints(
        policy_pack_id=seller["policy_pack_id"],
        avoid_claims=list(seller["constraints_avoid_claims"] or []),
        allowed_channels=list(seller["constraints_allowed_channels"] or []),
        language=language,
    )

    return EvidenceDigest(
        seller_summary=seller_summary,
        account_summary=account_summary,
        contact_summary=contact_summary,
        evidence_items=evidence_items,
        drafting_constraints=drafting_constraints,
    )
