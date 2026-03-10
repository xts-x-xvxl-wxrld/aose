"""
Abstract AccountDiscoveryAdapter interface for Epic E.

Contract rules (CONTRACT.yaml forbidden_behavior):
- Adapters must not write directly to canonical DB tables.
- Adapters must not bypass WorkItem idempotency or dedup checks.
- Adapters must not emit prose-only evidence without structured pointer fields.
- Budget accounting belongs to orchestration/handler flow, not the adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import AccountDiscoveryResult


class AccountDiscoveryAdapter(ABC):
    """
    Source-agnostic interface for account discovery adapters.

    Implementations must return a fully normalized AccountDiscoveryResult.
    Normalization (domain, country, confidence clamping) must be applied
    at the adapter boundary before constructing candidate objects.
    """

    @abstractmethod
    def search_accounts(
        self,
        query_object: Any,
        limits: dict[str, Any],
        context: dict[str, Any],
    ) -> AccountDiscoveryResult:
        """
        Search for accounts matching the given query object.

        Args:
            query_object: QueryObject ORM instance or compatible dict with at
                          least query_object_id, seller_id, buyer_context,
                          keywords, exclusions.
            limits: Run control caps (e.g. max_accounts, max_external_calls).
            context: Caller context (policy_pack_id, run_id, trace fields).

        Returns:
            AccountDiscoveryResult with normalized candidates.
            An empty candidates list signals no_signal to the handler.

        Raises:
            ValueError: If the adapter produces malformed or contract-violating
                        output.
        """
        ...
