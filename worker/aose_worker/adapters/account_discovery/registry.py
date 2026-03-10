"""
Adapter registry/selector for Epic E account discovery.

CONTRACT: exactly one configured real adapter slot must exist (PH-EPIC-E-001).
The dummy_predictable adapter is always available for tests and local
deterministic verification.

Adapter selection order:
1. Explicit name passed by the caller (from payload.data.adapter_plan)
2. ACCOUNT_DISCOVERY_ADAPTER environment variable
3. Default: "dummy_predictable"
"""

from __future__ import annotations

import os

from .base import AccountDiscoveryAdapter
from .dummy_predictable import DummyPredictableAdapter

# ---------------------------------------------------------------------------
# Registered adapters
# ---------------------------------------------------------------------------

# dummy_predictable is the required test adapter (CONTRACT.yaml
# implementations_locked.required_test_adapter).
#
# PH-EPIC-E-001 (OPEN): real adapter selection is deferred.
# The slot below must be populated once the provider is chosen.
# Do NOT invent a provider name; bind only after human decision.
_ADAPTER_REGISTRY: dict[str, AccountDiscoveryAdapter] = {
    "dummy_predictable": DummyPredictableAdapter(),
    # PH-EPIC-E-001: real adapter slot — bind once provider enum is decided
    # Example: "ajpes": AjpesAdapter(),
}

_DEFAULT_ADAPTER = "dummy_predictable"
_ENV_ADAPTER_KEY = "ACCOUNT_DISCOVERY_ADAPTER"


def get_adapter(name: str | None = None) -> AccountDiscoveryAdapter:
    """
    Resolve and return an AccountDiscoveryAdapter by name.

    Resolution order:
    1. explicit name argument (from payload.data.adapter_plan)
    2. ACCOUNT_DISCOVERY_ADAPTER env var
    3. dummy_predictable (default)

    Raises:
        ValueError: if the resolved name is not registered.
    """
    resolved = name or os.getenv(_ENV_ADAPTER_KEY) or _DEFAULT_ADAPTER

    adapter = _ADAPTER_REGISTRY.get(resolved)
    if adapter is None:
        registered = sorted(_ADAPTER_REGISTRY.keys())
        raise ValueError(
            f"Unknown account discovery adapter: {resolved!r}. "
            f"Registered adapters: {registered}. "
            f"See PH-EPIC-E-001 if you are trying to bind a real provider."
        )
    return adapter


def registered_adapter_names() -> list[str]:
    """Return the list of registered adapter names (for tests and introspection)."""
    return sorted(_ADAPTER_REGISTRY.keys())
