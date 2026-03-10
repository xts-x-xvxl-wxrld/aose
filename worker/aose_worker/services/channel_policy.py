"""
Channel send-policy helpers for Epic G3 contact enrichment.

Implements CONTRACT.yaml policy_inheritance send-eligibility rules:
  - free_email_domains_send_block: true
  - generic_mailbox_send_block: true
  - Note: contacts with blocked channels are stored; only automatic flow is blocked.

These helpers determine whether a normalized email is eligible for
automatic outreach under the current policy pack (safe_v0_1).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Free-email domain blocklist (send-ineligible for automatic outreach)
# ---------------------------------------------------------------------------
# Per CONTRACT.yaml policy_inheritance.free_email_domains_send_block = true.
# This list covers the most common consumer free-email providers.
# Additions require an explicit policy decision.

FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "ymail.com",
        "hotmail.com",
        "hotmail.co.uk",
        "outlook.com",
        "live.com",
        "live.co.uk",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "mail.com",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "zoho.com",
        "yandex.com",
        "yandex.ru",
        "inbox.com",
    }
)

# ---------------------------------------------------------------------------
# Generic mailbox local-part blocklist (send-ineligible for automatic outreach)
# ---------------------------------------------------------------------------
# Per CONTRACT.yaml policy_inheritance.generic_mailbox_send_block = true.
# Generic mailboxes are role addresses that do not identify a specific person.

GENERIC_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "info",
        "contact",
        "contacts",
        "admin",
        "administrator",
        "support",
        "helpdesk",
        "help",
        "hello",
        "hi",
        "office",
        "team",
        "staff",
        "no-reply",
        "noreply",
        "do-not-reply",
        "donotreply",
        "postmaster",
        "webmaster",
        "mail",
        "email",
        "service",
        "services",
        "billing",
        "accounts",
        "accounting",
        "hr",
        "humanresources",
        "jobs",
        "careers",
        "recruitment",
        "sales",
        "marketing",
        "press",
        "media",
        "pr",
        "legal",
        "privacy",
        "security",
        "abuse",
        "spam",
        "root",
    }
)


# ---------------------------------------------------------------------------
# Policy check functions
# ---------------------------------------------------------------------------


def is_free_email_domain(normalized_email: str) -> bool:
    """
    Return True if the email is from a known consumer free-email domain.

    Args:
        normalized_email: A normalized email string (local@domain format).
    """
    if "@" not in normalized_email:
        return False
    domain = normalized_email.split("@", 1)[1]
    return domain in FREE_EMAIL_DOMAINS


def is_generic_mailbox(normalized_email: str) -> bool:
    """
    Return True if the email local-part is a known generic mailbox identifier.

    Args:
        normalized_email: A normalized email string (local@domain format).
    """
    if "@" not in normalized_email:
        return False
    local = normalized_email.split("@", 1)[0]
    # Strip common sub-addressing patterns (e.g. info+noreply → info)
    base_local = local.split("+")[0]
    return base_local in GENERIC_LOCAL_PARTS


def is_send_blocked(normalized_email: str) -> bool:
    """
    Return True if the email is blocked from automatic outreach by policy.

    Combines free-email domain check and generic mailbox check.
    A blocked contact is stored but not routed to copy_generate automatically.
    """
    return is_free_email_domain(normalized_email) or is_generic_mailbox(
        normalized_email
    )
