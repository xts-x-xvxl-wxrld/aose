"""
Unit tests for Epic I3 send policy evaluator.
"""

from __future__ import annotations

from aose_worker.services import send_policy_service as sps


class _DummySession:
    pass


def _base_draft() -> dict:
    return {
        "draft_id": "draft:test:seq1:v1",
        "channel": "email",
        "subject": "Hello",
        "body": "Body with {{unsubscribe_token}}",
    }


def _base_contact() -> dict:
    return {
        "contact_id": "contact:test",
        "role_json": {"cluster": "economic_buyer", "title": "Head of Ops"},
        "channels_json": [
            {
                "type": "email",
                "value": "person@acme.example",
                "confidence": 0.9,
                "validated": "domain_ok",
            }
        ],
    }


def _base_account() -> dict:
    return {"account_id": "account:SI-12345", "domain": "acme.example"}


def _allow_all(monkeypatch) -> None:
    monkeypatch.setattr(sps, "_suppression_hit", lambda *a, **k: False)
    monkeypatch.setattr(sps, "_count_send_attempts_since", lambda *a, **k: 0)
    monkeypatch.setattr(sps, "_count_send_attempts_for_domain_since", lambda *a, **k: 0)
    monkeypatch.setattr(sps, "_distinct_evidence_categories", lambda *a, **k: 2)
    monkeypatch.setattr(sps, "_is_role_ambiguous", lambda *a, **k: False)
    monkeypatch.setattr(sps, "_has_linkedin_identity", lambda *a, **k: True)
    monkeypatch.setattr(sps, "_has_anchor_without_evidence", lambda *a, **k: False)
    monkeypatch.setattr(sps, "_has_unsubscribe_placeholder", lambda *a, **k: True)


def test_send_policy_stop_when_send_disabled(monkeypatch):
    _allow_all(monkeypatch)
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=_base_contact(),
        account=_base_account(),
        send_enabled=False,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.gate == "SendGate"


def test_send_policy_stop_on_free_email_domain(monkeypatch):
    _allow_all(monkeypatch)
    contact = _base_contact()
    contact["channels_json"][0]["value"] = "person@gmail.com"
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=contact,
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.reason == "free_email_domain_blocked"


def test_send_policy_stop_on_generic_mailbox(monkeypatch):
    _allow_all(monkeypatch)
    contact = _base_contact()
    contact["channels_json"][0]["value"] = "info@acme.example"
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=contact,
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.reason == "generic_mailbox_only"


def test_send_policy_stop_on_low_confidence(monkeypatch):
    _allow_all(monkeypatch)
    contact = _base_contact()
    contact["channels_json"][0]["confidence"] = 0.59
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=contact,
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.reason == "email_confidence_below_stop_threshold"


def test_send_policy_review_on_mid_confidence(monkeypatch):
    _allow_all(monkeypatch)
    contact = _base_contact()
    contact["channels_json"][0]["confidence"] = 0.70
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=contact,
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "REVIEW"
    assert decision.reason == "email_confidence_review_band"


def test_send_policy_stop_on_hourly_throttle(monkeypatch):
    _allow_all(monkeypatch)
    monkeypatch.setattr(
        sps,
        "_count_send_attempts_since",
        lambda *a, **k: sps.MAX_SENDS_PER_HOUR,
    )
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=_base_contact(),
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.reason in {
        "max_sends_per_day_exceeded",
        "max_sends_per_hour_exceeded",
    }


def test_send_policy_stop_on_domain_throttle(monkeypatch):
    _allow_all(monkeypatch)
    monkeypatch.setattr(
        sps,
        "_count_send_attempts_for_domain_since",
        lambda *a, **k: sps.MAX_SENDS_PER_TARGET_DOMAIN_24H,
    )
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=_base_contact(),
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.reason == "max_sends_per_target_domain_24h_exceeded"


def test_send_policy_stop_on_suppression_hit(monkeypatch):
    _allow_all(monkeypatch)
    monkeypatch.setattr(
        sps,
        "_suppression_hit",
        lambda *a, **k: True,
    )
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=_base_contact(),
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "STOP"
    assert decision.reason.startswith("suppression_hit:")


def test_send_policy_review_when_unsubscribe_placeholder_missing(monkeypatch):
    _allow_all(monkeypatch)
    monkeypatch.setattr(sps, "_has_unsubscribe_placeholder", lambda *a, **k: False)
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=_base_contact(),
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "REVIEW"
    assert decision.reason == "unsubscribe_placeholder_missing"


def test_send_policy_pass_when_all_checks_clear(monkeypatch):
    _allow_all(monkeypatch)
    decision = sps.evaluate_send_policy(
        session=_DummySession(),
        draft=_base_draft(),
        contact=_base_contact(),
        account=_base_account(),
        send_enabled=True,
        replay_existing=False,
    )
    assert decision.outcome == "PASS"
    assert decision.gate == "SendGate"
