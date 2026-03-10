"""
Canonical ID builders and normalization helpers for AOSE.

All functions are pure, side-effect-free, and deterministic.
Hash function: sha256 hex digest over UTF-8 bytes.
Composite hash join delimiter: "|"
"""

from __future__ import annotations

import hashlib
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
# ---------------------------------------------------------------------------


def normalize_domain(value: str | None) -> str | None:
    """
    Normalize a domain name or URL to a canonical lowercase ASCII host.

    Rules:
    - Trim whitespace
    - If input looks like a URL, parse host and discard scheme/path/query/fragment
    - Lowercase
    - Remove port
    - Remove trailing dot
    - Strip exactly one leading "www."
    - Convert host to IDNA ASCII
    - Return None if result is empty or invalid
    """
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    # If it contains a scheme or starts with "//", parse as URL; otherwise treat
    # as a bare host (possibly with port or path).
    if "://" in value or value.startswith("//"):
        parsed = urlparse(value)
        host = parsed.hostname  # already lowercased, port stripped by urlparse
    else:
        # Prepend scheme so urlparse handles it correctly
        parsed = urlparse("https://" + value)
        host = parsed.hostname

    if not host:
        return None

    # Remove trailing dot (FQDN notation)
    host = host.rstrip(".")

    # Strip exactly one leading "www."
    if host.startswith("www."):
        host = host[4:]

    if not host:
        return None

    # Convert to IDNA ASCII (handles internationalized domain names)
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return None

    return host if host else None


# ---------------------------------------------------------------------------
# Email normalization
# ---------------------------------------------------------------------------


def normalize_email(value: str | None) -> str | None:
    """
    Normalize an email address to canonical form.

    Rules:
    - Trim whitespace
    - Split on "@"; invalid split => None
    - Lowercase local part
    - Normalize domain using normalize_domain
    - Rejoin as "<local>@<normalized_domain>"
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
# LinkedIn URL normalization
# ---------------------------------------------------------------------------


def normalize_linkedin_url(value: str | None) -> str | None:
    """
    Normalize a LinkedIn profile URL to a stable canonical form.

    Rules:
    - Trim whitespace
    - Lowercase scheme and host
    - Remove query string and fragment
    - Remove trailing slash from path
    - Keep path as the identity-bearing component
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

    # Reconstruct without query or fragment
    normalized = urlunparse((scheme, netloc, path, "", "", ""))
    return normalized if normalized else None


# ---------------------------------------------------------------------------
# Canonical ID builders
# ---------------------------------------------------------------------------


def make_seller_id(seller_slug: str) -> str:
    """Return canonical seller ID: seller:<seller_slug>"""
    return f"seller:{seller_slug}"


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


def make_contact_id(
    account_id: str,
    email: str | None = None,
    linkedin_url: str | None = None,
) -> str:
    """
    Return canonical contact ID using locked fallback precedence:

    1. contact:<account_id>:<normalized_email>
    2. contact:<account_id>:<sha256(normalized_linkedin_url)>

    Raises ValueError if both email and LinkedIn are missing/invalid.
    """
    # Tier 1: email
    norm_email = normalize_email(email)
    if norm_email:
        return f"contact:{account_id}:{norm_email}"

    # Tier 2: LinkedIn hash
    norm_li = normalize_linkedin_url(linkedin_url)
    if norm_li:
        return f"contact:{account_id}:{_sha256(norm_li)}"

    raise ValueError(
        f"Cannot build contact ID for account '{account_id}': "
        "both email and linkedin_url are missing or invalid."
    )


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


def make_draft_id(contact_id: str, sequence_no: int, variant_no: int) -> str:
    """
    Return canonical draft ID.

    Formula: draft:<contact_id>:seq<sequence_no>:v<variant_no>
    """
    return f"draft:{contact_id}:seq{sequence_no}:v{variant_no}"


def make_decision_key(
    work_item_id: str,
    contact_id: str,
    action_type: str,
    policy_pack_id: str,
    draft_id: str,
) -> str:
    """
    Return decision key: sha256(work_item_id|contact_id|action_type|policy_pack_id|draft_id)
    """
    return _sha256_join(work_item_id, contact_id, action_type, policy_pack_id, draft_id)


def make_decision_id(draft_id: str, decision_key: str) -> str:
    """
    Return canonical decision ID.

    Formula: decision:<draft_id>:<decision_key>
    """
    return f"decision:{draft_id}:{decision_key}"


def make_send_id(draft_id: str, channel: str) -> str:
    """
    Return canonical send ID.

    Formula: send:<draft_id>:<channel>
    """
    return f"send:{draft_id}:{channel}"


def make_send_idempotency_key(draft_id: str, channel: str) -> str:
    """
    Return send idempotency key.

    Formula: send:<draft_id>:<channel>:v1
    """
    return f"send:{draft_id}:{channel}:v1"


def make_anchor_key(draft_id: str, span: str, evidence_ids: list[str]) -> str:
    """
    Return deterministic personalization anchor key.

    Formula: anchor:<sha256(draft_id|span|sorted_evidence_ids_joined)>

    evidence_ids are sorted before hashing so insertion order does not affect identity.
    No formula was locked in the Epic B contract; this is the narrowest choice
    consistent with existing project conventions.
    """
    sorted_ids = "|".join(sorted(evidence_ids))
    return f"anchor:{_sha256_join(draft_id, span, sorted_ids)}"


def make_scorecard_id(
    entity_ref_type: str,
    entity_ref_id: str,
    computed_at_iso: str,
) -> str:
    """
    Return canonical scorecard ID.

    Formula: scorecard:<sha256(entity_ref_type|entity_ref_id|computed_at_iso)>

    Assumption: scorecard identity is scoped to the entity + the exact computed_at
    timestamp. Two scoring runs at different times produce different IDs; re-running
    the same snapshot produces the same ID (replay-safe via PK).
    No formula was locked in the Epic B contract; this is the narrowest deterministic
    choice consistent with existing project conventions.
    """
    return f"scorecard:{_sha256_join(entity_ref_type, entity_ref_id, computed_at_iso)}"
