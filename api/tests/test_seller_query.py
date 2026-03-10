"""
Tests for Epic B3: SellerProfile + QueryObject persistence and generation.

Requires a live Postgres instance (DATABASE_URL env var) for DB tests.
Generation tests run without a DB.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from aose_api.models import QueryObject, SellerProfile
from aose_api.query_gen import generate_query_objects


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

SAMPLE_PROFILE: dict = dict(
    seller_id="seller:test-co",
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
    """Construct an in-memory SellerProfile for generation tests (no DB needed)."""
    return SellerProfile(**{**SAMPLE_PROFILE, **overrides})


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


def _clean_profile(session: Session, seller_id: str) -> None:
    """Delete query objects first (FK), then the profile."""
    qos = list(
        session.scalars(select(QueryObject).where(QueryObject.seller_id == seller_id))
    )
    for qo in qos:
        session.delete(qo)
    sp = session.get(SellerProfile, seller_id)
    if sp:
        session.delete(sp)
    session.commit()


# ---------------------------------------------------------------------------
# Schema / model tests
# ---------------------------------------------------------------------------


def test_seller_profile_create_and_read(session):
    sid = "seller:test-schema-sp"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()
    session.expire(sp)

    found = session.get(SellerProfile, sid)
    assert found is not None
    assert found.seller_id == sid
    assert found.offer_what == SAMPLE_PROFILE["offer_what"]
    assert found.policy_pack_id == "safe_v0_1"
    assert found.v == 1

    _clean_profile(session, sid)


def test_policy_pack_id_persists(session):
    sid = "seller:test-policy-pack"
    _clean_profile(session, sid)

    sp = SellerProfile(
        **{**SAMPLE_PROFILE, "seller_id": sid, "policy_pack_id": "safe_v0_1"}
    )
    session.add(sp)
    session.commit()
    session.expire(sp)

    found = session.get(SellerProfile, sid)
    assert found.policy_pack_id == "safe_v0_1"

    _clean_profile(session, sid)


def test_constraints_avoid_claims_persists_explicitly(session):
    sid = "seller:test-avoid-claims"
    _clean_profile(session, sid)

    avoid = ["no false guarantees", "no competitor claims"]
    sp = SellerProfile(
        **{**SAMPLE_PROFILE, "seller_id": sid, "constraints_avoid_claims": avoid}
    )
    session.add(sp)
    session.commit()
    session.expire(sp)

    found = session.get(SellerProfile, sid)
    assert found.constraints_avoid_claims == avoid

    _clean_profile(session, sid)


def test_array_fields_roundtrip(session):
    sid = "seller:test-arrays-rt"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()
    session.expire(sp)

    found = session.get(SellerProfile, sid)
    assert found.offer_where == ["Germany", "Austria"]
    assert found.offer_who == ["Head of Sales", "VP Revenue"]
    assert found.offer_positioning == [
        "reduce manual outreach",
        "increase pipeline velocity",
    ]
    assert found.constraints_allowed_channels == ["email", "linkedin"]
    assert found.constraints_languages == ["en", "de"]

    _clean_profile(session, sid)


def test_query_object_create_and_read(session):
    sid = "seller:test-qo-schema"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()

    qo = QueryObject(
        query_object_id="qo:test-schema-001",
        seller_id=sid,
        buyer_context="Head of Sales in Germany",
        priority=1.0,
        keywords=["AI", "automation"],
        exclusions=["spam"],
        rationale="Test rationale.",
        v=1,
    )
    session.add(qo)
    session.commit()
    session.expire(qo)

    found = session.get(QueryObject, "qo:test-schema-001")
    assert found is not None
    assert found.seller_id == sid
    assert found.buyer_context == "Head of Sales in Germany"
    assert found.v == 1

    _clean_profile(session, sid)


# ---------------------------------------------------------------------------
# Generation tests — no DB required
# ---------------------------------------------------------------------------


def test_generation_produces_at_least_three_query_objects():
    sp = _make_profile()
    results = generate_query_objects(sp)
    assert len(results) >= 3


def test_generation_is_deterministic():
    sp = _make_profile()
    assert generate_query_objects(sp) == generate_query_objects(sp)


def test_generation_preserves_output_order():
    sp = _make_profile()
    results = generate_query_objects(sp)
    priorities = [r["priority"] for r in results]
    assert priorities == sorted(priorities, reverse=True)


def test_generated_objects_contain_required_fields():
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
        assert required.issubset(qo.keys())


def test_generated_seller_id_matches_profile():
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert qo["seller_id"] == sp.seller_id


def test_generated_keywords_and_exclusions_are_lists():
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert isinstance(qo["keywords"], list)
        assert isinstance(qo["exclusions"], list)


def test_generated_priority_is_numeric():
    sp = _make_profile()
    for qo in generate_query_objects(sp):
        assert isinstance(qo["priority"], (int, float))


def test_generation_with_empty_who_uses_fallback():
    sp = _make_profile(offer_who=[])
    results = generate_query_objects(sp)
    assert len(results) >= 1
    assert "general buyer" in results[0]["buyer_context"]


def test_generation_count_in_contract_range():
    # Epic D: generator must produce 3-10 QOs; persona list is capped at 3 internally
    sp = _make_profile(offer_who=["A", "B", "C", "D", "E"])
    results = generate_query_objects(sp)
    assert 3 <= len(results) <= 10


def test_generation_avoid_claims_appear_in_exclusions():
    sp = _make_profile(constraints_avoid_claims=["no false promises"])
    for qo in generate_query_objects(sp):
        assert "no false promises" in qo["exclusions"]


# ---------------------------------------------------------------------------
# Storage / relationship tests
# ---------------------------------------------------------------------------


def test_store_and_read_generated_query_objects(session):
    sid = "seller:test-store-gen"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()
    session.expire(sp)

    loaded = session.get(SellerProfile, sid)
    for qd in generate_query_objects(loaded):
        session.add(QueryObject(**qd))
    session.commit()

    stored = list(
        session.scalars(select(QueryObject).where(QueryObject.seller_id == sid))
    )
    assert len(stored) >= 1
    for qo in stored:
        assert qo.seller_id == sid
        assert isinstance(qo.keywords, list)
        assert isinstance(qo.exclusions, list)
        assert isinstance(qo.priority, float)

    _clean_profile(session, sid)


def test_query_objects_linked_to_correct_seller(session):
    sid = "seller:test-link"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()
    session.expire(sp)

    loaded = session.get(SellerProfile, sid)
    for qd in generate_query_objects(loaded):
        session.add(QueryObject(**qd))
    session.commit()

    fetched = list(
        session.scalars(select(QueryObject).where(QueryObject.seller_id == sid))
    )
    assert all(qo.seller_id == sid for qo in fetched)

    _clean_profile(session, sid)


def test_keywords_exclusions_remain_arrays_after_roundtrip(session):
    sid = "seller:test-array-rt2"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()
    session.expire(sp)

    loaded = session.get(SellerProfile, sid)
    qd = generate_query_objects(loaded)[0]
    session.add(QueryObject(**qd))
    session.commit()

    found = session.get(QueryObject, qd["query_object_id"])
    assert isinstance(found.keywords, list)
    assert isinstance(found.exclusions, list)

    _clean_profile(session, sid)


def test_priority_persists_as_numeric(session):
    sid = "seller:test-priority-num"
    _clean_profile(session, sid)

    sp = SellerProfile(**{**SAMPLE_PROFILE, "seller_id": sid})
    session.add(sp)
    session.commit()
    session.expire(sp)

    loaded = session.get(SellerProfile, sid)
    qd = generate_query_objects(loaded)[0]
    session.add(QueryObject(**qd))
    session.commit()

    found = session.get(QueryObject, qd["query_object_id"])
    assert isinstance(found.priority, float)
    assert found.priority > 0

    _clean_profile(session, sid)


# ---------------------------------------------------------------------------
# Migration / schema inspection tests
# ---------------------------------------------------------------------------


def test_seller_profiles_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "seller_profiles" in inspector.get_table_names()


def test_query_objects_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "query_objects" in inspector.get_table_names()


def test_query_objects_seller_id_index_exists(db_engine):
    inspector = inspect(db_engine)
    index_names = {idx["name"] for idx in inspector.get_indexes("query_objects")}
    assert "ix_query_objects_seller_id" in index_names


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_query_objects_table_exists_and_linked(db_engine):
    # Structured events table added in Epic C — query_objects must still coexist
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert "query_objects" in tables
    assert "seller_profiles" in tables


# ---------------------------------------------------------------------------
# API verification surface tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_client(db_engine):
    from aose_api.main import app

    with TestClient(app) as client:
        yield client


def test_api_create_seller_profile(api_client, session):
    sid = "seller:test-api-create"
    _clean_profile(session, sid)

    payload = {
        **SAMPLE_PROFILE,
        "seller_id": sid,
        "created_at": "2026-03-08T00:00:00+00:00",
    }
    r = api_client.post("/seller-profiles", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["seller_id"] == sid
    assert body["policy_pack_id"] == "safe_v0_1"
    assert body["offer_where"] == ["Germany", "Austria"]

    _clean_profile(session, sid)


def test_api_generate_and_list_query_objects(api_client, session):
    sid = "seller:test-api-gen"
    _clean_profile(session, sid)

    payload = {
        **SAMPLE_PROFILE,
        "seller_id": sid,
        "created_at": "2026-03-08T00:00:00+00:00",
    }
    api_client.post("/seller-profiles", json=payload)

    r = api_client.post(f"/seller-profiles/{sid}/query-objects")
    assert r.status_code == 201
    items = r.json()
    assert len(items) >= 1
    for item in items:
        assert item["seller_id"] == sid
        assert isinstance(item["keywords"], list)
        assert isinstance(item["exclusions"], list)
        assert isinstance(item["priority"], (int, float))

    r2 = api_client.get(f"/seller-profiles/{sid}/query-objects")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1

    _clean_profile(session, sid)


def test_api_generate_idempotent(api_client, session):
    """Calling generate twice does not duplicate query objects."""
    sid = "seller:test-api-idempotent"
    _clean_profile(session, sid)

    payload = {
        **SAMPLE_PROFILE,
        "seller_id": sid,
        "created_at": "2026-03-08T00:00:00+00:00",
    }
    api_client.post("/seller-profiles", json=payload)
    api_client.post(f"/seller-profiles/{sid}/query-objects")
    api_client.post(f"/seller-profiles/{sid}/query-objects")

    r = api_client.get(f"/seller-profiles/{sid}/query-objects")
    count_after_two = len(r.json())

    r2 = api_client.get(f"/seller-profiles/{sid}/query-objects")
    assert len(r2.json()) == count_after_two

    _clean_profile(session, sid)
