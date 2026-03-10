"""
Account discovery service for Epic E.

Implements the core discovery logic:
  1. Load QueryObject and SellerProfile from canonical storage.
  2. Call the configured adapter.
  3. Normalize candidates (already done at adapter boundary).
  4. Write canonical Account, AccountAlias, Evidence records.
  5. Enqueue downstream intent_fit_scoring WorkItems.

Rules:
- Uses text() SQL to avoid importing aose_api ORM models into the worker.
- All writes are idempotent via ON CONFLICT DO NOTHING.
- Does NOT write Scorecard, Contact, OutreachDraft, ApprovalDecision, SendAttempt.
- Budget decrement is the caller's (handler's) responsibility.
- Structured event emission is the caller's (handler's) responsibility.
- CAST() syntax used for explicit type casts to avoid SQLAlchemy text() parser
  conflicts with PostgreSQL's :: operator when adjacent to named parameters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_worker.adapters.account_discovery.base import AccountDiscoveryAdapter
from aose_worker.adapters.account_discovery.types import AccountDiscoveryCandidate
from aose_worker.canonical_ids import (
    make_account_id,
    make_alias_id,
    make_evidence_id,
    make_scoring_idempotency_key,
    make_work_item_id,
    normalize_domain,
)
from aose_worker.services.dedup import (
    extract_account_trust_metadata,
    merge_evidence_ids,
    should_update_account,
)
from aose_api.scorecard_contract import ALLOWED_EVIDENCE_CATEGORIES

# ---------------------------------------------------------------------------
# Service result
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryServiceResult:
    """Summary of a completed account discovery service run."""

    accounts_created: int = 0
    accounts_updated: int = 0
    accounts_skipped: int = 0  # already existed (idempotent replay)
    evidence_created: int = 0
    downstream_enqueued: int = 0
    no_signal: bool = False
    stop_reason: str | None = None
    account_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------


def _parse_iso_dt(value: str) -> datetime:
    """
    Parse an ISO 8601 timestamp string to a timezone-aware datetime.

    Handles 'Z' suffix by replacing with '+00:00'.
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# DB read helpers (text() SQL — no aose_api import)
# ---------------------------------------------------------------------------


def _load_query_object(session: Session, query_object_id: str) -> dict[str, Any]:
    """Load a QueryObject row by primary key. Raises ValueError if not found."""
    sql = text(
        """
        SELECT query_object_id, seller_id, buyer_context, priority,
               keywords, exclusions, rationale, v
        FROM query_objects
        WHERE query_object_id = :id
        """
    )
    row = session.execute(sql, {"id": query_object_id}).mappings().first()
    if row is None:
        raise ValueError(f"QueryObject not found: {query_object_id!r}")
    return dict(row)


def _load_seller_profile(session: Session, seller_id: str) -> dict[str, Any]:
    """Load a SellerProfile row by primary key. Raises ValueError if not found."""
    sql = text(
        """
        SELECT seller_id, offer_what, offer_where, offer_who,
               offer_positioning, constraints_avoid_claims,
               constraints_allowed_channels, constraints_languages,
               policy_pack_id, v
        FROM seller_profiles
        WHERE seller_id = :id
        """
    )
    row = session.execute(sql, {"id": seller_id}).mappings().first()
    if row is None:
        raise ValueError(f"SellerProfile not found: {seller_id!r}")
    return dict(row)


# ---------------------------------------------------------------------------
# Canonical write helpers
# ---------------------------------------------------------------------------


def _registry_alias_value(candidate: AccountDiscoveryCandidate) -> str | None:
    """Build deterministic registry alias value for a candidate, if available."""
    if not candidate.registry_id or not candidate.country:
        return None
    return f"{candidate.country}-{candidate.registry_id.strip().upper()}"


def _find_account_id_by_alias(
    session: Session,
    alias_type: str,
    alias_value: str,
) -> str | None:
    """
    Resolve an account_id from aliases deterministically.

    If data corruption produced multiple rows with the same alias identity,
    select the lexicographically first account_id to preserve deterministic
    replay behavior.
    """
    sql = text(
        """
        SELECT account_id
        FROM account_aliases
        WHERE alias_type = :alias_type
          AND alias_value = :alias_value
        ORDER BY account_id ASC
        LIMIT 1
        """
    )
    row = session.execute(
        sql,
        {"alias_type": alias_type, "alias_value": alias_value},
    ).first()
    return str(row[0]) if row else None


def _load_account_state(session: Session, account_id: str) -> dict[str, Any] | None:
    """Load mutable account state needed for deterministic update decisions."""
    sql = text(
        """
        SELECT account_id, name, domain, country, provenance,
               evidence_ids, confidence, status, v
        FROM accounts
        WHERE account_id = :account_id
        """
    )
    row = session.execute(sql, {"account_id": account_id}).mappings().first()
    if row is None:
        return None
    return dict(row)


def _resolve_canonical_account_id(
    session: Session,
    candidate: AccountDiscoveryCandidate,
) -> str:
    """
    Resolve canonical account identity with locked precedence:
      1) registry (country + registry_id)
      2) normalized domain
      3) deterministic tmp hash fallback
    """
    registry_alias = _registry_alias_value(candidate)
    if registry_alias:
        registry_account_id = make_account_id(
            country=candidate.country,
            registry_id=candidate.registry_id,
            domain=None,
            legal_name_normalized=None,
            source_provider=None,
            source_ref=None,
        )
        if _load_account_state(session, registry_account_id):
            return registry_account_id
        alias_match = _find_account_id_by_alias(session, "registry", registry_alias)
        if alias_match:
            return alias_match

    normalized_domain = normalize_domain(candidate.domain)
    if normalized_domain:
        domain_account_id = make_account_id(
            country=None,
            registry_id=None,
            domain=normalized_domain,
            legal_name_normalized=None,
            source_provider=None,
            source_ref=None,
        )
        if _load_account_state(session, domain_account_id):
            return domain_account_id
        alias_match = _find_account_id_by_alias(session, "domain", normalized_domain)
        if alias_match:
            return alias_match

    return make_account_id(
        country=candidate.country,
        registry_id=candidate.registry_id,
        domain=normalized_domain,
        legal_name_normalized=candidate.legal_name_normalized,
        source_provider=candidate.source_provider,
        source_ref=candidate.source_ref,
    )


def _build_account_provenance_entry(
    candidate: AccountDiscoveryCandidate,
    query_object_id: str,
    adapter_name: str,
) -> dict[str, Any]:
    """Build a deterministic account provenance entry."""
    source_type = candidate.evidence[0].source_type if candidate.evidence else "unknown"
    return {
        "adapter": adapter_name,
        "query_object_id": query_object_id,
        "captured_at": candidate.observed_at,
        "source_type": source_type,
        "source_ref": candidate.source_ref,
    }


def _write_account(
    session: Session,
    account_id: str,
    existing_account: dict[str, Any] | None,
    candidate: AccountDiscoveryCandidate,
    evidence_ids: list[str],
    query_object_id: str,
    adapter_name: str,
    now: datetime,
) -> tuple[bool, bool]:
    """
    Insert or deterministically update an Account row.

    Returns (newly_created, updated).
    candidate status is always 'candidate' after discovery (CONTRACT.yaml
    locked_defaults.candidate_status_after_discovery).
    """
    new_prov = _build_account_provenance_entry(candidate, query_object_id, adapter_name)
    if existing_account is None:
        provenance = [new_prov]
        deduped_evidence_ids = merge_evidence_ids([], evidence_ids)
        sql = text(
            """
            INSERT INTO accounts (
                account_id, name, domain, country,
                provenance, evidence_ids, confidence, status, v
            ) VALUES (
                :account_id, :name, :domain, :country,
                CAST(:provenance AS JSONB), CAST(:evidence_ids AS JSONB),
                :confidence, 'candidate', 1
            ) ON CONFLICT (account_id) DO NOTHING
            """
        )
        result = session.execute(
            sql,
            {
                "account_id": account_id,
                "name": candidate.legal_name,
                "domain": candidate.domain,
                "country": candidate.country,
                "provenance": json.dumps(provenance),
                "evidence_ids": json.dumps(deduped_evidence_ids),
                "confidence": candidate.confidence,
            },
        )
        return result.rowcount > 0, False

    existing_provenance = existing_account.get("provenance")
    existing_source_type, existing_captured_at, existing_source_ref = (
        extract_account_trust_metadata(existing_provenance)
    )
    overwrite = should_update_account(
        existing_source_type=existing_source_type,
        existing_captured_at=existing_captured_at,
        existing_source_ref=existing_source_ref,
        new_source_type=new_prov["source_type"],
        new_captured_at=candidate.observed_at,
        new_source_ref=candidate.source_ref,
    )

    existing_evidence_ids = existing_account.get("evidence_ids") or []
    merged_evidence_ids = merge_evidence_ids(existing_evidence_ids, evidence_ids)

    if overwrite:
        sql = text(
            """
            UPDATE accounts
            SET name = :name,
                domain = :domain,
                country = :country,
                provenance = CAST(:provenance AS JSONB),
                evidence_ids = CAST(:evidence_ids AS JSONB),
                confidence = :confidence
            WHERE account_id = :account_id
            """
        )
        result = session.execute(
            sql,
            {
                "account_id": account_id,
                "name": candidate.legal_name,
                "domain": candidate.domain,
                "country": candidate.country,
                "provenance": json.dumps([new_prov]),
                "evidence_ids": json.dumps(merged_evidence_ids),
                "confidence": candidate.confidence,
            },
        )
        return False, result.rowcount > 0

    if merged_evidence_ids != existing_evidence_ids:
        sql = text(
            """
            UPDATE accounts
            SET evidence_ids = CAST(:evidence_ids AS JSONB)
            WHERE account_id = :account_id
            """
        )
        result = session.execute(
            sql,
            {
                "account_id": account_id,
                "evidence_ids": json.dumps(merged_evidence_ids),
            },
        )
        return False, result.rowcount > 0

    return False, False


def _write_account_alias(
    session: Session,
    account_id: str,
    alias_type: str,
    alias_value: str,
    source_provider: str | None,
    source_ref: str | None,
    now: datetime,
) -> None:
    """
    Insert an AccountAlias row (idempotent via ON CONFLICT DO NOTHING on
    the unique composite constraint uq_account_aliases_account_type_value).
    """
    alias_id = make_alias_id(account_id, alias_type, alias_value)
    sql = text(
        """
        INSERT INTO account_aliases (
            account_alias_id, account_id, alias_type, alias_value,
            source_provider, source_ref, created_at, v
        ) VALUES (
            :alias_id, :account_id, :alias_type, :alias_value,
            :source_provider, :source_ref, :created_at, 1
        ) ON CONFLICT ON CONSTRAINT uq_account_aliases_account_type_value DO NOTHING
        """
    )
    session.execute(
        sql,
        {
            "alias_id": alias_id,
            "account_id": account_id,
            "alias_type": alias_type,
            "alias_value": alias_value,
            "source_provider": source_provider,
            "source_ref": source_ref,
            "created_at": now,
        },
    )


def _write_aliases(
    session: Session,
    account_id: str,
    candidate: AccountDiscoveryCandidate,
    now: datetime,
) -> None:
    """
    Write all applicable alias rows for a candidate.

    CONTRACT.yaml required_alias_writes_when_present:
    - registry: { source, id } when registry_id is present
    - domain: normalized domain string when domain is present
    - legal_name_normalized: when legal_name_normalized is present
    """
    # Registry alias
    if candidate.registry_id and candidate.country:
        registry_value = f"{candidate.country}-{candidate.registry_id.strip().upper()}"
        _write_account_alias(
            session,
            account_id,
            "registry",
            registry_value,
            candidate.source_provider,
            candidate.source_ref,
            now,
        )

    # Domain alias
    if candidate.domain:
        _write_account_alias(
            session,
            account_id,
            "domain",
            candidate.domain,
            None,
            None,
            now,
        )

    # Legal name normalized alias
    if candidate.legal_name_normalized:
        _write_account_alias(
            session,
            account_id,
            "legal_name_normalized",
            candidate.legal_name_normalized,
            None,
            None,
            now,
        )


def _write_evidence(
    session: Session,
    ev_ptr: Any,  # EvidencePointer
    candidate: AccountDiscoveryCandidate,
    query_object_id: str,
    adapter_name: str,
    now: datetime,
) -> tuple[str, bool]:
    """
    Insert Evidence row (idempotent via ON CONFLICT DO NOTHING on evidence_id PK).

    Returns (evidence_id, newly_created).
    EvidenceContent is omitted for the dummy adapter; the capture policy
    applies "pointer-only" storage for non-registry sources in E2.
    """
    evidence_id = make_evidence_id(
        source_type=ev_ptr.source_type,
        canonical_url=ev_ptr.url,
        captured_at_iso=ev_ptr.captured_at,
        snippet_text=ev_ptr.snippet,
    )
    provenance = {
        "adapter": adapter_name,
        "query_object_id": query_object_id,
        **ev_ptr.provenance,
    }
    category = _resolve_evidence_category_for_write(
        source_type=ev_ptr.source_type,
        provenance=provenance,
    )

    # Parse ISO timestamp strings to datetime objects for psycopg3 compatibility
    captured_at_dt = _parse_iso_dt(ev_ptr.captured_at)
    observed_at_dt = _parse_iso_dt(candidate.observed_at)

    sql = text(
        """
        INSERT INTO evidence (
            evidence_id, source_type, canonical_url, captured_at,
            snippet, claim_frame, source_provider, source_ref,
            observed_at, confidence, category, provenance_json, content_ref_id, v
        ) VALUES (
            :evidence_id, :source_type, :canonical_url, :captured_at,
            :snippet, :claim_frame, :source_provider, :source_ref,
            :observed_at, :confidence, :category, CAST(:provenance AS JSONB),
            NULL, 1
        ) ON CONFLICT (evidence_id) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "evidence_id": evidence_id,
            "source_type": ev_ptr.source_type,
            "canonical_url": ev_ptr.url,
            "captured_at": captured_at_dt,
            "snippet": ev_ptr.snippet,
            "claim_frame": ev_ptr.claim_frame,
            "source_provider": candidate.source_provider,
            "source_ref": candidate.source_ref,
            "observed_at": observed_at_dt,
            "confidence": candidate.confidence,
            "category": category,
            "provenance": json.dumps(provenance),
        },
    )
    return evidence_id, result.rowcount > 0


def _resolve_evidence_category_for_write(
    *,
    source_type: str,
    provenance: dict[str, Any],
) -> str | None:
    raw_category = provenance.get("category")
    if isinstance(raw_category, str):
        candidate = raw_category.strip().lower()
        if candidate in ALLOWED_EVIDENCE_CATEGORIES:
            return candidate

    normalized_source_type = source_type.strip().lower()
    if normalized_source_type.startswith("registry"):
        return "firmographic"

    return None


def _enqueue_scoring_work_item(
    session: Session,
    account_id: str,
    query_object_id: str,
    parent_work_item: dict[str, Any],
    now: datetime,
) -> bool:
    """
    Enqueue a downstream intent_fit_scoring WorkItem (idempotent via
    ON CONFLICT DO NOTHING on idempotency_key unique constraint).

    Returns True if the work item was newly inserted.
    """
    idempotency_key = make_scoring_idempotency_key(account_id, query_object_id)
    work_item_id = make_work_item_id()
    payload = {"v": 1, "data": {"account_id": account_id}}

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
            :work_item_id, 'account', :account_id, 'intent_fit_scoring',
            CAST(:payload AS JSONB), 1,
            :attempt_budget_remaining, :attempt_budget_policy,
            :idempotency_key,
            :trace_run_id, :trace_parent_work_item_id,
            :trace_correlation_id, :trace_policy_pack_id,
            :created_at
        ) ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "work_item_id": work_item_id,
            "account_id": account_id,
            "payload": json.dumps(payload),
            "attempt_budget_remaining": parent_work_item.get(
                "attempt_budget_remaining", 3
            ),
            "attempt_budget_policy": parent_work_item.get(
                "attempt_budget_policy", "standard"
            ),
            "idempotency_key": idempotency_key,
            "trace_run_id": parent_work_item.get("trace_run_id", ""),
            "trace_parent_work_item_id": parent_work_item.get("work_item_id"),
            "trace_correlation_id": parent_work_item.get("trace_correlation_id", ""),
            "trace_policy_pack_id": parent_work_item.get(
                "trace_policy_pack_id", "safe_v0_1"
            ),
            "created_at": now,
        },
    )
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------


def run_account_discovery(
    *,
    session: Session,
    query_object_id: str,
    adapter: AccountDiscoveryAdapter,
    limits: dict[str, Any],
    context: dict[str, Any],
    parent_work_item: dict[str, Any],
) -> DiscoveryServiceResult:
    """
    Run account discovery for one query_object_id.

    Args:
        session:          SQLAlchemy Session (caller manages transaction).
        query_object_id:  ID of the QueryObject to discover against.
        adapter:          AccountDiscoveryAdapter implementation to use.
        limits:           Run caps dict (max_accounts, max_external_calls, etc.).
        context:          Caller context (policy_pack_id, run_id, trace fields).
        parent_work_item: Dict of the parent WorkItem row (for trace propagation
                          and downstream work item creation).

    Returns:
        DiscoveryServiceResult summarising what was written.

    Raises:
        ValueError: if QueryObject or SellerProfile is not found (contract error).
    """
    # 1. Load canonical pre-conditions
    qo = _load_query_object(session, query_object_id)
    _load_seller_profile(session, qo["seller_id"])  # raises if missing

    # 2. Call adapter (budget already spent by handler before this call)
    adapter_result = adapter.search_accounts(qo, limits, context)

    # 3. Process each candidate
    now = datetime.now(tz=timezone.utc)
    started_at = monotonic()
    adapter_name = adapter_result.adapter_name
    svc_result = DiscoveryServiceResult()
    max_accounts_per_run = int(
        limits.get("max_accounts_per_run", limits.get("max_accounts", 30))
    )
    max_accounts_per_query_object = int(limits.get("max_accounts_per_query_object", 10))
    max_runtime_seconds_per_run = int(limits.get("max_runtime_seconds_per_run", 900))

    # Stable processing order ensures deterministic behavior for equivalent input.
    candidates = sorted(
        adapter_result.candidates,
        key=lambda c: (
            c.country or "",
            c.registry_id or "",
            c.domain or "",
            c.legal_name_normalized or "",
            c.source_provider or "",
            c.source_ref or "",
        ),
    )

    for candidate in candidates:
        if monotonic() - started_at >= max_runtime_seconds_per_run:
            svc_result.stop_reason = "budget_exhausted"
            break
        if (
            svc_result.accounts_created >= max_accounts_per_run
            or svc_result.accounts_created >= max_accounts_per_query_object
        ):
            svc_result.stop_reason = "max_accounts_reached"
            break

        # Minimum creation rule (CONTRACT.yaml required_minimum_for_account_creation)
        has_legal_name_and_country = bool(candidate.legal_name and candidate.country)
        has_domain = bool(candidate.domain)
        if not has_legal_name_and_country and not has_domain:
            continue

        # Resolve canonical account_id using existing canonical identity first.
        account_id = _resolve_canonical_account_id(session, candidate)
        existing_account = _load_account_state(session, account_id)

        # Write Evidence rows first; collect IDs for account.evidence_ids
        evidence_ids: list[str] = []
        for ev_ptr in candidate.evidence:
            eid, ev_created = _write_evidence(
                session, ev_ptr, candidate, query_object_id, adapter_name, now
            )
            evidence_ids.append(eid)
            if ev_created:
                svc_result.evidence_created += 1
        evidence_ids = merge_evidence_ids([], evidence_ids)

        # Write Account row (create or deterministic overwrite)
        newly_created, updated = _write_account(
            session,
            account_id,
            existing_account,
            candidate,
            evidence_ids,
            query_object_id,
            adapter_name,
            now,
        )
        if newly_created:
            svc_result.accounts_created += 1
            svc_result.account_ids.append(account_id)
        elif updated:
            svc_result.accounts_updated += 1
            svc_result.account_ids.append(account_id)
        else:
            svc_result.accounts_skipped += 1

        # Write alias rows for all present normalized fields
        _write_aliases(session, account_id, candidate, now)

        # Enqueue downstream intent_fit_scoring work item
        enqueued = _enqueue_scoring_work_item(
            session, account_id, query_object_id, parent_work_item, now
        )
        if enqueued:
            svc_result.downstream_enqueued += 1

    # no_signal: current query yields zero new unique accounts after dedup.
    if svc_result.accounts_created == 0 and svc_result.stop_reason is None:
        svc_result.stop_reason = "no_signal"
        svc_result.no_signal = True
    elif svc_result.stop_reason == "no_signal":
        svc_result.no_signal = True

    return svc_result
