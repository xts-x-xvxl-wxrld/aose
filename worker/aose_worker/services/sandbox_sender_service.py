"""
Sandbox sender service for Epic I2.

Implements the only allowed send execution path in v0.1:
  1. Create or reuse one SendAttempt row by idempotency_key.
  2. Build a redacted sandbox sink payload for structured event logging.

No real delivery and no external network calls are performed here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import (
    make_send_attempt_id,
    make_send_attempt_idempotency_key,
    normalize_email,
)

LOCKED_PROVIDER = "SEND_SRC_01"
LOCKED_POLICY_PACK_ID = "safe_v0_1"
LOCKED_INITIAL_STATUS = "queued"
LOCKED_SEND_MODE = "sandbox_log_sink_only"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SendAttemptRecord:
    send_id: str
    idempotency_key: str
    channel: str
    provider: str
    status: str
    policy_pack_id: str
    reused: bool


def _recipient_redacted_identity(
    *,
    contact: dict[str, Any],
    channel: str,
) -> tuple[str, str]:
    """
    Return (recipient_domain, recipient_hash) from contact channels.

    No raw email is returned.
    """
    channels = contact.get("channels_json") or []
    if not isinstance(channels, list):
        return ("unknown", "unknown")

    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if ch.get("type") != channel:
            continue
        value = ch.get("value")
        if not isinstance(value, str):
            continue
        normalized = normalize_email(value)
        if normalized and "@" in normalized:
            _, domain = normalized.split("@", 1)
            return (domain, _sha256(normalized))
    return ("unknown", "unknown")


def _load_anchor_rows(session: Session, draft_id: str) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            text(
                """
                SELECT span, evidence_ids_json
                FROM personalization_anchors
                WHERE draft_id = :did
                ORDER BY anchor_key
                """
            ),
            {"did": draft_id},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def create_or_reuse_send_attempt(
    *,
    session: Session,
    draft_id: str,
    decision_id: str,
    channel: str,
) -> SendAttemptRecord:
    """
    Create or reuse SendAttempt by canonical idempotency key.

    Guarantees deterministic row reuse under replay.
    """
    send_id = make_send_attempt_id(draft_id, channel)
    idempotency_key = make_send_attempt_idempotency_key(draft_id, channel)

    existing = (
        session.execute(
            text(
                """
                SELECT send_id, idempotency_key, channel, provider, status, policy_pack_id
                FROM send_attempts
                WHERE idempotency_key = :ik
                """
            ),
            {"ik": idempotency_key},
        )
        .mappings()
        .first()
    )
    if existing is not None:
        row = dict(existing)
        return SendAttemptRecord(
            send_id=row["send_id"],
            idempotency_key=row["idempotency_key"],
            channel=row["channel"],
            provider=row["provider"],
            status=row["status"],
            policy_pack_id=row["policy_pack_id"],
            reused=True,
        )

    session.execute(
        text(
            """
            INSERT INTO send_attempts (
                send_id, draft_id, decision_id, channel, provider,
                status, idempotency_key, policy_pack_id, created_at, v
            ) VALUES (
                :send_id, :draft_id, :decision_id, :channel, :provider,
                :status, :idempotency_key, :policy_pack_id, now(), 1
            ) ON CONFLICT (idempotency_key) DO NOTHING
            """
        ),
        {
            "send_id": send_id,
            "draft_id": draft_id,
            "decision_id": decision_id,
            "channel": channel,
            "provider": LOCKED_PROVIDER,
            "status": LOCKED_INITIAL_STATUS,
            "idempotency_key": idempotency_key,
            "policy_pack_id": LOCKED_POLICY_PACK_ID,
        },
    )

    row = (
        session.execute(
            text(
                """
                SELECT send_id, idempotency_key, channel, provider, status, policy_pack_id
                FROM send_attempts
                WHERE idempotency_key = :ik
                """
            ),
            {"ik": idempotency_key},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise RuntimeError("SendAttempt create-or-reuse failed to return a row")

    data = dict(row)
    return SendAttemptRecord(
        send_id=data["send_id"],
        idempotency_key=data["idempotency_key"],
        channel=data["channel"],
        provider=data["provider"],
        status=data["status"],
        policy_pack_id=data["policy_pack_id"],
        reused=False,
    )


def get_existing_send_attempt(
    *,
    session: Session,
    draft_id: str,
    channel: str,
) -> SendAttemptRecord | None:
    """Return existing SendAttempt by canonical idempotency key, or None."""
    idempotency_key = make_send_attempt_idempotency_key(draft_id, channel)
    row = (
        session.execute(
            text(
                """
                SELECT send_id, idempotency_key, channel, provider, status, policy_pack_id
                FROM send_attempts
                WHERE idempotency_key = :ik
                """
            ),
            {"ik": idempotency_key},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    data = dict(row)
    return SendAttemptRecord(
        send_id=data["send_id"],
        idempotency_key=data["idempotency_key"],
        channel=data["channel"],
        provider=data["provider"],
        status=data["status"],
        policy_pack_id=data["policy_pack_id"],
        reused=True,
    )


def build_sandbox_sink_refs(
    *,
    session: Session,
    draft: dict[str, Any],
    contact: dict[str, Any],
    send_attempt: SendAttemptRecord,
) -> dict[str, Any]:
    """
    Build redacted sink refs for sandbox logging.

    Includes only safe metadata:
      - recipient domain/hash
      - deterministic template hash
      - claim hashes
      - linked evidence IDs
      - channel/provider/mode
    """
    draft_id = str(draft.get("draft_id", ""))
    channel = str(draft.get("channel", "email"))
    subject = str(draft.get("subject", ""))
    body = str(draft.get("body", ""))
    anchor_rows = _load_anchor_rows(session, draft_id)

    evidence_ids: set[str] = set()
    claim_hashes: list[str] = []
    for row in anchor_rows:
        span = row.get("span")
        if isinstance(span, str) and span:
            claim_hashes.append(_sha256(span))
        raw_evidence_ids = row.get("evidence_ids_json") or []
        if isinstance(raw_evidence_ids, list):
            for eid in raw_evidence_ids:
                if isinstance(eid, str) and eid:
                    evidence_ids.add(eid)

    recipient_domain, recipient_hash = _recipient_redacted_identity(
        contact=contact, channel=channel
    )
    template_id = f"tpl:{_sha256(subject + '|' + body + '|' + channel)}"

    return {
        "send_mode": LOCKED_SEND_MODE,
        "provider_id": send_attempt.provider,
        "channel": send_attempt.channel,
        "send_attempt_reused": send_attempt.reused,
        "recipient_domain": recipient_domain,
        "recipient_hash": recipient_hash,
        "template_id": template_id,
        "claim_hashes": sorted(set(claim_hashes)),
        "evidence_ids": sorted(evidence_ids),
    }
