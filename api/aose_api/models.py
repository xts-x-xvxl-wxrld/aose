"""SQLAlchemy ORM models for AOSE."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    bindparam,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)

from aose_api.scorecard_contract import normalize_and_validate_reasons


class Base(DeclarativeBase):
    pass


class WorkItem(Base):
    """
    Persisted envelope for all pipeline work items.

    Trace fields are embedded as columns — there is no separate Trace table.
    """

    __tablename__ = "work_items"
    __table_args__ = (
        Index("ix_work_items_stage", "stage"),
        Index("ix_work_items_idempotency_key", "idempotency_key"),
        Index("ix_work_items_entity_ref", "entity_ref_type", "entity_ref_id"),
        UniqueConstraint("idempotency_key", name="uq_work_items_idempotency_key"),
    )

    # Identity
    work_item_id: Mapped[str] = mapped_column(String, primary_key=True)

    # Entity anchor (flattened from entity_ref.type / entity_ref.id)
    entity_ref_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_ref_id: Mapped[str] = mapped_column(String, nullable=False)

    # Routing
    stage: Mapped[str] = mapped_column(String, nullable=False)

    # Payload (full payload body stored as JSONB; version extracted separately)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Attempt budget (flattened from attempt_budget.remaining / .policy)
    attempt_budget_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_budget_policy: Mapped[str] = mapped_column(String, nullable=False)

    # Replay / idempotency
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)

    # Embedded trace fields (no separate Trace table)
    trace_run_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_parent_work_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trace_correlation_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SellerProfile(Base):
    """Seller-side source object. Seed for query object generation."""

    __tablename__ = "seller_profiles"

    seller_id: Mapped[str] = mapped_column(String, primary_key=True)

    # Offer fields (scalar text + JSONB arrays)
    offer_what: Mapped[str] = mapped_column(Text, nullable=False)
    offer_where: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    offer_who: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    offer_positioning: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    # Constraint fields (JSONB arrays)
    constraints_avoid_claims: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    constraints_allowed_channels: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False
    )
    constraints_languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    # Policy touchpoint — must be stored explicitly
    policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)


class QueryObject(Base):
    """Structured search intent derived deterministically from a SellerProfile."""

    __tablename__ = "query_objects"
    __table_args__ = (Index("ix_query_objects_seller_id", "seller_id"),)

    query_object_id: Mapped[str] = mapped_column(String, primary_key=True)
    seller_id: Mapped[str] = mapped_column(
        String, ForeignKey("seller_profiles.seller_id"), nullable=False
    )
    buyer_context: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    exclusions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    v: Mapped[int] = mapped_column(Integer, nullable=False)


class Account(Base):
    """Canonical account record. Stable identity anchor for discovered companies."""

    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_domain", "domain"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_accounts_confidence_range",
        ),
    )

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    aliases: Mapped[list[AccountAlias]] = relationship(
        "AccountAlias", back_populates="account", cascade="all, delete-orphan"
    )


class AccountAlias(Base):
    """First-class alias row for a canonical Account."""

    __tablename__ = "account_aliases"
    __table_args__ = (
        Index("ix_account_aliases_account_id", "account_id"),
        Index("ix_account_aliases_alias_type_value", "alias_type", "alias_value"),
        UniqueConstraint(
            "account_id",
            "alias_type",
            "alias_value",
            name="uq_account_aliases_account_type_value",
        ),
        CheckConstraint(
            "alias_type IN ('registry', 'domain', 'legal_name_normalized')",
            name="ck_account_aliases_alias_type",
        ),
    )

    account_alias_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False
    )
    alias_type: Mapped[str] = mapped_column(String, nullable=False)
    alias_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    account: Mapped[Account] = relationship("Account", back_populates="aliases")

    @validates("alias_type")
    def _validate_alias_type(self, key: str, value: str) -> str:
        validate_account_alias_type(value)
        return value


class EvidenceContent(Base):
    """Deduped full content body for a piece of evidence. Optional attachment."""

    __tablename__ = "evidence_contents"
    __table_args__ = (
        Index("ix_evidence_contents_content_hash", "content_hash"),
        UniqueConstraint("content_hash", name="uq_evidence_contents_content_hash"),
    )

    evidence_content_id: Mapped[str] = mapped_column(String, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_ref_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_ref_id: Mapped[str | None] = mapped_column(String, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)


class Evidence(Base):
    """Canonical pointer-first evidence record."""

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_canonical_url", "canonical_url"),
        Index("ix_evidence_captured_at", "captured_at"),
        Index("ix_evidence_content_ref_id", "content_ref_id"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_evidence_confidence_range",
        ),
        CheckConstraint(
            "("
            "category IS NULL OR "
            "category IN ('firmographic', 'persona_fit', 'trigger', 'technographic')"
            ")",
            name="ck_evidence_category",
        ),
    )

    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    claim_frame: Mapped[str] = mapped_column(Text, nullable=False)
    source_provider: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    provenance_json: Mapped[dict[str, Any] | list[Any]] = mapped_column(
        JSONB, nullable=False
    )
    content_ref_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("evidence_contents.evidence_content_id"),
        nullable=True,
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)


def validate_reasons(reasons: object) -> list[dict[str, Any]]:
    """
    Validate a scorecard reasons list before persistence.

    Canonical Epic F shape is enforced on every new write:
    {code, text, evidence_ids[]}, with at least one evidence_id.
    """
    return normalize_and_validate_reasons(reasons)


class Scorecard(Base):
    """Fit + intent scorecard for a canonical entity. Reasons link to Evidence IDs."""

    __tablename__ = "scorecards"
    __table_args__ = (
        Index("ix_scorecards_entity_ref", "entity_ref_type", "entity_ref_id"),
        Index("ix_scorecards_computed_at", "computed_at"),
        CheckConstraint(
            "fit_score >= 0 AND fit_score <= 100",
            name="ck_scorecards_fit_score_range",
        ),
        CheckConstraint(
            "fit_confidence >= 0.0 AND fit_confidence <= 1.0",
            name="ck_scorecards_fit_confidence_range",
        ),
        CheckConstraint(
            "intent_score >= 0 AND intent_score <= 100",
            name="ck_scorecards_intent_score_range",
        ),
        CheckConstraint(
            "intent_confidence >= 0.0 AND intent_confidence <= 1.0",
            name="ck_scorecards_intent_confidence_range",
        ),
    )

    scorecard_id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_ref_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_ref_id: Mapped[str] = mapped_column(String, nullable=False)
    policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    fit_reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )
    intent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    intent_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    intent_reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )
    scoring_version: Mapped[str] = mapped_column(String, nullable=False)
    evidence_snapshot_hash: Mapped[str] = mapped_column(String, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    @validates("fit_reasons_json", "intent_reasons_json")
    def _validate_reasons(self, key: str, value: object) -> object:
        return validate_reasons(value)


def _scorecard_reason_evidence_ids(scorecard: Scorecard) -> list[str]:
    reason_lists = [
        scorecard.fit_reasons_json or [],
        scorecard.intent_reasons_json or [],
    ]
    evidence_ids: list[str] = []
    for reasons in reason_lists:
        normalized = normalize_and_validate_reasons(reasons)
        for reason in normalized:
            evidence_ids.extend(reason["evidence_ids"])
    return sorted(set(evidence_ids))


def _ensure_scorecard_references_existing_evidence(
    connection: Any,
    scorecard: Scorecard,
) -> None:
    evidence_ids = _scorecard_reason_evidence_ids(scorecard)
    if not evidence_ids:
        return

    stmt = text(
        "SELECT evidence_id FROM evidence WHERE evidence_id IN :evidence_ids"
    ).bindparams(bindparam("evidence_ids", expanding=True))
    found = {
        row[0]
        for row in connection.execute(
            stmt,
            {"evidence_ids": evidence_ids},
        ).fetchall()
    }
    missing = [eid for eid in evidence_ids if eid not in found]
    if missing:
        raise ValueError(f"scorecard reasons reference unknown evidence_ids: {missing}")


@event.listens_for(Scorecard, "before_insert")
def _validate_scorecard_reason_evidence_before_insert(
    mapper: Any,  # noqa: ARG001
    connection: Any,
    target: Scorecard,
) -> None:
    _ensure_scorecard_references_existing_evidence(connection, target)


@event.listens_for(Scorecard, "before_update")
def _validate_scorecard_reason_evidence_before_update(
    mapper: Any,  # noqa: ARG001
    connection: Any,
    target: Scorecard,
) -> None:
    _ensure_scorecard_references_existing_evidence(connection, target)


# ---------------------------------------------------------------------------
# Contact validators
# ---------------------------------------------------------------------------

_EMAIL_VALIDATION_LEVELS = frozenset(
    {"unverified", "syntax_ok", "domain_ok", "provider_verified", "human_verified"}
)
_LINKEDIN_VALIDATION_LEVELS = frozenset(
    {"unverified", "profile_exists", "human_verified"}
)
_ACCOUNT_ALIAS_TYPES = frozenset({"registry", "domain", "legal_name_normalized"})
_CONTACT_ALIAS_TYPES = frozenset({"email_normalized", "linkedin_url_normalized"})


def validate_channels(channels: list) -> None:
    """
    Validate a contact channels_json list before persistence.

    Each channel must be a dict with 'type' and 'value'. If 'validated' is
    present its value must be one of the locked levels for that channel type.
    Raises ValueError on any violation.
    """
    if not isinstance(channels, list):
        raise ValueError("channels_json must be a list")
    for i, ch in enumerate(channels):
        if not isinstance(ch, dict):
            raise ValueError(f"channel[{i}] must be a dict")
        ch_type = ch.get("type")
        validated = ch.get("validated")
        if validated is None:
            continue
        if ch_type == "email" and validated not in _EMAIL_VALIDATION_LEVELS:
            raise ValueError(
                f"channel[{i}] invalid email validation level: {validated!r}"
            )
        if ch_type == "linkedin" and validated not in _LINKEDIN_VALIDATION_LEVELS:
            raise ValueError(
                f"channel[{i}] invalid linkedin validation level: {validated!r}"
            )


def validate_contact_alias_type(alias_type: str) -> None:
    """Raise ValueError if alias_type is not in the locked ContactAlias enum."""
    if alias_type not in _CONTACT_ALIAS_TYPES:
        raise ValueError(
            f"Invalid contact alias type: {alias_type!r}. "
            f"Allowed: {sorted(_CONTACT_ALIAS_TYPES)}"
        )


def validate_account_alias_type(alias_type: str) -> None:
    """Raise ValueError if alias_type is not in the locked AccountAlias enum."""
    if alias_type not in _ACCOUNT_ALIAS_TYPES:
        raise ValueError(
            f"Invalid account alias type: {alias_type!r}. "
            f"Allowed: {sorted(_ACCOUNT_ALIAS_TYPES)}"
        )


# ---------------------------------------------------------------------------
# Contact ORM models
# ---------------------------------------------------------------------------


class Contact(Base):
    """Canonical contact record anchored to an Account."""

    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_account_id", "account_id"),)

    contact_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channels_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    aliases: Mapped[list[ContactAlias]] = relationship(
        "ContactAlias", back_populates="contact", cascade="all, delete-orphan"
    )

    @validates("channels_json")
    def _validate_channels(self, key: str, value: object) -> object:
        validate_channels(value)
        return value


class ContactAlias(Base):
    """Identity alias row for a canonical Contact. Composite PK (contact_id, alias_type)."""

    __tablename__ = "contact_aliases"
    __table_args__ = (
        Index("ix_contact_aliases_contact_id", "contact_id"),
        Index("ix_contact_aliases_account_id", "account_id"),
        Index(
            "ix_contact_aliases_account_type_value",
            "account_id",
            "alias_type",
            "alias_value",
        ),
        UniqueConstraint(
            "account_id",
            "alias_type",
            "alias_value",
            name="uq_contact_aliases_account_type_value",
        ),
        CheckConstraint(
            "alias_type IN ('email_normalized', 'linkedin_url_normalized')",
            name="ck_contact_aliases_alias_type",
        ),
    )

    contact_id: Mapped[str] = mapped_column(
        String, ForeignKey("contacts.contact_id"), primary_key=True
    )
    alias_type: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False)
    alias_value: Mapped[str] = mapped_column(Text, nullable=False)
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    contact: Mapped[Contact] = relationship("Contact", back_populates="aliases")

    @validates("alias_type")
    def _validate_alias_type(self, key: str, value: str) -> str:
        validate_contact_alias_type(value)
        return value


# ---------------------------------------------------------------------------
# OutreachDraft / PersonalizationAnchor validator
# ---------------------------------------------------------------------------


def validate_anchor_evidence_ids(evidence_ids: list) -> None:
    """
    Validate a personalization anchor evidence_ids list before persistence.

    Must be a non-empty list of strings.
    Raises ValueError on any violation.
    """
    if not isinstance(evidence_ids, list):
        raise ValueError("evidence_ids_json must be a list")
    if len(evidence_ids) == 0:
        raise ValueError(
            "anchor evidence_ids_json must contain at least one evidence ID"
        )


# ---------------------------------------------------------------------------
# OutreachDraft + PersonalizationAnchor ORM models
# ---------------------------------------------------------------------------


class OutreachDraft(Base):
    """Canonical outreach draft for a contact. Anchors are stored in a separate table."""

    __tablename__ = "outreach_drafts"
    __table_args__ = (
        Index("ix_outreach_drafts_contact_id", "contact_id"),
        Index("ix_outreach_drafts_account_id", "account_id"),
        Index("ix_outreach_drafts_created_at", "created_at"),
    )

    draft_id: Mapped[str] = mapped_column(String, primary_key=True)
    contact_id: Mapped[str] = mapped_column(
        String, ForeignKey("contacts.contact_id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    risk_flags_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    anchors: Mapped[list[PersonalizationAnchor]] = relationship(
        "PersonalizationAnchor",
        back_populates="draft",
        cascade="all, delete-orphan",
    )


class PersonalizationAnchor(Base):
    """Maps a text span in an OutreachDraft to one or more Evidence IDs."""

    __tablename__ = "personalization_anchors"
    __table_args__ = (Index("ix_personalization_anchors_draft_id", "draft_id"),)

    anchor_key: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        String, ForeignKey("outreach_drafts.draft_id"), nullable=False
    )
    span: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    v: Mapped[int] = mapped_column(Integer, nullable=False)

    draft: Mapped[OutreachDraft] = relationship(
        "OutreachDraft", back_populates="anchors"
    )

    @validates("evidence_ids_json")
    def _validate_evidence_ids(self, key: str, value: object) -> object:
        validate_anchor_evidence_ids(value)
        return value


# ---------------------------------------------------------------------------
# ApprovalDecision / SendAttempt validator + constants
# ---------------------------------------------------------------------------

APPROVAL_STATUSES = frozenset(
    {"approved", "rejected", "needs_rewrite", "needs_more_evidence"}
)
SEND_PROVIDERS = frozenset({"SEND_SRC_01"})


def validate_approval_status(status: str) -> None:
    """Raise ValueError if status is not in the locked ApprovalDecision set."""
    if status not in APPROVAL_STATUSES:
        raise ValueError(
            f"Invalid approval status: {status!r}. Allowed: {sorted(APPROVAL_STATUSES)}"
        )


def validate_send_provider(provider: str) -> None:
    """Raise ValueError if provider is not in the locked SendAttempt provider set."""
    if provider not in SEND_PROVIDERS:
        raise ValueError(
            f"Invalid send provider: {provider!r}. Allowed: {sorted(SEND_PROVIDERS)}"
        )


# ---------------------------------------------------------------------------
# ApprovalDecision + SendAttempt ORM models
# ---------------------------------------------------------------------------


class ApprovalDecision(Base):
    """Human approval decision for an OutreachDraft. Replay-safe via decision_key."""

    __tablename__ = "approval_decisions"
    __table_args__ = (
        Index("ix_approval_decisions_decision_key", "decision_key"),
        Index("ix_approval_decisions_draft_id", "draft_id"),
        Index("ix_approval_decisions_contact_id", "contact_id"),
        Index("ix_approval_decisions_decided_at", "decided_at"),
        UniqueConstraint("decision_key", name="uq_approval_decisions_decision_key"),
        CheckConstraint(
            "status IN ('approved', 'rejected', 'needs_rewrite', 'needs_more_evidence')",
            name="ck_approval_decisions_status",
        ),
    )

    decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    decision_key: Mapped[str] = mapped_column(String, nullable=False)
    draft_id: Mapped[str] = mapped_column(
        String, ForeignKey("outreach_drafts.draft_id"), nullable=False
    )
    work_item_id: Mapped[str] = mapped_column(
        String, ForeignKey("work_items.work_item_id"), nullable=False
    )
    contact_id: Mapped[str] = mapped_column(
        String, ForeignKey("contacts.contact_id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String, nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_gates_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)


class SendAttempt(Base):
    """Storage record for a send attempt. Replay-safe via idempotency_key uniqueness."""

    __tablename__ = "send_attempts"
    __table_args__ = (
        Index("ix_send_attempts_idempotency_key", "idempotency_key"),
        Index("ix_send_attempts_draft_id", "draft_id"),
        Index("ix_send_attempts_decision_id", "decision_id"),
        Index("ix_send_attempts_created_at", "created_at"),
        UniqueConstraint("idempotency_key", name="uq_send_attempts_idempotency_key"),
    )

    send_id: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        String, ForeignKey("outreach_drafts.draft_id"), nullable=False
    )
    decision_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("approval_decisions.decision_id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    policy_pack_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    v: Mapped[int] = mapped_column(Integer, nullable=False)


# ---------------------------------------------------------------------------
# StructuredEvent constants (mirrored from worker/aose_worker/events.py)
# ---------------------------------------------------------------------------

_SE_EVENT_TYPES = (
    "handler_started",
    "handler_succeeded",
    "handler_parked",
    "handler_failed_contract",
    "handler_failed_transient",
    "handler_noop_idempotent",
    "budget_decremented",
    "retry_scheduled",
    "work_item_completed",
    "work_item_parked",
    "work_item_failed_contract",
    "work_item_failed_transient",
    # Epic H event kinds (CONTRACT.yaml structured_events.required_event_kinds)
    "evidence_digest_built",
    "draft_generated",
    "draft_flagged_for_review",
    "approval_recorded",
)
_SE_OUTCOMES = (
    "ok",
    "parked",
    "failed_contract",
    "failed_transient",
    "retry_scheduled",
    "noop",
)

_SE_EVENT_TYPES_SQL = ", ".join(f"'{v}'" for v in _SE_EVENT_TYPES)
_SE_OUTCOMES_SQL = ", ".join(f"'{v}'" for v in _SE_OUTCOMES)


class StructuredEvent(Base):
    """
    Canonical structured event for all handler lifecycle transitions.

    entity_ref is stored as flattened columns (entity_ref_type, entity_ref_id)
    matching WorkItem convention, enabling indexed queries without JSONB operators.
    """

    __tablename__ = "structured_events"
    __table_args__ = (
        Index("ix_structured_events_work_item_id", "work_item_id"),
        Index(
            "ix_structured_events_entity_ref",
            "entity_ref_type",
            "entity_ref_id",
        ),
        Index("ix_structured_events_occurred_at", "occurred_at"),
        CheckConstraint(
            f"event_type IN ({_SE_EVENT_TYPES_SQL})",
            name="ck_structured_events_event_type",
        ),
        CheckConstraint(
            f"outcome IN ({_SE_OUTCOMES_SQL})",
            name="ck_structured_events_outcome",
        ),
    )

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    module: Mapped[str] = mapped_column(String, nullable=False)
    work_item_id: Mapped[str] = mapped_column(
        String, ForeignKey("work_items.work_item_id"), nullable=False
    )
    # entity_ref flattened — logical shape is {type: entity_ref_type, id: entity_ref_id}
    entity_ref_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_ref_id: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    counters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    v: Mapped[int] = mapped_column(Integer, nullable=False)
