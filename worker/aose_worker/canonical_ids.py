"""
Local canonical ID builders for the AOSE worker package.

Mirrors the formulas in aose_api/aose_api/ids.py without importing from the
api package (the worker container does not install aose_api).

CONTRACT LOCK: All formulas here are locked by the data spine and epic contracts.
Any change must be synchronized with aose_api.ids so the two packages always
produce identical IDs for the same inputs.
"""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import urlparse, urlunparse


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sha256(value: str) -> str:
    """Return sha256 hex digest of a UTF-8 encoded string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_join(*parts: str) -> str:
    """Return sha256 hex digest of parts joined by '|'."""
    return _sha256("|".join(parts))


def _normalize_registry_id(value: str) -> str:
    """Normalize a registry ID: strip whitespace, uppercase."""
    return value.strip().upper()


# ---------------------------------------------------------------------------
# Domain normalization
# Identical implementation to aose_api.ids.normalize_domain and
# aose_worker.adapters.account_discovery.types.normalize_domain.
# ---------------------------------------------------------------------------


def normalize_domain(value: str | None) -> str | None:
    """
    Normalize a domain name or URL to canonical lowercase ASCII host.

    Rules match the Epic B helper in aose_api.ids:
    - Trim whitespace; parse host from URL if scheme present
    - Lowercase, remove port, remove trailing dot
    - Strip exactly one leading "www."
    - Convert to IDNA ASCII
    - Return None for empty or invalid input
    """
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    if "://" in value or value.startswith("//"):
        parsed = urlparse(value)
        host = parsed.hostname
    else:
        parsed = urlparse("https://" + value)
        host = parsed.hostname

    if not host:
        return None

    host = host.rstrip(".")

    if host.startswith("www."):
        host = host[4:]

    if not host:
        return None

    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return None

    return host if host else None


# ---------------------------------------------------------------------------
# Canonical ID builders (CONTRACT-locked formulas)
# ---------------------------------------------------------------------------


def make_account_id(
    country: str | None,
    registry_id: str | None,
    domain: str | None,
    legal_name_normalized: str | None,
    source_provider: str | None,
    source_ref: str | None,
) -> str:
    """
    Return canonical account ID using locked fallback precedence:

    1. account:<COUNTRY>-<REGISTRY_ID>  (when country + registry_id both present)
    2. account:<normalized_domain>       (when registry absent but domain present)
    3. account:tmp:<sha256(country|legal_name_normalized|source_provider|source_ref)>
    """
    # Tier 1: registry-based
    if country and registry_id:
        country_up = country.strip().upper()
        reg_norm = _normalize_registry_id(registry_id)
        return f"account:{country_up}-{reg_norm}"

    # Tier 2: domain-based
    normalized = normalize_domain(domain)
    if normalized:
        return f"account:{normalized}"

    # Tier 3: tmp hash
    hash_input = "|".join(
        [
            country or "",
            legal_name_normalized or "",
            source_provider or "",
            source_ref or "",
        ]
    )
    return f"account:tmp:{_sha256(hash_input)}"


def make_alias_id(account_id: str, alias_type: str, alias_value: str) -> str:
    """
    Return canonical alias ID.

    Formula: alias:<sha256(account_id|alias_type|alias_value)>
    """
    digest = _sha256(f"{account_id}|{alias_type}|{alias_value}")
    return f"alias:{digest}"


def make_evidence_id(
    source_type: str,
    canonical_url: str,
    captured_at_iso: str,
    snippet_text: str | None,
) -> str:
    """
    Return canonical evidence ID.

    Formula: evidence:<sha256(source_type|canonical_url|captured_at_iso|sha256(snippet_text_or_empty))>
    """
    snippet_hash = _sha256(snippet_text if snippet_text is not None else "")
    outer = _sha256_join(source_type, canonical_url, captured_at_iso, snippet_hash)
    return f"evidence:{outer}"


def make_work_item_id() -> str:
    """Return a new unique work item ID."""
    return f"wi:{uuid.uuid4().hex}"


def make_scoring_idempotency_key(account_id: str, query_object_id: str) -> str:
    """
    Return a deterministic idempotency key for an intent_fit_scoring WorkItem.

    Formula: scoring:{account_id}:{query_object_id}:v1

    Guarantees that replaying the same account_discovery run for the same
    account does not enqueue duplicate scoring work items.
    """
    return f"scoring:{account_id}:{query_object_id}:v1"


# ---------------------------------------------------------------------------
# Email normalization (mirrors aose_api.ids.normalize_email)
# ---------------------------------------------------------------------------


def normalize_email(value: str | None) -> str | None:
    """
    Normalize an email address to canonical form.

    Rules (Epic B, inherited by Epic G):
    - Trim whitespace
    - Split on '@'; invalid split => None
    - Lowercase local part
    - Normalize domain using normalize_domain
    - Rejoin as '<local>@<normalized_domain>'
    - Do NOT remove plus-tags or dots
    - Return None for invalid input
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    parts = value.split("@")
    if len(parts) != 2:
        return None
    local, domain_part = parts
    if not local:
        return None
    local = local.lower()
    normalized = normalize_domain(domain_part)
    if normalized is None:
        return None
    return f"{local}@{normalized}"


# ---------------------------------------------------------------------------
# LinkedIn URL normalization (mirrors aose_api.ids.normalize_linkedin_url)
# ---------------------------------------------------------------------------


def normalize_linkedin_url(value: str | None) -> str | None:
    """
    Normalize a LinkedIn profile URL to a stable canonical form.

    Rules (Epic B, inherited by Epic G):
    - Trim whitespace
    - Lowercase scheme and host
    - Remove query string and fragment
    - Remove trailing slash from path
    - Return None for invalid input
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if not scheme or not netloc:
        return None
    normalized = urlunparse((scheme, netloc, path, "", "", ""))
    return normalized if normalized else None


# ---------------------------------------------------------------------------
# Contact ID builders (CONTRACT.yaml contact_identity.contact_id_precedence)
# ---------------------------------------------------------------------------


def make_contact_id(
    account_id: str,
    email: str | None = None,
    linkedin_url: str | None = None,
) -> str | None:
    """
    Return canonical contact ID using locked fallback precedence, or None.

    Formula (CONTRACT.yaml contact_identity.contact_id_precedence):
      1. contact:<account_id>:<normalized_email>
      2. contact:<account_id>:<sha256(normalized_linkedin_url)>

    Returns None if both normalized identities are absent.
    """
    norm_email = normalize_email(email)
    if norm_email:
        return f"contact:{account_id}:{norm_email}"
    norm_li = normalize_linkedin_url(linkedin_url)
    if norm_li:
        return f"contact:{account_id}:{_sha256(norm_li)}"
    return None


# ---------------------------------------------------------------------------
# People-search and enrichment idempotency keys
# (CONTRACT.yaml idempotency.work_item_keys)
# ---------------------------------------------------------------------------


def make_people_search_idempotency_key(
    account_id: str, source_mode_or_adapter: str
) -> str:
    """
    Return idempotency key for a people_search WorkItem.

    Formula: ppl:<account_id>:<source_mode_or_adapter>:v1
    """
    return f"ppl:{account_id}:{source_mode_or_adapter}:v1"


def make_enrichment_idempotency_key(contact_id: str) -> str:
    """
    Return idempotency key for a contact_enrichment WorkItem.

    Formula: enrich:<contact_id>:email:v1
    """
    return f"enrich:{contact_id}:email:v1"


def make_copy_generate_idempotency_key(contact_id: str) -> str:
    """
    Return idempotency key for a copy_generate WorkItem.

    Formula: copy:<contact_id>:v1
    """
    return f"copy:{contact_id}:v1"


def make_draft_id(contact_id: str, sequence_no: int, variant_no: int) -> str:
    """
    Return canonical draft ID.

    Formula: draft:<contact_id>:seq<sequence_no>:v<variant_no>
    Mirrors aose_api.ids.make_draft_id — must stay in sync.
    """
    return f"draft:{contact_id}:seq{sequence_no}:v{variant_no}"


def make_anchor_key(draft_id: str, span: str, evidence_ids: list[str]) -> str:
    """
    Return deterministic personalization anchor key.

    Formula: anchor:<sha256(draft_id|span|sorted_evidence_ids_joined)>
    Mirrors aose_api.ids.make_anchor_key — must stay in sync.
    """
    sorted_ids = "|".join(sorted(evidence_ids))
    return f"anchor:{_sha256_join(draft_id, span, sorted_ids)}"


def make_approval_request_idempotency_key(draft_id: str) -> str:
    """
    Return idempotency key for an approval_request WorkItem.

    Formula: approval:<draft_id>:v1
    """
    return f"approval:{draft_id}:v1"


def make_decision_key(
    work_item_id: str,
    contact_id: str,
    action_type: str,
    policy_pack_id: str,
    draft_id: str,
) -> str:
    """
    Return decision key: sha256(work_item_id|contact_id|action_type|policy_pack_id|draft_id)

    Mirrors aose_api.ids.make_decision_key — must stay in sync.
    """
    return _sha256_join(work_item_id, contact_id, action_type, policy_pack_id, draft_id)


def make_decision_id(draft_id: str, decision_key: str) -> str:
    """
    Return canonical decision ID.

    Formula: decision:<draft_id>:<decision_key>
    Mirrors aose_api.ids.make_decision_id — must stay in sync.
    """
    return f"decision:{draft_id}:{decision_key}"


def make_dispatch_idempotency_key(draft_id: str, decision_id: str) -> str:
    """
    Return idempotency key for a downstream WorkItem enqueued by approval_request.

    Formula: dispatch:<draft_id>:<decision_id>:v1
    """
    return f"dispatch:{draft_id}:{decision_id}:v1"


def make_send_attempt_id(draft_id: str, channel: str) -> str:
    """
    Return canonical SendAttempt ID.

    Formula: send:<draft_id>:<channel>
    Locked by Epic I CONTRACT.yaml send_attempt.send_id formula.
    """
    return f"send:{draft_id}:{channel}"


def make_send_attempt_idempotency_key(draft_id: str, channel: str) -> str:
    """
    Return idempotency key for a SendAttempt.

    Formula: send:<draft_id>:<channel>:v1
    Locked by Epic I CONTRACT.yaml send_attempt.idempotency_key formula.
    """
    return f"send:{draft_id}:{channel}:v1"
