"""
Static handler registry for the AOSE worker pipeline.

Keys are canonical stage strings only (CONTRACT.yaml canonical_enums.stages).
No reflection-based discovery, no alias guessing, no fuzzy matching.
Handlers must not call each other directly — handoff is via queue only.
"""

from __future__ import annotations

from typing import Any, Callable

HandlerFn = Callable[[Any], None]


def _stub_handler(work_item: Any) -> None:
    """
    Stub handler — no business logic implemented here.

    Business logic for each stage is deferred to later specs (C2–C5).
    See PH-EPIC-C-001 in docs/epics/epic-c/PLACEHOLDERS.md.
    """


def _get_account_discovery_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.account_discovery import (  # noqa: PLC0415
        handle_account_discovery,
    )

    return handle_account_discovery


def _get_intent_fit_scoring_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.intent_fit_scoring import (  # noqa: PLC0415
        handle_intent_fit_scoring,
    )

    return handle_intent_fit_scoring


def _get_people_search_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.people_search import (  # noqa: PLC0415
        handle_people_search,
    )

    return handle_people_search


def _get_contact_enrichment_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.contact_enrichment import (  # noqa: PLC0415
        handle_contact_enrichment,
    )

    return handle_contact_enrichment


def _get_copy_generate_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.copy_generate import (  # noqa: PLC0415
        handle_copy_generate,
    )

    return handle_copy_generate


def _get_approval_request_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.approval_request import (  # noqa: PLC0415
        handle_approval_request,
    )

    return handle_approval_request


def _get_sending_dispatch_handler() -> HandlerFn:
    """Lazy import to avoid circular imports at module load time."""
    from aose_worker.handlers.sending_dispatch import (  # noqa: PLC0415
        handle_sending_dispatch,
    )

    return handle_sending_dispatch


# Explicit static registry.
# Keys must exactly match canonical stage strings from CONTRACT.yaml.
# Handlers may not call downstream handlers directly.
HANDLER_REGISTRY: dict[str, HandlerFn] = {
    "seller_profile_build": _stub_handler,
    "query_objects_generate": _stub_handler,
    # Epic E: real handler (SPEC-E2)
    "account_discovery": _get_account_discovery_handler(),
    # Epic F: deterministic scorecard upsert handler (SPEC-F1)
    "intent_fit_scoring": _get_intent_fit_scoring_handler(),
    # Epic G: people search handler (SPEC-G1)
    "people_search": _get_people_search_handler(),
    # Epic G: contact enrichment handler (SPEC-G3)
    "contact_enrichment": _get_contact_enrichment_handler(),
    # Epic H: copy generate handler (SPEC-H1 evidence digest builder)
    "copy_generate": _get_copy_generate_handler(),
    # Epic H: approval request handler (SPEC-H3 approval workflow)
    "approval_request": _get_approval_request_handler(),
    # Epic I: sending dispatch handler (SPEC-I1 fail-closed skeleton)
    "sending_dispatch": _get_sending_dispatch_handler(),
}
