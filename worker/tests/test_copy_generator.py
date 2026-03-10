"""
Tests for Epic H2: Copy Generator v0.

Acceptance checks covered:
  unit: generate_draft_v0 — returns CopyGeneratorResult
  unit: generate_draft_v0 — draft has required fields (subject, body, anchors, risk_flags)
  unit: generate_draft_v0 — subject contains offer_what and account_name
  unit: generate_draft_v0 — body contains full_name greeting
  unit: generate_draft_v0 — body contains account_name in intro
  unit: generate_draft_v0 — each evidence item produces one anchor
  unit: generate_draft_v0 — anchor span is present in body
  unit: generate_draft_v0 — anchor evidence_ids references the correct evidence_id
  unit: generate_draft_v0 — DraftClaimEvidenceGate PASS when all items anchored
  unit: generate_draft_v0 — gate PASS means no risk_flags
  unit: generate_draft_v0 — empty evidence_items → gate REVIEW
  unit: generate_draft_v0 — full_name fallback to "there" when None
  unit: generate_draft_v0 — multiple evidence items → multiple anchors
  unit: make_draft_id formula
  unit: make_anchor_key is deterministic and evidence_ids order-independent
  unit: make_approval_request_idempotency_key formula
"""

from __future__ import annotations

from datetime import datetime, timezone

from aose_worker.canonical_ids import (
    make_anchor_key,
    make_approval_request_idempotency_key,
    make_draft_id,
)
from aose_worker.services.copy_generator_service import (
    MAX_DRAFTS_PER_CONTACT,
    GateOutcome,
    generate_draft_v0,
)
from aose_worker.services.evidence_digest_service import (
    AccountSummary,
    ContactSummary,
    DraftingConstraints,
    EvidenceDigest,
    EvidenceItem,
    SellerSummary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DT = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _make_digest(
    evidence_items: list[EvidenceItem] | None = None,
    full_name: str | None = "Alice Smith",
) -> EvidenceDigest:
    return EvidenceDigest(
        seller_summary=SellerSummary(
            seller_id="seller:test",
            offer={
                "what": "CRM software",
                "where": ["Slovenia"],
                "who": ["SMB"],
                "positioning": ["affordable"],
            },
            constraints={
                "avoid_claims": ["no ROI guarantees"],
                "allowed_channels": ["email"],
                "languages": ["en"],
            },
        ),
        account_summary=AccountSummary(
            account_id="account:acme.com",
            name="Acme Corp",
            domain="acme.com",
            country="US",
        ),
        contact_summary=ContactSummary(
            contact_id="contact:acme.com:ct-001",
            full_name=full_name,
            role={"cluster": "economic_buyer"},
            channels=[{"type": "email", "value": "a@acme.com"}],
        ),
        evidence_items=evidence_items
        if evidence_items is not None
        else [
            EvidenceItem(
                evidence_id="ev:001",
                source_type="registry/api",
                url="https://example.com/ev001",
                captured_at=_DT.isoformat(),
                claim_frame="Acme recently expanded into new markets",
                snippet="snippet001",
            )
        ],
        drafting_constraints=DraftingConstraints(
            policy_pack_id="safe_v0_1",
            avoid_claims=["no ROI guarantees"],
            allowed_channels=["email"],
            language="en",
        ),
    )


# ---------------------------------------------------------------------------
# generate_draft_v0 — basic shape
# ---------------------------------------------------------------------------


def test_generate_draft_v0_returns_result():
    result = generate_draft_v0(_make_digest())
    assert result is not None


def test_draft_has_subject():
    result = generate_draft_v0(_make_digest())
    assert result.draft.subject


def test_draft_has_body():
    result = generate_draft_v0(_make_digest())
    assert result.draft.body


def test_draft_has_anchors_list():
    result = generate_draft_v0(_make_digest())
    assert isinstance(result.draft.anchors, list)


def test_draft_has_risk_flags_list():
    result = generate_draft_v0(_make_digest())
    assert isinstance(result.draft.risk_flags, list)


# ---------------------------------------------------------------------------
# generate_draft_v0 — subject content
# ---------------------------------------------------------------------------


def test_subject_contains_offer_what():
    result = generate_draft_v0(_make_digest())
    assert "CRM software" in result.draft.subject


def test_subject_contains_account_name():
    result = generate_draft_v0(_make_digest())
    assert "Acme Corp" in result.draft.subject


# ---------------------------------------------------------------------------
# generate_draft_v0 — body content
# ---------------------------------------------------------------------------


def test_body_contains_full_name_greeting():
    result = generate_draft_v0(_make_digest())
    assert "Alice Smith" in result.draft.body


def test_body_full_name_fallback_when_none():
    digest = _make_digest(full_name=None)
    result = generate_draft_v0(digest)
    assert "Hi there," in result.draft.body


def test_body_contains_account_name():
    result = generate_draft_v0(_make_digest())
    assert "Acme Corp" in result.draft.body


# ---------------------------------------------------------------------------
# generate_draft_v0 — anchors
# ---------------------------------------------------------------------------


def test_one_evidence_item_produces_one_anchor():
    result = generate_draft_v0(_make_digest())
    assert len(result.draft.anchors) == 1


def test_anchor_span_present_in_body():
    result = generate_draft_v0(_make_digest())
    for anchor in result.draft.anchors:
        assert anchor.span in result.draft.body


def test_anchor_references_correct_evidence_id():
    result = generate_draft_v0(_make_digest())
    assert result.draft.anchors[0].evidence_ids == ["ev:001"]


def test_multiple_evidence_items_produce_multiple_anchors():
    items = [
        EvidenceItem(
            evidence_id="ev:001",
            source_type="registry/api",
            url="https://example.com/ev001",
            captured_at=_DT.isoformat(),
            claim_frame="Acme expanded into new markets",
            snippet="s1",
        ),
        EvidenceItem(
            evidence_id="ev:002",
            source_type="general web extracts",
            url="https://example.com/ev002",
            captured_at=_DT.isoformat(),
            claim_frame="Acme raised Series B funding",
            snippet="s2",
        ),
    ]
    result = generate_draft_v0(_make_digest(evidence_items=items))
    assert len(result.draft.anchors) == 2
    evidence_ids_anchored = {
        eid for a in result.draft.anchors for eid in a.evidence_ids
    }
    assert "ev:001" in evidence_ids_anchored
    assert "ev:002" in evidence_ids_anchored


# ---------------------------------------------------------------------------
# generate_draft_v0 — DraftClaimEvidenceGate
# ---------------------------------------------------------------------------


def test_gate_pass_when_all_items_anchored():
    result = generate_draft_v0(_make_digest())
    assert result.gate_outcome == GateOutcome.PASS


def test_gate_pass_means_no_risk_flags():
    result = generate_draft_v0(_make_digest())
    assert result.draft.risk_flags == []
    assert result.gate_detail is None


def test_gate_review_when_no_evidence_items():
    digest = _make_digest(evidence_items=[])
    result = generate_draft_v0(digest)
    assert result.gate_outcome == GateOutcome.REVIEW
    assert result.draft.risk_flags != []


def test_gate_review_sets_gate_detail():
    digest = _make_digest(evidence_items=[])
    result = generate_draft_v0(digest)
    assert result.gate_detail is not None


# ---------------------------------------------------------------------------
# canonical_ids — draft and anchor helpers
# ---------------------------------------------------------------------------


def test_make_draft_id_formula():
    did = make_draft_id("contact:acme.com:ct-001", 1, 1)
    assert did == "draft:contact:acme.com:ct-001:seq1:v1"


def test_make_draft_id_varies_by_sequence():
    a = make_draft_id("contact:x", 1, 1)
    b = make_draft_id("contact:x", 2, 1)
    assert a != b


def test_make_draft_id_varies_by_variant():
    a = make_draft_id("contact:x", 1, 1)
    b = make_draft_id("contact:x", 1, 2)
    assert a != b


def test_make_anchor_key_is_deterministic():
    k1 = make_anchor_key("draft:x", "some span", ["ev:001"])
    k2 = make_anchor_key("draft:x", "some span", ["ev:001"])
    assert k1 == k2


def test_make_anchor_key_evidence_ids_order_independent():
    k1 = make_anchor_key("draft:x", "some span", ["ev:001", "ev:002"])
    k2 = make_anchor_key("draft:x", "some span", ["ev:002", "ev:001"])
    assert k1 == k2


def test_make_anchor_key_differs_by_span():
    k1 = make_anchor_key("draft:x", "span A", ["ev:001"])
    k2 = make_anchor_key("draft:x", "span B", ["ev:001"])
    assert k1 != k2


def test_make_anchor_key_starts_with_prefix():
    k = make_anchor_key("draft:x", "span", ["ev:001"])
    assert k.startswith("anchor:")


def test_make_approval_request_idempotency_key_formula():
    key = make_approval_request_idempotency_key("draft:contact:x:seq1:v1")
    assert key == "approval:draft:contact:x:seq1:v1:v1"


def test_make_approval_request_idempotency_key_varies_by_draft():
    k1 = make_approval_request_idempotency_key("draft:a")
    k2 = make_approval_request_idempotency_key("draft:b")
    assert k1 != k2


# ---------------------------------------------------------------------------
# Cap constant
# ---------------------------------------------------------------------------


def test_max_drafts_per_contact_is_two():
    assert MAX_DRAFTS_PER_CONTACT == 2
