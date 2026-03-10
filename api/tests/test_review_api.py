"""
Tests for SPEC-H4: Draft Review API endpoints.

Acceptance checks covered:
  1. GET /drafts returns list of drafts.
  2. GET /drafts/{draft_id} returns full review context (contact, account,
     anchors, evidence items, gate outcomes).
  3. GET /drafts/{draft_id} 404 for unknown draft_id.
  4. POST /drafts/{draft_id}/decision creates approval_request WorkItem.
  5. POST /drafts/{draft_id}/decision is idempotent (same reviewer+draft = same work item).
  6. POST /drafts/{draft_id}/decision rejects viewer role.
  7. POST /drafts/{draft_id}/decision rejects invalid status.
  8. POST /drafts/{draft_id}/decision 404 for unknown draft_id.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from aose_api.ids import make_contact_id, make_draft_id, make_evidence_id
from aose_api.main import app
from aose_api.models import (
    Account,
    Contact,
    Evidence,
    OutreachDraft,
    PersonalizationAnchor,
    WorkItem,
)

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

_DB_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not _DB_URL, reason="DATABASE_URL not set — skipping DB tests"
)


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 9, 10, 0, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "account:h4-test.example.com"
CONTACT_ID = make_contact_id(account_id=ACCOUNT_ID, email="reviewer@h4.example.com")
DRAFT_ID = make_draft_id(contact_id=CONTACT_ID, sequence_no=1, variant_no=1)
EVIDENCE_ID = make_evidence_id(
    source_type="web",
    canonical_url="https://h4.example.com/article",
    captured_at_iso="2026-03-01T00:00:00+00:00",
    snippet_text="H4 review test snippet",
)
ANCHOR_KEY = "anchor:h4test001"
REVIEWER_ID = "reviewer:op-h4-001"
IDEMPOTENCY_KEY = f"decision_submit:{DRAFT_ID}:{REVIEWER_ID}:v1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(_sa_url(_DB_URL))
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def seed_h4(db_engine):
    """Create account, contact, evidence, draft, and anchor for H4 tests."""
    with Session(db_engine) as s:
        if s.get(Account, ACCOUNT_ID) is None:
            s.add(
                Account(
                    account_id=ACCOUNT_ID,
                    name="H4 Test Corp",
                    domain="h4-test.example.com",
                    country="SI",
                    provenance=[],
                    evidence_ids=[],
                    confidence=0.9,
                    status="candidate",
                    v=1,
                )
            )
        if s.get(Contact, CONTACT_ID) is None:
            s.add(
                Contact(
                    contact_id=CONTACT_ID,
                    account_id=ACCOUNT_ID,
                    full_name="H4 Reviewer",
                    role_json={"title": "CTO", "cluster": "technical"},
                    channels_json=[
                        {"type": "email", "value": "reviewer@h4.example.com"}
                    ],
                    provenance_json=[],
                    status="candidate",
                    v=1,
                )
            )
        if s.get(Evidence, EVIDENCE_ID) is None:
            s.add(
                Evidence(
                    evidence_id=EVIDENCE_ID,
                    source_type="web",
                    canonical_url="https://h4.example.com/article",
                    captured_at=NOW,
                    snippet="H4 review test snippet",
                    claim_frame="Company uses SMT assembly at scale",
                    source_provider="PROV_H4",
                    source_ref="ref_h4_001",
                    observed_at=NOW,
                    confidence=0.85,
                    provenance_json={},
                    content_ref_id=None,
                    v=1,
                )
            )
        if s.get(OutreachDraft, DRAFT_ID) is None:
            s.add(
                OutreachDraft(
                    draft_id=DRAFT_ID,
                    contact_id=CONTACT_ID,
                    account_id=ACCOUNT_ID,
                    channel="email",
                    language="en",
                    policy_pack_id="safe_v0_1",
                    subject="H4 test subject",
                    body="Hi H4 Reviewer, your SMT line caught our attention.",
                    risk_flags_json=[
                        {"gate": "DraftClaimEvidenceGate", "outcome": "PASS"}
                    ],
                    created_at=NOW,
                    v=1,
                )
            )
        if s.get(PersonalizationAnchor, ANCHOR_KEY) is None:
            s.add(
                PersonalizationAnchor(
                    anchor_key=ANCHOR_KEY,
                    draft_id=DRAFT_ID,
                    span="your SMT line caught our attention",
                    evidence_ids_json=[EVIDENCE_ID],
                    v=1,
                )
            )
        s.commit()
    yield
    # Cleanup
    with Session(db_engine) as s:
        s.query(WorkItem).filter(
            WorkItem.stage == "approval_request",
            WorkItem.entity_ref_id == CONTACT_ID,
        ).delete(synchronize_session=False)
        anchor = s.get(PersonalizationAnchor, ANCHOR_KEY)
        if anchor:
            s.delete(anchor)
        draft = s.get(OutreachDraft, DRAFT_ID)
        if draft:
            s.delete(draft)
        ev = s.get(Evidence, EVIDENCE_ID)
        if ev:
            s.delete(ev)
        contact = s.get(Contact, CONTACT_ID)
        if contact:
            s.delete(contact)
        account = s.get(Account, ACCOUNT_ID)
        if account:
            s.delete(account)
        s.commit()


@pytest.fixture(scope="module")
def client(db_engine, seed_h4):
    """TestClient wired to the live DB engine."""
    app.state.engine = db_engine
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Acceptance check 1: GET /drafts returns list
# ---------------------------------------------------------------------------


def test_list_drafts_returns_list(client):
    """Acceptance check 1: GET /drafts returns a list including the seeded draft."""
    resp = client.get("/drafts")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [d["draft_id"] for d in data]
    assert DRAFT_ID in ids


# ---------------------------------------------------------------------------
# Acceptance check 2: GET /drafts/{draft_id} returns full review context
# ---------------------------------------------------------------------------


def test_get_draft_review_returns_context(client):
    """Acceptance check 2: full review context includes all required panels."""
    resp = client.get(f"/drafts/{DRAFT_ID}")
    assert resp.status_code == 200
    data = resp.json()

    # draft_preview panel
    assert data["draft_id"] == DRAFT_ID
    assert data["subject"] == "H4 test subject"
    assert "SMT line" in data["body"]
    assert data["channel"] == "email"
    assert data["language"] == "en"

    # contact summary
    assert data["contact"]["contact_id"] == CONTACT_ID
    assert data["contact"]["full_name"] == "H4 Reviewer"

    # account summary
    assert data["account"]["account_id"] == ACCOUNT_ID
    assert data["account"]["name"] == "H4 Test Corp"

    # anchor_list panel
    assert len(data["anchors"]) == 1
    anchor = data["anchors"][0]
    assert anchor["anchor_key"] == ANCHOR_KEY
    assert "SMT line" in anchor["span"]
    assert EVIDENCE_ID in anchor["evidence_ids"]

    # evidence_cards panel
    assert len(data["evidence_items"]) == 1
    ev = data["evidence_items"][0]
    assert ev["evidence_id"] == EVIDENCE_ID
    assert ev["source_type"] == "web"
    assert ev["claim_frame"] == "Company uses SMT assembly at scale"
    assert ev["snippet"] == "H4 review test snippet"
    assert ev["url"] == "https://h4.example.com/article"

    # gate_outcomes panel
    assert len(data["risk_flags"]) == 1
    assert data["risk_flags"][0]["gate"] == "DraftClaimEvidenceGate"


# ---------------------------------------------------------------------------
# Acceptance check 3: GET /drafts/{draft_id} 404 for unknown
# ---------------------------------------------------------------------------


def test_get_draft_review_404(client):
    """Acceptance check 3: unknown draft_id returns 404."""
    resp = client.get("/drafts/draft:does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Acceptance check 4: POST /drafts/{draft_id}/decision creates WorkItem
# ---------------------------------------------------------------------------


def test_submit_decision_creates_work_item(client, db_engine):
    """Acceptance check 4: decision submission creates approval_request WorkItem."""
    # Clean up any existing decision work item first
    with Session(db_engine) as s:
        s.query(WorkItem).filter(WorkItem.idempotency_key == IDEMPOTENCY_KEY).delete(
            synchronize_session=False
        )
        s.commit()

    resp = client.post(
        f"/drafts/{DRAFT_ID}/decision",
        json={
            "status": "approved",
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": "operator",
            "notes": "Looks good.",
            "overridden_gates": [],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["draft_id"] == DRAFT_ID
    assert data["status"] == "approved"
    assert data["created"] is True

    # Verify work item exists in DB
    with Session(db_engine) as s:
        wi = s.get(WorkItem, data["work_item_id"])
        assert wi is not None
        assert wi.stage == "approval_request"
        assert wi.payload_json["data"]["draft_id"] == DRAFT_ID
        assert wi.payload_json["data"]["status"] == "approved"
        assert wi.payload_json["data"]["reviewer_id"] == REVIEWER_ID
        assert wi.payload_json["data"]["reviewer_role"] == "operator"


# ---------------------------------------------------------------------------
# Acceptance check 5: idempotent — same reviewer+draft = same work item
# ---------------------------------------------------------------------------


def test_submit_decision_idempotent(client):
    """Acceptance check 5: resubmitting the same decision returns created=False."""
    resp = client.post(
        f"/drafts/{DRAFT_ID}/decision",
        json={
            "status": "approved",
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": "operator",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["created"] is False


# ---------------------------------------------------------------------------
# Acceptance check 6: viewer role rejected
# ---------------------------------------------------------------------------


def test_submit_decision_viewer_rejected(client):
    """Acceptance check 6: viewer role cannot record a decision."""
    resp = client.post(
        f"/drafts/{DRAFT_ID}/decision",
        json={
            "status": "approved",
            "reviewer_id": "reviewer:viewer-001",
            "reviewer_role": "viewer",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Acceptance check 7: invalid status rejected
# ---------------------------------------------------------------------------


def test_submit_decision_invalid_status(client):
    """Acceptance check 7: unlocked status is rejected at the API layer."""
    resp = client.post(
        f"/drafts/{DRAFT_ID}/decision",
        json={
            "status": "pending",
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": "operator",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Acceptance check 8: 404 for unknown draft
# ---------------------------------------------------------------------------


def test_submit_decision_404_unknown_draft(client):
    """Acceptance check 8: decision submission for unknown draft returns 404."""
    resp = client.post(
        "/drafts/draft:does-not-exist/decision",
        json={
            "status": "approved",
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": "operator",
        },
    )
    assert resp.status_code == 404
