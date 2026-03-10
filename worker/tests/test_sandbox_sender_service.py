"""
Unit tests for Epic I2 sandbox sender service.

These tests avoid DB integration and validate redaction + no-network behavior.
"""

from __future__ import annotations

import socket

from aose_worker.services.sandbox_sender_service import (
    LOCKED_PROVIDER,
    SendAttemptRecord,
    _recipient_redacted_identity,
    build_sandbox_sink_refs,
)


class _EmptyResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _FakeSession:
    def execute(self, *args, **kwargs):
        return _EmptyResult()


def test_recipient_redacted_identity_returns_domain_and_hash():
    contact = {
        "channels_json": [
            {"type": "email", "value": "Alice@Example.com"},
        ]
    }
    domain, digest = _recipient_redacted_identity(contact=contact, channel="email")
    assert domain == "example.com"
    assert digest != "unknown"
    assert "@" not in digest


def test_recipient_redacted_identity_unknown_when_no_matching_channel():
    contact = {
        "channels_json": [{"type": "linkedin", "value": "https://linkedin.com/in/a"}]
    }
    domain, digest = _recipient_redacted_identity(contact=contact, channel="email")
    assert domain == "unknown"
    assert digest == "unknown"


def test_build_sandbox_sink_refs_is_redacted_and_no_network(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", _boom)
    session = _FakeSession()
    draft = {
        "draft_id": "draft:contact:acct:seq1:v1",
        "channel": "email",
        "subject": "Hello",
        "body": "Top secret body should never be logged",
    }
    contact = {"channels_json": [{"type": "email", "value": "alice@example.com"}]}
    send_attempt = SendAttemptRecord(
        send_id="send:x:email",
        idempotency_key="send:x:email:v1",
        channel="email",
        provider=LOCKED_PROVIDER,
        status="queued",
        policy_pack_id="safe_v0_1",
        reused=False,
    )

    refs = build_sandbox_sink_refs(
        session=session,
        draft=draft,
        contact=contact,
        send_attempt=send_attempt,
    )
    assert refs["provider_id"] == "SEND_SRC_01"
    assert refs["send_mode"] == "sandbox_log_sink_only"
    assert refs["recipient_domain"] == "example.com"
    assert "@" not in str(refs)
    assert "Top secret body" not in str(refs)
