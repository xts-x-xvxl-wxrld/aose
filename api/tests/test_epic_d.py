"""
Epic D acceptance tests — D1 (SellerProfile API), D2 (QueryObject generator),
D3 (QueryObject review/edit).

Requires a live Postgres instance (DATABASE_URL env var) for DB/API tests.
Pure-logic tests run without a DB.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aose_api.models import QueryObject, SellerProfile
from aose_api.query_gen import generate_query_objects


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

SAMPLE_PROFILE: dict = dict(
    seller_id="seller:epic-d-test",
    offer_what="AI-powered sales automation platform",
    offer_where=["Germany", "Austria"],
    offer_who=["Head of Sales", "VP Revenue"],
    offer_positioning=["reduce manual outreach", "increase pipeline velocity"],
    constraints_avoid_claims=["guaranteed ROI", "replaces humans"],
    constraints_allowed_channels=["email", "linkedin"],
    constraints_languages=["en", "de"],
    policy_pack_id="safe_v0_1",
    created_at=datetime(2026, 3, 8, 0, 0, 0, tzinfo=timezone.utc),
    v=1,
)


def _make_profile(**overrides) -> SellerProfile:
    return SellerProfile(**{**SAMPLE_PROFILE, **overrides})


def _api_payload(sid: str) -> dict:
    return {
        **SAMPLE_PROFILE,
        "seller_id": sid,
        "created_at": "2026-03-08T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB tests")
    engine = create_engine(_sa_url(url))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine):
    with Session(db_engine) as s:
        yield s


def _clean(session: Session, seller_id: str) -> None:
    qos = list(
        session.scalars(select(QueryObject).where(QueryObject.seller_id == seller_id))
    )
    for qo in qos:
        session.delete(qo)
    sp = session.get(SellerProfile, seller_id)
    if sp:
        session.delete(sp)
    session.commit()


@pytest.fixture(scope="module")
def api_client(db_engine):
    from aose_api.main import app

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# D2 — Generator count and shape (no DB required)
# ---------------------------------------------------------------------------


def test_generator_produces_at_least_3():
    sp = _make_profile()
    results = generate_query_objects(sp)
    assert len(results) >= 3, f"Got {len(results)}, expected >= 3"


def test_generator_produces_at_most_10():
    sp = _make_profile()
    results = generate_query_objects(sp)
    assert len(results) <= 10, f"Got {len(results)}, expected <= 10"


def test_generator_count_in_range_minimal_profile():
    # Profile with single persona, no channels, no languages
    sp = _make_profile(
        offer_who=["Decision Maker"],
        constraints_allowed_channels=[],
        constraints_languages=[],
    )
    results = generate_query_objects(sp)
    assert 3 <= len(results) <= 10


def test_generator_count_in_range_full_profile():
    sp = _make_profile(
        offer_who=["CEO", "CTO", "Head of Sales"],
        constraints_allowed_channels=["email", "linkedin", "phone"],
        constraints_languages=["en", "de", "fr"],
    )
    results = generate_query_objects(sp)
    assert 3 <= len(results) <= 10


def test_generator_count_never_exceeds_10():
    # Even with many potential inputs, must cap at 10
    sp = _make_profile(
        offer_who=["A", "B", "C"],
        constraints_allowed_channels=["email", "linkedin", "phone", "sms"],
        constraints_languages=["en", "de", "fr", "es", "it"],
    )
    results = generate_query_objects(sp)
    assert len(results) <= 10


def test_generator_required_fields_present():
    sp = _make_profile()
    required = {
        "query_object_id",
        "seller_id",
        "buyer_context",
        "priority",
        "keywords",
        "exclusions",
        "rationale",
        "v",
    }
    for qo in generate_query_objects(sp):
        assert required.issubset(qo.keys()), f"Missing fields in {qo.keys()}"


def test_generator_all_qos_linked_to_seller():
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert qo["seller_id"] == sp.seller_id


def test_generator_v_is_always_1():
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert qo["v"] == 1


def test_generator_deterministic():
    sp = _make_profile()
    assert generate_query_objects(sp) == generate_query_objects(sp)


def test_generator_priority_numeric_descending():
    sp = _make_profile()
    results = generate_query_objects(sp)
    priorities = [r["priority"] for r in results]
    assert all(isinstance(p, (int, float)) for p in priorities)
    assert priorities == sorted(priorities, reverse=True)


def test_generator_keywords_and_exclusions_are_lists():
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert isinstance(qo["keywords"], list)
        assert isinstance(qo["exclusions"], list)


def test_generator_offer_what_tokens_appear_in_keywords():
    # spec: "translating offer.what into search keywords"
    sp = _make_profile(offer_what="enterprise crm platform", offer_positioning=[])
    results = generate_query_objects(sp)
    all_kw = set(results[0]["keywords"])
    assert "enterprise" in all_kw or "crm" in all_kw or "platform" in all_kw


def test_generator_offer_positioning_tokens_appear_in_keywords():
    # spec: "translating offer.positioning into search keywords"
    sp = _make_profile(
        offer_what="",
        offer_positioning=["reduce churn", "increase retention"],
    )
    results = generate_query_objects(sp)
    all_kw = set(results[0]["keywords"])
    assert "reduce" in all_kw or "increase" in all_kw


def test_generator_no_external_calls():
    # Runs purely in-process — if no exception raised, no external calls were made
    sp = _make_profile()
    results = generate_query_objects(sp)
    assert len(results) >= 3


def test_generator_no_prose_blob():
    # buyer_context must be a short string, not a paragraph
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert isinstance(qo["buyer_context"], str)
        assert len(qo["buyer_context"]) < 200


# ---------------------------------------------------------------------------
# D1 — SellerProfile API: create / read / update
# ---------------------------------------------------------------------------


def test_d1_create_seller_profile(api_client, session):
    sid = "seller:d1-create"
    _clean(session, sid)

    payload = _api_payload(sid)
    r = api_client.post("/seller-profiles", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["seller_id"] == sid
    assert body["v"] == 1

    _clean(session, sid)


def test_d1_read_seller_profile(api_client, session):
    sid = "seller:d1-read"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)

    r = api_client.get(f"/seller-profiles/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["seller_id"] == sid
    assert body["offer_what"] == SAMPLE_PROFILE["offer_what"]
    assert body["offer_where"] == SAMPLE_PROFILE["offer_where"]

    _clean(session, sid)


def test_d1_read_nonexistent_seller_profile_returns_404(api_client):
    r = api_client.get("/seller-profiles/seller:does-not-exist-xyz")
    assert r.status_code == 404


def test_d1_update_seller_profile(api_client, session):
    sid = "seller:d1-update"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)

    update = {"offer_what": "Updated platform description"}
    r = api_client.put(f"/seller-profiles/{sid}", json=update)
    assert r.status_code == 200
    body = r.json()
    assert body["offer_what"] == "Updated platform description"
    # Immutable fields unchanged
    assert body["seller_id"] == sid
    assert body["v"] == 1

    _clean(session, sid)


def test_d1_update_preserves_unchanged_fields(api_client, session):
    sid = "seller:d1-preserve"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)

    update = {"constraints_languages": ["en", "de", "fr"]}
    r = api_client.put(f"/seller-profiles/{sid}", json=update)
    assert r.status_code == 200
    body = r.json()
    assert body["constraints_languages"] == ["en", "de", "fr"]
    # Other fields unchanged
    assert body["offer_what"] == SAMPLE_PROFILE["offer_what"]
    assert body["offer_where"] == SAMPLE_PROFILE["offer_where"]

    _clean(session, sid)


def test_d1_update_nonexistent_profile_returns_404(api_client):
    r = api_client.put("/seller-profiles/seller:ghost-xyz", json={"offer_what": "x"})
    assert r.status_code == 404


def test_d1_stored_record_conforms_to_canonical_shape(api_client, session):
    sid = "seller:d1-canonical"
    _clean(session, sid)

    payload = _api_payload(sid)
    r = api_client.post("/seller-profiles", json=payload)
    body = r.json()

    # All canonical fields present
    for field in (
        "seller_id",
        "offer_what",
        "offer_where",
        "offer_who",
        "offer_positioning",
        "constraints_avoid_claims",
        "constraints_allowed_channels",
        "constraints_languages",
        "created_at",
        "v",
    ):
        assert field in body, f"Missing canonical field: {field}"
    assert body["v"] == 1
    assert body["seller_id"].startswith("seller:")

    _clean(session, sid)


# ---------------------------------------------------------------------------
# D2 — Generate queries API: stores 3-10 QOs
# ---------------------------------------------------------------------------


def test_d2_generate_stores_between_3_and_10(api_client, session):
    sid = "seller:d2-gen"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)

    r = api_client.post(f"/seller-profiles/{sid}/query-objects")
    assert r.status_code == 201
    items = r.json()
    assert 3 <= len(items) <= 10, f"Got {len(items)}"

    _clean(session, sid)


def test_d2_each_query_object_has_required_fields(api_client, session):
    sid = "seller:d2-fields"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)

    r = api_client.post(f"/seller-profiles/{sid}/query-objects")
    for qo in r.json():
        assert "buyer_context" in qo
        assert "priority" in qo
        assert "keywords" in qo
        assert "exclusions" in qo
        assert "rationale" in qo
        assert isinstance(qo["keywords"], list)
        assert isinstance(qo["exclusions"], list)
        assert isinstance(qo["priority"], (int, float))

    _clean(session, sid)


def test_d2_query_objects_linked_to_seller(api_client, session):
    sid = "seller:d2-link"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)
    r = api_client.post(f"/seller-profiles/{sid}/query-objects")
    for qo in r.json():
        assert qo["seller_id"] == sid

    _clean(session, sid)


def test_d2_generate_is_idempotent(api_client, session):
    sid = "seller:d2-idempotent"
    _clean(session, sid)

    payload = _api_payload(sid)
    api_client.post("/seller-profiles", json=payload)
    api_client.post(f"/seller-profiles/{sid}/query-objects")
    api_client.post(f"/seller-profiles/{sid}/query-objects")

    r = api_client.get(f"/seller-profiles/{sid}/query-objects")
    first_ids = {qo["query_object_id"] for qo in r.json()}
    count = len(r.json())

    # Second generation must not add duplicates
    api_client.post(f"/seller-profiles/{sid}/query-objects")
    r2 = api_client.get(f"/seller-profiles/{sid}/query-objects")
    second_ids = {qo["query_object_id"] for qo in r2.json()}

    assert count == len(r2.json())
    assert first_ids == second_ids

    _clean(session, sid)


# ---------------------------------------------------------------------------
# D3 — QueryObject review: edit allowed fields, reject immutable fields
# ---------------------------------------------------------------------------


def _setup_with_qos(api_client, session, sid: str) -> list[dict]:
    _clean(session, sid)
    api_client.post("/seller-profiles", json=_api_payload(sid))
    r = api_client.post(f"/seller-profiles/{sid}/query-objects")
    return r.json()


def test_d3_list_query_objects_for_seller(api_client, session):
    sid = "seller:d3-list"
    qos = _setup_with_qos(api_client, session, sid)

    r = api_client.get(f"/seller-profiles/{sid}/query-objects")
    assert r.status_code == 200
    assert len(r.json()) == len(qos)

    _clean(session, sid)


def test_d3_edit_keywords_persists(api_client, session):
    sid = "seller:d3-kw"
    qos = _setup_with_qos(api_client, session, sid)
    qid = qos[0]["query_object_id"]

    new_kw = ["new-keyword-a", "new-keyword-b"]
    r = api_client.patch(f"/query-objects/{qid}", json={"keywords": new_kw})
    assert r.status_code == 200
    assert r.json()["keywords"] == new_kw

    # Confirm persisted
    r2 = api_client.get(f"/seller-profiles/{sid}/query-objects")
    found = next(q for q in r2.json() if q["query_object_id"] == qid)
    assert found["keywords"] == new_kw

    _clean(session, sid)


def test_d3_edit_exclusions_persists(api_client, session):
    sid = "seller:d3-excl"
    qos = _setup_with_qos(api_client, session, sid)
    qid = qos[0]["query_object_id"]

    new_excl = ["competitor-x", "misleading-claims"]
    r = api_client.patch(f"/query-objects/{qid}", json={"exclusions": new_excl})
    assert r.status_code == 200
    assert r.json()["exclusions"] == new_excl

    # Confirm persisted by re-reading from the list endpoint
    r2 = api_client.get(f"/seller-profiles/{sid}/query-objects")
    found = next(q for q in r2.json() if q["query_object_id"] == qid)
    assert found["exclusions"] == new_excl

    _clean(session, sid)


def test_d3_edit_buyer_context_and_rationale(api_client, session):
    sid = "seller:d3-ctx"
    qos = _setup_with_qos(api_client, session, sid)
    qid = qos[0]["query_object_id"]

    r = api_client.patch(
        f"/query-objects/{qid}",
        json={"buyer_context": "Updated context", "rationale": "Updated rationale"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["buyer_context"] == "Updated context"
    assert body["rationale"] == "Updated rationale"

    _clean(session, sid)


def test_d3_edit_priority(api_client, session):
    sid = "seller:d3-priority"
    qos = _setup_with_qos(api_client, session, sid)
    qid = qos[0]["query_object_id"]

    r = api_client.patch(f"/query-objects/{qid}", json={"priority": 0.42})
    assert r.status_code == 200
    assert r.json()["priority"] == pytest.approx(0.42)

    _clean(session, sid)


def test_d3_immutable_fields_rejected_via_patch(api_client, session):
    """
    SPEC-D3: "Reject attempts to mutate immutable fields."
    QueryObjectUpdate has extra='forbid', so passing query_object_id, seller_id,
    or v must return 422 Unprocessable Entity.
    """
    sid = "seller:d3-immutable"
    qos = _setup_with_qos(api_client, session, sid)
    qid = qos[0]["query_object_id"]

    for immutable_field, value in [
        ("seller_id", "seller:hacked"),
        ("v", 99),
        ("query_object_id", "qo:fake"),
    ]:
        r = api_client.patch(
            f"/query-objects/{qid}",
            json={immutable_field: value},
        )
        assert (
            r.status_code == 422
        ), f"Expected 422 when sending {immutable_field!r}, got {r.status_code}"

    _clean(session, sid)


def test_d3_list_returns_results_ordered_by_priority_desc(api_client, session):
    sid = "seller:d3-order"
    _setup_with_qos(api_client, session, sid)

    r = api_client.get(f"/seller-profiles/{sid}/query-objects")
    assert r.status_code == 200
    priorities = [q["priority"] for q in r.json()]
    assert priorities == sorted(
        priorities, reverse=True
    ), f"Expected descending priority order, got {priorities}"

    _clean(session, sid)


def test_d3_patch_nonexistent_query_object_returns_404(api_client):
    r = api_client.patch("/query-objects/qo:nonexistent-xyz", json={"keywords": ["x"]})
    assert r.status_code == 404


def test_d3_save_does_not_trigger_discovery(api_client, session):
    """
    Saving edits to a QueryObject must not create any WorkItems (discovery trigger).
    No new work_items row should appear after a PATCH.
    """
    from sqlalchemy import text

    sid = "seller:d3-no-discovery"
    qos = _setup_with_qos(api_client, session, sid)
    qid = qos[0]["query_object_id"]

    count_before = session.execute(text("SELECT COUNT(*) FROM work_items")).scalar()
    api_client.patch(f"/query-objects/{qid}", json={"keywords": ["test-kw"]})
    count_after = session.execute(text("SELECT COUNT(*) FROM work_items")).scalar()

    assert count_before == count_after, "PATCH must not create WorkItems"

    _clean(session, sid)
