"""
Send throttling and compliance policy evaluator for Epic I3.

Evaluates deterministic STOP/REVIEW/PASS outcomes before sandbox send creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import normalize_email
from aose_worker.services.channel_policy import is_free_email_domain, is_generic_mailbox

MAX_SENDS_PER_DAY = 20
MAX_SENDS_PER_HOUR = 5
MAX_SENDS_PER_TARGET_DOMAIN_24H = 1
MIN_EMAIL_CONFIDENCE_STOP = 0.60
MIN_EMAIL_CONFIDENCE_PASS = 0.80
UNSUBSCRIBE_PLACEHOLDERS = (
    "{{unsubscribe_token}}",
    "[[unsubscribe_token]]",
    "__UNSUBSCRIBE_TOKEN__",
)
ALLOWED_ROLE_CLUSTERS = frozenset(
    {"economic_buyer", "influencer", "gatekeeper", "referrer"}
)
SUPPRESSION_TABLES = (
    "global_dnc",
    "campaign_suppression",
    "complaint_suppression",
    "bounced_suppression",
)


@dataclass(frozen=True)
class SendPolicyDecision:
    outcome: str  # PASS | REVIEW | STOP
    gate: str
    reason: str
    recipient_domain: str


@dataclass(frozen=True)
class EmailSignal:
    normalized_email: str
    domain: str
    confidence: float
    validated: str
    explicit_invalid: bool
    generic: bool
    free_domain: bool


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _has_unsubscribe_placeholder(draft: dict[str, Any]) -> bool:
    subject = str(draft.get("subject") or "")
    body = str(draft.get("body") or "")
    text_blob = f"{subject}\n{body}".lower()
    return any(token.lower() in text_blob for token in UNSUBSCRIBE_PLACEHOLDERS)


def _extract_email_signal(contact: dict[str, Any], channel: str) -> EmailSignal | None:
    channels = contact.get("channels_json") or []
    if not isinstance(channels, list):
        return None
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if ch.get("type") != channel:
            continue
        raw = ch.get("value")
        if not isinstance(raw, str):
            continue
        normalized = normalize_email(raw)
        if not normalized or "@" not in normalized:
            continue
        _, domain = normalized.split("@", 1)
        confidence = ch.get("confidence")
        if not isinstance(confidence, (int, float)):
            source_trace = ch.get("source_trace") or {}
            if isinstance(source_trace, dict) and isinstance(
                source_trace.get("confidence"), (int, float)
            ):
                confidence = float(source_trace["confidence"])
            else:
                confidence = 0.0
        validated = str(ch.get("validated") or "unverified").lower()
        explicit_invalid = validated in {"invalid", "rejected", "bounced"}
        return EmailSignal(
            normalized_email=normalized,
            domain=domain,
            confidence=float(confidence),
            validated=validated,
            explicit_invalid=explicit_invalid,
            generic=is_generic_mailbox(normalized),
            free_domain=is_free_email_domain(normalized),
        )
    return None


def _has_linkedin_identity(session: Session, contact: dict[str, Any]) -> bool:
    contact_id = contact.get("contact_id")
    if not isinstance(contact_id, str) or not contact_id:
        return False
    has_alias = session.execute(
        text(
            """
            SELECT 1
            FROM contact_aliases
            WHERE contact_id = :cid AND alias_type = 'linkedin_url_normalized'
            """
        ),
        {"cid": contact_id},
    ).first()
    if has_alias:
        return True
    channels = contact.get("channels_json") or []
    if not isinstance(channels, list):
        return False
    return any(
        isinstance(ch, dict)
        and ch.get("type") == "linkedin"
        and isinstance(ch.get("value"), str)
        and bool(ch.get("value"))
        for ch in channels
    )


def _is_role_ambiguous(contact: dict[str, Any]) -> bool:
    role_json = contact.get("role_json") or {}
    if not isinstance(role_json, dict):
        return False
    cluster = role_json.get("cluster")
    if cluster is None:
        title = role_json.get("title")
        return isinstance(title, str) and not title.strip()
    return cluster not in ALLOWED_ROLE_CLUSTERS


def _distinct_evidence_categories(session: Session, draft_id: str) -> int:
    rows = (
        session.execute(
            text(
                """
                SELECT e.source_type, e.category, e.provenance_json
                FROM personalization_anchors pa
                JOIN LATERAL jsonb_array_elements_text(pa.evidence_ids_json) AS eids(eid) ON true
                JOIN evidence e ON e.evidence_id = eids.eid
                WHERE pa.draft_id = :did
                """
            ),
            {"did": draft_id},
        )
        .mappings()
        .all()
    )
    categories: set[str] = set()
    for row in rows:
        category = row.get("category")
        if isinstance(category, str) and category.strip():
            categories.add(category.strip().lower())
            continue

        provenance = row.get("provenance_json") or {}
        if isinstance(provenance, dict):
            category = provenance.get("category")
        if isinstance(category, str) and category.strip():
            categories.add(category.strip().lower())
        else:
            source_type = row.get("source_type")
            if isinstance(source_type, str) and source_type.strip():
                categories.add(source_type.strip().lower())
    return len(categories)


def _has_anchor_without_evidence(session: Session, draft_id: str) -> bool:
    row = session.execute(
        text(
            """
            SELECT 1
            FROM personalization_anchors
            WHERE draft_id = :did
              AND (
                jsonb_typeof(evidence_ids_json) != 'array'
                OR jsonb_array_length(evidence_ids_json) = 0
              )
            LIMIT 1
            """
        ),
        {"did": draft_id},
    ).first()
    return row is not None


def _count_send_attempts_since(session: Session, since_ts: datetime) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM send_attempts
                WHERE created_at >= :since_ts
                """
            ),
            {"since_ts": since_ts},
        ).scalar()
        or 0
    )


def _count_send_attempts_for_domain_since(
    session: Session,
    domain: str,
    since_ts: datetime,
) -> int:
    rows = (
        session.execute(
            text(
                """
                SELECT c.channels_json
                FROM send_attempts sa
                JOIN outreach_drafts d ON d.draft_id = sa.draft_id
                JOIN contacts c ON c.contact_id = d.contact_id
                WHERE sa.created_at >= :since_ts
                """
            ),
            {"since_ts": since_ts},
        )
        .mappings()
        .all()
    )
    count = 0
    for row in rows:
        channels = row.get("channels_json") or []
        if not isinstance(channels, list):
            continue
        for ch in channels:
            if not isinstance(ch, dict) or ch.get("type") != "email":
                continue
            val = ch.get("value")
            if not isinstance(val, str):
                continue
            norm = normalize_email(val)
            if norm and "@" in norm and norm.split("@", 1)[1] == domain:
                count += 1
                break
    return count


def _table_exists(session: Session, table_name: str) -> bool:
    row = session.execute(
        text("SELECT to_regclass(:name)"),
        {"name": table_name},
    ).first()
    return bool(row and row[0] is not None)


def _table_columns(session: Session, table_name: str) -> set[str]:
    rows = (
        session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        .mappings()
        .all()
    )
    return {str(r["column_name"]) for r in rows}


def _suppression_hit(
    session: Session,
    *,
    table_name: str,
    contact_id: str,
    account_id: str,
    normalized_email: str,
    domain: str,
) -> bool:
    if not _table_exists(session, table_name):
        return False
    cols = _table_columns(session, table_name)
    checks: list[str] = []
    params: dict[str, Any] = {}
    if "contact_id" in cols:
        checks.append("contact_id = :contact_id")
        params["contact_id"] = contact_id
    if "account_id" in cols:
        checks.append("account_id = :account_id")
        params["account_id"] = account_id
    if "email" in cols:
        checks.append("LOWER(email) = :email")
        params["email"] = normalized_email
    if "domain" in cols:
        checks.append("LOWER(domain) = :domain")
        params["domain"] = domain
    if not checks:
        return False
    where_sql = " OR ".join(checks)
    query = text(f"SELECT 1 FROM {table_name} WHERE {where_sql} LIMIT 1")
    return session.execute(query, params).first() is not None


def evaluate_send_policy(
    *,
    session: Session,
    draft: dict[str, Any],
    contact: dict[str, Any],
    account: dict[str, Any],
    send_enabled: bool,
    replay_existing: bool,
) -> SendPolicyDecision:
    """
    Evaluate I3 policy gates for sending_dispatch before SendAttempt creation.
    """
    channel = str(draft.get("channel") or "email")
    draft_id = str(draft.get("draft_id") or "")
    account_id = str(account.get("account_id") or "")

    if replay_existing:
        return SendPolicyDecision(
            outcome="PASS",
            gate="SendGate",
            reason="replay_existing_send_attempt",
            recipient_domain="unknown",
        )

    if not send_enabled:
        return SendPolicyDecision(
            outcome="STOP",
            gate="SendGate",
            reason="send_disabled",
            recipient_domain="unknown",
        )

    if not account.get("domain") and ":tmp:" in account_id:
        return SendPolicyDecision(
            outcome="STOP",
            gate="HardSafetyGate",
            reason="missing_domain_and_unique_identifier",
            recipient_domain="unknown",
        )

    signal = _extract_email_signal(contact, channel=channel)
    if signal is None:
        return SendPolicyDecision(
            outcome="STOP",
            gate="ContactabilityGate",
            reason="missing_email_channel",
            recipient_domain="unknown",
        )

    if signal.explicit_invalid:
        return SendPolicyDecision(
            outcome="STOP",
            gate="ContactabilityGate",
            reason="email_explicitly_invalid",
            recipient_domain=signal.domain,
        )
    if signal.free_domain:
        return SendPolicyDecision(
            outcome="STOP",
            gate="ContactabilityGate",
            reason="free_email_domain_blocked",
            recipient_domain=signal.domain,
        )
    if signal.generic:
        return SendPolicyDecision(
            outcome="STOP",
            gate="ContactabilityGate",
            reason="generic_mailbox_only",
            recipient_domain=signal.domain,
        )
    if signal.confidence < MIN_EMAIL_CONFIDENCE_STOP:
        return SendPolicyDecision(
            outcome="STOP",
            gate="ContactabilityGate",
            reason="email_confidence_below_stop_threshold",
            recipient_domain=signal.domain,
        )

    for table in SUPPRESSION_TABLES:
        if _suppression_hit(
            session,
            table_name=table,
            contact_id=str(contact.get("contact_id") or ""),
            account_id=account_id,
            normalized_email=signal.normalized_email,
            domain=signal.domain,
        ):
            return SendPolicyDecision(
                outcome="STOP",
                gate="HardSafetyGate",
                reason=f"suppression_hit:{table}",
                recipient_domain=signal.domain,
            )

    now = _now_utc()
    if (
        _count_send_attempts_since(session, now - timedelta(days=1))
        >= MAX_SENDS_PER_DAY
    ):
        return SendPolicyDecision(
            outcome="STOP",
            gate="HardSafetyGate",
            reason="max_sends_per_day_exceeded",
            recipient_domain=signal.domain,
        )
    if (
        _count_send_attempts_since(session, now - timedelta(hours=1))
        >= MAX_SENDS_PER_HOUR
    ):
        return SendPolicyDecision(
            outcome="STOP",
            gate="HardSafetyGate",
            reason="max_sends_per_hour_exceeded",
            recipient_domain=signal.domain,
        )
    if (
        _count_send_attempts_for_domain_since(
            session, signal.domain, now - timedelta(hours=24)
        )
        >= MAX_SENDS_PER_TARGET_DOMAIN_24H
    ):
        return SendPolicyDecision(
            outcome="STOP",
            gate="HardSafetyGate",
            reason="max_sends_per_target_domain_24h_exceeded",
            recipient_domain=signal.domain,
        )

    if signal.confidence < MIN_EMAIL_CONFIDENCE_PASS:
        return SendPolicyDecision(
            outcome="REVIEW",
            gate="ContactabilityGate",
            reason="email_confidence_review_band",
            recipient_domain=signal.domain,
        )
    if _distinct_evidence_categories(session, draft_id) < 2:
        return SendPolicyDecision(
            outcome="REVIEW",
            gate="EvidenceGate",
            reason="insufficient_distinct_evidence_categories",
            recipient_domain=signal.domain,
        )
    if _is_role_ambiguous(contact) and not _has_linkedin_identity(session, contact):
        return SendPolicyDecision(
            outcome="REVIEW",
            gate="FitScoreGate",
            reason="ambiguous_role_without_linkedin",
            recipient_domain=signal.domain,
        )
    if _has_anchor_without_evidence(session, draft_id):
        return SendPolicyDecision(
            outcome="REVIEW",
            gate="DraftClaimEvidenceGate",
            reason="draft_claim_missing_evidence_anchor",
            recipient_domain=signal.domain,
        )
    if not _has_unsubscribe_placeholder(draft):
        return SendPolicyDecision(
            outcome="REVIEW",
            gate="DraftClaimEvidenceGate",
            reason="unsubscribe_placeholder_missing",
            recipient_domain=signal.domain,
        )

    return SendPolicyDecision(
        outcome="PASS",
        gate="SendGate",
        reason="policy_checks_passed",
        recipient_domain=signal.domain,
    )
