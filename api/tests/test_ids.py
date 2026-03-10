"""
Unit tests for aose_api.ids — normalization helpers and canonical ID builders.

All tests verify deterministic, replay-safe outputs against the locked Epic B contract.
"""

import hashlib
import pytest

from aose_api.ids import (
    normalize_domain,
    normalize_email,
    normalize_linkedin_url,
    make_seller_id,
    make_account_id,
    make_contact_id,
    make_evidence_id,
    make_draft_id,
    make_decision_key,
    make_decision_id,
    make_send_id,
    make_send_idempotency_key,
)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# normalize_domain
# ---------------------------------------------------------------------------


class TestNormalizeDomain:
    def test_trims_whitespace(self):
        assert normalize_domain("  example.com  ") == "example.com"

    def test_lowercases(self):
        assert normalize_domain("Example.COM") == "example.com"

    def test_removes_one_leading_www(self):
        assert normalize_domain("www.example.com") == "example.com"

    def test_does_not_remove_double_www(self):
        # Only strip exactly one "www." prefix
        assert normalize_domain("www.www.example.com") == "www.example.com"

    def test_removes_port(self):
        assert normalize_domain("example.com:443") == "example.com"

    def test_strips_trailing_dot(self):
        assert normalize_domain("example.com.") == "example.com"

    def test_parses_full_url_to_host(self):
        assert normalize_domain("https://www.Example.com/path?q=1") == "example.com"

    def test_parses_url_with_port(self):
        assert normalize_domain("http://example.com:8080/foo") == "example.com"

    def test_idna_conversion(self):
        result = normalize_domain("bücher.de")
        assert result == "xn--bcher-kva.de"

    def test_returns_none_for_empty_string(self):
        assert normalize_domain("") is None

    def test_returns_none_for_none(self):
        assert normalize_domain(None) is None

    def test_returns_none_for_whitespace_only(self):
        assert normalize_domain("   ") is None

    def test_url_with_scheme_and_www(self):
        assert (
            normalize_domain("https://www.Example.com/path?q=1#frag") == "example.com"
        )


# ---------------------------------------------------------------------------
# normalize_email
# ---------------------------------------------------------------------------


class TestNormalizeEmail:
    def test_lowercases_local_part(self):
        assert normalize_email("John.Doe@example.com") == "john.doe@example.com"

    def test_preserves_plus_tags(self):
        assert normalize_email("John.Doe+Ops@Example.COM") == "john.doe+ops@example.com"

    def test_preserves_dots_in_local(self):
        result = normalize_email("john.doe@example.com")
        assert result == "john.doe@example.com"

    def test_normalizes_domain(self):
        assert (
            normalize_email(" John.Doe+Ops@Example.COM ") == "john.doe+ops@example.com"
        )

    def test_returns_none_for_no_at(self):
        assert normalize_email("bad-email") is None

    def test_returns_none_for_multiple_at(self):
        assert normalize_email("a@b@c.com") is None

    def test_returns_none_for_none(self):
        assert normalize_email(None) is None

    def test_returns_none_for_empty(self):
        assert normalize_email("") is None

    def test_trims_whitespace(self):
        assert normalize_email("  user@example.com  ") == "user@example.com"


# ---------------------------------------------------------------------------
# normalize_linkedin_url
# ---------------------------------------------------------------------------


class TestNormalizeLinkedinUrl:
    def test_removes_query_string(self):
        result = normalize_linkedin_url("https://www.linkedin.com/in/John-Doe/?trk=abc")
        assert "trk" not in result
        assert "?" not in result

    def test_removes_fragment(self):
        result = normalize_linkedin_url("https://www.linkedin.com/in/John-Doe/#section")
        assert "#" not in result

    def test_removes_trailing_slash(self):
        result = normalize_linkedin_url("https://www.linkedin.com/in/John-Doe/")
        assert not result.endswith("/")

    def test_keeps_identity_path(self):
        result = normalize_linkedin_url("https://www.linkedin.com/in/John-Doe/?trk=abc")
        assert "/in/John-Doe" in result

    def test_lowercases_scheme_and_host(self):
        result = normalize_linkedin_url("HTTPS://WWW.LINKEDIN.COM/in/John-Doe/")
        assert result.startswith("https://www.linkedin.com")

    def test_returns_none_for_none(self):
        assert normalize_linkedin_url(None) is None

    def test_returns_none_for_empty(self):
        assert normalize_linkedin_url("") is None

    def test_stable_canonical_url(self):
        url = "https://www.linkedin.com/in/John-Doe/?trk=abc"
        assert normalize_linkedin_url(url) == "https://www.linkedin.com/in/John-Doe"


# ---------------------------------------------------------------------------
# make_seller_id
# ---------------------------------------------------------------------------


class TestMakeSellerId:
    def test_format(self):
        assert make_seller_id("acme-corp") == "seller:acme-corp"

    def test_deterministic(self):
        assert make_seller_id("acme-corp") == make_seller_id("acme-corp")


# ---------------------------------------------------------------------------
# make_account_id
# ---------------------------------------------------------------------------


class TestMakeAccountId:
    def test_registry_tier(self):
        result = make_account_id(
            "us", "12345678", "example.com", "Example Inc", "clearbit", "cb-1"
        )
        assert result == "account:US-12345678"

    def test_registry_beats_domain(self):
        result = make_account_id("us", "12345678", "example.com", None, None, None)
        assert result == "account:US-12345678"

    def test_domain_tier(self):
        result = make_account_id(None, None, "example.com", None, None, None)
        assert result == "account:example.com"

    def test_domain_beats_tmp(self):
        result = make_account_id(
            None, None, "example.com", "Example Inc", "clearbit", "cb-1"
        )
        assert result == "account:example.com"

    def test_tmp_tier(self):
        expected_hash = sha256("US|Example Inc|clearbit|cb-1")
        result = make_account_id("US", None, None, "Example Inc", "clearbit", "cb-1")
        assert result == f"account:tmp:{expected_hash}"

    def test_tmp_hash_with_all_none(self):
        expected_hash = sha256("|||")
        result = make_account_id(None, None, None, None, None, None)
        assert result == f"account:tmp:{expected_hash}"

    def test_country_uppercased(self):
        result = make_account_id("gb", "R123", None, None, None, None)
        assert result == "account:GB-R123"

    def test_deterministic(self):
        args = ("us", "99", None, None, None, None)
        assert make_account_id(*args) == make_account_id(*args)


# ---------------------------------------------------------------------------
# make_contact_id
# ---------------------------------------------------------------------------


class TestMakeContactId:
    ACCOUNT_ID = "account:example.com"

    def test_email_tier(self):
        result = make_contact_id(self.ACCOUNT_ID, email="john@example.com")
        assert result == f"contact:{self.ACCOUNT_ID}:john@example.com"

    def test_email_beats_linkedin(self):
        result = make_contact_id(
            self.ACCOUNT_ID,
            email="john@example.com",
            linkedin_url="https://www.linkedin.com/in/john",
        )
        assert "john@example.com" in result

    def test_linkedin_tier(self):
        li_url = "https://www.linkedin.com/in/john-doe"
        expected_hash = sha256(li_url)
        result = make_contact_id(self.ACCOUNT_ID, email=None, linkedin_url=li_url)
        assert result == f"contact:{self.ACCOUNT_ID}:{expected_hash}"

    def test_linkedin_normalizes_before_hashing(self):
        # Trailing slash should be stripped before hashing
        result_with_trailing = make_contact_id(
            self.ACCOUNT_ID,
            email=None,
            linkedin_url="https://www.linkedin.com/in/john-doe/",
        )
        result_clean = make_contact_id(
            self.ACCOUNT_ID,
            email=None,
            linkedin_url="https://www.linkedin.com/in/john-doe",
        )
        assert result_with_trailing == result_clean

    def test_raises_when_both_missing(self):
        with pytest.raises(ValueError):
            make_contact_id(self.ACCOUNT_ID, email=None, linkedin_url=None)

    def test_raises_when_both_invalid(self):
        with pytest.raises(ValueError):
            make_contact_id(self.ACCOUNT_ID, email="bad-email", linkedin_url="")

    def test_deterministic(self):
        args = (self.ACCOUNT_ID,)
        kwargs = {"email": "jane@example.com"}
        assert make_contact_id(*args, **kwargs) == make_contact_id(*args, **kwargs)


# ---------------------------------------------------------------------------
# make_evidence_id
# ---------------------------------------------------------------------------


class TestMakeEvidenceId:
    def test_format(self):
        snippet_hash = sha256("some snippet")
        outer = sha256(
            "|".join(
                [
                    "web",
                    "https://example.com/page",
                    "2024-01-01T00:00:00Z",
                    snippet_hash,
                ]
            )
        )
        expected = f"evidence:{outer}"
        result = make_evidence_id(
            "web", "https://example.com/page", "2024-01-01T00:00:00Z", "some snippet"
        )
        assert result == expected

    def test_none_snippet_treated_as_empty_string(self):
        result_none = make_evidence_id(
            "web", "https://example.com", "2024-01-01T00:00:00Z", None
        )
        result_empty = make_evidence_id(
            "web", "https://example.com", "2024-01-01T00:00:00Z", ""
        )
        assert result_none == result_empty

    def test_stable_across_reruns(self):
        args = ("web", "https://example.com", "2024-01-01T00:00:00Z", "text")
        assert make_evidence_id(*args) == make_evidence_id(*args)

    def test_different_snippets_produce_different_ids(self):
        a = make_evidence_id(
            "web", "https://example.com", "2024-01-01T00:00:00Z", "text A"
        )
        b = make_evidence_id(
            "web", "https://example.com", "2024-01-01T00:00:00Z", "text B"
        )
        assert a != b


# ---------------------------------------------------------------------------
# make_draft_id
# ---------------------------------------------------------------------------


class TestMakeDraftId:
    def test_format(self):
        contact_id = "contact:account:example.com:user@example.com"
        result = make_draft_id(contact_id, 1, 2)
        assert result == f"draft:{contact_id}:seq1:v2"

    def test_deterministic(self):
        cid = "contact:account:example.com:user@example.com"
        assert make_draft_id(cid, 3, 1) == make_draft_id(cid, 3, 1)


# ---------------------------------------------------------------------------
# make_decision_key / make_decision_id
# ---------------------------------------------------------------------------


class TestDecision:
    def test_decision_key_format(self):
        expected = sha256("wi-1|c-1|outreach|pp-1|d-1")
        result = make_decision_key("wi-1", "c-1", "outreach", "pp-1", "d-1")
        assert result == expected

    def test_decision_id_format(self):
        key = make_decision_key("wi-1", "c-1", "outreach", "pp-1", "d-1")
        result = make_decision_id("d-1", key)
        assert result == f"decision:d-1:{key}"

    def test_decision_key_deterministic(self):
        args = ("wi-1", "c-1", "outreach", "pp-1", "d-1")
        assert make_decision_key(*args) == make_decision_key(*args)


# ---------------------------------------------------------------------------
# make_send_id / make_send_idempotency_key
# ---------------------------------------------------------------------------


class TestSend:
    def test_send_id_format(self):
        assert make_send_id("draft-1", "email") == "send:draft-1:email"

    def test_send_idempotency_key_format(self):
        assert make_send_idempotency_key("draft-1", "email") == "send:draft-1:email:v1"

    def test_send_id_deterministic(self):
        assert make_send_id("draft-1", "email") == make_send_id("draft-1", "email")

    def test_send_idempotency_key_deterministic(self):
        assert make_send_idempotency_key("d", "sms") == make_send_idempotency_key(
            "d", "sms"
        )


# ---------------------------------------------------------------------------
# Replay-safety / determinism sweep
# ---------------------------------------------------------------------------


class TestReplaySafety:
    """Verify repeated calls with same inputs produce byte-for-byte identical outputs."""

    def test_normalize_domain_replay(self):
        for _ in range(3):
            assert normalize_domain("www.Example.COM") == "example.com"

    def test_normalize_email_replay(self):
        for _ in range(3):
            assert normalize_email("User+Tag@Example.COM") == "user+tag@example.com"

    def test_make_account_id_replay(self):
        args = ("de", "HRB123", None, None, None, None)
        first = make_account_id(*args)
        for _ in range(3):
            assert make_account_id(*args) == first

    def test_make_evidence_id_replay(self):
        args = (
            "rss",
            "https://news.example.com/1",
            "2024-06-01T12:00:00Z",
            "headline text",
        )
        first = make_evidence_id(*args)
        for _ in range(3):
            assert make_evidence_id(*args) == first
