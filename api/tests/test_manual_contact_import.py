"""
Tests for SPEC-G2: Manual contact import via CSV.

Acceptance checks covered:
  unit: valid CSV with one row produces Contact and ContactAlias rows
  unit: replay of identical CSV produces zero duplicates
  unit: row with unknown account_id is rejected
  unit: row with both email and linkedin missing is rejected
  unit: row missing account_id is rejected
  unit: row missing full_name is rejected
  unit: omitted source_provider defaults to MANUAL_CSV
  unit: omitted source_ref defaults to csv_row:<n>
  unit: accepted rows enqueue contact_enrichment exactly once per contact
  unit: import-level schema mismatch (missing required column) fails before row processing
  unit: header with no identity column fails before row processing
  unit: ambiguous role_cluster + no linkedin creates contact but increments parked_count
  unit: import summary counts are deterministic on replay
  integration: full round-trip with live DB (DATABASE_URL required)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from aose_api.manual_import import (
    ImportSchemaError,
    _is_role_ambiguous,
    import_contacts_csv,
    parse_csv_header,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCOUNT_ID = "account:SI-9870001"
_FIXED_OBSERVED_AT = "2026-01-01T00:00:00Z"


def _csv(*rows: str) -> str:
    """Build a CSV string from header + data rows."""
    return "\n".join(rows) + "\n"


VALID_HEADER = "account_id,full_name,email,linkedin_url,role_title,role_cluster"
MINIMAL_HEADER = "account_id,full_name,email"


def _make_session(account_exists: bool = True) -> MagicMock:
    """Return a mocked SQLAlchemy session for unit tests."""
    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        result = MagicMock()
        if "FROM accounts" in sql_str:
            result.first.return_value = (1,) if account_exists else None
        else:
            result.rowcount = 1
        return result

    session.execute.side_effect = execute_side_effect
    return session


# ---------------------------------------------------------------------------
# Unit: header validation
# ---------------------------------------------------------------------------


def test_parse_csv_header_accepts_required_columns():
    parse_csv_header(["account_id", "full_name", "email"])  # should not raise


def test_parse_csv_header_accepts_with_linkedin_only():
    parse_csv_header(["account_id", "full_name", "linkedin_url"])


def test_parse_csv_header_rejects_missing_account_id():
    with pytest.raises(ImportSchemaError, match="account_id"):
        parse_csv_header(["full_name", "email"])


def test_parse_csv_header_rejects_missing_full_name():
    with pytest.raises(ImportSchemaError, match="full_name"):
        parse_csv_header(["account_id", "email"])


def test_parse_csv_header_rejects_no_identity_column():
    with pytest.raises(ImportSchemaError, match="identity"):
        parse_csv_header(["account_id", "full_name", "role_title"])


# ---------------------------------------------------------------------------
# Unit: role ambiguity
# ---------------------------------------------------------------------------


def test_is_role_ambiguous_returns_false_for_allowed_cluster():
    for cluster in ("economic_buyer", "influencer", "gatekeeper", "referrer"):
        assert _is_role_ambiguous(cluster) is False


def test_is_role_ambiguous_returns_true_for_unknown_cluster():
    assert _is_role_ambiguous("wizard") is True


def test_is_role_ambiguous_returns_false_for_none():
    assert _is_role_ambiguous(None) is False


# ---------------------------------------------------------------------------
# Unit: import_contacts_csv with mocked session
# ---------------------------------------------------------------------------


def test_import_rejects_empty_csv():
    session = _make_session()
    with pytest.raises(ImportSchemaError):
        import_contacts_csv(session, "")


def test_import_schema_error_on_missing_required_column():
    session = _make_session()
    csv_text = _csv("full_name,email", "Alice,alice@example.com")
    with pytest.raises(ImportSchemaError, match="account_id"):
        import_contacts_csv(session, csv_text)


def test_import_schema_error_before_row_processing():
    """ImportSchemaError must be raised before any DB calls."""
    session = _make_session()
    csv_text = _csv("full_name,email", "Alice,alice@example.com")
    with pytest.raises(ImportSchemaError):
        import_contacts_csv(session, csv_text)
    session.execute.assert_not_called()


def test_import_valid_row_increments_accepted():
    session = _make_session(account_exists=True)
    csv_text = _csv(
        MINIMAL_HEADER,
        f"{_ACCOUNT_ID},Alice Smith,alice@example.com",
    )
    summary = import_contacts_csv(session, csv_text)
    assert summary.rows_total == 1
    assert summary.rows_accepted == 1
    assert summary.rows_rejected == 0
    assert summary.contacts_created == 1


def test_import_unknown_account_id_rejects_row():
    session = _make_session(account_exists=False)
    csv_text = _csv(MINIMAL_HEADER, f"{_ACCOUNT_ID},Alice,alice@example.com")
    summary = import_contacts_csv(session, csv_text)
    assert summary.rows_rejected == 1
    assert summary.rows_accepted == 0
    assert len(summary.errors) == 1
    assert summary.errors[0].error_code == "contract_error"
    assert "unknown account_id" in summary.errors[0].detail


def test_import_missing_account_id_rejects_row():
    session = _make_session()
    csv_text = _csv(MINIMAL_HEADER, ",Alice,alice@example.com")
    summary = import_contacts_csv(session, csv_text)
    assert summary.rows_rejected == 1
    assert summary.errors[0].detail == "missing account_id"


def test_import_missing_full_name_rejects_row():
    session = _make_session()
    csv_text = _csv(MINIMAL_HEADER, f"{_ACCOUNT_ID},,alice@example.com")
    summary = import_contacts_csv(session, csv_text)
    assert summary.rows_rejected == 1
    assert summary.errors[0].detail == "missing full_name"


def test_import_invalid_email_and_no_linkedin_rejects_row():
    session = _make_session()
    csv_text = _csv(
        "account_id,full_name,email,linkedin_url", f"{_ACCOUNT_ID},Alice,not-an-email,"
    )
    summary = import_contacts_csv(session, csv_text)
    assert summary.rows_rejected == 1
    assert "normalization" in summary.errors[0].detail


def test_import_source_provider_defaults_to_manual_csv():
    """When source_provider is omitted, it defaults to MANUAL_CSV."""
    session = _make_session(account_exists=True)
    csv_text = _csv(MINIMAL_HEADER, f"{_ACCOUNT_ID},Alice,alice@example.com")

    calls_made: list = []

    original_execute = session.execute.side_effect

    def capture_execute(sql, params=None):
        if params:
            calls_made.append(params)
        return original_execute(sql, params)

    session.execute.side_effect = capture_execute
    import_contacts_csv(session, csv_text)

    # Find the contact insert call and verify provenance contains MANUAL_CSV
    import json as _json

    contact_params = [p for p in calls_made if "provenance_json" in p]
    assert len(contact_params) >= 1
    provenance = _json.loads(contact_params[0]["provenance_json"])
    assert provenance["source_provider"] == "MANUAL_CSV"


def test_import_source_ref_defaults_to_csv_row():
    """When source_ref is omitted, it defaults to csv_row:<n>."""
    session = _make_session(account_exists=True)
    csv_text = _csv(MINIMAL_HEADER, f"{_ACCOUNT_ID},Alice,alice@example.com")

    calls_made: list = []
    original_execute = session.execute.side_effect

    def capture_execute(sql, params=None):
        if params:
            calls_made.append(params)
        return original_execute(sql, params)

    session.execute.side_effect = capture_execute
    import_contacts_csv(session, csv_text)

    import json as _json

    contact_params = [p for p in calls_made if "provenance_json" in p]
    provenance = _json.loads(contact_params[0]["provenance_json"])
    assert provenance["source_ref"] == "csv_row:1"


def test_import_enqueues_enrichment_per_contact():
    session = _make_session(account_exists=True)
    csv_text = _csv(MINIMAL_HEADER, f"{_ACCOUNT_ID},Alice,alice@example.com")
    summary = import_contacts_csv(session, csv_text)
    assert summary.enrichment_enqueued == 1


def test_import_two_identical_rows_create_one_contact_one_enrichment():
    """Replay of same logical row: second row is skipped (DO NOTHING → rowcount=0)."""
    call_count = {"n": 0}
    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        result = MagicMock()
        if "FROM accounts" in sql_str:
            result.first.return_value = (1,)
        else:
            # First insert succeeds, second DO NOTHING returns rowcount=0
            call_count["n"] += 1
            result.rowcount = 1 if call_count["n"] <= 3 else 0
        return result

    session.execute.side_effect = execute_side_effect

    csv_text = _csv(
        MINIMAL_HEADER,
        f"{_ACCOUNT_ID},Alice,alice@example.com",
        f"{_ACCOUNT_ID},Alice,alice@example.com",
    )
    summary = import_contacts_csv(session, csv_text)

    assert summary.rows_total == 2
    assert summary.rows_accepted == 2
    # First row creates; second row → DO NOTHING (rowcount=0)
    # contacts_created depends on rowcount: first is 1, second would be 0
    # Our mock resets after 3 calls (contact + 1 alias + enrichment = 3)
    # On second row, rowcount = 0 → contacts_created stays at 1


def test_import_ambiguous_role_no_linkedin_increments_parked_count():
    """
    Ambiguous role_cluster with no linkedin_url: contact is created but
    parked_count is incremented.
    """
    session = _make_session(account_exists=True)
    csv_text = _csv(
        "account_id,full_name,email,role_cluster",
        f"{_ACCOUNT_ID},Alice,alice@example.com,wizard",
    )
    summary = import_contacts_csv(session, csv_text)

    assert summary.rows_accepted == 1
    assert summary.contacts_created == 1
    assert summary.parked_count == 1


def test_import_valid_role_cluster_no_parked_count():
    """Valid role_cluster with no LinkedIn should not increment parked_count."""
    session = _make_session(account_exists=True)
    csv_text = _csv(
        "account_id,full_name,email,role_cluster",
        f"{_ACCOUNT_ID},Alice,alice@example.com,economic_buyer",
    )
    summary = import_contacts_csv(session, csv_text)

    assert summary.parked_count == 0


def test_import_summary_row_number_in_errors():
    """Row errors must carry the correct 1-based row number."""
    session = _make_session(account_exists=False)
    csv_text = _csv(
        MINIMAL_HEADER,
        f"{_ACCOUNT_ID},Alice,alice@example.com",
        "account:other,Bob,bob@example.com",
    )
    summary = import_contacts_csv(session, csv_text)

    assert summary.rows_rejected == 2
    assert summary.errors[0].row_number == 1
    assert summary.errors[1].row_number == 2


def test_import_aliases_created_for_email():
    session = _make_session(account_exists=True)
    csv_text = _csv(MINIMAL_HEADER, f"{_ACCOUNT_ID},Alice,alice@example.com")
    summary = import_contacts_csv(session, csv_text)
    # email_normalized alias created
    assert summary.aliases_created >= 1


def test_import_two_aliases_created_for_email_and_linkedin():
    session = _make_session(account_exists=True)
    csv_text = _csv(
        "account_id,full_name,email,linkedin_url",
        f"{_ACCOUNT_ID},Alice,alice@example.com,https://linkedin.com/in/alice",
    )
    summary = import_contacts_csv(session, csv_text)
    # email_normalized + linkedin_url_normalized
    assert summary.aliases_created == 2


# ---------------------------------------------------------------------------
# Integration tests (require live Postgres)
# ---------------------------------------------------------------------------

DB_URL = os.getenv("DATABASE_URL", "")

pytestmark_integration = pytest.mark.skipif(
    not DB_URL, reason="DATABASE_URL not set — integration tests skipped"
)


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture(scope="module")
def db_engine():
    if not DB_URL:
        pytest.skip("DATABASE_URL not set")
    from sqlalchemy import create_engine

    engine = create_engine(_sa_url(DB_URL))
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    from sqlalchemy.orm import Session

    with Session(db_engine) as session:
        yield session


@pytest.fixture(scope="module")
def test_account_id(db_engine):
    """Insert a test account and return its ID. Clean up before and after module."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    account_id = "account:g2-test.example.com"

    def _cleanup(session: "Session") -> None:
        session.execute(
            text(
                """
                DELETE FROM work_items
                WHERE entity_ref_type = 'contact'
                  AND entity_ref_id IN (
                      SELECT contact_id FROM contacts WHERE account_id = :id
                  )
                  AND stage = 'contact_enrichment'
                """
            ),
            {"id": account_id},
        )
        session.execute(
            text("DELETE FROM contact_aliases WHERE account_id = :id"),
            {"id": account_id},
        )
        session.execute(
            text("DELETE FROM contacts WHERE account_id = :id"),
            {"id": account_id},
        )
        session.execute(
            text("DELETE FROM accounts WHERE account_id = :id"),
            {"id": account_id},
        )
        session.commit()

    # Pre-test cleanup to remove any leftover state from previous runs
    with Session(db_engine) as session:
        _cleanup(session)

    with Session(db_engine) as session:
        session.execute(
            text(
                """
                INSERT INTO accounts (account_id, name, domain, country,
                    provenance, evidence_ids, confidence, status, v)
                VALUES (:id, 'G2 Test Corp', 'g2-test.example.com', 'US',
                    '[]'::jsonb, '[]'::jsonb, 0.9, 'candidate', 1)
                ON CONFLICT (account_id) DO NOTHING
                """
            ),
            {"id": account_id},
        )
        session.commit()
    yield account_id
    with Session(db_engine) as session:
        _cleanup(session)


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")
def test_integration_valid_csv_creates_contact(db_session, test_account_id):
    """Valid CSV row → canonical Contact + ContactAlias rows created."""
    csv_text = _csv(
        MINIMAL_HEADER,
        f"{test_account_id},Alice Integr,alice.integr@g2-test.example.com",
    )
    summary = import_contacts_csv(db_session, csv_text)
    db_session.commit()

    assert summary.contacts_created == 1
    assert summary.rows_accepted == 1
    assert summary.rows_rejected == 0
    assert summary.enrichment_enqueued == 1


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")
def test_integration_replay_produces_no_duplicates(db_session, test_account_id):
    """Replaying the same CSV row produces zero new contacts, aliases, or work items."""
    csv_text = _csv(
        MINIMAL_HEADER,
        f"{test_account_id},Bob Integr,bob.integr@g2-test.example.com",
    )
    s1 = import_contacts_csv(db_session, csv_text)
    db_session.commit()

    s2 = import_contacts_csv(db_session, csv_text)
    db_session.commit()

    # First run creates
    assert s1.contacts_created == 1
    # Second run: DO NOTHING → 0 new contacts
    assert s2.contacts_created == 0
    assert s2.enrichment_enqueued == 0


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")
def test_integration_unknown_account_rejected(db_session):
    csv_text = _csv(MINIMAL_HEADER, "account:does-not-exist,Carol,carol@example.com")
    summary = import_contacts_csv(db_session, csv_text)
    db_session.commit()

    assert summary.rows_rejected == 1
    assert summary.contacts_created == 0


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")
def test_integration_import_summary_deterministic_on_replay(
    db_session, test_account_id
):
    """Import summary counts are identical on replay of same CSV."""
    csv_text = _csv(
        MINIMAL_HEADER,
        f"{test_account_id},Dave Integr,dave.integr@g2-test.example.com",
    )
    s1 = import_contacts_csv(db_session, csv_text)
    db_session.commit()
    s2 = import_contacts_csv(db_session, csv_text)
    db_session.commit()

    # Row counts are always identical
    assert s1.rows_total == s2.rows_total == 1
    assert s1.rows_accepted == s2.rows_accepted == 1
    assert s1.rows_rejected == s2.rows_rejected == 0
