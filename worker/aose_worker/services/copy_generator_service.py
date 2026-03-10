"""
Copy generator v0 for Epic H2.

Produces a template-based OutreachDraft and PersonalizationAnchors
from a pre-built EvidenceDigest (H1).

Design rules (CONTRACT.yaml copy_generation):
  - Every non-trivial personalized claim maps to one or more evidence_ids.
  - Generic greeting and closing lines do not require anchors.
  - If a specific claim cannot be anchored, strip it or mark for review.
  - Anchor evidence_ids must already exist in canonical Evidence.
  - max_drafts_per_contact = 2 cap enforced before persistence.

DraftClaimEvidenceGate:
  PASS   — all evidence items in the digest are referenced by at least one anchor.
  REVIEW — one or more evidence items are not anchored (claim stripped or orphaned).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aose_worker.services.evidence_digest_service import EvidenceDigest

# ---------------------------------------------------------------------------
# Cap constant (CONTRACT.yaml copy_generation.hard_limits)
# ---------------------------------------------------------------------------

MAX_DRAFTS_PER_CONTACT: int = 2


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnchorSpec:
    """Specifies a text span and the evidence IDs that back it."""

    span: str
    evidence_ids: list[str]


@dataclass
class DraftSpec:
    """Complete in-memory representation of a generated draft."""

    subject: str
    body: str
    anchors: list[AnchorSpec]
    risk_flags: list[dict]


class GateOutcome(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"


@dataclass
class CopyGeneratorResult:
    draft: DraftSpec
    gate_outcome: GateOutcome
    gate_detail: str | None = None


# ---------------------------------------------------------------------------
# Template builder
# ---------------------------------------------------------------------------

# Lines that constitute a generic greeting or closing — exempt from anchoring.
_GENERIC_LINES: frozenset[str] = frozenset(
    {
        "greeting",
        "closing",
    }
)


def _build_evidence_claim_sentence(claim_frame: str, account_name: str) -> str:
    """
    Turn an evidence claim_frame into a claim sentence for the draft body.

    Format: "- {claim_frame}" (bullet list style).
    """
    return f"- {claim_frame}"


def generate_draft_v0(digest: EvidenceDigest) -> CopyGeneratorResult:
    """
    Generate a template-based OutreachDraft from an EvidenceDigest.

    Template structure:
      [greeting]
      [intro mentioning account_name]
      [evidence claim bullets — each becomes a PersonalizationAnchor]
      [CTA]
      [closing]

    DraftClaimEvidenceGate PASS requires:
      - At least one anchor exists.
      - Every evidence item in the digest is referenced by exactly one anchor.

    Returns:
        CopyGeneratorResult with draft spec, gate outcome, and optional detail.
    """
    contact = digest.contact_summary
    account = digest.account_summary
    seller = digest.seller_summary

    full_name: str = contact.full_name or "there"
    account_name: str = account.name
    offer_what: str = seller.offer.get("what", "our solution")

    # --- Subject ---
    subject = f"{offer_what} — quick note for {account_name}"

    # --- Body lines ---
    greeting_line = f"Hi {full_name},"
    intro_line = f"\nI came across {account_name} and a few things caught my attention:"

    # Evidence claim bullets — each gets its own anchor
    claim_sentences: list[str] = []
    anchors: list[AnchorSpec] = []

    for item in digest.evidence_items:
        sentence = _build_evidence_claim_sentence(item.claim_frame, account_name)
        claim_sentences.append(sentence)
        anchors.append(
            AnchorSpec(
                span=sentence,
                evidence_ids=[item.evidence_id],
            )
        )

    cta_line = (
        f"\nGiven {account_name}'s profile, "
        f"I believe {offer_what} could be a strong fit."
    )
    closing_line = "\nWould you be open to a brief conversation?\n\nBest regards"

    body_parts = [greeting_line, intro_line, ""]
    body_parts.extend(claim_sentences)
    body_parts.extend([cta_line, closing_line])
    body = "\n".join(body_parts)

    # --- DraftClaimEvidenceGate ---
    evidence_ids_in_digest = {item.evidence_id for item in digest.evidence_items}
    evidence_ids_anchored = {eid for a in anchors for eid in a.evidence_ids}

    risk_flags: list[dict] = []

    if anchors and evidence_ids_anchored >= evidence_ids_in_digest:
        gate_outcome = GateOutcome.PASS
        gate_detail = None
    else:
        gate_outcome = GateOutcome.REVIEW
        unanchored = evidence_ids_in_digest - evidence_ids_anchored
        gate_detail = (
            f"Evidence items not anchored: {sorted(unanchored)}"
            if unanchored
            else "No anchors generated."
        )
        risk_flags.append(
            {
                "type": "DraftClaimEvidenceGate",
                "outcome": "REVIEW",
                "detail": gate_detail,
            }
        )

    return CopyGeneratorResult(
        draft=DraftSpec(
            subject=subject,
            body=body,
            anchors=anchors,
            risk_flags=risk_flags,
        ),
        gate_outcome=gate_outcome,
        gate_detail=gate_detail,
    )
