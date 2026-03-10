"""
Tests for Epic B7: Contact + ContactAlias persistence.

Requires a live Postgres instance (DATABASE_URL env var).
Tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_api.ids import make_contact_id, normalize_email, normalize_linkedin_url
from aose_api.models import (
    Account,
    Contact,
    ContactAlias,
    validate_channels,
    validate_contact_alias_type,
)


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ACCOUNT_ID = "account:SI-9870001"

SAMPLE_CHANNELS = [
    {
        "type": "email",
        "value": "jane.doe@example.si",
        "validated": "domain_ok",
        "validated_at": "2026-03-08T12:00:00Z",
        "source_trace": ["adapter:people_search_a"],
    }
]

SAMPLE_PROVENANCE = [
    {"adapter": "people_search_a", "captured_at": "2026-03-08T12:00:00Z"}
]


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


@pytest.fixture(scope="session")
def seed_account(db_engine):
    """Ensure the anchor account exists for all contact tests."""
    with Session(db_engine) as s:
        if s.get(Account, ACCOUNT_ID) is None:
            acct = Account(
                account_id=ACCOUNT_ID,
                name="Test Corp B7",
                domain=None,
                country="SI",
                provenance=[{"source": "AJPES", "ref": "9870001"}],
                evidence_ids=[],
                confidence=0.9,
                status="candidate",
                v=1,
            )
            s.add(acct)
            s.commit()
    yield


@pytest.fixture
def session(db_engine, seed_account):
    with Session(db_engine) as s:
        yield s


def _clean(session: Session, *contact_ids: str) -> None:
    for cid in contact_ids:
        aliases = (
            session.query(ContactAlias).filter(ContactAlias.contact_id == cid).all()
        )
        for a in aliases:
            session.delete(a)
        row = session.get(Contact, cid)
        if row:
            session.delete(row)
    session.commit()


def _make_email_contact_id(email: str = "jane.doe@example.si") -> str:
    return make_contact_id(account_id=ACCOUNT_ID, email=email)


def _make_linkedin_contact_id(
    linkedin_url: str = "https://www.linkedin.com/in/jane-doe",
) -> str:
    return make_contact_id(account_id=ACCOUNT_ID, linkedin_url=linkedin_url)


# ---------------------------------------------------------------------------
# Pure ID / normalization tests (no DB)
# ---------------------------------------------------------------------------


def test_email_contact_id_uses_normalized_email():
    cid = make_contact_id(account_id=ACCOUNT_ID, email="Jane.Doe@Example.SI")
    assert cid == f"contact:{ACCOUNT_ID}:jane.doe@example.si"


def test_linkedin_fallback_contact_id_is_hash():
    cid = make_contact_id(
        account_id=ACCOUNT_ID,
        linkedin_url="https://www.linkedin.com/in/jane-doe",
    )
    assert cid.startswith(f"contact:{ACCOUNT_ID}:")
    # Must not be a plain URL — it's a sha256 hash
    assert "linkedin.com" not in cid


def test_email_wins_over_linkedin():
    cid_email_only = make_contact_id(account_id=ACCOUNT_ID, email="jane@example.si")
    cid_both = make_contact_id(
        account_id=ACCOUNT_ID,
        email="jane@example.si",
        linkedin_url="https://www.linkedin.com/in/jane-doe",
    )
    assert cid_both == cid_email_only


def test_both_missing_raises():
    with pytest.raises(ValueError):
        make_contact_id(account_id=ACCOUNT_ID)


def test_invalid_email_falls_through_to_linkedin():
    """Malformed email is treated as absent; LinkedIn wins if valid."""
    cid = make_contact_id(
        account_id=ACCOUNT_ID,
        email="not-an-email",
        linkedin_url="https://www.linkedin.com/in/jane-doe",
    )
    assert cid.startswith(f"contact:{ACCOUNT_ID}:")


def test_contact_id_deterministic():
    cid1 = make_contact_id(account_id=ACCOUNT_ID, email="jane.doe@example.si")
    cid2 = make_contact_id(account_id=ACCOUNT_ID, email="jane.doe@example.si")
    assert cid1 == cid2


# ---------------------------------------------------------------------------
# validate_channels tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_validate_channels_accepts_valid_email():
    validate_channels([{"type": "email", "value": "a@b.com", "validated": "domain_ok"}])


def test_validate_channels_accepts_valid_linkedin():
    validate_channels(
        [{"type": "linkedin", "value": "https://...", "validated": "profile_exists"}]
    )


def test_validate_channels_accepts_empty_list():
    validate_channels([])


def test_validate_channels_accepts_no_validated_field():
    validate_channels([{"type": "email", "value": "a@b.com"}])


def test_validate_channels_rejects_invalid_email_level():
    with pytest.raises(ValueError, match="email validation level"):
        validate_channels(
            [{"type": "email", "value": "a@b.com", "validated": "profile_exists"}]
        )


def test_validate_channels_rejects_invalid_linkedin_level():
    with pytest.raises(ValueError, match="linkedin validation level"):
        validate_channels(
            [{"type": "linkedin", "value": "https://...", "validated": "domain_ok"}]
        )


def test_validate_channels_rejects_non_list():
    with pytest.raises(ValueError, match="list"):
        validate_channels({"type": "email"})  # type: ignore[arg-type]


def test_validate_contact_alias_type_accepts_allowed():
    validate_contact_alias_type("email_normalized")
    validate_contact_alias_type("linkedin_url_normalized")


def test_validate_contact_alias_type_rejects_address_normalized():
    with pytest.raises(ValueError):
        validate_contact_alias_type("address_normalized")


def test_validate_contact_alias_type_rejects_invented():
    with pytest.raises(ValueError):
        validate_contact_alias_type("twitter_url")


# ---------------------------------------------------------------------------
# DB: Contact with email
# ---------------------------------------------------------------------------


def test_contact_with_email_stores_successfully(session):
    cid = _make_email_contact_id()
    _clean(session, cid)

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json={
            "cluster": "economic_buyer",
            "title": "Head of Production",
            "confidence": 0.66,
        },
        channels_json=SAMPLE_CHANNELS,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.commit()

    found = session.get(Contact, cid)
    assert found is not None
    assert found.contact_id == cid
    assert found.account_id == ACCOUNT_ID
    assert found.status == "candidate"
    assert found.created_at is not None

    _clean(session, cid)


def test_contact_email_produces_email_based_id(session):
    email = "jane.doe@example.si"
    cid = make_contact_id(account_id=ACCOUNT_ID, email=email)
    _clean(session, cid)

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json=None,
        channels_json=SAMPLE_CHANNELS,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.commit()

    norm = normalize_email(email)
    assert cid == f"contact:{ACCOUNT_ID}:{norm}"

    _clean(session, cid)


# ---------------------------------------------------------------------------
# DB: Contact with LinkedIn fallback
# ---------------------------------------------------------------------------


def test_contact_with_linkedin_stores_successfully(session):
    linkedin = "https://www.linkedin.com/in/jane-doe"
    cid = make_contact_id(account_id=ACCOUNT_ID, linkedin_url=linkedin)
    _clean(session, cid)

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json=None,
        channels_json=[
            {
                "type": "linkedin",
                "value": linkedin,
                "validated": "profile_exists",
                "validated_at": "2026-03-08T12:00:00Z",
                "source_trace": ["adapter:people_search_a"],
            }
        ],
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.commit()

    found = session.get(Contact, cid)
    assert found is not None

    _clean(session, cid)


def test_contact_linkedin_produces_hash_based_id(session):
    linkedin = "https://www.linkedin.com/in/jane-doe"
    cid = make_contact_id(account_id=ACCOUNT_ID, linkedin_url=linkedin)
    _clean(session, cid)

    norm = normalize_linkedin_url(linkedin)
    expected_prefix = f"contact:{ACCOUNT_ID}:"
    assert cid.startswith(expected_prefix)
    assert norm is not None
    assert "linkedin.com" not in cid  # it's a hash, not a URL

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name=None,
        role_json=None,
        channels_json=[],
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.commit()

    _clean(session, cid)


# ---------------------------------------------------------------------------
# DB: Alias storage
# ---------------------------------------------------------------------------


def test_email_alias_stored_when_email_exists(session):
    email = "jane.doe@example.si"
    cid = make_contact_id(account_id=ACCOUNT_ID, email=email)
    _clean(session, cid)

    norm_email = normalize_email(email)
    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json=None,
        channels_json=SAMPLE_CHANNELS,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.flush()

    alias = ContactAlias(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        alias_type="email_normalized",
        alias_value=norm_email,
        v=1,
    )
    session.add(alias)
    session.commit()

    found = session.get(Contact, cid)
    assert len(found.aliases) == 1
    assert found.aliases[0].alias_type == "email_normalized"
    assert found.aliases[0].alias_value == norm_email

    _clean(session, cid)


def test_linkedin_alias_stored_when_linkedin_exists(session):
    linkedin = "https://www.linkedin.com/in/jane-doe"
    cid = make_contact_id(account_id=ACCOUNT_ID, linkedin_url=linkedin)
    _clean(session, cid)

    norm_li = normalize_linkedin_url(linkedin)
    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name=None,
        role_json=None,
        channels_json=[],
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.flush()

    alias = ContactAlias(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        alias_type="linkedin_url_normalized",
        alias_value=norm_li,
        v=1,
    )
    session.add(alias)
    session.commit()

    found = session.get(Contact, cid)
    assert len(found.aliases) == 1
    assert found.aliases[0].alias_type == "linkedin_url_normalized"
    assert found.aliases[0].alias_value == norm_li

    _clean(session, cid)


def test_both_aliases_stored_when_both_exist(session):
    email = "jane.doe@example.si"
    linkedin = "https://www.linkedin.com/in/jane-doe"
    cid = make_contact_id(account_id=ACCOUNT_ID, email=email)
    _clean(session, cid)

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json=None,
        channels_json=SAMPLE_CHANNELS,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.flush()

    for alias_type, alias_value in [
        ("email_normalized", normalize_email(email)),
        ("linkedin_url_normalized", normalize_linkedin_url(linkedin)),
    ]:
        session.add(
            ContactAlias(
                contact_id=cid,
                account_id=ACCOUNT_ID,
                alias_type=alias_type,
                alias_value=alias_value,
                v=1,
            )
        )
    session.commit()

    found = session.get(Contact, cid)
    assert len(found.aliases) == 2
    types = {a.alias_type for a in found.aliases}
    assert types == {"email_normalized", "linkedin_url_normalized"}

    _clean(session, cid)


# ---------------------------------------------------------------------------
# DB: Replay safety
# ---------------------------------------------------------------------------


def test_replay_alias_rejected(session):
    """Re-inserting the same alias row (same PK) must be rejected."""
    email = "jane.doe@example.si"
    cid = make_contact_id(account_id=ACCOUNT_ID, email=email)
    _clean(session, cid)

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json=None,
        channels_json=SAMPLE_CHANNELS,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.flush()

    alias = ContactAlias(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        alias_type="email_normalized",
        alias_value=normalize_email(email),
        v=1,
    )
    session.add(alias)
    session.commit()

    # Try inserting the same alias via a fresh session
    with Session(session.bind) as s2:
        alias2 = ContactAlias(
            contact_id=cid,
            account_id=ACCOUNT_ID,
            alias_type="email_normalized",
            alias_value=normalize_email(email),
            v=1,
        )
        s2.add(alias2)
        with pytest.raises(IntegrityError):
            s2.commit()

    _clean(session, cid)


# ---------------------------------------------------------------------------
# DB: Channels round-trip
# ---------------------------------------------------------------------------


def test_channels_roundtrip(session):
    email = "jane.doe@example.si"
    cid = make_contact_id(account_id=ACCOUNT_ID, email=email)
    _clean(session, cid)


def test_contact_alias_model_rejects_invalid_alias_type(session):
    cid = _make_email_contact_id("bad-alias@example.si")
    _clean(session, cid)

    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Bad Alias",
        role_json=None,
        channels_json=SAMPLE_CHANNELS,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.flush()

    with pytest.raises(ValueError, match="Invalid contact alias type"):
        session.add(
            ContactAlias(
                contact_id=cid,
                account_id=ACCOUNT_ID,
                alias_type="address_normalized",
                alias_value="ljubljana",
                v=1,
            )
        )
        session.flush()
    session.rollback()


def test_contact_model_rejects_invalid_channels_on_insert(session):
    cid = make_contact_id(account_id=ACCOUNT_ID, email="invalid.channels@example.si")
    _clean(session, cid)
    with pytest.raises(ValueError, match="email validation level"):
        Contact(
            contact_id=cid,
            account_id=ACCOUNT_ID,
            full_name="Invalid Channels",
            role_json=None,
            channels_json=[
                {"type": "email", "value": "x@y.com", "validated": "profile_exists"}
            ],
            provenance_json=SAMPLE_PROVENANCE,
            status="candidate",
            v=1,
        )
    session.rollback()

    channels = [
        {
            "type": "email",
            "value": "invalid.channels@example.si",
            "validated": "provider_verified",
            "validated_at": "2026-03-08T12:00:00Z",
            "source_trace": ["adapter:people_search_a"],
        },
        {
            "type": "linkedin",
            "value": "https://www.linkedin.com/in/jane-doe",
            "validated": "profile_exists",
            "validated_at": "2026-03-08T12:00:00Z",
            "source_trace": ["adapter:people_search_a"],
        },
    ]
    c = Contact(
        contact_id=cid,
        account_id=ACCOUNT_ID,
        full_name="Jane Doe",
        role_json=None,
        channels_json=channels,
        provenance_json=SAMPLE_PROVENANCE,
        status="candidate",
        v=1,
    )
    session.add(c)
    session.commit()
    session.expire(c)

    found = session.get(Contact, cid)
    assert found.channels_json == channels
    assert found.channels_json[0]["validated"] == "provider_verified"
    assert found.channels_json[1]["validated"] == "profile_exists"

    _clean(session, cid)


# ---------------------------------------------------------------------------
# Schema inspection tests
# ---------------------------------------------------------------------------


def test_contacts_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "contacts" in inspector.get_table_names()


def test_contact_aliases_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "contact_aliases" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    c_idx = {i["name"] for i in inspector.get_indexes("contacts")}
    ca_idx = {i["name"] for i in inspector.get_indexes("contact_aliases")}
    assert "ix_contacts_account_id" in c_idx
    assert "ix_contact_aliases_contact_id" in ca_idx
    assert "ix_contact_aliases_account_id" in ca_idx
    assert "ix_contact_aliases_account_type_value" in ca_idx


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_no_draft_table(db_engine):
    inspector = inspect(db_engine)
    assert "drafts" not in inspector.get_table_names()


def test_contacts_coexist_with_all_epic_c_tables(db_engine):
    # structured_events was added in Epic C — contacts must still coexist
    tables = inspect(db_engine).get_table_names()
    assert "contacts" in tables
    assert "contact_aliases" in tables
    assert "structured_events" in tables
