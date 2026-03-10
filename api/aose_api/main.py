from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal
import os
import uuid

import psycopg
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from psycopg import OperationalError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, selectinload

from aose_api.manual_import import ImportSchemaError, import_contacts_csv
from aose_api.models import (
    Account,
    AccountAlias,
    Contact,
    Evidence,
    OutreachDraft,
    PersonalizationAnchor,
    QueryObject,
    SellerProfile,
    StructuredEvent,
    WorkItem,
    APPROVAL_STATUSES,
)
from aose_api.query_gen import generate_query_objects


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.getenv("DATABASE_URL", "")
    app.state.engine = create_engine(_sa_url(url)) if url else None
    yield
    if app.state.engine:
        app.state.engine.dispose()


app = FastAPI(title="AOSE API", lifespan=lifespan)


def get_session(request: Request):
    if not request.app.state.engine:
        raise HTTPException(status_code=503, detail="Database not configured")
    with Session(request.app.state.engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Schemas — WorkItem
# ---------------------------------------------------------------------------


class WorkItemIn(BaseModel):
    work_item_id: str
    entity_ref_type: str
    entity_ref_id: str
    stage: str
    payload_json: dict[str, Any]
    payload_version: int
    attempt_budget_remaining: int
    attempt_budget_policy: str
    idempotency_key: str
    trace_run_id: str
    trace_parent_work_item_id: str | None = None
    trace_correlation_id: str
    trace_policy_pack_id: str
    created_at: datetime


class WorkItemOut(WorkItemIn):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Schemas — SellerProfile
# ---------------------------------------------------------------------------


class SellerProfileIn(BaseModel):
    seller_id: str
    offer_what: str
    offer_where: list[str]
    offer_who: list[str]
    offer_positioning: list[str]
    constraints_avoid_claims: list[str]
    constraints_allowed_channels: list[str]
    constraints_languages: list[str]
    policy_pack_id: str = "safe_v0_1"
    created_at: datetime
    v: int = 1


class SellerProfileOut(SellerProfileIn):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Schemas — QueryObject
# ---------------------------------------------------------------------------


class QueryObjectOut(BaseModel):
    query_object_id: str
    seller_id: str
    buyer_context: str
    priority: float
    keywords: list[str]
    exclusions: list[str]
    rationale: str
    v: int
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints — healthz
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            with psycopg.connect(db_url) as conn:
                conn.execute("SELECT 1")
        except OperationalError:
            raise HTTPException(status_code=503, detail="Database connection failed")
    return {"status": "ok", "env": os.getenv("APP_ENV", "local")}


# ---------------------------------------------------------------------------
# Endpoints — WorkItem
# ---------------------------------------------------------------------------


@app.post("/work-items", response_model=WorkItemOut, status_code=201)
def create_work_item(body: WorkItemIn, session: Session = Depends(get_session)):
    wi = WorkItem(**body.model_dump())
    session.add(wi)
    session.commit()
    session.refresh(wi)
    return wi


@app.get("/work-items/{work_item_id}", response_model=WorkItemOut)
def get_work_item(work_item_id: str, session: Session = Depends(get_session)):
    wi = session.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status_code=404, detail="WorkItem not found")
    return wi


# ---------------------------------------------------------------------------
# Endpoints — SellerProfile
# ---------------------------------------------------------------------------


@app.post("/seller-profiles", response_model=SellerProfileOut, status_code=201)
def create_seller_profile(
    body: SellerProfileIn, session: Session = Depends(get_session)
):
    sp = SellerProfile(**body.model_dump())
    session.add(sp)
    session.commit()
    session.refresh(sp)
    return sp


@app.get("/seller-profiles/{seller_id}", response_model=SellerProfileOut)
def get_seller_profile(seller_id: str, session: Session = Depends(get_session)):
    sp = session.get(SellerProfile, seller_id)
    if sp is None:
        raise HTTPException(status_code=404, detail="SellerProfile not found")
    return sp


class SellerProfileUpdate(BaseModel):
    offer_what: str | None = None
    offer_where: list[str] | None = None
    offer_who: list[str] | None = None
    offer_positioning: list[str] | None = None
    constraints_avoid_claims: list[str] | None = None
    constraints_allowed_channels: list[str] | None = None
    constraints_languages: list[str] | None = None


@app.put("/seller-profiles/{seller_id}", response_model=SellerProfileOut)
def update_seller_profile(
    seller_id: str,
    body: SellerProfileUpdate,
    session: Session = Depends(get_session),
):
    sp = session.get(SellerProfile, seller_id)
    if sp is None:
        raise HTTPException(status_code=404, detail="SellerProfile not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sp, field, value)
    session.commit()
    session.refresh(sp)
    return sp


# ---------------------------------------------------------------------------
# Endpoints — QueryObject (generate + store, then read)
# ---------------------------------------------------------------------------


@app.post(
    "/seller-profiles/{seller_id}/query-objects",
    response_model=list[QueryObjectOut],
    status_code=201,
)
def generate_and_store_query_objects(
    seller_id: str, session: Session = Depends(get_session)
):
    sp = session.get(SellerProfile, seller_id)
    if sp is None:
        raise HTTPException(status_code=404, detail="SellerProfile not found")

    query_dicts = generate_query_objects(sp)
    rows = []
    for qd in query_dicts:
        existing = session.get(QueryObject, qd["query_object_id"])
        if existing is None:
            qo = QueryObject(**qd)
            session.add(qo)
            rows.append(qo)
        else:
            rows.append(existing)
    session.commit()
    for r in rows:
        session.refresh(r)
    return rows


@app.get(
    "/seller-profiles/{seller_id}/query-objects",
    response_model=list[QueryObjectOut],
)
def list_query_objects(seller_id: str, session: Session = Depends(get_session)):
    stmt = (
        select(QueryObject)
        .where(QueryObject.seller_id == seller_id)
        .order_by(QueryObject.priority.desc())
    )
    return list(session.scalars(stmt).all())


class QueryObjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buyer_context: str | None = None
    priority: float | None = None
    keywords: list[str] | None = None
    exclusions: list[str] | None = None
    rationale: str | None = None


@app.patch("/query-objects/{query_object_id}", response_model=QueryObjectOut)
def update_query_object(
    query_object_id: str,
    body: QueryObjectUpdate,
    session: Session = Depends(get_session),
):
    qo = session.get(QueryObject, query_object_id)
    if qo is None:
        raise HTTPException(status_code=404, detail="QueryObject not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(qo, field, value)
    session.commit()
    session.refresh(qo)
    return qo


# ---------------------------------------------------------------------------
# Schemas — Account + AccountAlias
# ---------------------------------------------------------------------------


class AccountAliasIn(BaseModel):
    account_alias_id: str
    alias_type: Literal["registry", "domain", "legal_name_normalized"]
    alias_value: str
    source_provider: str | None = None
    source_ref: str | None = None
    created_at: datetime
    v: int = 1


class AccountAliasOut(AccountAliasIn):
    account_id: str
    model_config = ConfigDict(from_attributes=True)


class AccountIn(BaseModel):
    account_id: str
    name: str
    domain: str | None = None
    country: str | None = None
    provenance: list[Any]
    evidence_ids: list[str]
    confidence: float
    status: str
    created_at: datetime | None = None
    v: int = 1
    aliases: list[AccountAliasIn] = []


class AccountOut(BaseModel):
    account_id: str
    name: str
    domain: str | None
    country: str | None
    provenance: list[Any]
    evidence_ids: list[str]
    confidence: float
    status: str
    created_at: datetime
    v: int
    aliases: list[AccountAliasOut]
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints — Account
# ---------------------------------------------------------------------------


@app.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, session: Session = Depends(get_session)):
    data = body.model_dump(exclude={"aliases"})
    if data.get("created_at") is None:
        data.pop("created_at", None)
    account = Account(**data)
    session.add(account)
    for alias_in in body.aliases:
        alias = AccountAlias(**alias_in.model_dump(), account_id=body.account_id)
        session.add(alias)
    session.commit()
    stmt = (
        select(Account)
        .options(selectinload(Account.aliases))
        .where(Account.account_id == body.account_id)
    )
    return session.scalars(stmt).one()


@app.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: str, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


# ---------------------------------------------------------------------------
# Schemas — StructuredEvent
# ---------------------------------------------------------------------------

_RECENT_EVENTS_LIMIT = 20


class StructuredEventOut(BaseModel):
    event_id: str
    occurred_at: datetime
    module: str
    work_item_id: str
    entity_ref_type: str
    entity_ref_id: str
    stage: str
    event_type: str
    outcome: str
    error_code: str | None
    counters: dict[str, Any]
    refs: dict[str, Any]
    v: int
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints — StructuredEvent (recent-events run view)
# ---------------------------------------------------------------------------


@app.get(
    "/entities/{entity_ref_type}/{entity_ref_id}/events",
    response_model=list[StructuredEventOut],
)
def get_recent_events(
    entity_ref_type: str,
    entity_ref_id: str,
    session: Session = Depends(get_session),
):
    """
    Return the last 20 structured events for an entity, most recent first.

    CONTRACT.yaml structured_events.run_view_requirement.per_entity_recent_events = 20.
    """
    stmt = (
        select(StructuredEvent)
        .where(StructuredEvent.entity_ref_type == entity_ref_type)
        .where(StructuredEvent.entity_ref_id == entity_ref_id)
        .order_by(StructuredEvent.occurred_at.desc())
        .limit(_RECENT_EVENTS_LIMIT)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Schemas — Manual contact import (Epic G2)
# ---------------------------------------------------------------------------


class RowErrorOut(BaseModel):
    row_number: int
    error_code: str
    detail: str


class ImportSummaryOut(BaseModel):
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    contacts_created: int
    contacts_updated: int
    aliases_created: int
    parked_count: int
    enrichment_enqueued: int
    errors: list[RowErrorOut]


# ---------------------------------------------------------------------------
# Endpoint — Manual contact import (Epic G2)
# ---------------------------------------------------------------------------


@app.post("/contacts/import", response_model=ImportSummaryOut, status_code=200)
def import_contacts(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Import contacts from a UTF-8 CSV file.

    CSV contract (Epic G2 / CONTRACT.yaml manual_contact_import):
    - Required columns:  account_id, full_name
    - At least one of:   email, linkedin_url
    - Optional columns:  role_title, role_cluster, role_confidence,
                         source_provider, source_ref, observed_at, confidence
    - Forbidden rows:    missing account_id, missing full_name,
                         missing both identity fields, unknown account_id

    Idempotent: replaying the same CSV produces zero duplicate contacts,
    aliases, or enrichment work items.
    """
    raw_bytes = file.file.read()
    try:
        csv_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV file must be UTF-8 encoded")

    try:
        summary = import_contacts_csv(session=session, csv_content=csv_content)
    except ImportSchemaError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    session.commit()

    return ImportSummaryOut(
        rows_total=summary.rows_total,
        rows_accepted=summary.rows_accepted,
        rows_rejected=summary.rows_rejected,
        contacts_created=summary.contacts_created,
        contacts_updated=summary.contacts_updated,
        aliases_created=summary.aliases_created,
        parked_count=summary.parked_count,
        enrichment_enqueued=summary.enrichment_enqueued,
        errors=[
            RowErrorOut(
                row_number=e.row_number,
                error_code=e.error_code,
                detail=e.detail,
            )
            for e in summary.errors
        ],
    )


# ---------------------------------------------------------------------------
# Schemas — Draft Review (SPEC-H4)
# ---------------------------------------------------------------------------


class DraftListItemOut(BaseModel):
    draft_id: str
    contact_id: str
    account_id: str
    channel: str
    language: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AnchorOut(BaseModel):
    anchor_key: str
    span: str
    evidence_ids: list[str]


class EvidenceItemOut(BaseModel):
    evidence_id: str
    source_type: str
    url: str
    claim_frame: str
    snippet: str
    captured_at: datetime


class ContactSummaryOut(BaseModel):
    contact_id: str
    full_name: str | None
    role: dict | None
    channels: list[Any]


class AccountSummaryOut(BaseModel):
    account_id: str
    name: str
    domain: str | None
    country: str | None


class DraftReviewOut(BaseModel):
    draft_id: str
    contact: ContactSummaryOut
    account: AccountSummaryOut
    subject: str
    body: str
    channel: str
    language: str
    risk_flags: list[Any]
    anchors: list[AnchorOut]
    evidence_items: list[EvidenceItemOut]
    v: int


class DecisionIn(BaseModel):
    status: str
    reviewer_id: str
    reviewer_role: str
    notes: str | None = None
    overridden_gates: list[str] = []


class DecisionSubmittedOut(BaseModel):
    work_item_id: str
    draft_id: str
    status: str
    created: bool


# ---------------------------------------------------------------------------
# Endpoints — Draft Review (SPEC-H4)
# ---------------------------------------------------------------------------

_REVIEWER_ROLES_ALLOWED = frozenset({"operator", "admin"})


@app.get("/drafts", response_model=list[DraftListItemOut])
def list_drafts(session: Session = Depends(get_session)):
    """Return all outreach drafts ordered by creation time descending."""
    stmt = select(OutreachDraft).order_by(OutreachDraft.created_at.desc())
    return list(session.scalars(stmt).all())


@app.get("/drafts/{draft_id}", response_model=DraftReviewOut)
def get_draft_review(draft_id: str, session: Session = Depends(get_session)):
    """
    Return full review context for a draft.

    Includes: draft body, personalization anchors, linked evidence cards,
    contact summary, and account summary. All data is derived from canonical
    records — no raw provider payloads.
    """
    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    contact = session.get(Contact, draft.contact_id)
    account = session.get(Account, draft.account_id)

    # Load anchors
    stmt = select(PersonalizationAnchor).where(
        PersonalizationAnchor.draft_id == draft_id
    )
    anchors = list(session.scalars(stmt).all())

    # Collect all unique evidence IDs referenced by anchors
    all_evidence_ids: list[str] = []
    seen: set[str] = set()
    for anchor in anchors:
        for eid in anchor.evidence_ids_json or []:
            if eid not in seen:
                all_evidence_ids.append(eid)
                seen.add(eid)

    # Load evidence items
    evidence_items: list[EvidenceItemOut] = []
    if all_evidence_ids:
        stmt_ev = select(Evidence).where(Evidence.evidence_id.in_(all_evidence_ids))
        for ev in session.scalars(stmt_ev).all():
            evidence_items.append(
                EvidenceItemOut(
                    evidence_id=ev.evidence_id,
                    source_type=ev.source_type,
                    url=ev.canonical_url,
                    claim_frame=ev.claim_frame,
                    snippet=ev.snippet,
                    captured_at=ev.captured_at,
                )
            )

    return DraftReviewOut(
        draft_id=draft.draft_id,
        contact=ContactSummaryOut(
            contact_id=contact.contact_id if contact else draft.contact_id,
            full_name=contact.full_name if contact else None,
            role=contact.role_json if contact else None,
            channels=contact.channels_json if contact else [],
        ),
        account=AccountSummaryOut(
            account_id=account.account_id if account else draft.account_id,
            name=account.name if account else "",
            domain=account.domain if account else None,
            country=account.country if account else None,
        ),
        subject=draft.subject,
        body=draft.body,
        channel=draft.channel,
        language=draft.language,
        risk_flags=draft.risk_flags_json or [],
        anchors=[
            AnchorOut(
                anchor_key=a.anchor_key,
                span=a.span,
                evidence_ids=a.evidence_ids_json or [],
            )
            for a in anchors
        ],
        evidence_items=evidence_items,
        v=draft.v,
    )


@app.post(
    "/drafts/{draft_id}/decision",
    response_model=DecisionSubmittedOut,
    status_code=201,
)
def submit_decision(
    draft_id: str,
    body: DecisionIn,
    session: Session = Depends(get_session),
):
    """
    Submit a review decision for a draft.

    Creates an approval_request WorkItem with decision data so the worker
    can record the ApprovalDecision and route deterministically by status.

    Idempotent: the same reviewer+draft combination is deduplicated via
    the idempotency_key unique index on work_items.
    """
    # Validate draft exists
    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Validate reviewer_role — viewer cannot record decisions
    if body.reviewer_role not in _REVIEWER_ROLES_ALLOWED:
        raise HTTPException(
            status_code=422,
            detail=f"reviewer_role '{body.reviewer_role}' does not have authority "
            "to record decisions. Allowed roles: operator, admin.",
        )

    # Validate status
    if body.status not in APPROVAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. "
            f"Allowed: {sorted(APPROVAL_STATUSES)}",
        )

    # Build work item
    work_item_id = f"wi:{uuid.uuid4()}"
    idempotency_key = f"decision_submit:{draft_id}:{body.reviewer_id}:v1"
    payload = {
        "v": 1,
        "data": {
            "draft_id": draft_id,
            "status": body.status,
            "reviewer_id": body.reviewer_id,
            "reviewer_role": body.reviewer_role,
            "notes": body.notes,
            "overridden_gates": body.overridden_gates,
        },
    }

    # Insert idempotently
    import json

    sql = text(
        """
        INSERT INTO work_items (
            work_item_id, entity_ref_type, entity_ref_id, stage,
            payload_json, payload_version,
            attempt_budget_remaining, attempt_budget_policy,
            idempotency_key,
            trace_run_id, trace_parent_work_item_id,
            trace_correlation_id, trace_policy_pack_id,
            created_at
        ) VALUES (
            :work_item_id, 'contact', :entity_ref_id, 'approval_request',
            CAST(:payload AS JSONB), 1,
            3, 'standard',
            :idempotency_key,
            :trace_run_id, NULL,
            :trace_correlation_id, 'safe_v0_1',
            now()
        ) ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING work_item_id
        """
    )
    result = session.execute(
        sql,
        {
            "work_item_id": work_item_id,
            "entity_ref_id": draft.contact_id,
            "payload": json.dumps(payload),
            "idempotency_key": idempotency_key,
            "trace_run_id": f"run:{uuid.uuid4()}",
            "trace_correlation_id": f"corr:{draft_id}",
        },
    )
    row = result.fetchone()
    created = row is not None
    if not created:
        # Look up existing work_item_id for this idempotency key
        existing = session.execute(
            text("SELECT work_item_id FROM work_items WHERE idempotency_key = :key"),
            {"key": idempotency_key},
        ).first()
        work_item_id = existing[0] if existing else work_item_id

    session.commit()

    # Attempt to enqueue to RQ (best-effort; worker will also pick up from DB)
    _try_enqueue_rq(work_item_id, "approval_request")

    return DecisionSubmittedOut(
        work_item_id=work_item_id,
        draft_id=draft_id,
        status=body.status,
        created=created,
    )


def _try_enqueue_rq(work_item_id: str, stage: str) -> None:
    """
    Best-effort enqueue of a work item to the RQ default queue.

    Uses the rq library to add a job that calls
    aose_worker.run_worker.process_work_item(work_item_id, stage).
    Silently swallows all errors — the worker will still find the
    work item in the DB on its next polling cycle.
    """
    try:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        from redis import Redis  # noqa: PLC0415
        from rq import Queue  # noqa: PLC0415

        conn = Redis.from_url(redis_url)
        q = Queue(connection=conn)
        q.enqueue(
            "aose_worker.run_worker.process_work_item",
            work_item_id,
            stage,
        )
    except Exception:  # noqa: BLE001
        pass
