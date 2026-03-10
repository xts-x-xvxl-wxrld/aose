"""
Tests for SPEC-G3: Contact enrichment v0.

Acceptance checks covered:
  unit: email_validator — syntax check passes for valid email
  unit: email_validator — syntax check fails for malformed email
  unit: email_validator — validate_email returns unverified for bad syntax
  unit: email_validator — validate_email returns syntax_ok when dns_check=False
  unit: email_validator — validate_email raises TransientDnsError on timeout
  unit: email_validator — validation_level_gte ordering
  unit: email_validator — higher_validation_level returns max of two levels
  unit: channel_policy — is_free_email_domain detects free-email domains
  unit: channel_policy — is_generic_mailbox detects role-address local parts
  unit: channel_policy — is_send_blocked combines both checks
  unit: channel_policy — corporate email is not send-blocked
  unit: service — no email channel → route=no_signal
  unit: service — email syntax fail → route=no_signal (stays unverified)
  unit: service — domain_ok email with no policy block → route=copy_generate
  unit: service — free-email domain → route=policy_blocked
  unit: service — generic mailbox → route=policy_blocked
  unit: service — domain_ok + ambiguous role + no LinkedIn → route=needs_human
  unit: service — domain_ok + ambiguous role + LinkedIn alias → route=copy_generate
  unit: service — replay: copy_generate enqueued=False when ON CONFLICT hits
  unit: service — Contact not found → ValueError
  unit: service — validation level higher_wins (already domain_ok stays domain_ok)
  unit: copy_generate idempotency key formula
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aose_worker.canonical_ids import make_copy_generate_idempotency_key
from aose_worker.services.channel_policy import (
    is_free_email_domain,
    is_generic_mailbox,
    is_send_blocked,
)
from aose_worker.services.contact_enrichment_service import (
    ROUTE_COPY_GENERATE,
    ROUTE_NEEDS_HUMAN,
    ROUTE_NO_SIGNAL,
    ROUTE_POLICY_BLOCKED,
    run_contact_enrichment,
)
from aose_worker.services.email_validator import (
    TransientDnsError,
    check_email_syntax,
    higher_validation_level,
    validate_email,
    validation_level_gte,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_CONTACT_ID = "contact:account:acme.com:alice@acme.com"
_ACCOUNT_ID = "account:acme.com"

_PARENT_WI = {
    "work_item_id": "wi:parent-001",
    "attempt_budget_remaining": 3,
    "attempt_budget_policy": "standard",
    "trace_run_id": "run:001",
    "trace_correlation_id": "corr:001",
    "trace_policy_pack_id": "safe_v0_1",
}


def _make_contact(
    email: str | None = "alice@acme.com",
    validation_level: str = "unverified",
    role_json: dict | None = None,
) -> dict:
    """Build a minimal contact dict as returned by _load_contact."""
    channels = []
    if email is not None:
        channels.append(
            {
                "type": "email",
                "value": email,
                "validated": validation_level,
                "validated_at": None,
                "source_trace": {},
            }
        )
    return {
        "contact_id": _CONTACT_ID,
        "account_id": _ACCOUNT_ID,
        "full_name": "Alice Smith",
        "channels_json": channels,
        "role_json": role_json,
        "status": "candidate",
    }


def _mock_session(
    contact: dict | None = None,
    has_linkedin_alias: bool = False,
    copy_generate_new_row: bool = True,
    provider_count: int = 1,
) -> MagicMock:
    """
    Return a MagicMock SQLAlchemy session for enrichment service unit tests.

    Configures execute() side effects based on the SQL pattern:
      - FROM contacts (channels_json)  → load_contact result
      - FROM work_items (entity_ref_id) → provider count (G4)
      - FROM contact_aliases           → has_linkedin_alias result
      - UPDATE contacts                → no-op (channels update)
      - INSERT INTO work_items         → copy_generate enqueue result
    """
    if contact is None:
        contact = _make_contact()

    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        mock_result = MagicMock()

        if "FROM contacts" in sql_str and "channels_json" in sql_str:
            if contact is not None:
                mock_row = {k: v for k, v in contact.items()}
                mappings_result = MagicMock()
                mappings_result.first.return_value = mock_row
                mock_result.mappings.return_value = mappings_result
            else:
                mappings_result = MagicMock()
                mappings_result.first.return_value = None
                mock_result.mappings.return_value = mappings_result
        elif "FROM work_items" in sql_str and "entity_ref_id" in sql_str:
            # count_contact_providers (G4)
            mock_result.scalar.return_value = provider_count
        elif "FROM contact_aliases" in sql_str:
            mock_result.first.return_value = MagicMock() if has_linkedin_alias else None
        elif "UPDATE contacts" in sql_str:
            mock_result.rowcount = 1
        elif "INSERT INTO work_items" in sql_str:
            mock_result.rowcount = 1 if copy_generate_new_row else 0
        else:
            mock_result.rowcount = 1

        return mock_result

    session.execute.side_effect = execute_side_effect
    return session


# ---------------------------------------------------------------------------
# email_validator — syntax check
# ---------------------------------------------------------------------------


def test_syntax_valid_email():
    assert check_email_syntax("alice@acme.com") is True


def test_syntax_valid_email_with_subdomain():
    assert check_email_syntax("alice@mail.acme.com") is True


def test_syntax_invalid_no_at():
    assert check_email_syntax("alice-acme.com") is False


def test_syntax_invalid_empty():
    assert check_email_syntax("") is False


def test_syntax_invalid_no_domain():
    assert check_email_syntax("alice@") is False


def test_syntax_invalid_no_dot_in_domain():
    assert check_email_syntax("alice@localhost") is False


# ---------------------------------------------------------------------------
# email_validator — validate_email (dns_check=False)
# ---------------------------------------------------------------------------


def test_validate_email_unverified_for_bad_syntax():
    result = validate_email("not-an-email", dns_check=False)
    assert result == "unverified"


def test_validate_email_syntax_ok_when_no_dns():
    result = validate_email("alice@acme.com", dns_check=False)
    assert result == "syntax_ok"


def test_validate_email_domain_ok_when_resolves():
    with patch(
        "aose_worker.services.email_validator.check_domain_resolves",
        return_value=True,
    ):
        result = validate_email("alice@acme.com", dns_check=True)
    assert result == "domain_ok"


def test_validate_email_syntax_ok_when_domain_nxdomain():
    with patch(
        "aose_worker.services.email_validator.check_domain_resolves",
        return_value=False,
    ):
        result = validate_email("alice@nxdomain-xyz-abc.example", dns_check=True)
    assert result == "syntax_ok"


def test_validate_email_raises_transient_on_timeout():
    with patch(
        "aose_worker.services.email_validator.check_domain_resolves",
        side_effect=TransientDnsError("timeout"),
    ):
        with pytest.raises(TransientDnsError):
            validate_email("alice@acme.com", dns_check=True)


# ---------------------------------------------------------------------------
# email_validator — level ordering
# ---------------------------------------------------------------------------


def test_validation_level_gte_domain_ok_gte_syntax_ok():
    assert validation_level_gte("domain_ok", "syntax_ok") is True


def test_validation_level_gte_unverified_not_gte_syntax_ok():
    assert validation_level_gte("unverified", "syntax_ok") is False


def test_validation_level_gte_same_level():
    assert validation_level_gte("domain_ok", "domain_ok") is True


def test_higher_validation_level_returns_max():
    assert higher_validation_level("syntax_ok", "domain_ok") == "domain_ok"
    assert higher_validation_level("domain_ok", "syntax_ok") == "domain_ok"
    assert higher_validation_level("unverified", "unverified") == "unverified"


# ---------------------------------------------------------------------------
# channel_policy — free-email domain check
# ---------------------------------------------------------------------------


def test_is_free_email_domain_gmail():
    assert is_free_email_domain("user@gmail.com") is True


def test_is_free_email_domain_outlook():
    assert is_free_email_domain("user@outlook.com") is True


def test_is_free_email_domain_corporate_is_false():
    assert is_free_email_domain("user@acme.com") is False


def test_is_free_email_domain_no_at_is_false():
    assert is_free_email_domain("notanemail") is False


# ---------------------------------------------------------------------------
# channel_policy — generic mailbox check
# ---------------------------------------------------------------------------


def test_is_generic_mailbox_info():
    assert is_generic_mailbox("info@acme.com") is True


def test_is_generic_mailbox_sales():
    assert is_generic_mailbox("sales@acme.com") is True


def test_is_generic_mailbox_with_plus_tag():
    assert is_generic_mailbox("info+something@acme.com") is True


def test_is_generic_mailbox_personal_is_false():
    assert is_generic_mailbox("alice@acme.com") is False


def test_is_generic_mailbox_no_at_is_false():
    assert is_generic_mailbox("notanemail") is False


# ---------------------------------------------------------------------------
# channel_policy — combined is_send_blocked
# ---------------------------------------------------------------------------


def test_is_send_blocked_free_email():
    assert is_send_blocked("alice@gmail.com") is True


def test_is_send_blocked_generic_mailbox():
    assert is_send_blocked("info@acme.com") is True


def test_is_send_blocked_corporate_personal_is_false():
    assert is_send_blocked("alice@acme.com") is False


# ---------------------------------------------------------------------------
# copy_generate idempotency key formula
# ---------------------------------------------------------------------------


def test_copy_generate_idempotency_key_formula():
    key = make_copy_generate_idempotency_key(_CONTACT_ID)
    assert key == f"copy:{_CONTACT_ID}:v1"


# ---------------------------------------------------------------------------
# Service unit tests — routing
# ---------------------------------------------------------------------------


def test_service_no_email_channel_routes_no_signal():
    """Contact with no email channel → route=no_signal."""
    contact = _make_contact(email=None)
    session = _mock_session(contact=contact)

    result = run_contact_enrichment(
        session=session,
        contact_id=_CONTACT_ID,
        parent_work_item=_PARENT_WI,
        dns_check=False,
    )

    assert result.route == ROUTE_NO_SIGNAL
    assert result.copy_generate_enqueued is False
    assert result.channel_updated is False


def test_service_bad_syntax_email_routes_no_signal():
    """Email failing syntax check stays unverified → route=no_signal."""
    contact = _make_contact(email="not-valid")
    session = _mock_session(contact=contact)

    result = run_contact_enrichment(
        session=session,
        contact_id=_CONTACT_ID,
        parent_work_item=_PARENT_WI,
        dns_check=False,
    )

    assert result.route == ROUTE_NO_SIGNAL
    assert result.validation_level_after == "unverified"


def test_service_valid_email_no_dns_check_routes_no_signal():
    """Valid syntax but dns_check=False stays at syntax_ok → no_signal."""
    contact = _make_contact(email="alice@acme.com")
    session = _mock_session(contact=contact)

    result = run_contact_enrichment(
        session=session,
        contact_id=_CONTACT_ID,
        parent_work_item=_PARENT_WI,
        dns_check=False,
    )

    # syntax_ok < domain_ok → no_signal
    assert result.route == ROUTE_NO_SIGNAL
    assert result.validation_level_after == "syntax_ok"


def test_service_domain_ok_routes_copy_generate():
    """Email reaching domain_ok with no policy block → route=copy_generate."""
    contact = _make_contact(email="alice@acme.com")
    session = _mock_session(contact=contact)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    assert result.route == ROUTE_COPY_GENERATE
    assert result.copy_generate_enqueued is True
    assert result.validation_level_after == "domain_ok"


def test_service_free_email_domain_routes_policy_blocked():
    """Free-email domain email reaching domain_ok → route=policy_blocked."""
    contact = _make_contact(email="alice@gmail.com")
    session = _mock_session(contact=contact)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    assert result.route == ROUTE_POLICY_BLOCKED
    assert result.copy_generate_enqueued is False


def test_service_generic_mailbox_routes_policy_blocked():
    """Generic mailbox local-part reaching domain_ok → route=policy_blocked."""
    contact = _make_contact(email="info@acme.com")
    session = _mock_session(contact=contact)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    assert result.route == ROUTE_POLICY_BLOCKED
    assert result.copy_generate_enqueued is False


def test_service_ambiguous_role_no_linkedin_routes_needs_human():
    """Ambiguous role_cluster + no LinkedIn alias → route=needs_human."""
    contact = _make_contact(
        email="alice@acme.com",
        role_json={"cluster": "wizard", "title": "Grand Wizard", "confidence": 0.5},
    )
    session = _mock_session(contact=contact, has_linkedin_alias=False)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    assert result.route == ROUTE_NEEDS_HUMAN
    assert result.copy_generate_enqueued is False


def test_service_ambiguous_role_with_linkedin_routes_copy_generate():
    """Ambiguous role_cluster but LinkedIn alias present → route=copy_generate."""
    contact = _make_contact(
        email="alice@acme.com",
        role_json={"cluster": "wizard", "title": "Grand Wizard", "confidence": 0.5},
    )
    session = _mock_session(contact=contact, has_linkedin_alias=True)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    assert result.route == ROUTE_COPY_GENERATE
    assert result.copy_generate_enqueued is True


def test_service_contact_not_found_raises_value_error():
    """Missing contact → ValueError propagates (handler parks as contract_error)."""
    session = MagicMock()
    no_result = MagicMock()
    no_result.mappings.return_value.first.return_value = None
    session.execute.return_value = no_result

    with pytest.raises(ValueError, match="Contact not found"):
        run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=False,
        )


def test_service_replay_idempotent_copy_generate_not_double_enqueued():
    """Replaying enrichment when copy_generate already exists → enqueued=False."""
    contact = _make_contact(email="alice@acme.com")
    # copy_generate_new_row=False simulates ON CONFLICT DO NOTHING (already exists)
    session = _mock_session(contact=contact, copy_generate_new_row=False)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    assert result.route == ROUTE_COPY_GENERATE
    assert result.copy_generate_enqueued is False


def test_service_already_domain_ok_channel_stays_domain_ok():
    """Contact already at domain_ok stays at domain_ok (higher_wins is idempotent)."""
    contact = _make_contact(email="alice@acme.com", validation_level="domain_ok")
    session = _mock_session(contact=contact)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="syntax_ok",  # new check returns lower level
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id=_CONTACT_ID,
            parent_work_item=_PARENT_WI,
            dns_check=True,
        )

    # Higher level (domain_ok) must be preserved
    assert result.validation_level_after == "domain_ok"
    assert result.route == ROUTE_COPY_GENERATE
    assert result.channel_updated is False  # level didn't change
