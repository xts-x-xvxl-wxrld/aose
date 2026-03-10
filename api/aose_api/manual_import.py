"""
Manual contact import service for Epic G2.

Implements CSV-based contact import with full canonicalization, dedup, and
downstream contact_enrichment work item enqueue.

CSV contract (CONTRACT.yaml manual_contact_import.csv_contract):
  Required columns:  account_id, full_name
  At least one of:   email, linkedin_url
  Optional columns:  role_title, role_cluster, role_confidence,
                     source_provider, source_ref, observed_at, confidence
  Forbidden rows:    missing account_id, missing full_name,
                     missing both email and linkedin_url, unknown account_id

Defaults when omitted:
  source_provider = "MANUAL_CSV"
  source_ref = "csv_row:<row_number>"
  observed_at = import timestamp (ISO 8601)

All writes are idempotent (ON CONFLICT DO NOTHING).
Replay of the same CSV row produces zero duplicate contacts or aliases.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_api.ids import make_contact_id, normalize_email, normalize_linkedin_url

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SOURCE_PROVIDER_DEFAULT = "MANUAL_CSV"
_ALLOWED_ROLE_CLUSTERS: frozenset[str] = frozenset(
    {"economic_buyer", "influencer", "gatekeeper", "referrer"}
)

REQUIRED_COLUMNS: frozenset[str] = frozenset({"account_id", "full_name"})
IDENTITY_COLUMNS: frozenset[str] = frozenset({"email", "linkedin_url"})
OPTIONAL_COLUMNS: frozenset[str] = frozenset(
    {
        "role_title",
        "role_cluster",
        "role_confidence",
        "source_provider",
        "source_ref",
        "observed_at",
        "confidence",
    }
)

# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class RowError:
    """Details about a single rejected row."""

    row_number: int
    error_code: str
    detail: str


@dataclass
class ImportSummary:
    """Deterministic summary returned for every import run."""

    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    contacts_created: int = 0
    contacts_updated: int = 0  # always 0 with idempotent DO NOTHING writes
    aliases_created: int = 0
    parked_count: int = 0  # role-ambiguous rows accepted but flagged for human review
    enrichment_enqueued: int = 0
    errors: list[RowError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSV parsing + header validation
# ---------------------------------------------------------------------------


class ImportSchemaError(Exception):
    """Raised when the CSV header does not satisfy the contract."""


def parse_csv_header(header: list[str]) -> None:
    """
    Validate the CSV header row against the contract.

    Raises ImportSchemaError if any required column is missing or if no
    identity column (email, linkedin_url) is present.
    """
    cols = frozenset(c.strip().lower() for c in header)
    missing_required = REQUIRED_COLUMNS - cols
    if missing_required:
        raise ImportSchemaError(
            f"CSV is missing required columns: {sorted(missing_required)}"
        )
    if not (cols & IDENTITY_COLUMNS):
        raise ImportSchemaError(
            "CSV must include at least one identity column: email or linkedin_url"
        )


# ---------------------------------------------------------------------------
# DB helpers (text() SQL — no ORM import complexity for write path)
# ---------------------------------------------------------------------------


def _account_exists(session: Session, account_id: str) -> bool:
    row = session.execute(
        text("SELECT 1 FROM accounts WHERE account_id = :id"),
        {"id": account_id},
    ).first()
    return row is not None


def _write_contact(
    session: Session,
    contact_id: str,
    account_id: str,
    full_name: str,
    norm_email: str | None,
    role_json: dict | None,
    provenance: dict,
    source_trace: dict,
) -> bool:
    """
    Insert Contact row (idempotent via ON CONFLICT DO NOTHING).

    Returns True if newly inserted, False if already existed.
    """
    channels: list[dict] = []
    if norm_email:
        channels.append(
            {
                "type": "email",
                "value": norm_email,
                "validated": "unverified",
                "validated_at": None,
                "source_trace": source_trace,
            }
        )

    result = session.execute(
        text(
            """
            INSERT INTO contacts (
                contact_id, account_id, full_name,
                role_json, channels_json, provenance_json,
                status, v
            ) VALUES (
                :contact_id, :account_id, :full_name,
                CAST(:role_json AS JSONB), CAST(:channels_json AS JSONB),
                CAST(:provenance_json AS JSONB),
                'candidate', 1
            ) ON CONFLICT (contact_id) DO NOTHING
            """
        ),
        {
            "contact_id": contact_id,
            "account_id": account_id,
            "full_name": full_name,
            "role_json": json.dumps(role_json),
            "channels_json": json.dumps(channels),
            "provenance_json": json.dumps(provenance),
        },
    )
    return result.rowcount > 0


def _write_alias(
    session: Session,
    contact_id: str,
    account_id: str,
    alias_type: str,
    alias_value: str,
) -> bool:
    """
    Insert ContactAlias row (idempotent via ON CONFLICT DO NOTHING).

    Returns True if newly inserted.
    """
    result = session.execute(
        text(
            """
            INSERT INTO contact_aliases (
                contact_id, account_id, alias_type, alias_value, v
            ) VALUES (
                :contact_id, :account_id, :alias_type, :alias_value, 1
            ) ON CONFLICT (contact_id, alias_type) DO NOTHING
            """
        ),
        {
            "contact_id": contact_id,
            "account_id": account_id,
            "alias_type": alias_type,
            "alias_value": alias_value,
        },
    )
    return result.rowcount > 0


def _enqueue_enrichment(
    session: Session,
    contact_id: str,
    import_run_id: str,
) -> bool:
    """
    Enqueue a contact_enrichment WorkItem (idempotent via idempotency_key).

    Returns True if newly inserted.

    Formula (CONTRACT.yaml idempotency.work_item_keys.contact_enrichment):
      enrich:<contact_id>:email:v1
    """
    idempotency_key = f"enrich:{contact_id}:email:v1"
    work_item_id = f"wi:{uuid.uuid4().hex}"
    payload = {"v": 1, "data": {"contact_id": contact_id}}

    result = session.execute(
        text(
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
                :work_item_id, 'contact', :contact_id, 'contact_enrichment',
                CAST(:payload AS JSONB), 1,
                2, 'standard',
                :idempotency_key,
                :trace_run_id, NULL,
                :trace_correlation_id, 'safe_v0_1',
                now()
            ) ON CONFLICT (idempotency_key) DO NOTHING
            """
        ),
        {
            "work_item_id": work_item_id,
            "contact_id": contact_id,
            "payload": json.dumps(payload),
            "idempotency_key": idempotency_key,
            "trace_run_id": import_run_id,
            "trace_correlation_id": import_run_id,
        },
    )
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Row-level processing
# ---------------------------------------------------------------------------


def _coerce_float(raw: str | None) -> float | None:
    if not raw or not raw.strip():
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _is_role_ambiguous(role_cluster: str | None) -> bool:
    """
    Return True if role_cluster is set but not in the locked allowed set.
    Missing cluster (None) is not considered ambiguous.
    """
    return role_cluster is not None and role_cluster not in _ALLOWED_ROLE_CLUSTERS


def process_row(
    session: Session,
    row: dict[str, str],
    row_number: int,
    import_timestamp: str,
    import_run_id: str,
    summary: ImportSummary,
) -> None:
    """
    Process one CSV row. Updates summary in-place.

    Row numbering starts at 1 (first data row after header).
    """
    summary.rows_total += 1

    # --- Required field checks ---
    account_id = row.get("account_id", "").strip()
    full_name = row.get("full_name", "").strip()

    if not account_id:
        summary.rows_rejected += 1
        summary.errors.append(
            RowError(row_number, "contract_error", "missing account_id")
        )
        return

    if not full_name:
        summary.rows_rejected += 1
        summary.errors.append(
            RowError(row_number, "contract_error", "missing full_name")
        )
        return

    # --- Account existence check ---
    if not _account_exists(session, account_id):
        summary.rows_rejected += 1
        summary.errors.append(
            RowError(
                row_number,
                "contract_error",
                f"unknown account_id: {account_id!r}",
            )
        )
        return

    # --- Normalize identities ---
    raw_email = row.get("email", "").strip() or None
    raw_li = row.get("linkedin_url", "").strip() or None

    norm_email = normalize_email(raw_email)
    norm_li = normalize_linkedin_url(raw_li)

    if norm_email is None and norm_li is None:
        summary.rows_rejected += 1
        summary.errors.append(
            RowError(
                row_number,
                "contract_error",
                "both email and linkedin_url are missing or invalid after normalization",
            )
        )
        return

    # --- Compute contact_id ---
    contact_id = make_contact_id(
        account_id=account_id, email=raw_email, linkedin_url=raw_li
    )
    if contact_id is None:
        summary.rows_rejected += 1
        summary.errors.append(
            RowError(row_number, "contract_error", "cannot compute contact_id")
        )
        return

    # --- Provenance defaults ---
    source_provider = row.get("source_provider", "").strip() or _SOURCE_PROVIDER_DEFAULT
    source_ref = row.get("source_ref", "").strip() or f"csv_row:{row_number}"
    observed_at = row.get("observed_at", "").strip() or import_timestamp

    provenance = {
        "source_provider": source_provider,
        "source_ref": source_ref,
        "observed_at": observed_at,
        "import_run_id": import_run_id,
    }

    source_trace = {
        "source_provider": source_provider,
        "source_ref": source_ref,
        "observed_at": observed_at,
        "confidence": _coerce_float(row.get("confidence")),
    }

    # --- Role fields ---
    role_title = row.get("role_title", "").strip() or None
    role_cluster = row.get("role_cluster", "").strip() or None
    role_confidence = _coerce_float(row.get("role_confidence"))

    role_json: dict | None = None
    if role_title or role_cluster:
        role_json = {
            "title": role_title,
            "cluster": role_cluster,
            "confidence": role_confidence,
        }

    # --- Role ambiguity check ---
    # Per SPEC-G2: ambiguous role + no LinkedIn → accept contact but count in parked_count
    is_ambiguous = _is_role_ambiguous(role_cluster) and norm_li is None

    # --- Write Contact ---
    contact_created = _write_contact(
        session,
        contact_id=contact_id,
        account_id=account_id,
        full_name=full_name,
        norm_email=norm_email,
        role_json=role_json,
        provenance=provenance,
        source_trace=source_trace,
    )

    if contact_created:
        summary.contacts_created += 1
    # contacts_updated stays 0 (DO NOTHING semantics)

    # --- Write aliases ---
    if norm_email:
        alias_created = _write_alias(
            session, contact_id, account_id, "email_normalized", norm_email
        )
        if alias_created:
            summary.aliases_created += 1

    if norm_li:
        alias_created = _write_alias(
            session, contact_id, account_id, "linkedin_url_normalized", norm_li
        )
        if alias_created:
            summary.aliases_created += 1

    # --- Enqueue contact_enrichment ---
    if _enqueue_enrichment(session, contact_id, import_run_id):
        summary.enrichment_enqueued += 1

    if is_ambiguous:
        summary.parked_count += 1

    summary.rows_accepted += 1


# ---------------------------------------------------------------------------
# Public import entry point
# ---------------------------------------------------------------------------


def import_contacts_csv(
    session: Session,
    csv_content: str,
) -> ImportSummary:
    """
    Parse and import a contact CSV string.

    Args:
        session:     SQLAlchemy Session. Caller is responsible for committing
                     after this call if desired (or after the endpoint returns).
        csv_content: Raw CSV text (UTF-8 decoded).

    Returns:
        ImportSummary with per-row and aggregate counts.

    Raises:
        ImportSchemaError: If the CSV header does not satisfy the contract.
                           Raised before any row processing.
    """
    import_timestamp = datetime.now(tz=timezone.utc).isoformat()
    import_run_id = f"csv_import:{uuid.uuid4().hex[:16]}"

    reader = csv.DictReader(io.StringIO(csv_content))

    if reader.fieldnames is None:
        raise ImportSchemaError("CSV is empty or has no header row")

    parse_csv_header(list(reader.fieldnames))

    summary = ImportSummary()

    for row_number, row in enumerate(reader, start=1):
        process_row(
            session=session,
            row=dict(row),
            row_number=row_number,
            import_timestamp=import_timestamp,
            import_run_id=import_run_id,
            summary=summary,
        )

    return summary
