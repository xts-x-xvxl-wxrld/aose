"""
Email validation utilities for Epic G3 contact enrichment.

Implements the Epic G3 enrichment rules:
  - Normalize email using Epic B rules
  - Syntax check (implicit in normalization)
  - Domain check via DNS resolution
  - Maximum automated level: domain_ok
  - Never automate provider_verified or human_verified
  - Never perform mailbox probing

CONTRACT.yaml epic_g_enrichment_scope.email:
  allowed_automated_ceiling: domain_ok
  forbidden: mailbox probing, provider_verified automation
"""

from __future__ import annotations

import socket

# ---------------------------------------------------------------------------
# Validation level ordering (lower index = lower trust)
# ---------------------------------------------------------------------------

VALIDATION_LEVELS = (
    "unverified",
    "syntax_ok",
    "domain_ok",
    "provider_verified",
    "human_verified",
)

_LEVEL_ORDER: dict[str, int] = {level: i for i, level in enumerate(VALIDATION_LEVELS)}


def validation_level_gte(a: str, b: str) -> bool:
    """Return True if level a is >= level b (a is at least as validated as b)."""
    return _LEVEL_ORDER.get(a, 0) >= _LEVEL_ORDER.get(b, 0)


def higher_validation_level(a: str, b: str) -> str:
    """Return whichever validation level is higher (more validated)."""
    if _LEVEL_ORDER.get(a, 0) >= _LEVEL_ORDER.get(b, 0):
        return a
    return b


# ---------------------------------------------------------------------------
# Transient DNS error (signals retry-eligible failure)
# ---------------------------------------------------------------------------


class TransientDnsError(Exception):
    """
    Raised when a DNS lookup fails transiently (timeout).

    Handlers should not catch this — let it propagate so RQ retries
    the work item while the attempt budget remains.
    """


# ---------------------------------------------------------------------------
# Syntax check
# ---------------------------------------------------------------------------


def check_email_syntax(email: str) -> bool:
    """
    Return True if the email string passes basic syntax validation.

    Rules: must have exactly one '@', non-empty local part, non-empty domain
    with at least one '.'. Does NOT check DNS or mailbox existence.
    """
    if not email:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain:
        return False
    # Domain must have at least one dot
    if "." not in domain:
        return False
    return True


# ---------------------------------------------------------------------------
# Domain DNS resolution check
# ---------------------------------------------------------------------------

_DNS_TIMEOUT_SECONDS = 5.0


def check_domain_resolves(domain: str, timeout: float = _DNS_TIMEOUT_SECONDS) -> bool:
    """
    Return True if the domain resolves via DNS; False if it does not exist.

    Uses socket.getaddrinfo as a DNS resolution probe. Sets a temporary
    socket timeout to bound the call duration.

    Raises:
        TransientDnsError: if the lookup times out (socket.timeout).
                           This signals a transient failure eligible for retry.
    Returns:
        True  — domain resolves (domain_ok is achievable).
        False — domain does not exist / not resolvable (stays at syntax_ok).
    """
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        socket.getaddrinfo(domain, None)
        return True
    except socket.timeout:
        raise TransientDnsError(f"DNS lookup timed out for {domain!r}")
    except socket.gaierror:
        # Permanent resolution failure (NXDOMAIN, SERVFAIL treated as permanent)
        return False
    finally:
        socket.setdefaulttimeout(old_timeout)


# ---------------------------------------------------------------------------
# Full validation pipeline
# ---------------------------------------------------------------------------


def validate_email(
    email: str,
    *,
    dns_check: bool = True,
    dns_timeout: float = _DNS_TIMEOUT_SECONDS,
) -> str:
    """
    Run the full email validation chain and return the resulting validation level.

    Steps:
      1. Check syntax → 'syntax_ok' if passes, 'unverified' if fails
      2. DNS domain resolution → 'domain_ok' if resolves (when dns_check=True)

    Maximum automated level is 'domain_ok' per CONTRACT.yaml.

    Args:
        email:       Normalized email string (already passed through normalize_email).
        dns_check:   Set to False to skip DNS check (for unit tests or dry runs).
        dns_timeout: DNS lookup timeout in seconds.

    Returns:
        Validation level string: 'unverified', 'syntax_ok', or 'domain_ok'.

    Raises:
        TransientDnsError: if DNS lookup times out (propagate for retry).
    """
    if not check_email_syntax(email):
        return "unverified"

    if not dns_check:
        return "syntax_ok"

    domain = email.split("@")[1]
    resolves = check_domain_resolves(domain, timeout=dns_timeout)
    return "domain_ok" if resolves else "syntax_ok"
