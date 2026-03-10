"""
Abstract PeopleSearchAdapter interface for Epic G.

Contract rules (CONTRACT.yaml forbidden_behavior):
- Adapters must not write directly to canonical DB tables.
- Adapters must not bypass WorkItem idempotency or dedup checks.
- Budget accounting belongs to orchestration/handler flow, not the adapter.
- Adapters must not create provider-specific canonical enums or statuses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import ContactCandidate


class PeopleSearchAdapter(ABC):
    """
    Source-agnostic interface for people search adapters.

    Implementations must return fully normalized ContactCandidate objects.
    Normalization (email, LinkedIn URL, confidence clamping) must be applied
    at the adapter boundary before constructing candidate objects.
    """

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return the stable adapter identifier string."""
        ...

    @abstractmethod
    def search_people(
        self,
        account_id: str,
        role_targets: list[str] | None = None,
    ) -> list[ContactCandidate]:
        """
        Search for people at the given account.

        Args:
            account_id: Canonical account ID to search within.
            role_targets: Optional list of role cluster strings to target.
                          Must be from the locked role_model.allowed_clusters set.

        Returns:
            List of normalized ContactCandidate objects.
            An empty list signals no_signal to the handler.

        Raises:
            ValueError: If the adapter produces malformed or contract-violating output.
        """
        ...
