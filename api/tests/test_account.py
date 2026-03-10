"""
Tests for Epic B4: Account + AccountAlias persistence.

Requires a live Postgres instance (DATABASE_URL env var).
Tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_api.ids import make_account_id
from aose_api.models import Account, AccountAlias, validate_account_alias_type


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


def _alias_id(account_id: str, alias_type: str, alias_value: str) -> str:
    digest = hashlib.sha256(
        f"{account_id}|{alias_type}|{alias_value}".encode()
    ).hexdigest()
    return f"alias:{digest}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 8, 12, 0, 0, tzinfo=timezone.utc)

REGISTRY_ACCOUNT_ID = make_account_id(
    country="SI",
    registry_id="1234567",
    domain=None,
    legal_name_normalized=None,
    source_provider=None,
    source_ref=None,
)

DOMAIN_ACCOUNT_ID = make_account_id(
    country=None,
    registry_id=None,
    domain="example.com",
    legal_name_normalized=None,
    source_provider=None,
    source_ref=None,
)

TMP_ACCOUNT_ID = make_account_id(
    country=None,
    registry_id=None,
    domain=None,
    legal_name_normalized="Acme Corp",
    source_provider="manual",
    source_ref="ref-001",
)

SAMPLE_ACCOUNT = dict(
    name="Test Company d.o.o.",
    domain=None,
    country="SI",
    provenance=[{"source": "AJPES", "ref": "1234567", "captured_at": "2026-03-08"}],
    evidence_ids=["evidence:abc123"],
    confidence=0.95,
    status="candidate",
    v=1,
)


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


def _clean_account(session: Session, *account_ids: str) -> None:
    for aid in account_ids:
        # aliases cascade via FK; delete aliases first then account
        aliases = (
            session.query(AccountAlias).filter(AccountAlias.account_id == aid).all()
        )
        for a in aliases:
            session.delete(a)
        row = session.get(Account, aid)
        if row:
            session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# Schema / model tests
# ---------------------------------------------------------------------------


def test_account_create_and_read(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert found is not None
    assert found.account_id == aid
    assert found.name == "Test Company d.o.o."
    assert found.country == "SI"
    assert found.confidence == 0.95
    assert found.status == "candidate"
    assert found.created_at is not None
    assert found.v == 1

    _clean_account(session, aid)


def test_account_alias_create_and_read(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    alias = AccountAlias(
        account_alias_id=_alias_id(aid, "registry", "SI-1234567"),
        account_id=aid,
        alias_type="registry",
        alias_value="SI-1234567",
        source_provider="AJPES",
        source_ref="ref-1234567",
        created_at=NOW,
        v=1,
    )
    session.add(alias)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert len(found.aliases) == 1
    a = found.aliases[0]
    assert a.alias_type == "registry"
    assert a.alias_value == "SI-1234567"
    assert a.source_provider == "AJPES"
    assert a.source_ref == "ref-1234567"

    _clean_account(session, aid)


def test_domain_nullable(session):
    aid = TMP_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "domain": None})
    session.add(account)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert found.domain is None

    _clean_account(session, aid)


def test_provenance_roundtrip(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    provenance = [
        {"source": "AJPES", "ref": "1234567", "captured_at": "2026-03-08"},
        {"source": "manual", "ref": "override", "captured_at": "2026-03-08"},
    ]
    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "provenance": provenance})
    session.add(account)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert found.provenance == provenance

    _clean_account(session, aid)


def test_evidence_ids_roundtrip(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    evidence_ids = ["evidence:abc", "evidence:def", "evidence:ghi"]
    account = Account(
        **{**SAMPLE_ACCOUNT, "account_id": aid, "evidence_ids": evidence_ids}
    )
    session.add(account)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert found.evidence_ids == evidence_ids

    _clean_account(session, aid)


# ---------------------------------------------------------------------------
# Relationship tests
# ---------------------------------------------------------------------------


def test_aliases_linked_to_account(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    aliases = [
        AccountAlias(
            account_alias_id=_alias_id(aid, "registry", "SI-1234567"),
            account_id=aid,
            alias_type="registry",
            alias_value="SI-1234567",
            source_provider="AJPES",
            source_ref=None,
            created_at=NOW,
            v=1,
        ),
        AccountAlias(
            account_alias_id=_alias_id(aid, "domain", "testcompany.si"),
            account_id=aid,
            alias_type="domain",
            alias_value="testcompany.si",
            source_provider=None,
            source_ref=None,
            created_at=NOW,
            v=1,
        ),
    ]
    for a in aliases:
        session.add(a)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert len(found.aliases) == 2
    types = {a.alias_type for a in found.aliases}
    assert types == {"registry", "domain"}

    _clean_account(session, aid)


def test_aliases_fetchable_by_account_id(session):
    aid = DOMAIN_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "domain": "example.com"})
    session.add(account)
    session.flush()

    alias = AccountAlias(
        account_alias_id=_alias_id(aid, "domain", "example.com"),
        account_id=aid,
        alias_type="domain",
        alias_value="example.com",
        source_provider=None,
        source_ref=None,
        created_at=NOW,
        v=1,
    )
    session.add(alias)
    session.commit()

    rows = session.query(AccountAlias).filter(AccountAlias.account_id == aid).all()
    assert len(rows) == 1
    assert rows[0].alias_value == "example.com"

    _clean_account(session, aid)


# ---------------------------------------------------------------------------
# Alias storage tests
# ---------------------------------------------------------------------------


def test_registry_alias_persists(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    alias = AccountAlias(
        account_alias_id=_alias_id(aid, "registry", "SI-1234567"),
        account_id=aid,
        alias_type="registry",
        alias_value="SI-1234567",
        source_provider="AJPES",
        source_ref="ref-1234567",
        created_at=NOW,
        v=1,
    )
    session.add(alias)
    session.commit()
    session.expire(alias)

    found = session.get(AccountAlias, _alias_id(aid, "registry", "SI-1234567"))
    assert found.alias_type == "registry"
    assert found.alias_value == "SI-1234567"
    assert found.source_provider == "AJPES"
    assert found.source_ref == "ref-1234567"

    _clean_account(session, aid)


def test_domain_alias_persists(session):
    aid = DOMAIN_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "domain": "example.com"})
    session.add(account)
    session.flush()

    alias = AccountAlias(
        account_alias_id=_alias_id(aid, "domain", "example.com"),
        account_id=aid,
        alias_type="domain",
        alias_value="example.com",
        source_provider=None,
        source_ref=None,
        created_at=NOW,
        v=1,
    )
    session.add(alias)
    session.commit()
    session.expire(alias)

    found = session.get(AccountAlias, _alias_id(aid, "domain", "example.com"))
    assert found.alias_type == "domain"
    assert found.alias_value == "example.com"

    _clean_account(session, aid)


def test_legal_name_normalized_alias_persists(session):
    aid = TMP_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "domain": None})
    session.add(account)
    session.flush()

    alias = AccountAlias(
        account_alias_id=_alias_id(aid, "legal_name_normalized", "acme corp"),
        account_id=aid,
        alias_type="legal_name_normalized",
        alias_value="acme corp",
        source_provider=None,
        source_ref=None,
        created_at=NOW,
        v=1,
    )
    session.add(alias)
    session.commit()
    session.expire(alias)

    found = session.get(
        AccountAlias, _alias_id(aid, "legal_name_normalized", "acme corp")
    )
    assert found.alias_type == "legal_name_normalized"
    assert found.alias_value == "acme corp"

    _clean_account(session, aid)


def test_multiple_alias_types_for_same_account(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    for alias_type, alias_value in [
        ("registry", "SI-1234567"),
        ("domain", "testcompany.si"),
        ("legal_name_normalized", "test company doo"),
    ]:
        alias = AccountAlias(
            account_alias_id=_alias_id(aid, alias_type, alias_value),
            account_id=aid,
            alias_type=alias_type,
            alias_value=alias_value,
            source_provider=None,
            source_ref=None,
            created_at=NOW,
            v=1,
        )
        session.add(alias)
    session.commit()
    session.expire(account)

    found = session.get(Account, aid)
    assert len(found.aliases) == 3

    _clean_account(session, aid)


def test_account_confidence_above_one_rejected(session):
    aid = f"{TMP_ACCOUNT_ID}:conf-high"
    _clean_account(session, aid)
    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "confidence": 1.1})
    session.add(account)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_account_confidence_below_zero_rejected(session):
    aid = f"{TMP_ACCOUNT_ID}:conf-low"
    _clean_account(session, aid)
    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid, "confidence": -0.1})
    session.add(account)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_duplicate_alias_rejected(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)


def test_validate_account_alias_type_accepts_locked_values():
    validate_account_alias_type("registry")
    validate_account_alias_type("domain")
    validate_account_alias_type("legal_name_normalized")


def test_validate_account_alias_type_rejects_deferred_or_invented_values():
    with pytest.raises(ValueError):
        validate_account_alias_type("address_normalized")
    with pytest.raises(ValueError):
        validate_account_alias_type("twitter_url")


def test_account_alias_model_rejects_invalid_alias_type(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    with pytest.raises(ValueError, match="Invalid account alias type"):
        session.add(
            AccountAlias(
                account_alias_id=_alias_id(aid, "address_normalized", "ljubljana"),
                account_id=aid,
                alias_type="address_normalized",
                alias_value="ljubljana",
                source_provider=None,
                source_ref=None,
                created_at=NOW,
                v=1,
            )
        )
        session.flush()
    session.rollback()

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    alias1 = AccountAlias(
        account_alias_id=_alias_id(aid, "registry", "SI-1234567"),
        account_id=aid,
        alias_type="registry",
        alias_value="SI-1234567",
        source_provider="AJPES",
        source_ref=None,
        created_at=NOW,
        v=1,
    )
    session.add(alias1)
    session.commit()

    alias2 = AccountAlias(
        account_alias_id="alias:different_id",
        account_id=aid,
        alias_type="registry",
        alias_value="SI-1234567",
        source_provider="OTHER",
        source_ref=None,
        created_at=NOW,
        v=1,
    )
    session.add(alias2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    _clean_account(session, aid)


# ---------------------------------------------------------------------------
# Identity boundary tests
# ---------------------------------------------------------------------------


def test_registry_based_account_can_be_inserted(session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)
    assert aid.startswith("account:SI-")

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.commit()

    found = session.get(Account, aid)
    assert found is not None

    _clean_account(session, aid)


def test_domain_based_account_can_be_inserted(session):
    aid = DOMAIN_ACCOUNT_ID
    _clean_account(session, aid)
    assert aid == "account:example.com"

    account = Account(
        **{
            **SAMPLE_ACCOUNT,
            "account_id": aid,
            "domain": "example.com",
            "country": None,
        }
    )
    session.add(account)
    session.commit()

    found = session.get(Account, aid)
    assert found is not None

    _clean_account(session, aid)


def test_tmp_hash_account_can_be_inserted(session):
    aid = TMP_ACCOUNT_ID
    _clean_account(session, aid)
    assert aid.startswith("account:tmp:")

    account = Account(
        **{**SAMPLE_ACCOUNT, "account_id": aid, "domain": None, "country": None}
    )
    session.add(account)
    session.commit()

    found = session.get(Account, aid)
    assert found is not None

    _clean_account(session, aid)


def test_alias_preserves_data_for_future_merge(session):
    """Alias storage preserves enough data for future identity upgrade."""
    aid = TMP_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(
        **{**SAMPLE_ACCOUNT, "account_id": aid, "domain": None, "country": None}
    )
    session.add(account)
    session.flush()

    # Store a registry alias so a future merge can find the canonical ID
    alias = AccountAlias(
        account_alias_id=_alias_id(aid, "registry", "SI-9999999"),
        account_id=aid,
        alias_type="registry",
        alias_value="SI-9999999",
        source_provider="AJPES",
        source_ref="ref-999",
        created_at=NOW,
        v=1,
    )
    session.add(alias)
    session.commit()

    rows = (
        session.query(AccountAlias)
        .filter(
            AccountAlias.account_id == aid,
            AccountAlias.alias_type == "registry",
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].source_provider == "AJPES"

    _clean_account(session, aid)


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_no_merge_table(db_engine):
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert "account_merges" not in tables
    assert "account_merge_log" not in tables


def test_no_evidences_plural_table(db_engine):
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert (
        "evidences" not in tables
    )  # plural form not used; canonical table is "evidence"


def test_address_normalized_alias_type_not_stored(session):
    """address_normalized alias type must not be accepted or introduced."""
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    account = Account(**{**SAMPLE_ACCOUNT, "account_id": aid})
    session.add(account)
    session.flush()

    # We confirm no row with address_normalized exists after normal operations
    rows = (
        session.query(AccountAlias)
        .filter(
            AccountAlias.account_id == aid,
            AccountAlias.alias_type == "address_normalized",
        )
        .all()
    )
    assert rows == []

    _clean_account(session, aid)


# ---------------------------------------------------------------------------
# Schema inspection tests
# ---------------------------------------------------------------------------


def test_accounts_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "accounts" in inspector.get_table_names()


def test_account_aliases_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "account_aliases" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    account_indexes = {idx["name"] for idx in inspector.get_indexes("accounts")}
    alias_indexes = {idx["name"] for idx in inspector.get_indexes("account_aliases")}
    assert "ix_accounts_domain" in account_indexes
    assert "ix_account_aliases_account_id" in alias_indexes
    assert "ix_account_aliases_alias_type_value" in alias_indexes


def test_account_confidence_check_constraint_exists(db_engine):
    inspector = inspect(db_engine)
    constraints = {c["name"] for c in inspector.get_check_constraints("accounts")}
    assert "ck_accounts_confidence_range" in constraints


# ---------------------------------------------------------------------------
# API verification surface
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_client(db_engine):
    from aose_api.main import app

    with TestClient(app) as client:
        yield client


def test_api_create_and_fetch_account(api_client, session):
    aid = REGISTRY_ACCOUNT_ID
    _clean_account(session, aid)

    body = {
        "account_id": aid,
        "name": "Test Company d.o.o.",
        "domain": None,
        "country": "SI",
        "provenance": [{"source": "AJPES", "ref": "1234567"}],
        "evidence_ids": ["evidence:abc"],
        "confidence": 0.9,
        "status": "candidate",
        "v": 1,
        "aliases": [
            {
                "account_alias_id": _alias_id(aid, "registry", "SI-1234567"),
                "alias_type": "registry",
                "alias_value": "SI-1234567",
                "source_provider": "AJPES",
                "source_ref": "ref-1234567",
                "created_at": "2026-03-08T12:00:00+00:00",
                "v": 1,
            }
        ],
    }
    r = api_client.post("/accounts", json=body)
    assert r.status_code == 201
    out = r.json()
    assert out["account_id"] == aid
    assert out["status"] == "candidate"
    assert out["created_at"]
    assert len(out["aliases"]) == 1
    assert out["aliases"][0]["alias_type"] == "registry"

    r2 = api_client.get(f"/accounts/{aid}")
    assert r2.status_code == 200
    out2 = r2.json()
    assert out2["account_id"] == aid
    assert out2["aliases"][0]["source_provider"] == "AJPES"

    _clean_account(session, aid)


def test_api_get_nonexistent_account_returns_404(api_client):
    r = api_client.get("/accounts/account:does-not-exist-xyz")
    assert r.status_code == 404
